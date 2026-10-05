from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from scirag.db.models import User


async def get_by_email(db: AsyncSession, email: str) -> User | None:
    return await db.scalar(select(User).where(User.email == email))


async def create(db: AsyncSession, email: str, password_hash: str) -> User:
    user = User(email=email, password_hash=password_hash)
    db.add(user)
    await db.flush()
    return user
