"""Ingestion end to end, against real PostgreSQL and Qdrant.

The PDF parser and the model provider are replaced: the parser needs a model
download and a minute per paper, the provider needs somebody's key. Everything
between them is real, including the workflow engine.
"""

import asyncio
import hashlib
import json
import uuid
from collections.abc import AsyncIterator, Iterator
from concurrent.futures import ThreadPoolExecutor

import pytest
from dbos import DBOS
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.worker.main import launch
from scientrag.config import get_settings
from scientrag.db.models import Chunk, IngestionRun, Paper, PaperSection, ProviderUsage
from scientrag.index import qdrant_index
from scientrag.ingestion import steps, workflow
from scientrag.ingestion.errors import PermanentIngestionError
from scientrag.parsing.document import Block, ScientificDocument, Section
from scientrag.providers.base import Usage
from scientrag.providers.defaults import models_for
from scientrag.providers.errors import ProviderError
from tests.conftest import pdf_bytes

# A model name no other run uses, so the collections made here can be dropped afterwards.
EMBEDDING_MODEL = f"test-embedding-{uuid.uuid4().hex[:8]}"
OTHER_EMBEDDING_MODEL = f"{EMBEDDING_MODEL}-b"
DIMENSION = 8
BOX = (0.1, 0.1, 0.9, 0.2)
CONNECTION = {
    "kind": "gemini",
    "label": "Mine",
    "api_key": "test-gemini-key-0000-abcd",
    "models": {"embedding": EMBEDDING_MODEL},
}


def sample_document(**changes) -> ScientificDocument:
    sections = [
        Section(index=0, parent=None, level=1, title="Abstract", page=1),
        Section(index=1, parent=None, level=1, title="1 Method", page=1),
        Section(index=2, parent=1, level=2, title="1.1 Training", page=2),
        Section(index=3, parent=None, level=1, title="References", page=2),
    ]

    def block(text: str, section: int, kind: str = "text", page: int = 1) -> Block:
        return Block(kind=kind, text=text, page=page, bbox=BOX, section=section)

    blocks = [
        block("We study widgets. doi:10.1234/widgets.2021.", 0),
        block("Our method sorts widgets by weight.", 1),
        block("| size | score |\n| 1 | 0.9 |", 1, "table"),
        block("Table 1: Scores by size.", 1, "caption"),
        block("We train for ten epochs.", 2, page=2),
        block("L = sum(x)", 2, "formula", page=2),
        block("[1] A. Author. Widgets. 2019.", 3, "reference", page=2),
    ]
    fields = {
        "title": "A Study of Widgets",
        "page_count": 2,
        "sections": sections,
        "blocks": blocks,
        "warnings": [],
    }
    return ScientificDocument(**{**fields, **changes})


class FakeProvider:
    """Stands in for the owner's provider. Vectors depend only on the text."""

    fail_with: ProviderError | None = None

    def __init__(self, models: dict[str, str]) -> None:
        self.models = models
        self.usage = []

    def model(self, role: str) -> str:
        return self.models[role]

    async def complete(self, messages, *, role, max_tokens, system=None, json_output=False) -> str:
        if self.fail_with:
            raise self.fail_with
        self.usage.append(Usage(role, self.models[role], 100, 20))
        if json_output:
            return json.dumps(
                {"title": "Wrong", "authors": ["Ada Lovelace", "Alan Turing"], "year": 2021}
            )
        return "This paper studies widgets."

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if self.fail_with:
            raise self.fail_with
        self.usage.append(Usage("embedding", self.models["embedding"], len(texts), 0))
        return [
            [byte / 255 for byte in hashlib.sha256(text.encode()).digest()[:DIMENSION]]
            for text in texts
        ]

    async def aclose(self) -> None:
        pass


@pytest.fixture(scope="module")
async def working_thread_pool() -> AsyncIterator[None]:
    yield
    # The engine made its thread pool this event loop's default and shut it down on
    # the way out; the tests that follow share the loop and need a working one.
    asyncio.get_running_loop().set_default_executor(ThreadPoolExecutor())


@pytest.fixture(scope="module", autouse=True)
def workflow_engine(working_thread_pool: None) -> Iterator[None]:
    launch()
    yield
    DBOS.destroy()


