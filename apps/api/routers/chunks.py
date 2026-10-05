import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from apps.api.deps import CurrentUser, Db
from apps.api.schemas.chats import ChunkDetail
from scirag.db.models import Chunk, Paper

router = APIRouter(prefix="/chunks", tags=["chunks"])


@router.get("/{chunk_id}", response_model=ChunkDetail)
async def get_chunk(chunk_id: uuid.UUID, user: CurrentUser, db: Db):
    """The passage behind a citation: its text, pages and boxes on the page."""
    chunk = await db.scalar(
        select(Chunk)
        .join(Paper, Paper.id == Chunk.paper_id)
        .where(Chunk.id == chunk_id, Paper.owner_id == user.id, Paper.deleted_at.is_(None))
    )
    if chunk is None:
        # Also the answer for a passage of someone else's paper.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Passage not found")
    return chunk
