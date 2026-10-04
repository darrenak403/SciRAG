"""The measures an evaluation run reports. Each one is computed per question.

Retrieval is scored against evidence passages. A passage can be spread over
more than one chunk, so each passage is given as the set of chunks that hold
it, and counts as found when any of them was retrieved.
"""

import math
import re
import string
from collections import Counter
from collections.abc import Hashable, Sequence
from typing import Any

_ARTICLES = re.compile(r"\b(a|an|the)\b")
_PUNCTUATION = str.maketrans("", "", string.punctuation)


def recall_at_k[T: Hashable](ranked: Sequence[T], evidence: Sequence[set[T]], k: int) -> float:
    """The share of evidence passages that have a chunk among the first k results."""
    top = set(ranked[:k])
    return sum(1 for chunks in evidence if chunks & top) / len(evidence)


def mrr[T: Hashable](ranked: Sequence[T], relevant: set[T]) -> float:
    """One over the rank of the first evidence chunk; 0 when none was retrieved."""
    for rank, item in enumerate(ranked, start=1):
        if item in relevant:
            return 1 / rank
    return 0.0


def ndcg_at_k[T: Hashable](ranked: Sequence[T], relevant: set[T], k: int) -> float:
    """How close the order of the first k results is to having every evidence chunk on top."""
    gain = sum(
        1 / math.log2(rank + 1) for rank, item in enumerate(ranked[:k], 1) if item in relevant
    )
    ideal = sum(1 / math.log2(rank + 1) for rank in range(1, min(k, len(relevant)) + 1))
    return gain / ideal if ideal else 0.0


def _answer_tokens(text: str) -> list[str]:
    text = _ARTICLES.sub(" ", text.lower().translate(_PUNCTUATION))
    return text.split()


def token_f1(prediction: str, reference: str) -> float:
    """Word overlap between an answer and the reference answer, as SQuAD and QASPER score it."""
    predicted, expected = _answer_tokens(prediction), _answer_tokens(reference)
    if not predicted or not expected:
        return float(predicted == expected)
    common = sum((Counter(predicted) & Counter(expected)).values())
    if not common:
        return 0.0
    precision, recall = common / len(predicted), common / len(expected)
    return 2 * precision * recall / (precision + recall)


def percentile(values: Sequence[float], share: float) -> float:
    """The value below which this share of the values fall (nearest rank)."""
    ordered = sorted(values)
    return ordered[max(0, math.ceil(share * len(ordered)) - 1)]


def mean(values: Sequence[float]) -> float:
    return sum(values) / len(values)


# Times of a question, in the order they are reached. Shown as p50 / p95, not as a mean.
TIMINGS = ("retrieved_ms", "ranked_ms", "first_token_ms", "total_ms")


def summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Averages over the questions that have each measure, with how many those were."""
    summary: dict[str, Any] = {}
    names = dict.fromkeys(
        name
        for row in rows
        for name, value in row.items()
        if isinstance(value, int | float) and not isinstance(value, bool) and name not in TIMINGS
    )
    for name in names:
        values = [row[name] for row in rows if isinstance(row.get(name), int | float)]
        summary[name] = {"mean": mean(values), "n": len(values)}
    for name in TIMINGS:
        values = [row[name] for row in rows if name in row]
        if values:
            summary[name] = {
                "p50": percentile(values, 0.5),
                "p95": percentile(values, 0.95),
                "n": len(values),
            }
    spent = [row["tokens"] for row in rows if row.get("tokens")]
    for role in sorted({role for tokens in spent for role in tokens}):
        for position, direction in enumerate(("input", "output")):
            summary[f"tokens_{role}_{direction}"] = {
                "mean": mean([tokens.get(role, [0, 0])[position] for tokens in spent]),
                "n": len(spent),
            }
    return summary