@pytest.fixture(scope="module", autouse=True)
async def drop_test_collections() -> AsyncIterator[None]:
    yield
    client = qdrant_index.get_client()
    for model in (EMBEDDING_MODEL, OTHER_EMBEDDING_MODEL):
        name = qdrant_index.chunks_collection(model, DIMENSION)
        await client.delete_collection(name)
        await client.delete_collection(qdrant_index.papers_collection(name))


@pytest.fixture(autouse=True)
def fakes(monkeypatch: pytest.MonkeyPatch) -> list[tuple]:
    """Replaces the parser, the provider and the queue. Returns what the API queued."""
    queued: list[tuple] = []
    FakeProvider.fail_with = None

    async def enqueue_ingest(paper_id: uuid.UUID, first_step: str = "parse") -> bool:
        queued.append(("ingest", paper_id, first_step))
        return True

    async def enqueue_delete(paper_id: uuid.UUID) -> bool:
        queued.append(("delete", paper_id))
        return True

    monkeypatch.setattr("scientrag.ingestion.queue.enqueue_ingest", enqueue_ingest)
    monkeypatch.setattr("scientrag.ingestion.queue.enqueue_delete", enqueue_delete)
    monkeypatch.setattr(steps, "parse_document", lambda storage_key: sample_document())
    monkeypatch.setattr(
        "scientrag.providers.resolve.build_provider",
        lambda connection: FakeProvider(
            models_for(connection.kind, connection.config.get("models", {}))
        ),
    )
    return queued


async def work(queued: list[tuple]) -> None:
    """Does what the worker would: runs every queued workflow to its end."""
    while queued:
        kind, paper_id, *arguments = queued.pop(0)
        if kind == "ingest":
            await workflow.ingest_paper(str(paper_id), *arguments)
        else:
            await workflow.delete_paper(str(paper_id))


async def upload(client: AsyncClient, body: str = "widgets", filename: str = "upload.pdf") -> str:
    response = await client.post(
        "/papers", files={"file": (filename, pdf_bytes(body), "application/pdf")}
    )
    assert response.status_code == 202, response.text
    return response.json()["id"]


@pytest.fixture
async def owner(alice: AsyncClient) -> AsyncClient:
    """Alice, with a working model connection."""
    assert (await alice.post("/settings/providers", json=CONNECTION)).status_code == 201
    return alice


async def points(paper_id: str, model: str = EMBEDDING_MODEL) -> int:
    collection = qdrant_index.chunks_collection(model, DIMENSION)
    if not await qdrant_index.get_client().collection_exists(collection):
        return 0
    return await qdrant_index.count_chunks(collection, uuid.UUID(paper_id))


async def test_an_uploaded_paper_becomes_ready(owner: AsyncClient, fakes: list, db: AsyncSession):
    paper_id = await upload(owner)
    assert fakes == [("ingest", uuid.UUID(paper_id), "parse")]

    await work(fakes)

    paper = (await owner.get(f"/papers/{paper_id}")).json()
    assert paper["status"] == "READY"
    assert paper["processing_step"] is None
    assert paper["error_code"] is None
    assert paper["page_count"] == 2
    assert paper["needs_reindex"] is False
    # The file name is replaced by what the paper says; the model fills in the rest.
    assert paper["title"] == "A Study of Widgets"
    assert paper["authors"] == ["Ada Lovelace", "Alan Turing"]
    assert paper["year"] == 2021
    assert paper["doi"] == "10.1234/widgets.2021"

    chunks = (await owner.get(f"/papers/{paper_id}/chunks")).json()
    assert chunks["total"] == len(chunks["items"]) == 7
    assert await points(paper_id) == 7
    assert [chunk["kind"] for chunk in chunks["items"]] == [
        "text",
        "text",
        "table",
        "caption",
        "text",
        "formula",
        "reference",
    ]
    for chunk in chunks["items"]:
        assert chunk["page_start"] >= 1
        assert chunk["bboxes"][0]["bbox"] == list(BOX)
        assert chunk["section_path"]
    assert chunks["items"][4]["section_path"] == ["1 Method", "1.1 Training"]

    sections = (await owner.get(f"/papers/{paper_id}/sections")).json()
    assert [section["title"] for section in sections] == [
        "Abstract",
        "1 Method",
        "1.1 Training",
        "References",
    ]
    assert sections[2]["parent_id"] == sections[1]["id"]

    runs = (await owner.get(f"/papers/{paper_id}/ingestion")).json()
    assert [(run["step"], run["status"], run["attempt"]) for run in runs] == [
        (step, "done", 1) for step in steps.STEPS
    ]
    assert runs[2]["details"] == {"sections": 4, "chunks": 7}

    # The owner's key paid for it, and the tokens are counted.
    usage = (await owner.get("/settings/providers/usage")).json()
    assert [(row["role"], row["input_tokens"], row["output_tokens"]) for row in usage] == [
        # Metadata and summary: two calls to the fast model.
        ("fast", 200, 40),
        # Seven chunks and the paper as a whole.
        ("embedding", 8, 0),
    ]
    assert {row.user_id for row in await db.scalars(select(ProviderUsage))} == {
        (await db.scalar(select(Paper))).owner_id
    }
    # The vectors were only a hand-over between two steps.
    assert not steps.get_storage().exists(steps.vectors_key(uuid.UUID(paper_id)))


