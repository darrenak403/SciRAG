import uuid
from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from apps.api.schemas.text import NoNul

ChatTitle = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200), NoNul
]
Question = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000), NoNul
]
PaperIds = Annotated[list[uuid.UUID], Field(max_length=200)]


class ChatCreate(BaseModel):
    title: ChatTitle | None = None
    # The papers the chat searches. May be empty and filled in later.
    paper_ids: PaperIds = []


class ChatUpdate(BaseModel):
    """Fields left out are not changed. paper_ids, when given, replaces the whole scope."""

    title: ChatTitle | None = None
    paper_ids: PaperIds | None = None


class ChatOut(BaseModel):
    id: uuid.UUID
    title: str | None
    paper_ids: list[uuid.UUID]
    # How many papers the chat searches, for the list of recent chats.
    source_count: int
    created_at: datetime
    updated_at: datetime


class QuestionIn(BaseModel):
    content: Question


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
