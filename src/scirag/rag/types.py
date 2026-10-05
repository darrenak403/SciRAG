"""What answering a question produces, in the order it is produced."""

import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

# answered: the model wrote an answer from the passages found.
# no_papers: nothing in the scope can be searched. no_evidence: the search found nothing.
Outcome = Literal["answered", "no_papers", "no_evidence"]
# factual: one answer from the best passages. comparison: a table with a row per paper.
# synthesis: findings gathered across many papers, written up in fixed parts.
Mode = Literal["factual", "comparison", "synthesis"]


@dataclass(frozen=True)
class Source:
    """A passage given to the model, under the marker the answer cites it by."""

    marker: str
    chunk_id: uuid.UUID
    paper_id: uuid.UUID
    paper_title: str
    page: int
    section_path: list[str]
    snippet: str


@dataclass(frozen=True)
class Sources:
    """First event: the passages the answer may cite."""

    sources: list[Source]
    # How they were found so far; the same dict the last event carries, not yet complete.
    retrieval: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Status:
    """What is being done before the answer starts, for answers that take a while.

    stage is one of: selecting, gathering, comparing, writing. done and total
    count the passages read so far, in the stage that reads them one by one.
    """

    stage: str
    done: int | None = None
    total: int | None = None
    # The kind of answer being made, which decides the stages still to come.
    mode: Mode | None = None


@dataclass(frozen=True)
class Table:
    """A comparison: {"columns": [...], "rows": [{"paper_id", "paper_title", "cells"}]},
    each cell {"text", "markers"}. Every paper compared has exactly one row."""

    table: dict[str, Any]


@dataclass(frozen=True)
class Delta:
    """A piece of the answer as the model writes it. Not yet checked."""

    text: str


@dataclass(frozen=True)
class Done:
    """Last event: the answer with invented markers removed, and the markers it uses."""

    text: str
    citations: list[Source]
    outcome: Outcome
    trace_id: str
    # How the passages were found, for the advanced view and for evaluation.
    retrieval: dict[str, Any] = field(default_factory=dict)
    mode: Mode = "factual"
    table: dict[str, Any] | None = None
    # Something the reader should know about how the answer was made, in plain words.
    notice: str | None = None


Event = Sources | Status | Table | Delta | Done
