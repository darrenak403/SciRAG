from pathlib import Path

from httpx import AsyncClient, Response

from apps.api.deps import get_storage
from scirag.config import get_settings
from scirag.ingestion import queue
from tests.conftest import pdf_bytes


async def upload(
    client: AsyncClient,
    content: bytes | None = None,
    filename: str = "attention.pdf",
    content_type: str = "application/pdf",
) -> Response:
    files = {"file": (filename, pdf_bytes() if content is None else content, content_type)}
    return await client.post("/papers", files=files)


async def upload_with(client: AsyncClient, body: str, **metadata) -> str:
    """Uploads a distinct file, sets its metadata, and returns the paper id."""
    paper_id = (await upload(client, pdf_bytes(body), f"{body}.pdf")).json()["id"]
    response = await client.patch(f"/papers/{paper_id}", json=metadata)
    assert response.status_code == 200, response.text
    return paper_id


def stored_files() -> list[Path]:
    return [path for path in get_settings().storage_dir.rglob("*") if path.is_file()]


async def test_upload_stores_the_file_and_records_the_paper(alice: AsyncClient):
    response = await upload(alice)

    assert response.status_code == 202
    paper = response.json()
    assert paper["status"] == "UPLOADED"
    assert paper["title"] == "attention"
    assert paper["original_filename"] == "attention.pdf"
    assert paper["authors"] == []
    assert get_storage().exists(f"papers/{paper['id']}/original.pdf")

    listing = (await alice.get("/papers")).json()
    assert listing["total"] == 1
    assert listing["items"][0]["id"] == paper["id"]

    detail = await alice.get(f"/papers/{paper['id']}")
    assert detail.status_code == 200
    assert detail.json() == {**paper, "summary": None}


async def test_download_returns_the_uploaded_bytes(alice: AsyncClient):
    content = pdf_bytes("the whole paper")
    paper_id = (await upload(alice, content)).json()["id"]

    response = await alice.get(f"/papers/{paper_id}/file")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content == content


async def test_upload_requires_a_session(anon: AsyncClient):
    assert (await upload(anon)).status_code == 401
    assert stored_files() == []


async def test_upload_rejects_a_file_that_is_not_a_pdf(alice: AsyncClient):
    wrong_type = await upload(alice, b"plain text", "notes.txt", "text/plain")
    # Named and labelled as a PDF, but the content is not one.
    wrong_content = await upload(alice, b"<html></html>", "paper.pdf")

    assert wrong_type.status_code == 415
    assert wrong_content.status_code == 415
    assert stored_files() == []
    assert (await alice.get("/papers")).json()["total"] == 0


async def test_upload_rejects_a_file_over_the_size_limit(alice: AsyncClient):
    limit_bytes = get_settings().max_upload_mb * 1024 * 1024
    too_big = b"%PDF-" + b"0" * limit_bytes

    response = await upload(alice, too_big)

    assert response.status_code == 413
    assert stored_files() == []


async def test_upload_accepts_a_file_exactly_at_the_size_limit(alice: AsyncClient):
    limit_bytes = get_settings().max_upload_mb * 1024 * 1024
    at_limit = b"%PDF-" + b"0" * (limit_bytes - 5)

    assert (await upload(alice, at_limit)).status_code == 202


async def test_uploading_the_same_file_twice_points_to_the_first_paper(alice: AsyncClient):
    first = (await upload(alice, filename="first.pdf")).json()

    again = await upload(alice, filename="renamed.pdf")

    assert again.status_code == 409
    body = again.json()
    assert body["code"] == "duplicate_paper"
    assert body["paper_id"] == first["id"]
    assert body["title"] == "first"
    assert len(stored_files()) == 1
    assert (await alice.get("/papers")).json()["total"] == 1


async def test_two_users_can_upload_the_same_file(alice: AsyncClient, bob: AsyncClient):
    assert (await upload(alice)).status_code == 202
    assert (await upload(bob)).status_code == 202
    assert len(stored_files()) == 2


async def test_the_uploaded_file_name_never_reaches_the_storage_path(alice: AsyncClient):
    response = await upload(alice, filename="../../../etc/passwd.pdf")

    assert response.status_code == 202
    paper = response.json()
    assert paper["original_filename"] == "passwd.pdf"
    (stored,) = stored_files()
    assert stored == get_settings().storage_dir / "papers" / paper["id"] / "original.pdf"


async def test_another_user_cannot_see_the_paper(alice: AsyncClient, bob: AsyncClient):
    paper_id = (await upload(alice)).json()["id"]

    # 404, not 403: the answer must not reveal that the paper exists.
    assert (await bob.get(f"/papers/{paper_id}")).status_code == 404
    assert (await bob.get(f"/papers/{paper_id}/file")).status_code == 404
    assert (await bob.patch(f"/papers/{paper_id}", json={"title": "mine now"})).status_code == 404
    assert (await bob.get("/papers")).json() == {
        "items": [],
        "total": 0,
        "page": 1,
        "page_size": 20,
    }
    assert (await alice.get(f"/papers/{paper_id}")).json()["title"] == "attention"


async def test_edit_metadata(alice: AsyncClient):
    paper_id = (await upload(alice)).json()["id"]

    response = await alice.patch(
        f"/papers/{paper_id}",
        json={
            "title": "Attention Is All You Need",
            "authors": ["Ashish Vaswani", " Noam Shazeer ", "Ashish Vaswani", ""],
            "year": 2017,
            "doi": "10.48550/arXiv.1706.03762",
        },
    )

    assert response.status_code == 200
    paper = response.json()
    assert paper["title"] == "Attention Is All You Need"
    # Order kept, names trimmed, repeats and blanks dropped.
    assert paper["authors"] == ["Ashish Vaswani", "Noam Shazeer"]
    assert paper["year"] == 2017
    assert paper["doi"] == "10.48550/arXiv.1706.03762"
    assert (await alice.get(f"/papers/{paper_id}")).json() == {**paper, "summary": None}