async def test_the_index_point_carries_the_owner(owner: AsyncClient, fakes: list, db: AsyncSession):
    paper_id = await upload(owner)
    await work(fakes)

    paper = await db.get(Paper, uuid.UUID(paper_id))
    assert paper.embedding_model == EMBEDDING_MODEL
    found, _ = await qdrant_index.get_client().scroll(paper.index_collection, limit=100)
    mine = [point for point in found if point.payload["paper_id"] == paper_id]
    assert len(mine) == 7
    assert {point.payload["owner_id"] for point in mine} == {str(paper.owner_id)}
    # A point and its chunk share one id.
    chunk_ids = set(await db.scalars(select(Chunk.id).where(Chunk.paper_id == paper.id)))
    assert {uuid.UUID(point.id) for point in mine} == chunk_ids


async def test_ingesting_again_changes_nothing(owner: AsyncClient, fakes: list, db: AsyncSession):
    paper_id = await upload(owner)
    await work(fakes)
    before = set(await db.scalars(select(Chunk.id)))

    for _ in range(2):
        response = await owner.post(f"/papers/{paper_id}/reingest")
        assert response.status_code == 202
        assert response.json()["status"] == "UPLOADED"
        await work(fakes)

    assert (await owner.get(f"/papers/{paper_id}")).json()["status"] == "READY"
    assert set(await db.scalars(select(Chunk.id))) == before
    assert await points(paper_id) == 7
    assert await db.scalar(select(func.count()).select_from(PaperSection)) == 4


async def test_a_shorter_second_parse_leaves_no_stale_chunks(
    owner: AsyncClient, fakes: list, monkeypatch: pytest.MonkeyPatch
):
    paper_id = await upload(owner)
    await work(fakes)

    shorter = sample_document(blocks=sample_document().blocks[:3])
    monkeypatch.setattr(steps, "parse_document", lambda storage_key: shorter)
    await owner.post(f"/papers/{paper_id}/reingest")
    await work(fakes)

    assert (await owner.get(f"/papers/{paper_id}/chunks")).json()["total"] == 3
    assert await points(paper_id) == 3


async def test_what_the_owner_typed_is_not_overwritten(owner: AsyncClient, fakes: list):
    paper_id = await upload(owner)
    typed = {"title": "My own title", "authors": ["Me"], "year": 1999, "doi": "10.9/mine"}
    assert (await owner.patch(f"/papers/{paper_id}", json=typed)).status_code == 200

    await work(fakes)

    paper = (await owner.get(f"/papers/{paper_id}")).json()
    assert paper["status"] == "READY"
    assert {key: paper[key] for key in typed} == typed


async def test_parse_warnings_do_not_stop_the_paper(
    owner: AsyncClient, fakes: list, monkeypatch: pytest.MonkeyPatch
):
    warned = sample_document(warnings=["2 formulas were read as plain characters."])
    monkeypatch.setattr(steps, "parse_document", lambda storage_key: warned)
    paper_id = await upload(owner)

    await work(fakes)

    paper = (await owner.get(f"/papers/{paper_id}")).json()
    assert paper["status"] == "READY"
    assert paper["warnings"] == ["2 formulas were read as plain characters."]


