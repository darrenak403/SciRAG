"""Provider connection queries. Every function takes user_id: connections are private."""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from scirag.db.models import ProviderConnection


async def list_for_user(db: AsyncSession, user_id: uuid.UUID) -> list[ProviderConnection]:
    rows = await db.scalars(
        select(ProviderConnection)
        .where(ProviderConnection.user_id == user_id)
        .order_by(ProviderConnection.created_at)
    )
    return list(rows)


async def get(
    db: AsyncSession, user_id: uuid.UUID, connection_id: uuid.UUID
) -> ProviderConnection | None:
    return await db.scalar(
        select(ProviderConnection).where(
            ProviderConnection.id == connection_id, ProviderConnection.user_id == user_id
        )
    )


async def create(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    kind: str,
    label: str,
    config: dict[str, Any],
    secret_encrypted: str,
    secret_last4: str,
) -> ProviderConnection:
    connection = ProviderConnection(
        user_id=user_id,
        kind=kind,
        label=label,
        config=config,
        secret_encrypted=secret_encrypted,
        secret_last4=secret_last4,
    )
    db.add(connection)
    await db.flush()
    await db.refresh(connection)
    return connection
