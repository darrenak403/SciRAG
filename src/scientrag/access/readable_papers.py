"""Which papers an account may read. Every path that shows paper content asks here."""

import uuid
from collections.abc import Collection

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from scientrag.db.models import Paper, PaperStatus


async def readable_papers(
    db: AsyncSession, user_id: uuid.UUID, paper_ids: Collection[uuid.UUID], *, ready_only: bool
) -> list[Paper]:
    """Those of paper_ids the account may read: its own papers that are not deleted.

    ready_only keeps only papers that finished processing, which is what can be searched.
    """
    if not paper_ids:
        return []
    query = select(Paper).where(
        Paper.id.in_(paper_ids), Paper.owner_id == user_id, Paper.deleted_at.is_(None)
    )
    if ready_only:
        query = query.where(Paper.status == PaperStatus.READY)
    return list(await db.scalars(query.order_by(Paper.id)))
