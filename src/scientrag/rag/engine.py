"""Answers a question from the papers in scope, with the asking account's own models.

One path: make the question stand alone, search the papers the account may
read, rerank, give the best passages to the model, check the markers it wrote.
Each step is a span of one trace.
"""

import asyncio
import time
import uuid
from collections.abc import AsyncIterator, Iterator, Sequence
from contextlib import aclosing, contextmanager
from typing import Any

from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.trace import Span, Status, StatusCode
from sqlalchemy import select

from scientrag.access.readable_papers import readable_papers
from scientrag.config import get_settings
from scientrag.db.engine import get_sessionmaker
from scientrag.db.models import Chunk, Paper, ProviderConnection
from scientrag.index import search as index_search
from scientrag.index.qdrant_index import chunks_collection
from scientrag.providers.base import Message, ModelProvider
from scientrag.providers.errors import ProviderError
from scientrag.providers.resolve import connection_provider
from scientrag.rag import analyzer, citation, reranker
from scientrag.rag.context_builder import build_context
from scientrag.rag.prompts import ANSWER_SYSTEM
from scientrag.rag.types import Delta, Done, Event, Sources
from scientrag.telemetry.tracing import SPAN_KIND, get_tracer

NO_PAPERS = "There are no processed papers in the scope of this chat."
NO_EVIDENCE = "I could not find anything about this in the selected papers."


def _error_code(error: Exception) -> str:
    return error.code if isinstance(error, ProviderError) else type(error).__name__


@contextmanager
def _span(name: str, parent: Context, kind: str, **attributes: Any) -> Iterator[Span]:
    """A child span that is never made the current one.

    The answer is an async generator; a span left current across its yields
    would be closed from another context than it was opened in.
    """
    span = get_tracer().start_span(name, context=parent, attributes={SPAN_KIND: kind, **attributes})
    try:
        yield span
    except Exception as error:
        span.set_status(Status(StatusCode.ERROR, _error_code(error)))
        raise
    finally:
        span.end()


def _tokens(span: Span, provider: ModelProvider, calls_before: int) -> None:
    """Records on the span the model and tokens of the calls made since calls_before."""
    calls = provider.usage[calls_before:]
    if calls:
        span.set_attribute("llm.model_name", calls[-1].model)
        span.set_attribute("llm.token_count.prompt", sum(call.input_tokens for call in calls))
        span.set_attribute("llm.token_count.completion", sum(call.output_tokens for call in calls))


def _token_totals(provider: ModelProvider) -> dict[str, list[int]]:
    """Tokens in and out per role, over every call made for this question."""
    totals: dict[str, list[int]] = {}
    for call in provider.usage:
        spent = totals.setdefault(call.role, [0, 0])
        spent[0] += call.input_tokens
        spent[1] += call.output_tokens
    return totals


def _documents(span: Span, ranked: Sequence[tuple[uuid.UUID, float | None]]) -> None:
    for position, (chunk_id, score) in enumerate(ranked):
        prefix = f"retrieval.documents.{position}.document"
        span.set_attribute(f"{prefix}.id", str(chunk_id))
        if score is not None:
            span.set_attribute(f"{prefix}.score", score)


async def _searchable(user_id: uuid.UUID, paper_ids: Sequence[uuid.UUID]) -> list[Paper]:
    async with get_sessionmaker()() as db:
        return await readable_papers(db, user_id, paper_ids, ready_only=True)


async def _load_chunks(chunk_ids: Sequence[uuid.UUID], paper_ids: set[uuid.UUID]) -> list[Chunk]:
    """The chunks in the order given. One that is gone, or not of these papers, is dropped."""
    async with get_sessionmaker()() as db:
        rows = await db.scalars(
            select(Chunk).where(Chunk.id.in_(chunk_ids), Chunk.paper_id.in_(paper_ids))
        )
        by_id = {row.id: row for row in rows}
    return [by_id[chunk_id] for chunk_id in chunk_ids if chunk_id in by_id]


