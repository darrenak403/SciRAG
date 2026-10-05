"""Collections through the API: private to their account, and usable as the scope of a chat."""

from collections.abc import AsyncIterator

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.rag_factory import (
    CONNECTION,
    ScriptedProvider,
    drop_collections,
    events,
    ready_paper,
    user_id,
)


@pytest.fixture(scope="module", autouse=True)
async def index() -> AsyncIterator[None]:
    yield
    await drop_collections()


@pytest.fixture(autouse=True)
def provider(monkeypatch: pytest.MonkeyPatch) -> None:
    ScriptedProvider.reset()
    monkeypatch.setattr("scientrag.providers.resolve.build_provider", ScriptedProvider)


@pytest.fixture
async def papers(alice: AsyncClient, db: AsyncSession):
    owner = await user_id(alice)
    return [
        await ready_paper(db, owner, "Widget Study", ["Widgets are sorted by weight."]),
        await ready_paper(db, owner, "Gadget Study", ["Gadgets are sorted by colour."]),
    ]


async def create(client: AsyncClient, name: str = "Sorting", *papers) -> dict:
    payload = {"name": name, "paper_ids": [str(paper.id) for paper in papers]}
    response = await client.post("/collections", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


async def test_a_collection_is_created_changed_and_deleted(alice: AsyncClient, papers):
    widget, gadget = papers
    made = await create(alice, "Sorting", widget)
    assert (made["name"], made["description"], made["paper_ids"]) == (
        "Sorting",
        None,
        [str(widget.id)],
    )
    url = f"/collections/{made['id']}"

    changed = await alice.patch(url, json={"name": "Sorting methods", "description": "How"})
    assert (changed.json()["name"], changed.json()["description"]) == ("Sorting methods", "How")
    assert (await alice.put(f"{url}/papers/{gadget.id}")).status_code == 204
    # Adding a paper twice is not an error and does not list it twice.
    assert (await alice.put(f"{url}/papers/{gadget.id}")).status_code == 204
    assert (await alice.get(url)).json()["paper_ids"] == [str(widget.id), str(gadget.id)]
    assert (await alice.delete(f"{url}/papers/{widget.id}")).status_code == 204
    assert [item["paper_ids"] for item in (await alice.get("/collections")).json()] == [
        [str(gadget.id)]
    ]

    assert (await alice.delete(url)).status_code == 204
    assert (await alice.get(url)).status_code == 404
    # The papers themselves are untouched.
    assert (await alice.get("/papers")).json()["total"] == 2


async def test_a_collection_cannot_be_seen_or_changed_by_another_account(
    alice: AsyncClient, bob: AsyncClient, papers, db: AsyncSession
):
    made = await create(alice, "Sorting", papers[0])
    url = f"/collections/{made['id']}"
    his = await ready_paper(db, await user_id(bob), "Bob's Study", ["Sprockets spin."])

    assert (await bob.get("/collections")).json() == []
    assert (await bob.get(url)).status_code == 404
    assert (await bob.patch(url, json={"name": "Mine now"})).status_code == 404
    assert (await bob.delete(url)).status_code == 404
    assert (await bob.put(f"{url}/papers/{his.id}")).status_code == 404
    assert (await bob.get("/papers", params={"collection_id": made["id"]})).json()["total"] == 0
    assert (await bob.post("/chats", json={"collection_id": made["id"]})).status_code == 422


async def test_a_paper_of_another_account_cannot_be_put_in_a_collection(
    alice: AsyncClient, bob: AsyncClient, papers, db: AsyncSession
):
    his = await ready_paper(db, await user_id(bob), "Bob's Study", ["Sprockets spin."])
    made = await create(alice)

    assert (await alice.put(f"/collections/{made['id']}/papers/{his.id}")).status_code == 404
    refused = await alice.post("/collections", json={"name": "Two", "paper_ids": [str(his.id)]})
    assert refused.status_code == 404
    assert len((await alice.get("/collections")).json()) == 1


async def test_the_library_can_be_filtered_by_collection_and_drops_deleted_papers(
    alice: AsyncClient, papers
):
    widget, gadget = papers
    made = await create(alice, "Sorting", widget, gadget)
    listed = await alice.get("/papers", params={"collection_id": made["id"]})
    assert listed.json()["total"] == 2

    assert (await alice.delete(f"/papers/{widget.id}")).status_code == 204

    listed = await alice.get("/papers", params={"collection_id": made["id"]})
    assert [item["id"] for item in listed.json()["items"]] == [str(gadget.id)]
    assert (await alice.get(f"/collections/{made['id']}")).json()["paper_ids"] == [str(gadget.id)]


async def test_a_chat_on_a_collection_searches_what_the_collection_holds_when_asked(
    alice: AsyncClient, papers
):
    assert (await alice.post("/settings/providers", json=CONNECTION)).status_code == 201
    widget, gadget = papers
    made = await create(alice, "Sorting", widget)
    chat = (await alice.post("/chats", json={"collection_id": made["id"]})).json()
    assert (chat["collection_id"], chat["paper_ids"]) == (made["id"], [str(widget.id)])

    # The paper is added after the chat was made: the next question searches it too.
    await alice.put(f"/collections/{made['id']}/papers/{gadget.id}")
    response = await alice.post(
        f"/chats/{chat['id']}/messages", json={"content": "How are gadgets sorted?"}
    )

    sources = events(response.text)[0][1]
    assert sources[0]["paper_id"] == str(gadget.id)
    assert (await alice.get(f"/chats/{chat['id']}")).json()["source_count"] == 2
    on_it = await alice.get("/chats", params={"collection_id": made["id"]})
    assert [item["id"] for item in on_it.json()] == [chat["id"]]
    other = await create(alice, "Empty")
    assert (await alice.get("/chats", params={"collection_id": other["id"]})).json() == []

    # A chat can be moved to named papers and back; never both at once.
    both = {"collection_id": made["id"], "paper_ids": [str(widget.id)]}
    assert (await alice.patch(f"/chats/{chat['id']}", json=both)).status_code == 422
    moved = await alice.patch(f"/chats/{chat['id']}", json={"paper_ids": [str(widget.id)]})
    assert (moved.json()["collection_id"], moved.json()["paper_ids"]) == (None, [str(widget.id)])


async def test_a_chat_whose_collection_was_deleted_has_nothing_to_search(
    alice: AsyncClient, papers
):
    assert (await alice.post("/settings/providers", json=CONNECTION)).status_code == 201
    made = await create(alice, "Sorting", *papers)
    chat = (await alice.post("/chats", json={"collection_id": made["id"]})).json()
    await alice.delete(f"/collections/{made['id']}")

    shown = (await alice.get(f"/chats/{chat['id']}")).json()
    assert (shown["collection_id"], shown["paper_ids"]) == (None, [])
    response = await alice.post(f"/chats/{chat['id']}/messages", json={"content": "Anything?"})
    assert events(response.text)[-1][1]["outcome"] == "no_papers"
