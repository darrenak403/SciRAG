import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from apps.api.schemas.text import NoNul

CollectionName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200), NoNul
]
Description = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000), NoNul]


class CollectionCreate(BaseModel):
    name: CollectionName
    description: Description | None = None
    # Papers to start the collection with.
    paper_ids: Annotated[list[uuid.UUID], Field(max_length=200)] = []


class CollectionUpdate(BaseModel):
    """Fields left out are not changed."""

    name: CollectionName | None = None
    description: Description | None = None


class CollectionOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    # The papers in it that still exist, in the order they were added.
    paper_ids: list[uuid.UUID]
    created_at: datetime
    updated_at: datetime
