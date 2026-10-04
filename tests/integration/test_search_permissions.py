"""The search never returns a passage of a paper the asking account cannot read."""

from collections.abc import AsyncIterator

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from scientrag.access.readable_papers import readable_papers
from scientrag.db.models import ChatSession, PaperStatus
from scientrag.index.qdrant_index import chunks_collection
from scientrag.index.search import search
from tests.rag_factory import (
    CONNECTION,
    DIMENSION,
    EMBEDDING_MODEL,
    ScriptedProvider,
    drop_collections,
    events,
    ready_paper,
    user_id,
    vector,
)

PASSAGES = ["Widgets are sorted by weight before packing.", "Gadgets are counted twice."]
QUESTION = "How are widgets sorted?"
COLLECTION = chunks_collection(EMBEDDING_MODEL, DIMENSION)


@pytest.fixture(scope="module", autouse=True)
async def collections() -> AsyncIterator[None]:
    yield
    await drop_collections()


@pytest.fixture(autouse=True)
def provider(monkeypatch: pytest.MonkeyPatch) -> None:
    ScriptedProvider.reset()
    monkeypatch.setattr("scientrag.providers.resolve.build_provider", ScriptedProvider)


async def find(owner, paper_ids, question: str = QUESTION):
    return await search(
        COLLECTION,
        owner_id=owner,
        paper_ids=paper_ids,
        query_text=question,
        query_vector=vector(question),
        candidates=50,
        limit=30,
    )


@pytest.fixture
async def papers(alice: AsyncClient, bob: AsyncClient, db: AsyncSession):
    """Alice and Bob each own a paper with the same text."""
    alice_id, bob_id = await user_id(alice), await user_id(bob)
    hers = await ready_paper(db, alice_id, "Widget Study", PASSAGES)
    his = await ready_paper(db, bob_id, "Widget Study", PASSAGES)
    return alice_id, hers, bob_id, his


async def test_each_account_finds_only_its_own_paper(papers):
    alice_id, hers, bob_id, his = papers

    assert {hit.paper_id for hit in await find(alice_id, [hers.id])} == {hers.id}
    assert {hit.paper_id for hit in await find(bob_id, [his.id])} == {his.id}


async def test_naming_someone_elses_paper_finds_nothing_of_it(papers):
    alice_id, hers, _, his = papers

    assert {hit.paper_id for hit in await find(alice_id, [hers.id, his.id])} == {hers.id}
    assert await find(alice_id, [his.id]) == []


async def test_no_papers_means_no_search_at_all(papers):
    alice_id, *_ = papers

    assert await find(alice_id, []) == []


async def test_the_best_match_comes_first_and_references_are_left_out(
    alice: AsyncClient, db: AsyncSession
):
    alice_id = await user_id(alice)
    paper = await ready_paper(
        db,
        alice_id,
        "Sorting",
        [
            "Gadgets are counted twice.",
            "Widgets are sorted by weight.",
            "[1] How widgets are sorted. Journal of Widgets.",
        ],
        kinds={2: "reference"},
    )

    hits = await find(alice_id, [paper.id])

    assert len(hits) == 2
    assert hits[0].score >= hits[1].score


async def test_only_ready_live_papers_of_the_account_are_readable(papers, db: AsyncSession):
    alice_id, hers, _, his = papers
    processing = await ready_paper(db, alice_id, "Still processing", PASSAGES)
    processing.status = PaperStatus.PROCESSING
    await db.commit()
    wanted = [hers.id, his.id, processing.id]

    searchable = await readable_papers(db, alice_id, wanted, ready_only=True)
    owned = await readable_papers(db, alice_id, wanted, ready_only=False)

    assert [paper.id for paper in searchable] == [hers.id]
    assert {paper.id for paper in owned} == {hers.id, processing.id}


async def test_a_chat_whose_scope_holds_someone_elses_paper_still_answers_only_from_its_own(
    alice: AsyncClient, papers, db: AsyncSession
):
    """The scope is checked when it is saved; the search does not rely on that."""
    _, hers, _, his = papers
    await alice.post("/settings/providers", json=CONNECTION)
    chat_id = (await alice.post("/chats", json={"paper_ids": [str(hers.id)]})).json()["id"]
    session = await db.get(ChatSession, chat_id)
    session.scope = {"paper_ids": [str(his.id), str(hers.id)]}
    await db.commit()

    response = await alice.post(f"/chats/{chat_id}/messages", json={"content": QUESTION})

    name, sources = events(response.text)[0]
    assert name == "sources"
    assert sources
    assert {source["paper_id"] for source in sources} == {str(hers.id)}
