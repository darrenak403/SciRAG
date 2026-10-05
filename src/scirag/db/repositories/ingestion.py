"""What ingestion produced for a paper. Callers check who owns the paper first."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from scirag.db.models import (
    Chunk,
    IngestionRun,
    Paper,
    PaperSection,
    PaperStatus,
    PaperSummary,
)


async def sections(db: AsyncSession, paper_id: uuid.UUID) -> list[PaperSection]:
    rows = await db.scalars(
        select(PaperSection)
        .where(PaperSection.paper_id == paper_id)
        .order_by(PaperSection.position)
    )
    return list(rows)


async def summary(db: AsyncSession, paper_id: uuid.UUID) -> str | None:
    return await db.scalar(select(PaperSummary.summary).where(PaperSummary.paper_id == paper_id))


async def runs(db: AsyncSession, paper_id: uuid.UUID) -> list[IngestionRun]:
    """Every attempt at every step, oldest first."""
    rows = await db.scalars(
        select(IngestionRun)
        .where(IngestionRun.paper_id == paper_id)
        .order_by(IngestionRun.created_at, IngestionRun.id)
    )
    return list(rows)


async def chunks(
    db: AsyncSession, paper_id: uuid.UUID, *, page: int, page_size: int
) -> tuple[list[Chunk], int]:
    total = await db.scalar(
        select(func.count()).select_from(Chunk).where(Chunk.paper_id == paper_id)
    )
    rows = await db.scalars(
        select(Chunk)
        .where(Chunk.paper_id == paper_id)
        .order_by(Chunk.chunk_index)
        .limit(page_size)
        .offset((page - 1) * page_size)
    )
    return list(rows), total or 0


async def papers_needing_reindex(
    db: AsyncSession, owner_id: uuid.UUID, embedding_model: str
) -> list[uuid.UUID]:
    """Ready papers that were indexed with another embedding model."""
    rows = await db.scalars(
        select(Paper.id).where(
            Paper.owner_id == owner_id,
            Paper.deleted_at.is_(None),
            Paper.status == PaperStatus.READY,
            Paper.embedding_model != embedding_model,
        )
    )
    return list(rows)
