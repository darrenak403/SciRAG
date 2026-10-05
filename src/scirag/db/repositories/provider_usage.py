import uuid
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from scirag.db.models import ProviderUsage
from scirag.providers.base import Usage


async def add(
    db: AsyncSession, user_id: uuid.UUID, connection_id: uuid.UUID, usage: list[Usage]
) -> None:
    """Adds the calls to today's totals and empties the list."""
    totals: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0])
    for call in usage:
        totals[call.model, call.role][0] += call.input_tokens
        totals[call.model, call.role][1] += call.output_tokens
    usage.clear()
    for (model, role), (input_tokens, output_tokens) in totals.items():
        row = insert(ProviderUsage).values(
            user_id=user_id,
            connection_id=connection_id,
            model=model,
            role=role,
            day=func.current_date(),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        await db.execute(
            row.on_conflict_do_update(
                constraint="uq_provider_usage",
                set_={
                    "input_tokens": ProviderUsage.input_tokens + input_tokens,
                    "output_tokens": ProviderUsage.output_tokens + output_tokens,
                    "updated_at": func.now(),
                },
            )
        )


async def totals(db: AsyncSession, user_id: uuid.UUID, days: int) -> list[dict]:
    """Tokens per connection, model and role over the last `days` days."""
    rows = await db.execute(
        select(
            ProviderUsage.connection_id,
            ProviderUsage.model,
            ProviderUsage.role,
            func.sum(ProviderUsage.input_tokens).label("input_tokens"),
            func.sum(ProviderUsage.output_tokens).label("output_tokens"),
        )
        .where(ProviderUsage.user_id == user_id, ProviderUsage.day > date.today() - timedelta(days))
        .group_by(ProviderUsage.connection_id, ProviderUsage.model, ProviderUsage.role)
        .order_by(ProviderUsage.model, ProviderUsage.role)
    )
    return [dict(row._mapping) for row in rows]
