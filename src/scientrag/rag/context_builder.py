"""Turns the chosen passages into the text the model reads, each under a marker."""

import re
from collections.abc import Sequence

from scientrag.db.models import Chunk
from scientrag.rag.types import Source

SNIPPET_CHARS = 300


def _attribute(value: str) -> str:
    return re.sub(r"\s+", " ", value).replace('"', "'").replace("<", "(").replace(">", ")")


def _snippet(text: str) -> str:
    flat = re.sub(r"\s+", " ", text).strip()
    return flat if len(flat) <= SNIPPET_CHARS else flat[: SNIPPET_CHARS - 1].rstrip() + "…"


def build_context(
    chunks: Sequence[Chunk], titles: dict, *, max_tokens: int
) -> tuple[str, list[Source]]:
    """The passages in order, as <source> blocks, until the token budget is used up.

    titles maps a paper id to its title. The first passage is always included.
    """
    blocks: list[str] = []
    sources: list[Source] = []
    spent = 0
    for chunk in chunks:
        if sources and spent + chunk.token_count > max_tokens:
            break
        spent += chunk.token_count
        marker = f"S{len(sources) + 1}"
        title = titles[chunk.paper_id]
        section = " > ".join(_attribute(part) for part in chunk.section_path)
        # A passage must not be able to close its own tag and pose as instructions.
        body = re.sub(r"<(\s*/?\s*source)", r"&lt;\1", chunk.text, flags=re.IGNORECASE)
        blocks.append(
            f'<source id="{marker}" paper="{_attribute(title)}" '
            f'section="{section}" page="{chunk.page_start}">\n'
            f"{body}\n</source>"
        )
        sources.append(
            Source(
                marker=marker,
                chunk_id=chunk.id,
                paper_id=chunk.paper_id,
                paper_title=title,
                page=chunk.page_start,
                section_path=list(chunk.section_path),
                snippet=_snippet(chunk.text),
            )
        )
    return "\n\n".join(blocks), sources
