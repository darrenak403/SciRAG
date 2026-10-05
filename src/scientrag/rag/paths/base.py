"""What the three ways of answering share: the question as prepared, and the steps
each of them takes."""

import uuid
from collections.abc import AsyncIterator, Callable, Iterator, Sequence
from contextlib import aclosing, contextmanager
from dataclasses import dataclass
from typing import Any

from opentelemetry.context import Context
from opentelemetry.trace import Span, Status, StatusCode
from sqlalchemy import select

from scientrag.config import Settings
from scientrag.db.engine import get_sessionmaker
from scientrag.db.models import Chunk, Paper
from scientrag.index import search as index_search
from scientrag.providers.base import Message, ModelProvider, Role
from scientrag.providers.errors import ProviderError
from scientrag.rag import analyzer, citation
from scientrag.rag.types import Delta, Outcome, Source
from scientrag.telemetry.tracing import SPAN_KIND, get_tracer

NO_EVIDENCE = "I could not find anything about this in the selected papers."


@dataclass
class Ask:
    """A question ready to be answered: understood, embedded, its papers chosen."""

    provider: ModelProvider
    settings: Settings
    user_id: uuid.UUID
    # As the user wrote it, and as it is searched for.
    question: str
    query: str
    vector: list[float]
    # The chunk collection of the papers, and the papers that are in it.
    collection: str
    papers: list[Paper]
    history: list[Message]
    # The fast model of the connection cannot be relied on to return JSON.
    json_unreliable: bool
    # The trace of the question, and what is recorded about how it was answered.
    parent: Context
    details: dict[str, Any]
    elapsed_ms: Callable[[], int]

    @property
    def titles(self) -> dict[uuid.UUID, str]:
        return {paper.id: paper.title for paper in self.papers}


@dataclass(frozen=True)
class Written:
    """What a path ends with: the checked answer and the passages it cites."""

    text: str
    citations: list[Source]
    outcome: Outcome
    table: dict[str, Any] | None = None
    notice: str | None = None


def error_code(error: Exception) -> str:
    return error.code if isinstance(error, ProviderError) else type(error).__name__


@contextmanager
def span(name: str, parent: Context, kind: str, **attributes: Any) -> Iterator[Span]:
    """A child span that is never made the current one.

    The answer is an async generator; a span left current across its yields
    would be closed from another context than it was opened in.
    """
    opened = get_tracer().start_span(
        name, context=parent, attributes={SPAN_KIND: kind, **attributes}
    )
    try:
        yield opened
    except Exception as error:
        opened.set_status(Status(StatusCode.ERROR, error_code(error)))
        raise
    finally:
        opened.end()


def tokens(
    opened: Span, provider: ModelProvider, calls_before: int, role: Role | None = None
) -> None:
    """Records on the span the model and tokens of the calls made since calls_before.

    role keeps only the calls of that role, for a step that ran beside another.
    """
    calls = [call for call in provider.usage[calls_before:] if role in (None, call.role)]
    if calls:
        opened.set_attribute("llm.model_name", calls[-1].model)
        opened.set_attribute("llm.token_count.prompt", sum(call.input_tokens for call in calls))
        opened.set_attribute(
            "llm.token_count.completion", sum(call.output_tokens for call in calls)
        )


def documents(opened: Span, ranked: Sequence[tuple[uuid.UUID, float | None]]) -> None:
    for position, (chunk_id, score) in enumerate(ranked):
        prefix = f"retrieval.documents.{position}.document"
        opened.set_attribute(f"{prefix}.id", str(chunk_id))
        if score is not None:
            opened.set_attribute(f"{prefix}.score", score)


async def load_chunks(chunk_ids: Sequence[uuid.UUID], paper_ids: set[uuid.UUID]) -> list[Chunk]:
    """The chunks in the order given. One that is gone, or not of these papers, is dropped."""
    async with get_sessionmaker()() as db:
        rows = await db.scalars(
            select(Chunk).where(Chunk.id.in_(chunk_ids), Chunk.paper_id.in_(paper_ids))
        )
        by_id = {row.id: row for row in rows}
    return [by_id[chunk_id] for chunk_id in chunk_ids if chunk_id in by_id]