async def test_a_pdf_that_cannot_be_read_fails_once_with_a_clear_message(
    owner: AsyncClient, fakes: list, monkeypatch: pytest.MonkeyPatch, db: AsyncSession
):
    def locked(storage_key: str) -> ScientificDocument:
        raise PermanentIngestionError("unreadable_pdf", "The PDF is password-protected.")

    monkeypatch.setattr(steps, "parse_document", locked)
    paper_id = await upload(owner)

    await work(fakes)

    paper = (await owner.get(f"/papers/{paper_id}")).json()
    assert paper["status"] == "FAILED"
    assert paper["error_code"] == "unreadable_pdf"
    assert paper["error"] == "The PDF is password-protected."
    assert paper["processing_step"] == "parse"
    runs = list(await db.scalars(select(IngestionRun)))
    assert [(run.step, run.status, run.attempt) for run in runs] == [("parse", "failed", 1)]


async def test_without_a_model_connection_the_paper_fails_with_that_reason(
    alice: AsyncClient, fakes: list
):
    paper_id = await upload(alice)

    await work(fakes)

    paper = (await alice.get(f"/papers/{paper_id}")).json()
    assert paper["status"] == "FAILED"
    assert paper["error_code"] == "provider_not_configured"
    # Found out before the slow parse, not after it.
    assert paper["processing_step"] == "parse"


async def test_a_rejected_key_fails_the_paper_without_retrying(
    owner: AsyncClient, fakes: list, db: AsyncSession
):
    FakeProvider.fail_with = ProviderError("invalid_key")
    paper_id = await upload(owner)

    await work(fakes)

    paper = (await owner.get(f"/papers/{paper_id}")).json()
    assert (paper["status"], paper["error_code"]) == ("FAILED", "invalid_key")
    attempts = await db.scalar(
        select(func.count()).select_from(IngestionRun).where(IngestionRun.step == "metadata")
    )
    assert attempts == 1

    # With a working key, the same paper goes through.
    FakeProvider.fail_with = None
    assert (await owner.post(f"/papers/{paper_id}/reingest")).status_code == 202
    await work(fakes)
    assert (await owner.get(f"/papers/{paper_id}")).json()["status"] == "READY"


async def test_deleting_a_paper_removes_every_trace(
    owner: AsyncClient, fakes: list, db: AsyncSession
):
    paper_id = await upload(owner)
    kept_id = await upload(owner, "another paper")
    await work(fakes)
    assert await points(paper_id) == 7

    assert (await owner.delete(f"/papers/{paper_id}")).status_code == 204

    # Gone for the owner at once, before the worker has cleaned up.
    assert (await owner.get(f"/papers/{paper_id}")).status_code == 404
    assert (await owner.get("/papers")).json()["total"] == 1
    assert (await owner.delete(f"/papers/{paper_id}")).status_code == 404

    await work(fakes)

    assert await points(paper_id) == 0
    assert await db.get(Paper, uuid.UUID(paper_id)) is None
    assert set(await db.scalars(select(Chunk.paper_id))) == {uuid.UUID(kept_id)}
    stored = [path for path in get_settings().storage_dir.rglob("*") if path.is_file()]
    assert stored and all(kept_id in str(path) for path in stored)
    # The other paper is untouched, and the same file can be uploaded again.
    assert await points(kept_id) == 7
    await upload(owner)


async def test_a_paper_deleted_while_waiting_is_never_processed(owner: AsyncClient, fakes: list):
    paper_id = await upload(owner)
    assert (await owner.delete(f"/papers/{paper_id}")).status_code == 204

    await work(fakes)

    assert await points(paper_id) == 0


async def test_another_user_cannot_reach_the_paper(
    owner: AsyncClient, bob: AsyncClient, fakes: list
):
    paper_id = await upload(owner)
    await work(fakes)

    for path in ("sections", "ingestion", "chunks"):
        assert (await bob.get(f"/papers/{paper_id}/{path}")).status_code == 404
    assert (await bob.post(f"/papers/{paper_id}/reingest")).status_code == 404
    assert (await bob.delete(f"/papers/{paper_id}")).status_code == 404
    assert fakes == []
    assert (await owner.get(f"/papers/{paper_id}")).json()["status"] == "READY"


