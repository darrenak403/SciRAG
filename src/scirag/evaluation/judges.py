"""Scores that need a model to read the answer: is it grounded, relevant, well cited.

The definitions follow Ragas (faithfulness, answer relevance, context precision,
context recall). The prompts are our own and go through the account's provider,
so the numbers compare runs of this project with each other, not with numbers
published elsewhere. Every judge returns None when the model's reply cannot be
used; such questions are left out of the average and counted.
"""

import json
import math
import re
from typing import Any

from scirag.providers.base import ModelProvider
from scirag.providers.errors import ProviderError
from scirag.rag import citation

PASSAGE_CHARS = 2400
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+|\n+")

FAITHFULNESS = """\
You check whether an answer is supported by source passages.
Break the answer into its separate factual claims. For each claim decide whether the passages \
state or directly imply it. Ignore citation markers such as [S1]. Reply with JSON only:
{"claims": [{"claim": "...", "supported": true}]}"""

GENERATED_QUESTIONS = """\
You are given an answer. Write three different questions that this answer would be a complete \
and direct reply to. Reply with JSON only: {"questions": ["...", "...", "..."]}"""

CONTEXT_PRECISION = """\
You are given a question, its correct answer, and numbered passages. For each passage decide \
whether it helps to arrive at the correct answer. Reply with JSON only, one value per passage \
in the order given: {"useful": [true, false]}"""

CONTEXT_RECALL = """\
You are given a correct answer and passages. Break the correct answer into its separate \
statements. For each statement decide whether the passages contain it. Reply with JSON only:
{"statements": [{"statement": "...", "attributed": true}]}"""

CITATION_SUPPORT = """\
You check citations. Each numbered item holds a sentence from an answer and the passages that \
the sentence cites. For each item decide whether the cited passages state or directly imply \
what the sentence claims. Reply with JSON only, one value per item in the order given:
{"supported": [true, false]}"""


async def _ask(provider: ModelProvider, system: str, content: str) -> Any:
    try:
        reply = await provider.complete(
            [{"role": "user", "content": content}],
            role="answer",
            max_tokens=2048,
            system=system,
            json_output=True,
        )
        return json.loads(reply)
    except ProviderError, ValueError:
        return None


def _numbered(passages: list[str]) -> str:
    return "\n\n".join(
        f"[{number}]\n{passage[:PASSAGE_CHARS]}" for number, passage in enumerate(passages, 1)
    )


def _flags(
    reply: Any, key: str, field: str | None, expected: int | None = None
) -> list[bool] | None:
    """The true/false verdicts of a reply, or None when it does not have the asked shape."""
    items = reply.get(key) if isinstance(reply, dict) else None
    if not isinstance(items, list) or not items:
        return None
    values = [item.get(field) if field and isinstance(item, dict) else item for item in items]
    if not all(isinstance(value, bool) for value in values):
        return None
    if expected is not None and len(values) != expected:
        return None
    return values


async def faithfulness(provider: ModelProvider, answer: str, passages: list[str]) -> float | None:
    """The share of the answer's claims that the passages support."""
    reply = await _ask(
        provider, FAITHFULNESS, f"Passages:\n{_numbered(passages)}\n\nAnswer:\n{answer}"
    )
    flags = _flags(reply, "claims", "supported")
    return sum(flags) / len(flags) if flags else None


def _cosine(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    norms = math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right))
    return dot / norms if norms else 0.0


async def answer_relevance(provider: ModelProvider, question: str, answer: str) -> float | None:
    """How close the questions this answer would answer are to the one that was asked."""
    reply = await _ask(provider, GENERATED_QUESTIONS, f"Answer:\n{answer}")
    generated = reply.get("questions") if isinstance(reply, dict) else None
    if not isinstance(generated, list) or not generated:
        return None
    generated = [text for text in generated if isinstance(text, str) and text.strip()][:3]
    if not generated:
        return None
    try:
        asked, *others = await provider.embed_documents([question, *generated])
    except ProviderError:
        return None
    return sum(_cosine(asked, other) for other in others) / len(others)


async def context_precision(
    provider: ModelProvider, question: str, reference: str, passages: list[str]
) -> float | None:
    """Whether the useful passages come first: average precision over the ranked passages."""
    content = (
        f"Question: {question}\nCorrect answer: {reference}\n\nPassages:\n{_numbered(passages)}"
    )
    flags = _flags(await _ask(provider, CONTEXT_PRECISION, content), "useful", None, len(passages))
    if flags is None:
        return None
    if not any(flags):
        return 0.0
    precisions = [
        sum(flags[: rank + 1]) / (rank + 1) for rank, useful in enumerate(flags) if useful
    ]
    return sum(precisions) / len(precisions)


async def context_recall(
    provider: ModelProvider, reference: str, passages: list[str]
) -> float | None:
    """The share of the correct answer's statements that the passages contain."""
    content = f"Passages:\n{_numbered(passages)}\n\nCorrect answer:\n{reference}"
    flags = _flags(await _ask(provider, CONTEXT_RECALL, content), "statements", "attributed")
    return sum(flags) / len(flags) if flags else None


def cited_sentences(answer: str, passages: dict[str, str]) -> list[dict[str, Any]]:
    """The sentences of an answer that cite something, each with the passages it cites."""
    found = []
    for sentence in _SENTENCE_END.split(answer):
        cited = list(dict.fromkeys(m for m in citation.markers(sentence) if m in passages))
        if cited:
            found.append({"sentence": sentence.strip(), "markers": cited})
    return found


async def citation_support(
    provider: ModelProvider, answer: str, passages: dict[str, str]
) -> list[dict[str, Any]] | None:
    """Each citing sentence with the judge's verdict: do the passages it cites back it up.

    passages maps a marker to the text of its passage. An answer that cites
    nothing gives an empty list.
    """
    sentences = cited_sentences(answer, passages)
    if not sentences:
        return []
    items = "\n\n".join(
        f"Item {number}\nSentence: {citation.without_markers(item['sentence'])}\nCited passages:\n"
        + "\n".join(passages[marker][:PASSAGE_CHARS] for marker in item["markers"])
        for number, item in enumerate(sentences, 1)
    )
    flags = _flags(await _ask(provider, CITATION_SUPPORT, items), "supported", None, len(sentences))
    if flags is None:
        return None
    return [{**item, "supported": flag} for item, flag in zip(sentences, flags, strict=True)]