async def test_edit_changes_only_the_fields_sent(alice: AsyncClient):
    paper_id = await upload_with(alice, "one", title="Kept", authors=["A", "B"], year=2020)

    paper = (await alice.patch(f"/papers/{paper_id}", json={"year": None})).json()
    assert paper["year"] is None
    assert paper["title"] == "Kept"
    assert paper["authors"] == ["A", "B"]

    # authors replaces the whole list, including its order.
    paper = (await alice.patch(f"/papers/{paper_id}", json={"authors": ["B", "C"]})).json()
    assert paper["authors"] == ["B", "C"]
    assert paper["title"] == "Kept"


async def test_edit_rejects_an_empty_title(alice: AsyncClient):
    paper_id = (await upload(alice)).json()["id"]
    assert (await alice.patch(f"/papers/{paper_id}", json={"title": ""})).status_code == 422
    assert (await alice.patch(f"/papers/{paper_id}", json={"title": None})).status_code == 422


async def test_search_and_filter(alice: AsyncClient):
    resnet = await upload_with(
        alice, "resnet", title="Deep Residual Learning", authors=["Kaiming He"], year=2015
    )
    bert = await upload_with(
        alice, "bert", title="BERT: Pre-training", authors=["Jacob Devlin"], year=2018
    )
    adam = await upload_with(
        alice, "adam", title="Adam: 100% Stochastic", authors=["Diederik Kingma"], year=2015
    )

    async def ids(**params) -> set[str]:
        body = (await alice.get("/papers", params=params)).json()
        assert body["total"] == len(body["items"])
        return {item["id"] for item in body["items"]}

    assert await ids(q="residual") == {resnet}
    assert await ids(year=2015) == {resnet, adam}
    assert await ids(author="devlin") == {bert}
    assert await ids(year=2015, author="kingma") == {adam}
    assert await ids(status="UPLOADED") == {resnet, bert, adam}
    assert await ids(status="READY") == set()
    assert await ids(status=["UPLOADED", "PROCESSING"]) == {resnet, bert, adam}
    # "%" is searched for literally, not treated as a wildcard.
    assert await ids(q="100%") == {adam}
    assert await ids(q="%") == {adam}


async def test_sort(alice: AsyncClient):
    resnet = await upload_with(alice, "resnet", title="deep residual", authors=["He"], year=2015)
    bert = await upload_with(alice, "bert", title="BERT", authors=["Devlin"], year=2018)
    no_metadata = (await upload(alice, pdf_bytes("x"), "zzz.pdf")).json()["id"]

    async def order(**params) -> list[str]:
        return [item["id"] for item in (await alice.get("/papers", params=params)).json()["items"]]

    assert await order() == [no_metadata, bert, resnet]  # newest first
    assert await order(sort="added", order="asc") == [resnet, bert, no_metadata]
    assert await order(sort="title", order="asc") == [bert, resnet, no_metadata]
    # A paper without the sort value goes last in both directions.
    assert await order(sort="year", order="desc") == [bert, resnet, no_metadata]
    assert await order(sort="year", order="asc") == [resnet, bert, no_metadata]
    assert await order(sort="author", order="asc") == [bert, resnet, no_metadata]


async def test_pagination(alice: AsyncClient):
    for number in range(5):
        await upload(alice, pdf_bytes(str(number)), f"{number}.pdf")

    first = (
        await alice.get("/papers", params={"page_size": 2, "sort": "title", "order": "asc"})
    ).json()
    last = (
        await alice.get(
            "/papers", params={"page_size": 2, "page": 3, "sort": "title", "order": "asc"}
        )
    ).json()

    assert first["total"] == last["total"] == 5
    assert [item["title"] for item in first["items"]] == ["0", "1"]
    assert [item["title"] for item in last["items"]] == ["4"]
    assert (await alice.get("/papers", params={"page_size": 101})).status_code == 422
    assert (await alice.get("/papers", params={"sort": "password"})).status_code == 422


async def queued_workflows(paper_id: str) -> list[tuple[str, str]]:
    rows = await queue._client().list_workflows_async(queue_name=queue.INGEST_QUEUE)
    return [(row.name, row.status) for row in rows if paper_id in str(row.input)]


async def test_upload_queues_the_paper_for_the_worker(alice: AsyncClient):
    paper_id = (await upload(alice)).json()["id"]

    assert await queued_workflows(paper_id) == [("ingest_paper", "ENQUEUED")]


async def test_a_paper_already_waiting_cannot_be_queued_twice(alice: AsyncClient):
    paper_id = (await upload(alice)).json()["id"]

    assert (await alice.post(f"/papers/{paper_id}/reingest")).status_code == 409
    assert len(await queued_workflows(paper_id)) == 1


async def test_delete_hides_the_paper_and_queues_its_cleanup(alice: AsyncClient):
    paper_id = (await upload(alice)).json()["id"]

    assert (await alice.delete(f"/papers/{paper_id}")).status_code == 204

    assert (await alice.get(f"/papers/{paper_id}")).status_code == 404
    assert (await alice.get(f"/papers/{paper_id}/file")).status_code == 404
    assert ("delete_paper", "ENQUEUED") in await queued_workflows(paper_id)
    # The file stays until the worker removes it, but the same PDF can be uploaded again.
    assert (await upload(alice)).status_code == 202
