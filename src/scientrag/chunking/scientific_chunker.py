"""Splits a parsed paper into the passages that are embedded, searched and cited."""

from dataclasses import dataclass, field

from scientrag.parsing.document import Block, BlockKind, ScientificDocument

# Bump when the rules below change, so chunks made by different rules can be told apart.
CHUNKING_VERSION = 1


@dataclass
class ChunkDraft:
    index: int
    kind: BlockKind
    text: str
    embed_text: str
    section_path: list[str]
    page_start: int
    page_end: int
    bboxes: list[dict]
    token_count: int


@dataclass
class _Pending:
    """Paragraphs of one section collected until they fill a chunk."""

    section: int | None
    blocks: list[Block] = field(default_factory=list)
    tokens: int = 0


def count_tokens(text: str) -> int:
    """About four characters per token. Close enough to size chunks; no tokenizer needed."""
    return max(1, len(text) // 4)


def _split(block: Block, max_tokens: int) -> list[Block]:
    """Cuts a block that alone exceeds the limit, at sentence ends where there are any."""
    if count_tokens(block.text) <= max_tokens:
        return [block]
    limit = max_tokens * 4
    pieces: list[str] = []
    rest = block.text
    while len(rest) > limit:
        cut = max(rest.rfind(". ", 0, limit), rest.rfind("\n", 0, limit))
        cut = cut + 1 if cut > limit // 2 else limit
        pieces.append(rest[:cut].strip())
        rest = rest[cut:].strip()
    if rest:
        pieces.append(rest)
    return [block.model_copy(update={"text": piece}) for piece in pieces]


def chunk_document(
    document: ScientificDocument, *, title: str, max_tokens: int
) -> list[ChunkDraft]:
    """Chunks in reading order.

    Paragraphs are merged up to max_tokens but never across a heading. Tables,
    captions and formulas are chunks of their own, so they are not diluted by the
    prose around them. The reference list is kept apart from the body.
    """
    drafts: list[ChunkDraft] = []

    def emit(kind: BlockKind, blocks: list[Block], section: int | None) -> None:
        text = "\n\n".join(block.text for block in blocks)
        path = document.section_path(section)
        drafts.append(
            ChunkDraft(
                index=len(drafts),
                kind=kind,
                text=text,
                embed_text="\n".join([title, " > ".join(path), text])
                if path
                else f"{title}\n{text}",
                section_path=path,
                page_start=min(block.page for block in blocks),
                page_end=max(block.page for block in blocks),
                bboxes=[{"page": block.page, "bbox": list(block.bbox)} for block in blocks],
                token_count=count_tokens(text),
            )
        )

    pending = _Pending(section=None)

    def flush() -> None:
        if pending.blocks:
            emit(pending.blocks[0].kind, pending.blocks, pending.section)
        pending.blocks, pending.tokens = [], 0

    for block in document.blocks:
        for piece in _split(block, max_tokens):
            if piece.kind not in ("text", "reference"):
                flush()
                emit(piece.kind, [piece], piece.section)
                continue
            tokens = count_tokens(piece.text)
            same_run = (
                pending.blocks
                and pending.section == piece.section
                and pending.blocks[0].kind == piece.kind
            )
            if not same_run or pending.tokens + tokens > max_tokens:
                flush()
                pending.section = piece.section
            pending.blocks.append(piece)
            pending.tokens += tokens
    flush()
    return drafts