async def answer(
    connection: ProviderConnection,
    question: str,
    *,
    paper_ids: Sequence[uuid.UUID],
    history: list[Message],
) -> AsyncIterator[Event]:
    """Yields the sources, then the answer piece by piece, then the checked result.

    connection is the asking account's own; paper_ids is the scope it asked in.
    Raises ProviderError when the account's provider fails.
    """
    settings = get_settings()
    user_id = connection.user_id
    root = get_tracer().start_span(
        "answer_question",
        attributes={
            SPAN_KIND: "CHAIN",
            "input.value": question,
            "user.id": str(user_id),
            "provider.kind": connection.kind,
        },
    )
    parent = trace.set_span_in_context(root)
    trace_id = format(root.get_span_context().trace_id, "032x")
    started = time.monotonic()
    details: dict[str, Any] = {"papers_in_scope": len(paper_ids)}

    def elapsed_ms() -> int:
        return round((time.monotonic() - started) * 1000)

    def finished(text: str, cited: list, outcome: str) -> Done:
        details["total_ms"] = elapsed_ms()
        root.set_attribute("output.value", text)
        root.set_attribute("answer.outcome", outcome)
        return Done(text, cited, outcome, trace_id, details)

    try:
        papers = await _searchable(user_id, paper_ids)
        if not papers:
            yield Sources([])
            yield finished(NO_PAPERS, [], "no_papers")
            return

        async with connection_provider(connection) as provider:
            embedding_model = provider.model("embedding")
            details["embedding_model"] = embedding_model

            query = question
            if history:
                with _span("rewrite_question", parent, "LLM", **{"input.value": question}) as span:
                    calls = len(provider.usage)
                    try:
                        async with asyncio.timeout(settings.fast_model_timeout_seconds):
                            query = await analyzer.rewrite(provider, history, question)
                    except (ProviderError, TimeoutError) as error:
                        # The question as written is still worth searching for.
                        code = error.code if isinstance(error, ProviderError) else "timeout"
                        span.set_attribute("warning", f"rewrite failed: {code}")
                    _tokens(span, provider, calls)
                    span.set_attribute("output.value", query)
            details["search_query"] = query

            with _span("retrieve", parent, "RETRIEVER", **{"input.value": query}) as span:
                calls = len(provider.usage)
                vector = await provider.embed_query(query)
                _tokens(span, provider, calls)
                collection = chunks_collection(embedding_model, len(vector))
                # Vectors of another model cannot be compared with this query.
                searched = [paper for paper in papers if paper.index_collection == collection]
                details["papers_searched"] = len(searched)
                details["papers_skipped"] = [
                    str(paper.id) for paper in papers if paper.index_collection != collection
                ]
                if not searched:
                    others = sorted({paper.embedding_model or "unknown" for paper in papers})
                    raise ProviderError(
                        "capability_missing",
                        f"the papers in scope were indexed with {', '.join(others)}; "
                        f"index them again to search them with {embedding_model}",
                    )
                hits = await index_search.search(
                    collection,
                    owner_id=user_id,
                    paper_ids=[paper.id for paper in searched],
                    query_text=query,
                    query_vector=vector,
                    candidates=settings.search_candidates,
                    limit=settings.rerank_candidates,
                    fusion=settings.search_fusion,
                )
                _documents(span, [(hit.chunk_id, hit.score) for hit in hits])
            details["candidates"] = [
                {"chunk_id": str(hit.chunk_id), "score": hit.score} for hit in hits
            ]
            # Since the question arrived: the rewrite, the embedding and the search.
            details["retrieved_ms"] = elapsed_ms()

            titles = {paper.id: paper.title for paper in searched}
            chunks = await _load_chunks([hit.chunk_id for hit in hits], set(titles))
            if not chunks:
                yield Sources([])
                yield finished(NO_EVIDENCE, [], "no_evidence")
                return

            chosen = chunks[: settings.context_chunks]
            capabilities = connection.capabilities or {}
            if not settings.rerank_enabled:
                details["rerank"] = "off"
            elif capabilities.get("rerank_disabled"):
                details["rerank"] = "skipped: the fast model does not return JSON"
            elif len(chunks) > 1:
                with _span("rerank", parent, "RERANKER", **{"input.value": query}) as span:
                    calls = len(provider.usage)
                    try:
                        async with asyncio.timeout(settings.fast_model_timeout_seconds):
                            order = await reranker.rerank(
                                provider,
                                query,
                                [chunk.embed_text for chunk in chunks],
                                settings.context_chunks,
                            )
                        chosen = [chunks[index] for index in order]
                        details["rerank"] = "model"
                    except (ProviderError, TimeoutError, ValueError) as error:
                        # The search order is a usable ranking; the answer does not wait on this.
                        reason = _error_code(error)
                        details["rerank"] = f"failed: {reason}"
                        span.set_attribute("warning", f"rerank failed: {reason}")
                    _tokens(span, provider, calls)
                    _documents(span, [(chunk.id, None) for chunk in chosen])

            details["ranked_ms"] = elapsed_ms()

            context, sources = build_context(chosen, titles, max_tokens=settings.context_max_tokens)
            details["context"] = [
                {"marker": source.marker, "chunk_id": str(source.chunk_id)} for source in sources
            ]
            yield Sources(sources, details)

            pieces: list[str] = []
            with _span("generate", parent, "LLM", **{"input.value": query}) as span:
                calls = len(provider.usage)
                messages = [
                    *analyzer.clipped(history),
                    {"role": "user", "content": f"{context}\n\nQuestion: {question}"},
                ]
                stream = provider.stream(
                    messages,
                    role="answer",
                    max_tokens=settings.answer_max_tokens,
                    system=ANSWER_SYSTEM,
                )
                # Closed with this generator: when the reader leaves, the call to the
                # model ends there instead of running on until it is collected.
                async with aclosing(stream):
                    async for piece in stream:
                        piece = citation.plain(piece)
                        if not piece:
                            continue
                        if not pieces:
                            details["first_token_ms"] = elapsed_ms()
                            span.set_attribute("first_token_ms", details["first_token_ms"])
                        pieces.append(piece)
                        yield Delta(piece)
                _tokens(span, provider, calls)
                span.set_attribute("output.value", "".join(pieces))
            details["answer_model"] = provider.model("answer")
            details["tokens"] = _token_totals(provider)

            by_marker = {source.marker: source for source in sources}
            # PostgreSQL stores no NUL, and no answer needs one.
            answer_text = "".join(pieces).replace("\x00", "")
            text, used = citation.validate(answer_text, set(by_marker))
            if not text:
                raise ProviderError("provider_rejected", "the model returned no answer")
            # An answer that cites nothing is the model saying the passages do not hold it.
            outcome = "answered" if used else "no_evidence"
            yield finished(text, [by_marker[marker] for marker in used], outcome)
    except Exception as error:
        root.set_status(Status(StatusCode.ERROR, _error_code(error)))
        raise
    finally:
        root.end()
