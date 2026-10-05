"""A question that sets papers side by side: every paper brings its own passages,
and the answer is a table with a row for each."""

import json
import re
import uuid
from collections.abc import AsyncIterator
from typing import Any

from scirag.rag import citation
from scirag.rag.context_builder import build_paper_context
from scirag.rag.paths.base import (
    NO_EVIDENCE,
    Ask,
    Written,
    checked,
    most_relevant_papers,
    passages_per_paper,
    span,
    tokens,
    write,
)
from scirag.rag.prompts import COMPARE_SYSTEM, COMPARE_TEXT_SYSTEM
from scirag.rag.types import Delta, Source, Sources, Status, Table

MAX_COLUMNS = 6
COLUMN_CHARS = 80
NOT_STATED = "Not stated in the passages found"
NOT_FOUND = "No passage about this was found in this paper"
# The table is asked for twice before the answer is written as text instead.
ATTEMPTS = 2


def parse_table(
    reply: str, papers: dict[str, uuid.UUID], sources: list[Source], titles: dict[uuid.UUID, str]
) -> tuple[dict[str, Any], str, list[str]]:
    """The table, the summary and the markers they use, from the model's reply.

    papers maps the ids the model was given ("P1", ...) to papers. Every one of
    them gets exactly one row, in that order: a row the model left out is filled
    in as not found, a row for an unknown or repeated paper is dropped. A marker
    in a cell is kept only if it names a passage of that row's paper.

    Raises ValueError when the reply holds no usable table.
    """
    try:
        parsed = json.loads(reply)
    except ValueError:
        # Some models wrap the JSON in prose or a code fence.
        found = re.search(r"\{.*\}", reply, re.DOTALL)
        if not found:
            raise
        parsed = json.loads(found.group())
    if not isinstance(parsed, dict):
        raise ValueError("the reply is not an object")
    if not isinstance(parsed.get("columns"), list) or not isinstance(parsed.get("rows"), list):
        raise ValueError("the reply holds no list of columns and rows")
    columns = [
        " ".join(column.split())[:COLUMN_CHARS]
        for column in parsed.get("columns") or []
        if isinstance(column, str) and column.strip()
    ][:MAX_COLUMNS]
    if not columns:
        raise ValueError("the reply names no columns")

    of_paper: dict[uuid.UUID, set[str]] = {paper_id: set() for paper_id in papers.values()}
    for source in sources:
        of_paper[source.paper_id].add(source.marker)

    used: list[str] = []
    written: dict[uuid.UUID, list[dict[str, Any]]] = {}
    for row in parsed.get("rows") or []:
        named = row.get("paper") if isinstance(row, dict) else None
        paper_id = papers.get(named) if isinstance(named, str) else None
        if paper_id is None or paper_id in written:
            continue
        given = row.get("cells") if isinstance(row.get("cells"), list) else []
        cells = []
        for index in range(len(columns)):
            raw = given[index] if index < len(given) and isinstance(given[index], str) else ""
            text, markers = citation.validate(raw.replace("\x00", ""), of_paper[paper_id])
            text = " ".join(citation.without_markers(text).split())
            cells.append({"text": text or NOT_STATED, "markers": markers if text else []})
            used += [marker for marker in cells[-1]["markers"] if marker not in used]
        written[paper_id] = cells
    if not written:
        raise ValueError("the reply holds no row for a paper that was compared")

    empty = [{"text": NOT_FOUND, "markers": []} for _ in columns]
    table = {
        "columns": columns,
        "rows": [
            {
                "paper_id": str(paper_id),
                "paper_title": titles[paper_id],
                "cells": written.get(paper_id, empty),
            }
            for paper_id in papers.values()
        ],
    }
    summary = parsed.get("summary") if isinstance(parsed.get("summary"), str) else ""
    # The ids papers were given in the prompt mean nothing to the reader: "Adam (P1)".
    summary = re.sub(r"\s*\((?:paper\s+)?P\d+\)", "", summary, flags=re.IGNORECASE)
    summary, cited = citation.validate(
        summary.replace("\x00", ""), {source.marker for source in sources}
    )
    used += [marker for marker in cited if marker not in used]
    return table, summary, used


async def run(ask: Ask) -> AsyncIterator[Sources | Status | Table | Delta | Written]:
    settings, details, provider = ask.settings, ask.details, ask.provider

    yield Status("selecting")
    papers, notice = await most_relevant_papers(ask)
    yield Status("gathering")
    groups = await passages_per_paper(ask, papers)
    if not any(chunks for _, chunks in groups):
        yield Sources([])
        yield Written(NO_EVIDENCE, [], "no_evidence", notice=notice)
        return

    context, sources, keys = build_paper_context(
        groups, ask.titles, max_tokens=settings.multi_paper_context_tokens
    )
    details["context"] = [
        {"marker": source.marker, "chunk_id": str(source.chunk_id)} for source in sources
    ]
    yield Sources(sources, details)
    yield Status("comparing")

    content = f"{context}\n\nQuestion: {ask.query}"
    for attempt in range(ATTEMPTS):
        with span("generate", ask.parent, "LLM", **{"input.value": ask.query}) as opened:
            calls = len(provider.usage)
            reply = await provider.complete(
                [{"role": "user", "content": content}],
                role="answer",
                max_tokens=settings.multi_paper_answer_tokens,
                system=COMPARE_SYSTEM,
                json_output=True,
            )
            tokens(opened, provider, calls)
            opened.set_attribute("output.value", reply)
        try:
            table, summary, used = parse_table(reply, keys, sources, ask.titles)
        except ValueError as error:
            details["table"] = f"failed {attempt + 1} of {ATTEMPTS}: {error}"
            continue
        details["table"] = "model"
        details["first_token_ms"] = ask.elapsed_ms()
        yield Table(table)
        if summary:
            yield Delta(summary)
        by_marker = {source.marker: source for source in sources}
        yield Written(
            summary or f"Comparison of {len(table['rows'])} papers.",
            [by_marker[marker] for marker in used],
            "answered" if used else "no_evidence",
            table=table,
            notice=notice,
        )
        return

    # No usable table: the same comparison as text, paper by paper.
    yield Status("writing")
    pieces: list[str] = []
    async for delta in write(
        ask, content, COMPARE_TEXT_SYSTEM, pieces, max_tokens=settings.multi_paper_answer_tokens
    ):
        yield delta
    yield checked(pieces, sources, notice=notice)
