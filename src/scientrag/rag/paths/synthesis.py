"""A question about the papers as a whole: pick the papers, read each one's best
passages for the question, and write up what they say together."""

from collections.abc import AsyncIterator
from contextlib import aclosing

from scientrag.rag import evidence_summarizer
from scientrag.rag.context_builder import build_context
from scientrag.rag.paths.base import (
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
from scientrag.rag.prompts import SYNTHESIS_SYSTEM
from scientrag.rag.types import Delta, Sources, Status


async def run(ask: Ask) -> AsyncIterator[Sources | Status | Delta | Written]:
    settings, details, provider = ask.settings, ask.details, ask.provider

    yield Status("selecting")
    papers, notice = await most_relevant_papers(ask)
    groups = await passages_per_paper(ask, papers)
    # Paper by paper, each paper's best passage first.
    chunks = [chunk for _, found in groups for chunk in found]
    if not chunks:
        yield Sources([])
        yield Written(NO_EVIDENCE, [], "no_evidence", notice=notice)
        return

    yield Status("gathering", 0, len(chunks))
    judged: dict[int, evidence_summarizer.Evidence] = {}
    with span("gather_evidence", ask.parent, "CHAIN", **{"input.value": ask.query}) as opened:
        calls = len(provider.usage)
        gathering = evidence_summarizer.gather(
            provider,
            ask.query,
            [chunk.text for chunk in chunks],
            parallel=settings.multi_paper_parallel_calls,
            timeout=settings.fast_model_timeout_seconds,
        )
        done = 0
        # Closed with this generator: a reader who leaves ends the calls still running.
        async with aclosing(gathering):
            async for index, evidence in gathering:
                done += 1
                if evidence is not None:
                    judged[index] = evidence
                yield Status("gathering", done, len(chunks))
        tokens(opened, provider, calls)
    details["evidence"] = [
        {"chunk_id": str(chunks[index].id), "relevance": evidence.relevance}
        for index, evidence in sorted(judged.items())
    ]
    details["evidence_unjudged"] = len(chunks) - len(judged)
    details["ranked_ms"] = ask.elapsed_ms()

    yield Status("comparing")
    kept = sorted(
        (
            index
            for index, evidence in judged.items()
            if evidence.relevance >= settings.evidence_min_relevance and evidence.summary
        ),
        # The most useful findings first; among equals, the order they were found in.
        key=lambda index: (-judged[index].relevance, index),
    )
    if not kept and len(judged) == len(chunks):
        # Every passage was read and none bears on the question.
        yield Sources([])
        yield Written(NO_EVIDENCE, [], "no_evidence", notice=notice)
        return
    if kept:
        context, sources = build_context(
            [chunks[index] for index in kept],
            ask.titles,
            max_tokens=settings.multi_paper_context_tokens,
            bodies={chunks[index].id: judged[index].summary for index in kept},
        )
    else:
        # Nothing useful among the passages that were judged, and some never were: the
        # fast model is failing, and "nothing found" would be a guess. The answer is
        # written from each paper's best passage as it stands.
        details["evidence"] = f"failed: {len(chunks) - len(judged)} passages could not be judged"
        context, sources = build_context(
            [found[0] for _, found in groups if found],
            ask.titles,
            max_tokens=settings.multi_paper_context_tokens,
        )
    details["context"] = [
        {"marker": source.marker, "chunk_id": str(source.chunk_id)} for source in sources
    ]
    yield Sources(sources, details)

    yield Status("writing")
    pieces: list[str] = []
    content = f"{context}\n\nQuestion: {ask.query}"
    async for delta in write(
        ask, content, SYNTHESIS_SYSTEM, pieces, max_tokens=settings.multi_paper_answer_tokens
    ):
        yield delta
    yield checked(pieces, sources, notice=notice)
