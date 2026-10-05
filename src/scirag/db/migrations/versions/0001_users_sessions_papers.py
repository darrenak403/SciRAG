"""Users, sessions, provider connections, papers and authors."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
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


def upgrade() -> None:
    op.create_table(
        "users",
        *entity_columns(),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("active_connection_id", sa.Uuid(), nullable=True),
        sa.UniqueConstraint("email"),
    )

    op.create_table(
        "provider_connections",
        *entity_columns(),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("label", sa.String(100), nullable=False),
        sa.Column(
            "config", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column("secret_encrypted", sa.Text(), nullable=False),
        sa.Column("secret_last4", sa.String(4), nullable=False),
    )
    op.create_index("ix_provider_connections_user_id", "provider_connections", ["user_id"])
    # users and provider_connections reference each other; this side goes in last.
    op.create_foreign_key(
        "fk_users_active_connection_id",
        "users",
        "provider_connections",
        ["active_connection_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "sessions",
        *entity_columns(),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])

    op.create_table(
        "papers",
        *entity_columns(),
        sa.Column(
            "owner_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("doi", sa.String(255), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("file_sha256", sa.String(64), nullable=False),
        sa.Column("storage_key", sa.String(255), nullable=False),
        sa.Column("status", sa.String(16), server_default="UPLOADED", nullable=False),
        sa.Column("processing_step", sa.String(32), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "warnings", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_papers_owner_id", "papers", ["owner_id"])
    op.create_index(
        "uq_papers_owner_sha_live",
        "papers",
        ["owner_id", "file_sha256"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "authors",
        *entity_columns(),
        sa.Column("name", sa.String(255), nullable=False),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "paper_authors",
        sa.Column(
            "paper_id", sa.Uuid(), sa.ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column(
            "author_id",
            sa.Uuid(),
            sa.ForeignKey("authors.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.UniqueConstraint("paper_id", "position", name="uq_paper_authors_position"),
    )
    op.create_index("ix_paper_authors_author_id", "paper_authors", ["author_id"])


def downgrade() -> None:
    op.drop_table("paper_authors")
    op.drop_table("authors")
    op.drop_table("papers")
    op.drop_table("sessions")
    op.drop_constraint("fk_users_active_connection_id", "users", type_="foreignkey")
    op.drop_table("provider_connections")
    op.drop_table("users")
