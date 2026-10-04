"""CPU validation spike: PDF -> parse -> chunk -> embed -> Qdrant -> hybrid search -> rerank.

Embedding and reranking go through the Gemini API (see gemini_client.py).

Throwaway code. Prints timings per stage and writes everything to out/results.json.
Stages that need an API key are skipped and reported as "not measured" when no key is set.
"""

import json
import os
import platform
import statistics
import time
from pathlib import Path

import httpx
from docling.chunking import HybridChunker
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from qdrant_client import QdrantClient, models

import gemini_client

SAMPLES = Path("samples")
OUT = Path("out")
BM25_MODEL = "Qdrant/bm25"

# Public arXiv papers, one per layout the parser has to survive.
SAMPLE_PAPERS = {
    "resnet-two-column-tables": "https://arxiv.org/pdf/1512.03385v1",
    "bert-two-column": "https://arxiv.org/pdf/1810.04805v2",
    "adam-formulas": "https://arxiv.org/pdf/1412.6980v9",
}

QUESTIONS = [
    "What top-5 error does the ResNet ensemble achieve on the ImageNet test set?",
    "How does Adam compute the bias-corrected first moment estimate?",
    "Which values of β1 and β2 are recommended as defaults for Adam?",
    "BERT-Large có bao nhiêu tham số?",
    "What percentage of tokens is masked in BERT's masked LM pre-training?",
]


def cgroup_peak_mb() -> float:
    """Peak memory of this container since it started."""
    return int(Path("/sys/fs/cgroup/memory.peak").read_text()) / 2**20


def machine_info() -> dict:
    mem_kb = int(Path("/proc/meminfo").read_text().split()[1])
    return {
        "arch": platform.machine(),
        "python": platform.python_version(),
        "cpus_visible_to_container": os.cpu_count(),
        "ram_visible_to_container_gb": round(mem_kb / 2**20, 1),
    }


def fetch_samples() -> list[Path]:
    SAMPLES.mkdir(exist_ok=True)
    paths = []
    for name, url in SAMPLE_PAPERS.items():
        path = SAMPLES / f"{name}.pdf"
        if not path.exists():
            print(f"downloading {url}")
            response = httpx.get(url, follow_redirects=True, timeout=120)
            response.raise_for_status()
            path.write_bytes(response.content)
        paths.append(path)
    return paths


def normalized_bbox(doc, prov) -> list[float]:
    """Bounding box as fractions of the page, origin top-left: [left, top, right, bottom]."""
    size = doc.pages[prov.page_no].size
    box = prov.bbox.to_top_left_origin(page_height=size.height)
    return [
        round(box.l / size.width, 3),
        round(box.t / size.height, 3),
        round(box.r / size.width, 3),
        round(box.b / size.height, 3),
    ]


def parse(paths: list[Path]) -> tuple[dict, list]:
    options = PdfPipelineOptions(do_ocr=False, do_table_structure=True)
    converter = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
    )
    started = time.perf_counter()
    converter.initialize_pipeline(InputFormat.PDF)
    load_seconds = time.perf_counter() - started

    papers, docs = [], []
    for path in paths:
        started = time.perf_counter()
        doc = converter.convert(path).document
        seconds = time.perf_counter() - started
        pages = len(doc.pages)

        (OUT / f"{path.stem}.json").write_text(json.dumps(doc.export_to_dict()))

        # Reading order of the first two pages, for checking two-column layout by eye.
        items = [item for item, _ in doc.iterate_items()]
        with_bbox = [item for item in items if getattr(item, "prov", None)]
        lines = []
        for item in with_bbox:
            prov = item.prov[0]
            if prov.page_no > 2:
                continue
            text = getattr(item, "text", "") or ""
            lines.append(f"p{prov.page_no} {normalized_bbox(doc, prov)} {item.label}: {text[:70]}")
        (OUT / f"{path.stem}-reading-order.txt").write_text("\n".join(lines))

        papers.append(
            {
                "paper": path.stem,
                "pages": pages,
                "seconds": round(seconds, 1),
                "seconds_per_page": round(seconds / pages, 2),
                "items": len(items),
                "items_with_page_and_bbox": len(with_bbox),
                "tables": len(doc.tables),
                "formulas": sum(1 for item in items if str(item.label) == "formula"),
            }
        )
        docs.append((path.stem, doc))
        print(f"  parsed {path.stem}: {pages} pages in {seconds:.1f}s")

    return (
        {
            "model_load_seconds": round(load_seconds, 1),
            "papers": papers,
            "peak_ram_mb": round(cgroup_peak_mb()),
        },
        docs,
    )


def chunk(docs: list) -> tuple[dict, list[dict]]:
    chunker = HybridChunker()
    chunks, per_paper = [], []
    for name, doc in docs:
        started = time.perf_counter()
        paper_chunks = list(chunker.chunk(dl_doc=doc))
        seconds = time.perf_counter() - started
        tokens = []
        for piece in paper_chunks:
            text = chunker.contextualize(chunk=piece)
            page = piece.meta.doc_items[0].prov[0].page_no if piece.meta.doc_items[0].prov else None
            tokens.append(chunker.tokenizer.count_tokens(text))
            chunks.append({"paper": name, "page": page, "text": text})
        ordered = sorted(tokens)
        per_paper.append(
            {
                "paper": name,
                "chunks": len(paper_chunks),
                "seconds": round(seconds, 2),
                "tokens_min": ordered[0],
                "tokens_median": int(statistics.median(ordered)),
                "tokens_p95": ordered[int(len(ordered) * 0.95) - 1],
                "tokens_max": ordered[-1],
            }
        )
    return {"tokenizer": str(chunker.tokenizer.get_tokenizer().name_or_path), "papers": per_paper}, chunks


