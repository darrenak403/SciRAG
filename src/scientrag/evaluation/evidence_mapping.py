"""Finds which chunks hold an evidence passage.

Datasets mark evidence as text: a paragraph, or a quote. Chunks are cut by other
rules, so a passage may sit inside one chunk or be split over two. A chunk holds
the passage when it contains enough of the passage's word sequences.
"""

import re
from collections.abc import Hashable, Sequence

# Word sequences of this length are compared, so shared common words do not count as a match.
SHINGLE_WORDS = 4
# A passage cut in two leaves just under half of its sequences in each chunk.
MIN_COVERAGE = 0.4

_WORD = re.compile(r"[a-z0-9]+")


def _words(text: str) -> list[str]:
    return _WORD.findall(text.lower())


def _shingles(words: list[str], size: int) -> set[tuple[str, ...]]:
    return {tuple(words[start : start + size]) for start in range(len(words) - size + 1)}


def coverage(evidence: str, chunk_text: str) -> float:
    """The share of the evidence's word sequences that the chunk contains."""
    words = _words(evidence)
    # A quote shorter than a sequence is looked for whole.
    size = min(SHINGLE_WORDS, len(words))
    if not size:
        return 0.0
    wanted = _shingles(words, size)
    return len(wanted & _shingles(_words(chunk_text), size)) / len(wanted)


def covering_chunks[T: Hashable](evidence: str, chunks: Sequence[tuple[T, str]]) -> set[T]:
    """The chunks, given as (id, text), that hold the evidence. Empty when none does."""
    return {chunk_id for chunk_id, text in chunks if coverage(evidence, text) >= MIN_COVERAGE}
