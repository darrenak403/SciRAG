"""Answers a question from the papers in scope, with the asking account's own models.

The question is made to stand alone and its kind decided; then one of three
paths answers it: factual (the best passages of all the papers), comparison
(a table with a row per paper) or synthesis (findings gathered across papers).
Each step is a span of one trace.
"""

import asyncio
import dataclasses
import time
import uuid
from collections.abc import AsyncIterator, Sequence
from contextlib import aclosing
from typing import Any, Literal

from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.trace import Status, StatusCode

from scientrag.access.readable_papers import readable_papers
from scientrag.config import Settings, get_settings
from scientrag.db.engine import get_sessionmaker
from scientrag.db.models import Paper, ProviderConnection
from scientrag.index.qdrant_index import chunks_collection
from scientrag.providers.base import Message, ModelProvider
from scientrag.providers.errors import ProviderError
from scientrag.providers.resolve import connection_provider
from scientrag.rag import analyzer
from scientrag.rag.paths import comparison, factual, synthesis
from scientrag.rag.paths.base import NO_EVIDENCE, Ask, Written, error_code, span, tokens
from scientrag.rag.types import Done, Event, Mode, Sources
from scientrag.rag.types import Status as Progress
from scientrag.telemetry.tracing import SPAN_KIND, get_tracer

__all__ = ["NO_EVIDENCE", "NO_PAPERS", "answer"]

NO_PAPERS = "There are no processed papers in the scope of this chat."
PATHS = {"factual": factual.run, "comparison": comparison.run, "synthesis": synthesis.run}

# auto: the kind of question is worked out from the question itself.
AskedMode = Literal["auto", "factual", "comparison", "synthesis"]


def _token_totals(provider: ModelProvider) -> dict[str, list[int]]:
    """Tokens in and out per role, over every call made for this question."""
    totals: dict[str, list[int]] = {}
    for call in provider.usage:
        spent = totals.setdefault(call.role, [0, 0])
        spent[0] += call.input_tokens
        spent[1] += call.output_tokens
    return totals


async def _searchable(user_id: uuid.UUID, paper_ids: Sequence[uuid.UUID]) -> list[Paper]:
    async with get_sessionmaker()() as db:
        return await readable_papers(db, user_id, paper_ids, ready_only=True)


async def _understand(
    provider: ModelProvider,
    settings: Settings,
    parent: Context,
    question: str,
    history: list[Message],
    asked: AskedMode,
    papers: int,
) -> tuple[Mode, str, list[float]]:
    """The kind of question, the question as it is searched for, and its vector."""
    # One paper cannot be compared or synthesized: whatever was asked for is a plain question.
    classify = asked == "auto" and papers > 1

    async def prepared() -> tuple[Mode, str]:
        if not classify and not history:
            # A first question already stands alone.
            return ("factual" if asked == "auto" else asked), question
        name = "analyze_question" if classify else "rewrite_question"
        with span(name, parent, "LLM", **{"input.value": question}) as opened:
            calls = len(provider.usage)
            mode: Mode = "factual" if asked == "auto" else asked
            query = question
            try:
                async with asyncio.timeout(settings.fast_model_timeout_seconds):
                    if classify:
                        mode, query = await analyzer.analyze(provider, history, question)
                    else:
                        query = await analyzer.rewrite(provider, history, question)
            except (ProviderError, TimeoutError) as error:
                # The question as written is still worth searching for, as a plain question.
                code = error.code if isinstance(error, ProviderError) else "timeout"
                opened.set_attribute("warning", f"{name} failed: {code}")
            tokens(opened, provider, calls, role="fast")
            opened.set_attribute("output.value", query)
            return mode, query

    async def embedded(text: str) -> list[float]:
        with span("embed_query", parent, "EMBEDDING", **{"input.value": text}) as opened:
            calls = len(provider.usage)
            vector = await provider.embed_query(text)
            tokens(opened, provider, calls, role="embedding")
            return vector

    if history:
        # The search is for the rewritten question, so the rewrite comes first.
        mode, query = await prepared()
        return mode, query, await embedded(query)
    # Nothing to rewrite: the question is embedded while its kind is worked out.
    (mode, _), vector = await asyncio.gather(prepared(), embedded(question))
    return mode, question, vector


async def answer(
    connection: ProviderConnection,
    question: str,
    *,
    paper_ids: Sequence[uuid.UUID],
    history: list[Message],
    mode: AskedMode = "auto",
) -> AsyncIterator[Event]:
    """Yields what is being done and the sources, then the answer piece by piece
    (after its table, for a comparison), then the checked result.

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

    def finished(written: Written, kind: Mode = "factual") -> Done:
        details["total_ms"] = elapsed_ms()
        root.set_attribute("output.value", written.text)
        root.set_attribute("answer.outcome", written.outcome)
        root.set_attribute("answer.mode", kind)
        return Done(
            written.text,
            written.citations,
            written.outcome,
            trace_id,
            details,
            kind,
            written.table,
            written.notice,
        )

    try:
        papers = await _searchable(user_id, paper_ids)
        if not papers:
            yield Sources([])
            yield finished(Written(NO_PAPERS, [], "no_papers"))
            return

        async with connection_provider(connection) as provider:
            embedding_model = provider.model("embedding")
            details["embedding_model"] = embedding_model

            kind, query, vector = await _understand(
                provider, settings, parent, question, history, mode, len(papers)
            )
            details["mode"] = kind
            details["search_query"] = query

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
            if len(searched) == 1:
                kind = details["mode"] = "factual"

            ask = Ask(
                provider=provider,
                settings=settings,
                user_id=user_id,
                question=question,
                query=query,
                vector=vector,
                collection=collection,
                papers=searched,
                history=history,
                json_unreliable=bool((connection.capabilities or {}).get("rerank_disabled")),
                parent=parent,
                details=details,
                elapsed_ms=elapsed_ms,
            )
            path = PATHS[kind](ask)
            # Closed with this generator, so a reader who leaves ends the path's calls too.
            async with aclosing(path):
                async for item in path:
                    if isinstance(item, Written):
                        if details["papers_skipped"]:
                            left_out = (
                                f"{len(details['papers_skipped'])} of the papers in scope were "
                                "left out: they were indexed with another embedding model."
                            )
                            item = dataclasses.replace(
                                item, notice=" ".join(filter(None, [item.notice, left_out]))
                            )
                        details["answer_model"] = provider.model("answer")
                        details["tokens"] = _token_totals(provider)
                        yield finished(item, kind)
                    elif isinstance(item, Progress):
                        # The stages ahead depend on the kind of answer being made.
                        yield dataclasses.replace(item, mode=kind)
                    else:
                        yield item
    except Exception as error:
        root.set_status(Status(StatusCode.ERROR, error_code(error)))
        raise
    finally:
        root.end()
