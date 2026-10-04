import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from scientrag.db.base import Base, Entity
from scientrag.db.models.author import PaperAuthor


class PaperStatus(enum.StrEnum):
    UPLOADED = "UPLOADED"
    PROCESSING = "PROCESSING"
    READY = "READY"
    FAILED = "FAILED"


class Paper(Entity, Base):
    __tablename__ = "papers"
    __table_args__ = (
        # One live copy of a file per owner. A deleted paper does not block re-upload.
        Index(
            "uq_papers_owner_sha_live",
            "owner_id",
            "file_sha256",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(Text)
    year: Mapped[int | None]
    doi: Mapped[str | None] = mapped_column(String(255))
    page_count: Mapped[int | None]
    # What the user's file was called. Display only: never used to build a path.
    original_filename: Mapped[str] = mapped_column(String(255))
    file_sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16), server_default=PaperStatus.UPLOADED.value)
    # Which ingestion step is running while status is PROCESSING.
    processing_step: Mapped[str | None] = mapped_column(String(32))
    error_code: Mapped[str | None] = mapped_column(String(64))
    error: Mapped[str | None] = mapped_column(Text)
    warnings: Mapped[list[Any]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The embedding model the paper's chunks were indexed with, and the Qdrant
    # collection they are in. Both are null until the paper has been indexed.
    embedding_model: Mapped[str | None] = mapped_column(String(255))
    index_collection: Mapped[str | None] = mapped_column(String(255))

    author_links: Mapped[list[PaperAuthor]] = relationship(
        order_by=PaperAuthor.position, cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def authors(self) -> list[str]:
        """Author names in the order they appear on the paper."""
        return [link.author.name for link in self.author_links]
