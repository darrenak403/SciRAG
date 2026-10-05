"""Chat sessions, their messages, and the passages each answer cites."""

import uuid
from typing import Any

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from scirag.db.base import Base, Entity


class ChatSession(Entity, Base):
    __tablename__ = "chat_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # Null until named: the first question becomes the title.
    title: Mapped[str | None] = mapped_column(Text)
    # What the session searches: {"paper_ids": [...]}, or {"collection_id": "..."} for
    # whatever the collection holds. Each question uses the scope as it is when asked.
    scope: Mapped[dict[str, Any]] = mapped_column(JSONB)


class ChatMessage(Entity, Base):
    __tablename__ = "chat_messages"

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"), index=True
    )
    # user | assistant
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    # Assistant messages only: the trace of the answer, and how its passages were found.
    trace_id: Mapped[str | None] = mapped_column(String(32))
    retrieval: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    # factual | comparison | synthesis: how the answer was produced, and so how it is shown.
    mode: Mapped[str] = mapped_column(String(16), server_default="factual")
    # A comparison's table: {"columns": [...], "rows": [{"paper_id", "paper_title", "cells"}]}.
    table: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class MessageSource(Entity, Base):
    """A passage an answer cites, kept as it was shown.

    chunk_id and paper_id are not foreign keys: the citation stays readable after
    the paper is processed again or deleted.
    """

    __tablename__ = "message_sources"
    __table_args__ = (UniqueConstraint("message_id", "marker", name="uq_message_sources_marker"),)

    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chat_messages.id", ondelete="CASCADE"), index=True
    )
    # "S1", "S2", ...: what the answer text refers to.
    marker: Mapped[str] = mapped_column(String(8))
    chunk_id: Mapped[uuid.UUID]
    paper_id: Mapped[uuid.UUID]
    paper_title: Mapped[str] = mapped_column(Text)
    page: Mapped[int]
    section_path: Mapped[list[str]] = mapped_column(JSONB)
    snippet: Mapped[str] = mapped_column(Text)
