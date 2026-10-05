"""Reads one passage for one question with the account's fast model: how much it
helps, and what it says that bears on the question."""

import asyncio
import json
import math
import re
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass

from scientrag.providers.base import ModelProvider
from scientrag.providers.errors import ProviderError
from scientrag.rag.prompts import EVIDENCE_SYSTEM

PASSAGE_CHARS = 3000
SUMMARY_CHARS = 1200
# Room for a model that reasons before it replies: the reply itself is a few sentences,
# but a lower ceiling leaves such a model nothing to write them with.
REPLY_TOKENS = 1024
# This many passages in a row that could not be judged: the fast model is down, and
# the passages still waiting are not sent to it.
GIVE_UP_AFTER = 8


@dataclass(frozen=True)
class Evidence:
    # 0: says nothing about the question. 10: answers it directly.
    relevance: int
    summary: str


def parse_evidence(reply: str) -> Evidence:
    """Raises ValueError when the reply holds no score."""
    try:
        parsed = json.loads(reply)
    except ValueError:
        # Some models wrap the JSON in prose or a code fence.
        found = re.search(r"\{.*\}", reply, re.DOTALL)
        if not found:
            raise
        parsed = json.loads(found.group())
    relevance = parsed.get("relevance") if isinstance(parsed, dict) else None
    if isinstance(relevance, bool) or not isinstance(relevance, int | float):
        raise ValueError("the reply holds no score")
    if not math.isfinite(relevance):
        raise ValueError("the score is not a number")
    summary = parsed.get("summary") if isinstance(parsed.get("summary"), str) else ""
    summary = " ".join(summary.replace("\x00", "").split())[:SUMMARY_CHARS]
    return Evidence(max(0, min(10, round(relevance))), summary)


async def judge(provider: ModelProvider, question: str, passage: str) -> Evidence:
    # A passage must not be able to close its own tag and pose as instructions.
    body = re.sub(r"<(\s*/?\s*passage)", r"&lt;\1", passage[:PASSAGE_CHARS], flags=re.IGNORECASE)
    reply = await provider.complete(
        [
            {
                "role": "user",
                "content": f"Question: {question}\n\n<passage>\n{body}\n</passage>",
            }
        ],
        role="fast",
        max_tokens=REPLY_TOKENS,
        system=EVIDENCE_SYSTEM,
        json_output=True,
    )
    return parse_evidence(reply)


async def gather(
    provider: ModelProvider,
    question: str,
    passages: Sequence[str],
    *,
    parallel: int,
    timeout: float,
) -> AsyncIterator[tuple[int, Evidence | None]]:
    """Judges every passage, a few at a time, yielding each one's index and result
    as it is done. A passage whose call fails yields None: one bad reply does not
    cost the question its answer. After several failures in a row the rest yield
    None without a call, so a model that is down does not hold the answer up.
    """
    slots = asyncio.Semaphore(parallel)
    failed_in_a_row = 0

    async def one(index: int) -> tuple[int, Evidence | None]:
        nonlocal failed_in_a_row
        async with slots:
            if failed_in_a_row >= GIVE_UP_AFTER:
                return index, None
            try:
                async with asyncio.timeout(timeout):
                    evidence = await judge(provider, question, passages[index])
            except ProviderError, TimeoutError, ValueError:
                failed_in_a_row += 1
                return index, None
            failed_in_a_row = 0
            return index, evidence

    tasks = [asyncio.create_task(one(index)) for index in range(len(passages))]
    try:
        for finished in asyncio.as_completed(tasks):
            yield await finished
    finally:
        # The reader left, or something failed: no call is left running.
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
