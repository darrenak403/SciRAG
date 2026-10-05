"""What ingestion produces for a paper: its sections, chunks, summary and step history."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from scirag.db.base import Base, Entity


class PaperSection(Entity, Base):
    """A heading of the paper. Together they form the outline shown in the reader."""

    __tablename__ = "paper_sections"

    paper_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"), index=True
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("paper_sections.id", ondelete="CASCADE")
    )
    # Order of appearance in the paper.
    position: Mapped[int]
    level: Mapped[int]
    title: Mapped[str] = mapped_column(Text)
    page: Mapped[int]


class Chunk(Entity, Base):
    """A passage of a paper. Its id is also the id of its point in Qdrant."""

    __tablename__ = "chunks"
    __table_args__ = (UniqueConstraint("paper_id", "chunk_index", name="uq_chunks_paper_index"),)

    paper_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"), index=True
    )
    chunk_index: Mapped[int]
    # text | table | caption | formula | reference
    kind: Mapped[str] = mapped_column(String(16))
    # What is shown and cited.
    text: Mapped[str] = mapped_column(Text)
    # What is embedded and searched: the text with the paper title and section path in front.
    embed_text: Mapped[str] = mapped_column(Text)
    section_path: Mapped[list[str]] = mapped_column(JSONB)
    page_start: Mapped[int]
    page_end: Mapped[int]
    # [{"page": 3, "bbox": [left, top, right, bottom]}], fractions of the page, origin top-left.
    bboxes: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    token_count: Mapped[int]


class PaperSummary(Base):
    __tablename__ = "paper_summaries"

    paper_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True
    )
    summary: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IngestionRun(Entity, Base):
    """One attempt at one ingestion step. created_at is when the attempt started."""

    __tablename__ = "ingestion_runs"

    paper_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"), index=True
    )
    step: Mapped[str] = mapped_column(String(32))
    attempt: Mapped[int]
    # running | done | failed
    status: Mapped[str] = mapped_column(String(16), server_default="running")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # A few numbers about what the step did: pages, chunks, points.
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    error: Mapped[str | None] = mapped_column(Text)
