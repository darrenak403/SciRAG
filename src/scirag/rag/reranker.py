"""Reorders search results by asking the account's fast model which passages help most."""

import json
import re

from scirag.providers.base import ModelProvider
from scirag.rag.prompts import RERANK_SYSTEM

PASSAGE_CHARS = 1200


def parse_ranking(reply: str, count: int) -> list[int]:
    """Passage numbers from the model's reply, without repeats or numbers out of range.

    Raises ValueError when the reply holds no list of numbers.
    """
    try:
        parsed = json.loads(reply)
    except ValueError:
        # Some models wrap the JSON in prose or a code fence.
        found = re.search(r"\[[\d\s,]*\]", reply)
        if not found:
            raise
        parsed = json.loads(found.group())
    if isinstance(parsed, dict):
        parsed = next((value for value in parsed.values() if isinstance(value, list)), None)
    if not isinstance(parsed, list):
        raise ValueError("the reply holds no ranking")
    ranking: list[int] = []
    for item in parsed:
        if isinstance(item, int) and not isinstance(item, bool) and 0 <= item < count:
            if item not in ranking:
                ranking.append(item)
    return ranking


async def rerank(provider: ModelProvider, query: str, passages: list[str], top_n: int) -> list[int]:
    """Indexes of the top_n passages, best first.

    Passages the model did not name follow in their original order, so a model
    that names too few never shrinks what reaches the answer.
    """
    numbered = "\n\n".join(
        f"[{number}]\n{passage[:PASSAGE_CHARS]}" for number, passage in enumerate(passages)
    )
    reply = await provider.complete(
        [
            {
                "role": "user",
                "content": f"Question: {query}\n\nReturn at most {top_n} numbers.\n\n{numbered}",
            }
        ],
        role="fast",
        max_tokens=256,
        system=RERANK_SYSTEM,
        json_output=True,
    )
    ranking = parse_ranking(reply, len(passages))
    rest = [index for index in range(len(passages)) if index not in ranking]
    return (ranking + rest)[:top_n]