async def most_relevant_papers(ask: Ask) -> tuple[list[Paper], str | None]:
    """The papers looked at: all of them, or the most relevant ones when the scope
    holds more than the limit. With them, what to tell the reader about the cut."""
    limit = ask.settings.multi_paper_max_papers
    ask.details["papers_considered"] = min(len(ask.papers), limit)
    if len(ask.papers) <= limit:
        return ask.papers, None
    ranked = await index_search.search_papers(
        ask.collection,
        owner_id=ask.user_id,
        paper_ids=[paper.id for paper in ask.papers],
        query_text=ask.query,
        query_vector=ask.vector,
        limit=limit,
        fusion=ask.settings.search_fusion,
    )
    by_id = {paper.id: paper for paper in ask.papers}
    chosen = [by_id[paper_id] for paper_id in ranked if paper_id in by_id]
    # Papers without a point of their own are never found; fill up in the scope's order.
    chosen += [paper for paper in ask.papers if paper not in chosen][: limit - len(chosen)]
    notice = (
        f"Only the {len(chosen)} most relevant of the {len(ask.papers)} papers "
        "in scope were considered."
    )
    return chosen, notice


async def write(
    ask: Ask,
    user_content: str,
    system: str,
    pieces: list[str],
    *,
    with_history: bool = False,
    max_tokens: int | None = None,
) -> AsyncIterator[Delta]:
    """Has the answer model write, yielding each piece as it comes. The pieces are
    collected in `pieces` for the caller to check once the stream ends."""
    with span("generate", ask.parent, "LLM", **{"input.value": ask.query}) as opened:
        calls = len(ask.provider.usage)
        history = analyzer.clipped(ask.history) if with_history else []
        stream = ask.provider.stream(
            [*history, {"role": "user", "content": user_content}],
            role="answer",
            max_tokens=max_tokens or ask.settings.answer_max_tokens,
            system=system,
        )
        # Closed with this generator: when the reader leaves, the call to the
        # model ends there instead of running on until it is collected.
        async with aclosing(stream):
            async for piece in stream:
                piece = citation.plain(piece)
                if not piece:
                    continue
                if not pieces:
                    ask.details["first_token_ms"] = ask.elapsed_ms()
                    opened.set_attribute("first_token_ms", ask.details["first_token_ms"])
                pieces.append(piece)
                yield Delta(piece)
        tokens(opened, ask.provider, calls)
        opened.set_attribute("output.value", "".join(pieces))


def checked(pieces: list[str], sources: list[Source], **extra: Any) -> Written:
    """The written answer with invented markers removed, and the passages it cites."""
    by_marker = {source.marker: source for source in sources}
    # PostgreSQL stores no NUL, and no answer needs one.
    text, used = citation.validate("".join(pieces).replace("\x00", ""), set(by_marker))
    if not text:
        raise ProviderError("provider_rejected", "the model returned no answer")
    # An answer that cites nothing is the model saying the passages do not hold it.
    outcome: Outcome = "answered" if used else "no_evidence"
    return Written(text, [by_marker[marker] for marker in used], outcome, **extra)


async def passages_per_paper(ask: Ask, papers: list[Paper]) -> list[tuple[uuid.UUID, list[Chunk]]]:
    """Each paper with its own best passages for the question, in the papers' order."""
    with span("retrieve", ask.parent, "RETRIEVER", **{"input.value": ask.query}) as opened:
        groups = await index_search.search_grouped(
            ask.collection,
            owner_id=ask.user_id,
            paper_ids=[paper.id for paper in papers],
            query_text=ask.query,
            query_vector=ask.vector,
            candidates=ask.settings.search_candidates,
            group_size=ask.settings.multi_paper_chunks,
            fusion=ask.settings.search_fusion,
        )
        hits = [hit for found in groups.values() for hit in found]
        documents(opened, [(hit.chunk_id, hit.score) for hit in hits])
    ask.details["candidates"] = [
        {"chunk_id": str(hit.chunk_id), "score": hit.score} for hit in hits
    ]
    ask.details["retrieved_ms"] = ask.elapsed_ms()
    chunks = await load_chunks([hit.chunk_id for hit in hits], {paper.id for paper in papers})
    by_paper: dict[uuid.UUID, list[Chunk]] = {paper.id: [] for paper in papers}
    for chunk in chunks:
        by_paper[chunk.paper_id].append(chunk)
    return list(by_paper.items())
