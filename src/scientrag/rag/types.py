"""What answering a question produces, in the order it is produced."""

import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

# answered: the model wrote an answer from the passages found.
# no_papers: nothing in the scope can be searched. no_evidence: the search found nothing.
Outcome = Literal["answered", "no_papers", "no_evidence"]


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


Event = Sources | Delta | Done
