import uuid
from datetime import date

from sqlalchemy import BigInteger, Date, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from scientrag.db.base import Base, Entity


class ProviderUsage(Entity, Base):
    """Tokens one account used on one model, in one role, on one day."""

    __tablename__ = "provider_usage"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "connection_id", "model", "role", "day", name="uq_provider_usage"
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # Usage is deleted with the connection it was made on.
    connection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("provider_connections.id", ondelete="CASCADE"), index=True
    )
    model: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16))
    day: Mapped[date] = mapped_column(Date)
    input_tokens: Mapped[int] = mapped_column(BigInteger, server_default="0")
    output_tokens: Mapped[int] = mapped_column(BigInteger, server_default="0")
