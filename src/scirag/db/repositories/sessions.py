import uuid
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from scirag.db.models import Session, User


async def create(
    db: AsyncSession, user_id: uuid.UUID, token_hash: str, expires_at: datetime
) -> Session:
    session = Session(user_id=user_id, token_hash=token_hash, expires_at=expires_at)
    db.add(session)
    await db.flush()
    return session


async def get_user_for_token(db: AsyncSession, token_hash: str) -> User | None:
    """The user owning this session, or None if the session is unknown or expired."""
    return await db.scalar(
        select(User)
        .join(Session, Session.user_id == User.id)
        .where(Session.token_hash == token_hash, Session.expires_at > func.now())
    )


async def delete_by_token(db: AsyncSession, token_hash: str) -> None:
    await db.execute(delete(Session).where(Session.token_hash == token_hash))


async def delete_expired(db: AsyncSession, user_id: uuid.UUID) -> None:
    await db.execute(
        delete(Session).where(Session.user_id == user_id, Session.expires_at <= func.now())
    )
