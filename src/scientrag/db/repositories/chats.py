"""Chat queries. Chats are private to their account: functions that take no user_id
expect ids the caller already looked up for that account."""

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from scientrag.db.models import ChatMessage, ChatSession, MessageSource


async def create(
    db: AsyncSession, user_id: uuid.UUID, *, title: str | None, scope: dict[str, Any]
) -> ChatSession:
    session = ChatSession(user_id=user_id, title=title, scope=scope)
    db.add(session)
    await db.flush()
    await db.refresh(session)
    return session


def scope_of(paper_ids: list[uuid.UUID]) -> dict[str, Any]:
    return {"paper_ids": [str(paper_id) for paper_id in dict.fromkeys(paper_ids)]}


def collection_scope(collection_id: uuid.UUID) -> dict[str, Any]:
    return {"collection_id": str(collection_id)}


def paper_ids_of(session: ChatSession) -> list[uuid.UUID]:
    """The papers a chat names one by one. Empty for a chat that searches a collection."""
    return [uuid.UUID(paper_id) for paper_id in session.scope.get("paper_ids", [])]


def collection_id_of(session: ChatSession) -> uuid.UUID | None:
    collection_id = session.scope.get("collection_id")
    return uuid.UUID(collection_id) if collection_id else None


async def get(
    db: AsyncSession, user_id: uuid.UUID, session_id: uuid.UUID, *, for_update: bool = False
) -> ChatSession | None:
    query = select(ChatSession).where(ChatSession.id == session_id, ChatSession.user_id == user_id)
    if for_update:
        query = query.with_for_update()
    return await db.scalar(query)


async def list_recent(
    db: AsyncSession, user_id: uuid.UUID, *, limit: int, collection_id: uuid.UUID | None = None
) -> list[ChatSession]:
    """The account's chats, the one used last first. collection_id keeps only the
    chats that search that collection."""
    conditions = [ChatSession.user_id == user_id]
    if collection_id is not None:
        conditions.append(ChatSession.scope["collection_id"].astext == str(collection_id))
    rows = await db.scalars(
        select(ChatSession)
        .where(*conditions)
        .order_by(ChatSession.updated_at.desc(), ChatSession.id.desc())
        .limit(limit)
    )
    return list(rows)


async def messages(
    db: AsyncSession, session_id: uuid.UUID, *, last: int | None = None
) -> list[ChatMessage]:
    """The messages of a chat, oldest first. last keeps only that many of the newest."""
    # Ids are UUIDv7: they sort in the order the rows were inserted.
    query = select(ChatMessage).where(ChatMessage.session_id == session_id)
    if last is None:
        return list(await db.scalars(query.order_by(ChatMessage.id)))
    newest = await db.scalars(query.order_by(ChatMessage.id.desc()).limit(last))
    return list(newest)[::-1]


async def sources(
    db: AsyncSession, message_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[MessageSource]]:
    """The cited passages of each message, in the order they are first cited."""
    by_message: dict[uuid.UUID, list[MessageSource]] = {}
    if message_ids:
        rows = await db.scalars(
            select(MessageSource)
            .where(MessageSource.message_id.in_(message_ids))
            .order_by(MessageSource.id)
        )
        for row in rows:
            by_message.setdefault(row.message_id, []).append(row)
    return by_message


async def get_message(
    db: AsyncSession, user_id: uuid.UUID, message_id: uuid.UUID
) -> ChatMessage | None:
    return await db.scalar(
        select(ChatMessage)
        .join(ChatSession, ChatSession.id == ChatMessage.session_id)
        .where(ChatMessage.id == message_id, ChatSession.user_id == user_id)
    )


async def touch(db: AsyncSession, session: ChatSession) -> None:
    """Moves the chat to the top of the recent list."""
    session.updated_at = func.now()
    await db.flush()
