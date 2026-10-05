"""Collections of papers, and the kind of each answer."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "collections",
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "owner_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
    )
    op.create_index("ix_collections_owner_id", "collections", ["owner_id"])

    op.create_table(
        "collection_papers",
        sa.Column(
            "collection_id",
            sa.Uuid(),
            sa.ForeignKey("collections.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "paper_id", sa.Uuid(), sa.ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_collection_papers_paper_id", "collection_papers", ["paper_id"])

    # factual | comparison | synthesis: how the answer was produced, and so how it is shown.
    op.add_column(
        "chat_messages",
        sa.Column("mode", sa.String(16), server_default="factual", nullable=False),
    )
    # A comparison's table: {"columns": [...], "rows": [{"paper_id", "paper_title", "cells"}]}.
    op.add_column("chat_messages", sa.Column("table", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    # A chat that searched a collection has no papers left to search.
    op.execute(
        """UPDATE chat_sessions SET scope = '{"paper_ids": []}' WHERE scope ? 'collection_id'"""
    )
    op.drop_column("chat_messages", "table")
    op.drop_column("chat_messages", "mode")
    op.drop_table("collection_papers")
    op.drop_table("collections")
