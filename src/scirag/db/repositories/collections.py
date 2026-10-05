"""Collection queries. Every function takes owner_id: a collection is private to its account."""

import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from scirag.db.models import Collection, CollectionPaper, Paper


async def create(
    db: AsyncSession, owner_id: uuid.UUID, *, name: str, description: str | None
) -> Collection:
    collection = Collection(owner_id=owner_id, name=name, description=description)
    db.add(collection)
    await db.flush()
    await db.refresh(collection)
    return collection


async def get(db: AsyncSession, owner_id: uuid.UUID, collection_id: uuid.UUID) -> Collection | None:
    return await db.scalar(
        select(Collection).where(Collection.id == collection_id, Collection.owner_id == owner_id)
    )


async def list_all(db: AsyncSession, owner_id: uuid.UUID) -> list[Collection]:
    """The account's collections, the one changed last first."""
    rows = await db.scalars(
        select(Collection)
        .where(Collection.owner_id == owner_id)
        .order_by(Collection.updated_at.desc(), Collection.id.desc())
    )
    return list(rows)


async def paper_ids(
    db: AsyncSession, owner_id: uuid.UUID, collection_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[uuid.UUID]]:
    """The papers of each collection, in the order they were added. Deleted papers,
    and papers that are not the owner's, are left out."""
    by_collection: dict[uuid.UUID, list[uuid.UUID]] = {cid: [] for cid in collection_ids}
    if collection_ids:
        rows = await db.execute(
            select(CollectionPaper.collection_id, CollectionPaper.paper_id)
            .join(Collection, Collection.id == CollectionPaper.collection_id)
            .join(Paper, Paper.id == CollectionPaper.paper_id)
            .where(
                CollectionPaper.collection_id.in_(collection_ids),
                Collection.owner_id == owner_id,
                Paper.owner_id == owner_id,
                Paper.deleted_at.is_(None),
            )
            .order_by(CollectionPaper.created_at, CollectionPaper.paper_id)
        )
        for collection_id, paper_id in rows:
            by_collection[collection_id].append(paper_id)
    return by_collection


async def add_papers(db: AsyncSession, collection: Collection, ids: list[uuid.UUID]) -> None:
    """Puts the papers in the collection. One that is already in it stays as it is.

    The caller has checked that the papers are the owner's.
    """
    if ids:
        await db.execute(
            insert(CollectionPaper)
            .values([{"collection_id": collection.id, "paper_id": paper_id} for paper_id in ids])
            .on_conflict_do_nothing()
        )
        await touch(db, collection)


async def remove_paper(db: AsyncSession, collection: Collection, paper_id: uuid.UUID) -> None:
    await db.execute(
        delete(CollectionPaper).where(
            CollectionPaper.collection_id == collection.id, CollectionPaper.paper_id == paper_id
        )
    )
    await touch(db, collection)


async def touch(db: AsyncSession, collection: Collection) -> None:
    """Moves the collection to the top of the list."""
    collection.updated_at = func.now()
    await db.flush()
