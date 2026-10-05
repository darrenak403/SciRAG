"""Searching each paper by itself, and searching for whole papers."""

from collections.abc import AsyncIterator

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from scirag.index.qdrant_index import chunks_collection
from scirag.index.search import search, search_grouped, search_papers
from tests.rag_factory import (
    DIMENSION,
    EMBEDDING_MODEL,
    drop_collections,
    ready_paper,
    user_id,
    vector,
)

COLLECTION = chunks_collection(EMBEDDING_MODEL, DIMENSION)
QUESTION = "How are widgets sorted?"
# Says a lot about the question, in many passages.
LOUD = [f"Widgets are sorted by weight, widgets sorted in batch {n}." for n in range(8)]
QUIET = [
    "Gadgets are counted twice a day.",
    "Widgets are mentioned once here.",
    "Lunch is at noon.",
]


@pytest.fixture(scope="module", autouse=True)
async def index() -> AsyncIterator[None]:
    yield
    await drop_collections()


def query(**changes) -> dict:
    return {"query_text": QUESTION, "query_vector": vector(QUESTION), **changes}


@pytest.fixture
async def papers(alice: AsyncClient, db: AsyncSession):
    owner = await user_id(alice)
    loud = await ready_paper(db, owner, "Widget Sorting Study", LOUD)
    quiet = await ready_paper(db, owner, "Factory Notes", QUIET)
    other = await ready_paper(db, owner, "Sprocket Study", ["Sprockets spin clockwise."])
    return owner, loud, quiet, other


async def test_every_paper_brings_its_own_passages_and_no_more_than_asked(papers):
    owner, loud, quiet, other = papers
    ids = [loud.id, quiet.id, other.id]

    groups = await search_grouped(
        COLLECTION, owner_id=owner, paper_ids=ids, candidates=50, group_size=2, **query()
    )

    assert set(groups) == set(ids)
    assert [len(groups[paper_id]) for paper_id in ids] == [2, 2, 1]
    assert all(hit.paper_id == paper_id for paper_id, hits in groups.items() for hit in hits)
    # Searched together, the paper that says most takes every place.
    together = await search(
        COLLECTION, owner_id=owner, paper_ids=ids, candidates=50, limit=6, **query()
    )
    assert {hit.paper_id for hit in together} == {loud.id}


async def test_searching_each_paper_never_reaches_another_account(
    papers, bob: AsyncClient, db: AsyncSession
):
    owner, loud, _, _ = papers
    bob_id = await user_id(bob)
    his = await ready_paper(db, bob_id, "Widget Sorting Study", LOUD)

    groups = await search_grouped(
        COLLECTION,
        owner_id=owner,
        paper_ids=[loud.id, his.id],
        candidates=50,
        group_size=3,
        **query(),
    )
    found = await search_papers(
        COLLECTION, owner_id=owner, paper_ids=[loud.id, his.id], limit=5, **query()
    )

    assert set(groups) == {loud.id}
    assert found == [loud.id]
    assert (
        await search_grouped(
            COLLECTION, owner_id=owner, paper_ids=[], candidates=50, group_size=3, **query()
        )
        == {}
    )


async def test_whole_papers_are_ranked_by_how_close_they_are_to_the_question(papers):
    owner, loud, quiet, other = papers
    ids = [other.id, quiet.id, loud.id]

    ranked = await search_papers(COLLECTION, owner_id=owner, paper_ids=ids, limit=2, **query())

    assert ranked[0] == loud.id
    assert len(ranked) == 2
