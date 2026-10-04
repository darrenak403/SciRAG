import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from scientrag.db.base import Base, Entity


class User(Entity, Base):
    __tablename__ = "users"

    # Stored lowercased; uniqueness is therefore case-insensitive.
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    # The one provider connection this account uses for every model call:
    # answering, fast tasks and embedding. users and
    # provider_connections reference each other, so this constraint is added
    # after both tables exist (use_alter).
    active_connection_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "provider_connections.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_users_active_connection_id",
        )
    )
