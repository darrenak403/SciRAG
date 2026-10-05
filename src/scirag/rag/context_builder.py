"""Turns the chosen passages into the text the model reads, each under a marker."""

import re
import uuid
from collections.abc import Sequence

from scirag.db.models import Chunk
from scirag.rag.types import Source

SNIPPET_CHARS = 300


def _attribute(value: str) -> str:
    return re.sub(r"\s+", " ", value).replace('"', "'").replace("<", "(").replace(">", ")")


def _snippet(text: str) -> str:
    flat = re.sub(r"\s+", " ", text).strip()
    return flat if len(flat) <= SNIPPET_CHARS else flat[: SNIPPET_CHARS - 1].rstrip() + "…"


def _source(chunk: Chunk, marker: str, title: str) -> Source:
    return Source(
        marker=marker,
        chunk_id=chunk.id,
        paper_id=chunk.paper_id,
        paper_title=title,
        page=chunk.page_start,
        section_path=list(chunk.section_path),
        snippet=_snippet(chunk.text),
    )


def _body(text: str) -> str:
    # A passage must not be able to close its own tag and pose as instructions.
    return re.sub(r"<(\s*/?\s*(?:source|paper))", r"&lt;\1", text, flags=re.IGNORECASE)


def _section(chunk: Chunk) -> str:
    return " > ".join(_attribute(part) for part in chunk.section_path)


def build_context(
    chunks: Sequence[Chunk],
    titles: dict,
    *,
    max_tokens: int,
    bodies: dict[uuid.UUID, str] | None = None,
) -> tuple[str, list[Source]]:
    """The passages in order, as <source> blocks, until the token budget is used up.

    titles maps a paper id to its title. The first passage is always included.
    bodies, when given, maps a chunk id to the text shown in place of the passage:
    a summary of it. The source still names the passage itself.
    """
    blocks: list[str] = []
    sources: list[Source] = []
    spent = 0
    for chunk in chunks:
        body = bodies[chunk.id] if bodies else chunk.text
        cost = len(body) // 4 if bodies else chunk.token_count
        if sources and spent + cost > max_tokens:
            break
        spent += cost
        marker = f"S{len(sources) + 1}"
        title = titles[chunk.paper_id]
        blocks.append(
            f'<source id="{marker}" paper="{_attribute(title)}" '
            f'section="{_section(chunk)}" page="{chunk.page_start}">\n'
            f"{_body(body)}\n</source>"
        )
        sources.append(_source(chunk, marker, title))
    return "\n\n".join(blocks), sources


def build_paper_context(
    groups: Sequence[tuple[uuid.UUID, Sequence[Chunk]]], titles: dict, *, max_tokens: int
) -> tuple[str, list[Source], dict[str, uuid.UUID]]:
    """Each paper as a <paper> block holding its passages, for comparing papers.

    groups lists the papers in the order they are shown, each with its passages,
    best first; a paper with none still gets a block, so the model sees it was
    looked at. Returns the text, the sources, and which paper each paper id
    ("P1", ...) stands for.

    When the budget runs out, every paper keeps its best passage before any
    paper gets a second one.
    """
    kept: set[uuid.UUID] = set()
    spent = 0
    depth = max((len(chunks) for _, chunks in groups), default=0)
    for rank in range(depth):
        for _, chunks in groups:
            if rank < len(chunks) and (rank == 0 or spent + chunks[rank].token_count <= max_tokens):
                kept.add(chunks[rank].id)
                spent += chunks[rank].token_count

    blocks: list[str] = []
    sources: list[Source] = []
    papers: dict[str, uuid.UUID] = {}
    for paper_id, chunks in groups:
        key = f"P{len(papers) + 1}"
        papers[key] = paper_id
        title = titles[paper_id]
        inner: list[str] = []
        for chunk in chunks:
            if chunk.id not in kept:
                continue
            marker = f"S{len(sources) + 1}"
            inner.append(
                f'<source id="{marker}" section="{_section(chunk)}" page="{chunk.page_start}">\n'
                f"{_body(chunk.text)}\n</source>"
            )
            sources.append(_source(chunk, marker, title))
        passages = "\n".join(inner) if inner else "(no passage about the question was found)"
        blocks.append(f'<paper id="{key}" title="{_attribute(title)}">\n{passages}\n</paper>')
    return "\n\n".join(blocks), sources, papers
