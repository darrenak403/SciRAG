"""FastAPI dependencies shared by the routers."""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from scientrag.auth.sessions import COOKIE_NAME, hash_token
from scientrag.db.engine import get_sessionmaker
from scientrag.db.models import User
from scientrag.db.repositories import sessions as sessions_repo
from scientrag.storage import get_storage
from scientrag.storage.base import ObjectStorage


async def get_db() -> AsyncIterator[AsyncSession]:
    """One database session per request. Routers commit explicitly."""
    async with get_sessionmaker()() as session:
        yield session


Db = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user(
    db: Db, token: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None
) -> User:
    user = await sessions_repo.get_user_for_token(db, hash_token(token)) if token else None
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


Storage = Annotated[ObjectStorage, Depends(get_storage)]
