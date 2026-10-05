"""A specific question: search every paper in scope at once, rerank, answer from
the best passages."""

import asyncio
from collections.abc import AsyncIterator

from scientrag.index import search as index_search
from scientrag.providers.errors import ProviderError
from scientrag.rag import reranker
from scientrag.rag.context_builder import build_context
from scientrag.rag.paths.base import (
    NO_EVIDENCE,
    Ask,
    Written,
    checked,
    documents,
    error_code,
    load_chunks,
    span,
    tokens,
    write,
)
from scientrag.rag.prompts import ANSWER_SYSTEM
from scientrag.rag.types import Delta, Sources


async def run(ask: Ask) -> AsyncIterator[Sources | Delta | Written]:
    settings, details, provider = ask.settings, ask.details, ask.provider

    with span("retrieve", ask.parent, "RETRIEVER", **{"input.value": ask.query}) as opened:
        hits = await index_search.search(
            ask.collection,
            owner_id=ask.user_id,
            paper_ids=[paper.id for paper in ask.papers],
            query_text=ask.query,
            query_vector=ask.vector,
            candidates=settings.search_candidates,
            limit=settings.rerank_candidates,
            fusion=settings.search_fusion,
        )
        documents(opened, [(hit.chunk_id, hit.score) for hit in hits])
    details["candidates"] = [{"chunk_id": str(hit.chunk_id), "score": hit.score} for hit in hits]
    # Since the question arrived: the rewrite, the embedding and the search.
    details["retrieved_ms"] = ask.elapsed_ms()

    titles = ask.titles
    chunks = await load_chunks([hit.chunk_id for hit in hits], set(titles))
    if not chunks:
        yield Sources([])
        yield Written(NO_EVIDENCE, [], "no_evidence")
        return

    chosen = chunks[: settings.context_chunks]
    if not settings.rerank_enabled:
        details["rerank"] = "off"
    elif ask.json_unreliable:
        details["rerank"] = "skipped: the fast model does not return JSON"
    elif len(chunks) > 1:
        with span("rerank", ask.parent, "RERANKER", **{"input.value": ask.query}) as opened:
            calls = len(provider.usage)
            try:
                async with asyncio.timeout(settings.fast_model_timeout_seconds):
                    order = await reranker.rerank(
                        provider,
                        ask.query,
                        [chunk.embed_text for chunk in chunks],
                        settings.context_chunks,
                    )
                chosen = [chunks[index] for index in order]
                details["rerank"] = "model"
            except (ProviderError, TimeoutError, ValueError) as error:
                # The search order is a usable ranking; the answer does not wait on this.
                reason = error_code(error)
                details["rerank"] = f"failed: {reason}"
                opened.set_attribute("warning", f"rerank failed: {reason}")
            tokens(opened, provider, calls)
            documents(opened, [(chunk.id, None) for chunk in chosen])

    details["ranked_ms"] = ask.elapsed_ms()

    context, sources = build_context(chosen, titles, max_tokens=settings.context_max_tokens)
    details["context"] = [
        {"marker": source.marker, "chunk_id": str(source.chunk_id)} for source in sources
    ]
    yield Sources(sources, details)

    pieces: list[str] = []
    content = f"{context}\n\nQuestion: {ask.question}"
    async for delta in write(ask, content, ANSWER_SYSTEM, pieces, with_history=True):
        yield delta
    yield checked(pieces, sources)
