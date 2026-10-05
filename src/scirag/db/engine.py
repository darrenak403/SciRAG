"""Async engine and session factory, created on first use."""

from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from scirag.config import get_settings


@lru_cache
def get_engine() -> AsyncEngine:
    return create_async_engine(
        # hide_parameters: a logged database error must not carry emails or other user data.
        get_settings().database_url,
        pool_pre_ping=True,
        hide_parameters=True,
    )


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    # expire_on_commit=False: objects stay readable after commit, so a router can
    # commit and then serialize what it just wrote without another query.
    return async_sessionmaker(get_engine(), expire_on_commit=False)
