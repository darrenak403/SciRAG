import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from scientrag.db.base import Base, Entity


class Author(Entity, Base):
    __tablename__ = "authors"

    name: Mapped[str] = mapped_column(String(255), unique=True)


class PaperAuthor(Base):
    """Links a paper to an author and keeps the author order."""

    __tablename__ = "paper_authors"
    __table_args__ = (UniqueConstraint("paper_id", "position", name="uq_paper_authors_position"),)

    paper_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True
    )
    author_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("authors.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    position: Mapped[int]

    author: Mapped[Author] = relationship(lazy="joined")