def bm25(text: str) -> models.Document:
    """Text that the Qdrant server turns into a BM25 sparse vector itself."""
    return models.Document(text=text, model=BM25_MODEL)


def index_and_query(client: QdrantClient, name: str, chunks: list[dict], dense, embed_query) -> dict:
    """Builds one collection and runs every question against it.

    dense is the list of chunk vectors, or None to test the BM25 branch on its own.
    """
    if client.collection_exists(name):
        client.delete_collection(name)
    client.create_collection(
        name,
        vectors_config=(
            {"dense": models.VectorParams(size=len(dense[0]), distance=models.Distance.COSINE)}
            if dense
            else {}
        ),
        sparse_vectors_config={"bm25": models.SparseVectorParams(modifier=models.Modifier.IDF)},
    )

    points = []
    for position, item in enumerate(chunks):
        vector = {"bm25": bm25(item["text"])}
        if dense:
            vector["dense"] = dense[position]
        points.append(models.PointStruct(id=position, vector=vector, payload=item))
    started = time.perf_counter()
    for start in range(0, len(points), 64):
        client.upsert(name, points=points[start : start + 64], wait=True)
    upsert_seconds = time.perf_counter() - started

    queries = []
    for question in QUESTIONS:
        embed_seconds = None
        if dense:
            started = time.perf_counter()
            question_vector = embed_query(question)
            embed_seconds = round(time.perf_counter() - started, 3)
            started = time.perf_counter()
            hits = client.query_points(
                name,
                prefetch=[
                    models.Prefetch(query=question_vector, using="dense", limit=50),
                    models.Prefetch(query=bm25(question), using="bm25", limit=50),
                ],
                query=models.FusionQuery(fusion=models.Fusion.RRF),
                limit=30,
            ).points
        else:
            started = time.perf_counter()
            hits = client.query_points(name, query=bm25(question), using="bm25", limit=30).points
        search_seconds = time.perf_counter() - started
        queries.append(
            {
                "question": question,
                "embed_question_seconds": embed_seconds,
                "search_seconds": round(search_seconds, 3),
                "candidates": [hit.id for hit in hits],
                "top3": [
                    f"{hit.payload['paper']} p{hit.payload['page']}: {hit.payload['text'][:90]!r}"
                    for hit in hits[:3]
                ],
            }
        )
    return {"points": len(points), "upsert_seconds": round(upsert_seconds, 2), "queries": queries}


def measure_gemini(client: QdrantClient, chunks: list[dict]) -> dict:
    texts = [item["text"] for item in chunks]
    result = {
        "embed_model": gemini_client.EMBED_MODEL,
        "rerank_model": gemini_client.RERANK_MODEL,
        "dimensions_requested": gemini_client.DIMENSIONS,
    }

    # Embedding time is reported for one paper (the first); the rest is embedded untimed.
    first_paper = [text for text, item in zip(texts, chunks) if item["paper"] == chunks[0]["paper"]]
    started = time.perf_counter()
    dense = gemini_client.embed(first_paper, "document")
    result["embed_one_paper"] = {
        "chunks": len(first_paper),
        "seconds": round(time.perf_counter() - started, 2),
    }
    dense += gemini_client.embed(texts[len(first_paper) :], "document")
    result["dimensions"] = len(dense[0])

    result["hybrid"] = index_and_query(
        client,
        "spike_gemini",
        chunks,
        dense,
        lambda question: gemini_client.embed([question], "query")[0],
    )

    # No rerank API on Gemini: the LLM picks the best passages out of the RRF candidates.
    rerank = []
    for query in result["hybrid"]["queries"]:
        row = {"question": query["question"]}
        for size in (30, 15):
            documents = [texts[i] for i in query["candidates"][:size]]
            started = time.perf_counter()
            order = gemini_client.rerank(query["question"], documents, top_n=8)
            row[f"llm_rerank_{size}_seconds"] = round(time.perf_counter() - started, 3)
            if size == 30 and order:
                best = chunks[query["candidates"][order[0]]]
                row["top1_after_llm_rerank"] = f"{best['paper']} p{best['page']}: {best['text'][:90]!r}"
        rerank.append(row)
    result["llm_rerank"] = rerank
    for size in (30, 15):
        result[f"llm_rerank_{size}_median_seconds"] = statistics.median(
            row[f"llm_rerank_{size}_seconds"] for row in rerank
        )
    result["retries"] = gemini_client.retry_count
    return result


def main() -> None:
    OUT.mkdir(exist_ok=True)
    results = {"machine": machine_info()}
    print("machine:", results["machine"])

    print("[parse]")
    results["parse"], docs = parse(fetch_samples())
    print("[chunk]")
    results["chunk"], chunks = chunk(docs)

    client = QdrantClient(url=os.environ["QDRANT_URL"], timeout=60)
    print("[bm25 only]")
    try:
        results["bm25_server_side"] = {"works": True, **index_and_query(client, "spike_bm25", chunks, None, None)}
    except Exception as error:  # the outcome itself is what the spike records
        results["bm25_server_side"] = {"works": False, "error": f"{type(error).__name__}: {error}"[:500]}

    if gemini_client.api_key():
        print("[gemini]")
        try:
            results["gemini"] = measure_gemini(client, chunks)
        except Exception as error:
            results["gemini"] = {"error": f"{type(error).__name__}: {error}"[:500]}
    else:
        print("[gemini] GEMINI_API_KEY not set: embedding, hybrid search and rerank not measured")
        results["gemini"] = "not measured"

    results["peak_ram_mb_whole_run"] = round(cgroup_peak_mb())
    (OUT / "results.json").write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
