"""QASPER: questions on NLP papers, with the paragraphs that answer them marked.

The dataset ships the papers as text already split into sections and paragraphs,
not as PDFs. So it measures chunking, retrieval and answering, never the parser.
"""

import io
import json
import random
import tarfile
from pathlib import Path
from typing import Any

import httpx

from scientrag.evaluation.datasets.base import EvalDataset, EvalPaper, EvalQuestion
from scientrag.parsing.document import Block, ScientificDocument, Section

URL = "https://qasper-dataset.s3.us-west-2.amazonaws.com/qasper-train-dev-v0.3.tgz"
SPLIT_FILE = "qasper-dev-v0.3.json"
# Evidence that is a figure or a table, of which the dataset holds only the caption.
FLOAT_PREFIX = "FLOAT SELECTED"
WHOLE_PAGE = (0.0, 0.0, 1.0, 1.0)


def _download(cache: Path) -> dict[str, Any]:
    path = cache / SPLIT_FILE
    if not path.exists():
        cache.mkdir(parents=True, exist_ok=True)
        archive = httpx.get(URL, timeout=120, follow_redirects=True).raise_for_status().content
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            member = next(item for item in tar.getmembers() if item.name.endswith(SPLIT_FILE))
            path.write_bytes(tar.extractfile(member).read())
    return json.loads(path.read_text())


def to_document(paper: dict[str, Any]) -> ScientificDocument:
    """The paper in the form the chunker takes. Section names nest with " ::: "."""
    sections: list[Section] = []
    blocks: list[Block] = []
    index_of: dict[tuple[str, ...], int] = {}

    def section(path: tuple[str, ...]) -> int:
        if path not in index_of:
            parent = section(path[:-1]) if len(path) > 1 else None
            index_of[path] = len(sections)
            sections.append(
                Section(index=len(sections), parent=parent, level=len(path), title=path[-1], page=1)
            )
        return index_of[path]

    def add(text: str, path: tuple[str, ...]) -> None:
        if text.strip():
            blocks.append(
                Block(
                    kind="text", text=text.strip(), page=1, bbox=WHOLE_PAGE, section=section(path)
                )
            )

    add(paper.get("abstract") or "", ("Abstract",))
    for part in paper["full_text"]:
        path = tuple(name.strip() for name in (part["section_name"] or "Body").split(" ::: "))
        for paragraph in part["paragraphs"]:
            add(paragraph, path)
    return ScientificDocument(
        title=paper["title"], page_count=1, sections=sections, blocks=blocks, warnings=[]
    )


def _reference(answer: dict[str, Any]) -> str | None:
    if answer["free_form_answer"]:
        return answer["free_form_answer"]
    if answer["extractive_spans"]:
        return ", ".join(answer["extractive_spans"])
    if answer["yes_no"] is not None:
        return "Yes" if answer["yes_no"] else "No"
    return None


def _question(paper_key: str, item: dict[str, Any]) -> EvalQuestion | None:
    """The question with its first usable annotation, or None when it has none.

    Usable: answerable from text. Questions whose only evidence is a figure or a
    table are left out, because the dataset does not hold their content.
    """
    for annotation in item["answers"]:
        answer = annotation["answer"]
        evidence = [text for text in answer["evidence"] if not text.startswith(FLOAT_PREFIX)]
        reference = _reference(answer)
        if not answer["unanswerable"] and evidence and reference:
            return EvalQuestion(
                item["question_id"], item["question"], [paper_key], evidence, reference
            )
    return None


def load(cache: Path, *, papers: int, seed: int) -> EvalDataset:
    """A fixed sample of the development split: the same papers for the same seed."""
    raw = _download(cache)
    usable: dict[str, list[EvalQuestion]] = {}
    for key in sorted(raw):
        questions = [q for item in raw[key]["qas"] if (q := _question(key, item))]
        if questions:
            usable[key] = questions
    chosen = sorted(random.Random(seed).sample(sorted(usable), min(papers, len(usable))))
    return EvalDataset(
        name="qasper",
        papers={key: EvalPaper(key, raw[key]["title"], to_document(raw[key])) for key in chosen},
        questions=[question for key in chosen for question in usable[key]],
    )
