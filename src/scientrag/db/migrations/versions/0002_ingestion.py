"""Sections, chunks, summaries, ingestion history and provider usage."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def entity_columns() -> list[sa.Column]:
    """Primary key and timestamps shared by every entity table."""
    return [
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def paper_id_column(**kwargs) -> sa.Column:
    return sa.Column(
        "paper_id", sa.Uuid(), sa.ForeignKey("papers.id", ondelete="CASCADE"), **kwargs
    )


def upgrade() -> None:
    op.add_column("papers", sa.Column("embedding_model", sa.String(255), nullable=True))
    op.add_column("papers", sa.Column("index_collection", sa.String(255), nullable=True))
    op.add_column(
        "provider_connections", sa.Column("capabilities", postgresql.JSONB(), nullable=True)
    )

    op.create_table(
        "paper_sections",
        *entity_columns(),
        paper_id_column(nullable=False),
        sa.Column(
            "parent_id",
            sa.Uuid(),
            sa.ForeignKey("paper_sections.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("page", sa.Integer(), nullable=False),
    )
    op.create_index("ix_paper_sections_paper_id", "paper_sections", ["paper_id"])

    op.create_table(
        "chunks",
        *entity_columns(),
        paper_id_column(nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embed_text", sa.Text(), nullable=False),
        sa.Column("section_path", postgresql.JSONB(), nullable=False),
        sa.Column("page_start", sa.Integer(), nullable=False),
        sa.Column("page_end", sa.Integer(), nullable=False),
        sa.Column("bboxes", postgresql.JSONB(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.UniqueConstraint("paper_id", "chunk_index", name="uq_chunks_paper_index"),
    )
    op.create_index("ix_chunks_paper_id", "chunks", ["paper_id"])

    op.create_table(
        "paper_summaries",
        paper_id_column(primary_key=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("model", sa.String(255), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )

    op.create_table(
        "ingestion_runs",
        *entity_columns(),
        paper_id_column(nullable=False),
        sa.Column("step", sa.String(32), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), server_default="running", nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "details", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column("error", sa.Text(), nullable=True),
    )
    op.create_index("ix_ingestion_runs_paper_id", "ingestion_runs", ["paper_id"])

    op.create_table(
        "provider_usage",
        *entity_columns(),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "connection_id",
            sa.Uuid(),
            sa.ForeignKey("provider_connections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("model", sa.String(255), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("input_tokens", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("output_tokens", sa.BigInteger(), server_default="0", nullable=False),
        sa.UniqueConstraint(
            "user_id", "connection_id", "model", "role", "day", name="uq_provider_usage"
        ),
    )
    op.create_index("ix_provider_usage_user_id", "provider_usage", ["user_id"])
    op.create_index("ix_provider_usage_connection_id", "provider_usage", ["connection_id"])


def downgrade() -> None:
    op.drop_table("provider_usage")
    op.drop_table("ingestion_runs")
    op.drop_table("paper_summaries")
    op.drop_table("chunks")
    op.drop_table("paper_sections")
    op.drop_column("provider_connections", "capabilities")
    op.drop_column("papers", "index_collection")
    op.drop_column("papers", "embedding_model")
