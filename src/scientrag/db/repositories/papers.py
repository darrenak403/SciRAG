"""Paper queries. Every function takes owner_id: there is no lookup by paper id alone."""

import uuid
from collections.abc import Sequence
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from scientrag.db.models import Author, Collection, CollectionPaper, Paper, PaperAuthor

SortField = Literal["added", "year", "title", "author"]
SortOrder = Literal["asc", "desc"]


def _live(owner_id: uuid.UUID):
    return (Paper.owner_id == owner_id, Paper.deleted_at.is_(None))


async def get(
    db: AsyncSession, owner_id: uuid.UUID, paper_id: uuid.UUID, *, for_update: bool = False
) -> Paper | None:
    """for_update locks the row until commit, so two edits of one paper run one after the other."""
    query = select(Paper).where(Paper.id == paper_id, *_live(owner_id))
    if for_update:
        query = query.with_for_update()
    return await db.scalar(query)


async def get_by_sha256(db: AsyncSession, owner_id: uuid.UUID, file_sha256: str) -> Paper | None:
    return await db.scalar(select(Paper).where(Paper.file_sha256 == file_sha256, *_live(owner_id)))


async def create(
    db: AsyncSession,
    *,
    paper_id: uuid.UUID,
    owner_id: uuid.UUID,
    title: str,
    original_filename: str,
    file_sha256: str,
    storage_key: str,
) -> Paper:
    paper = Paper(
        id=paper_id,
        owner_id=owner_id,
        title=title,
        original_filename=original_filename,
        file_sha256=file_sha256,
        storage_key=storage_key,
    )
    db.add(paper)
    await db.flush()
    await db.refresh(paper)
    return paper


async def list_papers(
    db: AsyncSession,
    owner_id: uuid.UUID,
    *,
    q: str | None = None,
    statuses: Sequence[str] | None = None,
    year: int | None = None,
    author: str | None = None,
    collection_id: uuid.UUID | None = None,
    sort: SortField = "added",
    order: SortOrder = "desc",
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Paper], int]:
    """One page of the owner's papers and the total number matching the filters."""
    conditions = [*_live(owner_id)]
    if q:
        conditions.append(Paper.title.icontains(q, autoescape=True))
    if statuses:
        conditions.append(Paper.status.in_(statuses))
    if year is not None:
        conditions.append(Paper.year == year)
    if author:
        conditions.append(
            select(PaperAuthor.paper_id)
            .join(Author, Author.id == PaperAuthor.author_id)
            .where(
                PaperAuthor.paper_id == Paper.id,
                Author.name.icontains(author, autoescape=True),
            )
            .exists()
        )
    if collection_id is not None:
        conditions.append(
            select(CollectionPaper.paper_id)
            .join(Collection, Collection.id == CollectionPaper.collection_id)
            .where(
                CollectionPaper.paper_id == Paper.id,
                CollectionPaper.collection_id == collection_id,
                # Someone else's collection filters to nothing.
                Collection.owner_id == owner_id,
            )
            .exists()
        )

    first_author = (
        select(Author.name)
        .join(PaperAuthor, PaperAuthor.author_id == Author.id)
        .where(PaperAuthor.paper_id == Paper.id, PaperAuthor.position == 0)
        .scalar_subquery()
    )
    sort_column = {
        "added": Paper.created_at,
        "year": Paper.year,
        "title": func.lower(Paper.title),
        "author": func.lower(first_author),
    }[sort]
    direction = sort_column.asc() if order == "asc" else sort_column.desc()

    total = await db.scalar(select(func.count()).select_from(Paper).where(*conditions))
    rows = await db.scalars(
        select(Paper)
        .where(*conditions)
        # Papers missing the sort value go last; id breaks ties so pages are stable.
        .order_by(direction.nulls_last(), Paper.id.desc())
        .limit(page_size)
        .offset((page - 1) * page_size)
    )
    return list(rows), total or 0


async def replace_authors(db: AsyncSession, paper: Paper, names: list[str]) -> None:
    """Sets the paper's authors to exactly these names, in this order."""
    cleaned = list(dict.fromkeys(name.strip() for name in names if name.strip()))

    if cleaned:
        # Authors are shared between papers and users; create the missing ones
        # without failing when another request creates the same name first.
        await db.execute(
            insert(Author).values([{"name": name} for name in cleaned]).on_conflict_do_nothing()
        )
    ids_by_name = {
        name: author_id
        for author_id, name in await db.execute(
            select(Author.id, Author.name).where(Author.name.in_(cleaned))
        )
    }

    paper.author_links.clear()
    await db.flush()
    for position, name in enumerate(cleaned):
        paper.author_links.append(
            PaperAuthor(paper_id=paper.id, author_id=ids_by_name[name], position=position)
        )
    await db.flush()
    await db.refresh(paper, ["author_links"])