async def test_changing_the_embedding_model_asks_for_a_reindex(owner: AsyncClient, fakes: list):
    paper_id = await upload(owner)
    await work(fakes)
    connection_id = (await owner.get("/settings/providers")).json()[0]["id"]

    changed = await owner.patch(
        f"/settings/providers/{connection_id}",
        json={"models": {"embedding": OTHER_EMBEDDING_MODEL}},
    )
    assert changed.status_code == 200

    assert (await owner.get(f"/papers/{paper_id}")).json()["needs_reindex"] is True
    assert (await owner.get("/papers")).json()["items"][0]["needs_reindex"] is True

    response = await owner.post("/papers/reindex")
    assert response.status_code == 202
    assert response.json() == {"queued": 1}
    # Only embedding and indexing run again; the PDF is not parsed a second time.
    assert fakes == [("ingest", uuid.UUID(paper_id), "embed")]
    await work(fakes)

    paper = (await owner.get(f"/papers/{paper_id}")).json()
    assert (paper["status"], paper["needs_reindex"]) == ("READY", False)
    assert await points(paper_id, OTHER_EMBEDDING_MODEL) == 7
    assert await points(paper_id, EMBEDDING_MODEL) == 0
    assert (await owner.post("/papers/reindex")).json() == {"queued": 0}


async def test_a_failed_reindex_leaves_the_paper_searchable(owner: AsyncClient, fakes: list):
    paper_id = await upload(owner)
    await work(fakes)
    connection_id = (await owner.get("/settings/providers")).json()[0]["id"]
    await owner.patch(
        f"/settings/providers/{connection_id}",
        json={"models": {"embedding": OTHER_EMBEDDING_MODEL}},
    )
    FakeProvider.fail_with = ProviderError("quota_exceeded")

    await owner.post("/papers/reindex")
    await work(fakes)

    paper = (await owner.get(f"/papers/{paper_id}")).json()
    assert (paper["status"], paper["error_code"]) == ("READY", "quota_exceeded")
    assert paper["needs_reindex"] is True
    assert await points(paper_id, EMBEDDING_MODEL) == 7

    # It is offered again once the quota is back.
    FakeProvider.fail_with = None
    assert (await owner.post("/papers/reindex")).json() == {"queued": 1}
    await work(fakes)
    paper = (await owner.get(f"/papers/{paper_id}")).json()
    assert (paper["status"], paper["error_code"], paper["needs_reindex"]) == ("READY", None, False)


async def test_malformed_vectors_fail_the_paper_and_reach_no_index(
    owner: AsyncClient, fakes: list, monkeypatch: pytest.MonkeyPatch
):
    async def uneven(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] * (DIMENSION + position % 2) for position in range(len(texts))]

    monkeypatch.setattr(FakeProvider, "embed_documents", uneven)
    paper_id = await upload(owner)

    await work(fakes)

    paper = (await owner.get(f"/papers/{paper_id}")).json()
    assert (paper["status"], paper["error_code"]) == ("FAILED", "provider_rejected")
    assert paper["processing_step"] == "embed"
    assert await points(paper_id) == 0


async def test_an_unexpected_error_is_not_shown_to_the_owner(
    owner: AsyncClient, fakes: list, monkeypatch: pytest.MonkeyPatch
):
    async def explode(paper_id: uuid.UUID) -> dict:
        raise RuntimeError("password=hunter2 host=postgres")

    monkeypatch.setitem(steps.WORK, "chunk", explode)
    monkeypatch.setattr(workflow, "should_retry", lambda error: False)
    paper_id = await upload(owner)

    await work(fakes)

    paper = (await owner.get(f"/papers/{paper_id}")).json()
    runs = (await owner.get(f"/papers/{paper_id}/ingestion")).json()
    assert (paper["status"], paper["error_code"]) == ("FAILED", "temporary_failure")
    assert "hunter2" not in json.dumps(paper) + json.dumps(runs)
    assert runs[-1]["error"] == "Unexpected error"


async def test_reindex_needs_a_model_connection(alice: AsyncClient):
    assert (await alice.post("/papers/reindex")).status_code == 409
