import uuid
from collections.abc import Sequence

from fastapi import APIRouter, HTTPException, status

from apps.api.deps import CurrentUser, Db
from apps.api.schemas.collections import CollectionCreate, CollectionOut, CollectionUpdate
from scientrag.access.readable_papers import readable_papers
from scientrag.db.models import Collection
from scientrag.db.repositories import collections as collections_repo

router = APIRouter(prefix="/collections", tags=["collections"])


async def _outs(db: Db, user_id: uuid.UUID, found: Sequence[Collection]) -> list[CollectionOut]:
    papers = await collections_repo.paper_ids(db, user_id, [collection.id for collection in found])
    return [
        CollectionOut(
            id=collection.id,
            name=collection.name,
            description=collection.description,
            paper_ids=papers[collection.id],
            created_at=collection.created_at,
            updated_at=collection.updated_at,
        )
        for collection in found
    ]


async def _out(db: Db, collection: Collection) -> CollectionOut:
    await db.refresh(collection)
    return (await _outs(db, collection.owner_id, [collection]))[0]


async def _get_or_404(db: Db, user_id: uuid.UUID, collection_id: uuid.UUID) -> Collection:
    collection = await collections_repo.get(db, user_id, collection_id)
    if collection is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Collection not found")
    return collection


async def _own_papers(db: Db, user_id: uuid.UUID, paper_ids: list[uuid.UUID]) -> list[uuid.UUID]:
    """The ids, once it is sure every one is a paper of the account."""
    wanted = list(dict.fromkeys(paper_ids))
    readable = await readable_papers(db, user_id, wanted, ready_only=False)
    if len(readable) != len(wanted):
        # The same answer for a paper that does not exist and for someone else's.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Paper not found")
    return wanted


@router.post("", status_code=status.HTTP_201_CREATED, response_model=CollectionOut)
async def create_collection(payload: CollectionCreate, user: CurrentUser, db: Db):
    paper_ids = await _own_papers(db, user.id, payload.paper_ids)
    collection = await collections_repo.create(
        db, user.id, name=payload.name, description=payload.description or None
    )
    await collections_repo.add_papers(db, collection, paper_ids)
    await db.commit()
    return await _out(db, collection)


@router.get("", response_model=list[CollectionOut])
async def list_collections(user: CurrentUser, db: Db):
    """The account's collections, the one changed last first."""
    return await _outs(db, user.id, await collections_repo.list_all(db, user.id))


@router.get("/{collection_id}", response_model=CollectionOut)
async def get_collection(collection_id: uuid.UUID, user: CurrentUser, db: Db):
    return await _out(db, await _get_or_404(db, user.id, collection_id))


@router.patch("/{collection_id}", response_model=CollectionOut)
async def update_collection(
    collection_id: uuid.UUID, changes: CollectionUpdate, user: CurrentUser, db: Db
):
    collection = await _get_or_404(db, user.id, collection_id)
    if changes.name is not None:
        collection.name = changes.name
    if "description" in changes.model_fields_set:
        collection.description = changes.description or None
    await db.commit()
    return await _out(db, collection)


@router.delete("/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_collection(collection_id: uuid.UUID, user: CurrentUser, db: Db) -> None:
    """Removes the collection. Its papers stay in the library."""
    await db.delete(await _get_or_404(db, user.id, collection_id))
    await db.commit()


@router.put("/{collection_id}/papers/{paper_id}", status_code=status.HTTP_204_NO_CONTENT)
async def add_paper(collection_id: uuid.UUID, paper_id: uuid.UUID, user: CurrentUser, db: Db):
    collection = await _get_or_404(db, user.id, collection_id)
    await collections_repo.add_papers(db, collection, await _own_papers(db, user.id, [paper_id]))
    await db.commit()


@router.delete("/{collection_id}/papers/{paper_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_paper(collection_id: uuid.UUID, paper_id: uuid.UUID, user: CurrentUser, db: Db):
    collection = await _get_or_404(db, user.id, collection_id)
    await collections_repo.remove_paper(db, collection, paper_id)
    await db.commit()
