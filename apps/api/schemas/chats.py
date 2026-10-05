import uuid
from datetime import datetime
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from apps.api.schemas.text import NoNul

ChatTitle = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200), NoNul
]
Question = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000), NoNul
]
PaperIds = Annotated[list[uuid.UUID], Field(max_length=200)]


class _OneScope(BaseModel):
    @model_validator(mode="after")
    def one_scope(self) -> Self:
        if self.paper_ids and self.collection_id is not None:
            raise ValueError("give paper_ids or collection_id, not both")
        return self


class ChatCreate(_OneScope):
    title: ChatTitle | None = None
    # The papers the chat searches. May be empty and filled in later.
    paper_ids: PaperIds = []
    # Instead of paper_ids: the chat searches whatever this collection holds.
    collection_id: uuid.UUID | None = None


class ChatUpdate(_OneScope):
    """Fields left out are not changed. paper_ids or collection_id, when given,
    replaces the whole scope."""

    title: ChatTitle | None = None
    paper_ids: PaperIds | None = None
    collection_id: uuid.UUID | None = None


class ChatOut(BaseModel):
    id: uuid.UUID
    title: str | None
    paper_ids: list[uuid.UUID]
    # Set when the chat searches a collection; paper_ids is then what the collection holds now.
    collection_id: uuid.UUID | None
    # How many papers the chat searches, for the list of recent chats.
    source_count: int
    created_at: datetime
    updated_at: datetime


class QuestionIn(BaseModel):
    content: Question
    # auto: the kind of question is worked out from the question. The others say it outright.
    mode: Literal["auto", "factual", "comparison", "synthesis"] = "auto"


class SourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    marker: str
    chunk_id: uuid.UUID
    paper_id: uuid.UUID
    paper_title: str
    page: int
    section_path: list[str]
    snippet: str


class MessageOut(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    # The passages an assistant message cites. Empty for user messages.
    citations: list[SourceOut]
    # How an assistant message was produced: factual, comparison or synthesis.
    mode: str
    # A comparison's table; its cells cite passages by the markers in citations.
    table: dict[str, Any] | None
    notice: str | None
    created_at: datetime


class RetrievalOut(BaseModel):
    message_id: uuid.UUID
    trace_id: str | None
    retrieval: dict[str, Any] | None


class ChunkDetail(BaseModel):
    """A passage and where it sits on the page, for highlighting it in the reader."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    paper_id: uuid.UUID
    kind: str
    text: str
    section_path: list[str]
    page_start: int
    page_end: int
    bboxes: list[dict[str, Any]]
