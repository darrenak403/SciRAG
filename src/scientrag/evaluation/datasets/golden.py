"""The project's own question set, on real PDFs that go through the real parser.

eval/golden/papers.jsonl names the papers: {"key", "title", "url"}.
eval/golden/factual.jsonl holds the questions:
{"id", "question", "paper_ids": [keys], "evidence_chunk_text": [quotes copied
from the paper], "reference_answer", "type"}. A question the papers cannot
answer has no evidence and a null reference answer.

PDFs are downloaded and parsed once; both are kept in the cache directory.
"""

import json
from pathlib import Path
from typing import Any

import httpx

from scientrag.config import get_settings
from scientrag.evaluation.datasets.base import EvalDataset, EvalPaper, EvalQuestion
from scientrag.parsing.document import ScientificDocument

GOLDEN_DIR = Path("eval/golden")


def _rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _document(cache: Path, key: str, url: str) -> ScientificDocument:
    parsed = cache / "parsed" / f"{key}.json"
    if parsed.exists():
        return ScientificDocument.model_validate_json(parsed.read_text())
    # Imported here: only the worker image has the parser.
    from scientrag.parsing.docling_parser import parse_pdf

    pdf = cache / "pdf" / f"{key}.pdf"
    if not pdf.exists():
        pdf.parent.mkdir(parents=True, exist_ok=True)
        pdf.write_bytes(
            httpx.get(url, timeout=120, follow_redirects=True).raise_for_status().content
        )
    document = parse_pdf(pdf, get_settings().max_paper_pages)
    parsed.parent.mkdir(parents=True, exist_ok=True)
    parsed.write_text(document.model_dump_json())
    return document


def load(cache: Path, directory: Path = GOLDEN_DIR) -> EvalDataset:
    papers = {
        row["key"]: EvalPaper(row["key"], row["title"], _document(cache, row["key"], row["url"]))
        for row in _rows(directory / "papers.jsonl")
    }
    questions = [
        EvalQuestion(
            id=row["id"],
            text=row["question"],
            paper_keys=row["paper_ids"],
            evidence=row["evidence_chunk_text"],
            reference=row["reference_answer"],
            answerable=bool(row["evidence_chunk_text"]),
            kind=row.get("type", "factual"),
        )
        for row in _rows(directory / "factual.jsonl")
    ]
    unknown = {key for question in questions for key in question.paper_keys} - set(papers)
    if unknown:
        raise ValueError(f"questions name papers that are not in papers.jsonl: {sorted(unknown)}")
    return EvalDataset(name="golden", papers=papers, questions=questions)
