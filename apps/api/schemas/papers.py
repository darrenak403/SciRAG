import uuid
from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from apps.api.schemas.text import NoNul, Text

Title = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000), NoNul
]
# Blank names are allowed here and dropped when the list is saved.
AuthorName = Annotated[str, StringConstraints(strip_whitespace=True, max_length=255), NoNul]


class PaperOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    authors: list[str]
    year: int | None
    doi: str | None
    page_count: int | None
    original_filename: str
    status: str
    processing_step: str | None
    error_code: str | None
    error: str | None
    warnings: list[Any]
    # The paper was indexed with another embedding model than the account uses now.
    # It is left out of search until it is indexed again.
    needs_reindex: bool = False
    created_at: datetime
    updated_at: datetime


class PaperDetail(PaperOut):
    # Written by the model while the paper was processed. None until that step is done.
    summary: str | None = None


class PaperPage(BaseModel):
    items: list[PaperOut]
    total: int
    page: int
    page_size: int


class PaperUpdate(BaseModel):
    """Fields left out are not changed. authors, when given, replaces the whole list."""

    title: Title | None = None
    authors: list[AuthorName] | None = Field(default=None, max_length=200)
    year: int | None = Field(default=None, ge=1000, le=2100)
    doi: Text | None = Field(default=None, max_length=255)


class SectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    parent_id: uuid.UUID | None
    position: int
    level: int
    title: str
    page: int


class IngestionRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    step: str
    attempt: int
    status: str
    started_at: datetime = Field(validation_alias="created_at")
    finished_at: datetime | None
    details: dict[str, Any]
    error: str | None


class ChunkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    chunk_index: int
    kind: str
    text: str
    section_path: list[str]
    page_start: int
    page_end: int
    bboxes: list[dict[str, Any]]
    token_count: int


class ChunkPage(BaseModel):
    items: list[ChunkOut]
    total: int
    page: int
    page_size: int


class ReindexOut(BaseModel):
    queued: int
