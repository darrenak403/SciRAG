import uuid
from typing import Any

from sqlalchemy import ForeignKey, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from scientrag.db.base import Base, Entity


class ProviderConnection(Entity, Base):
    """One account's credentials for one model provider."""

    __tablename__ = "provider_connections"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # gemini | bedrock | openai_compatible
    kind: Mapped[str] = mapped_column(String(32))
    label: Mapped[str] = mapped_column(String(100))
    # Non-secret settings: region, base URL, chosen model per role.
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    # Fernet token of a JSON object holding the credentials. Never leaves the server.
    secret_encrypted: Mapped[str] = mapped_column(Text)
    # Last four characters of the key, so the UI can tell connections apart.
    secret_last4: Mapped[str] = mapped_column(String(4))
    # Result of the last capability test; null until the connection has been tested.
    capabilities: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
