"""Papers that are ready to be searched, and a model provider to ask them with.

The papers are written straight to PostgreSQL and Qdrant, as ingestion would
leave them. The provider answers from a script; its vectors are word counts,
so both halves of the search rank passages by the words they share with the question.
"""

import hashlib
import json
import re
import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from scirag.chunking.scientific_chunker import CHUNKING_VERSION
from scirag.db.models import Chunk, Paper, PaperStatus
from scirag.index import qdrant_index
from scirag.providers.base import Usage
from scirag.providers.defaults import models_for
from scirag.providers.errors import ProviderError
from scirag.rag import prompts

# Model names no other run uses, so the collections made here can be dropped afterwards.
EMBEDDING_MODEL = f"test-chat-embedding-{uuid.uuid4().hex[:8]}"
OTHER_EMBEDDING_MODEL = f"{EMBEDDING_MODEL}-b"
DIMENSION = 256
CONNECTION = {
    "kind": "gemini",
    "label": "Mine",
    "api_key": "test-gemini-key-0000-abcd",
    "models": {"embedding": EMBEDDING_MODEL},
}


def vector(text: str) -> list[float]:
    """Counts of the text's words, each word in a slot of its own: texts that share
    words get vectors that point the same way, as a real embedding would."""
    counts = [0.0] * DIMENSION
    for word in re.findall(r"[a-z]+", text.lower()):
        counts[int.from_bytes(hashlib.sha256(word.encode()).digest()[:4]) % DIMENSION] += 1
    return counts if any(counts) else [1.0] * DIMENSION


async def drop_collections() -> None:
    client = qdrant_index.get_client()
    for model in (EMBEDDING_MODEL, OTHER_EMBEDDING_MODEL):
        name = qdrant_index.chunks_collection(model, DIMENSION)
        await client.delete_collection(name)
        await client.delete_collection(qdrant_index.papers_collection(name))


async def user_id(client: AsyncClient) -> uuid.UUID:
    return uuid.UUID((await client.get("/auth/me")).json()["id"])


async def ready_paper(
    db: AsyncSession,
    owner_id: uuid.UUID,
    title: str,
    passages: list[str],
    *,
    model: str = EMBEDDING_MODEL,
    kinds: dict[int, str] | None = None,
) -> Paper:
    """A processed paper with one chunk per passage, indexed under `model`."""
    paper_id = uuid.uuid7()
    collection = qdrant_index.chunks_collection(model, DIMENSION)
    paper = Paper(
        id=paper_id,
        owner_id=owner_id,
        title=title,
        original_filename=f"{title}.pdf",
        file_sha256=hashlib.sha256(paper_id.bytes).hexdigest(),
        storage_key=f"papers/{paper_id}/original.pdf",
        status=PaperStatus.READY,
        embedding_model=model,
        index_collection=collection,
    )
    db.add(paper)
    await db.flush()
    chunks = [
        Chunk(
            id=qdrant_index.point_id(paper_id, index, CHUNKING_VERSION),
            paper_id=paper_id,
            chunk_index=index,
            kind=(kinds or {}).get(index, "text"),
            text=text,
            embed_text=f"{title}\n{text}",
            section_path=["1 Method"],
            page_start=index + 1,
            page_end=index + 1,
            bboxes=[{"page": index + 1, "bbox": [0.1, 0.1, 0.9, 0.2]}],
            token_count=len(text) // 4,
        )
        for index, text in enumerate(passages)
    ]
    db.add_all(chunks)
    await db.commit()
    await qdrant_index.replace_paper(
        collection,
        owner_id=owner_id,
        paper_id=paper_id,
        chunks=[
            qdrant_index.IndexedChunk(
                chunk.id, chunk.chunk_index, chunk.kind, chunk.embed_text, vector(chunk.embed_text)
            )
            for chunk in chunks
        ],
        paper_text=title,
        paper_vector=vector(title),
    )
    return paper


class ScriptedProvider:
    """Stands in for an account's provider. Class attributes script what it says;
    `calls` records what it was asked, across every instance."""

    answer = "Widgets are sorted by weight [S1]."
    rewritten: str | None = None
    ranking: str = '{"ranking": []}'
    # What the fast model says the question is. None: a factual one, as written.
    analysis: str | None = None
    # The fast model's judgement of a passage, by a word the passage holds. Others score 8.
    evidence: dict[str, str] = {}
    # The answer model's replies when asked for a comparison table, in order.
    tables: list[str] = []
    fail_at: str | None = None
    calls: list[dict] = []
    streams_closed = 0
    STEPS = {
        prompts.REWRITE_SYSTEM: "rewrite",
        prompts.RERANK_SYSTEM: "rerank",
        prompts.ANALYZE_SYSTEM: "analyze",
        prompts.EVIDENCE_SYSTEM: "judge",
        prompts.COMPARE_SYSTEM: "table",
    }

    @classmethod
    def reset(cls) -> None:
        cls.answer = "Widgets are sorted by weight [S1]."
        cls.rewritten = None
        cls.ranking = '{"ranking": []}'
        cls.analysis = None
        cls.evidence = {}
        cls.tables = []
        cls.fail_at = None
        cls.calls = []
        cls.streams_closed = 0

    def __init__(self, connection) -> None:
        self.owner = connection.user_id
        self.models = models_for(connection.kind, connection.config.get("models", {}))
        self.usage: list[Usage] = []

    def model(self, role: str) -> str:
        return self.models[role]

    def _called(self, step: str, **what) -> None:
        self.calls.append({"step": step, "owner": self.owner, **what})
        if self.fail_at == step:
            raise ProviderError("quota_exceeded")

    async def complete(self, messages, *, role, max_tokens, system=None, json_output=False) -> str:
        step = self.STEPS[system]
        self._called(step, messages=messages, role=role)
        self.usage.append(Usage(role, self.models[role], 50, 5))
        content = messages[-1]["content"]
        asked = content.rsplit("Last question: ", 1)[-1]
        if step == "rerank":
            return self.ranking
        if step == "analyze":
            return self.analysis or json.dumps({"type": "factual", "question": asked})
        if step == "judge":
            passage = content.split("<passage>\n", 1)[1].rsplit("\n</passage>", 1)[0]
            for word, reply in self.evidence.items():
                if word in passage:
                    return reply
            return json.dumps({"relevance": 8, "summary": f"Summary: {passage}"})
        if step == "table":
            return type(self).tables.pop(0) if self.tables else "not a table"
        return self.rewritten or asked

    async def stream(self, messages, *, role, max_tokens, system=None):
        self._called("generate", messages=messages, system=system)
        try:
            for word in self.answer.split(" "):
                yield word + " "
                if self.fail_at == "mid-answer":
                    raise ProviderError("provider_unreachable")
            self.usage.append(Usage(role, self.models[role], 200, 20))
        finally:
            type(self).streams_closed += 1

    async def embed_query(self, text: str) -> list[float]:
        self._called("embed", text=text)
        self.usage.append(Usage("embedding", self.models["embedding"], 3, 0))
        return vector(text)

    async def aclose(self) -> None:
        pass


def events(body: str) -> list[tuple[str, object]]:
    """The server-sent events of a response body, as (name, data) pairs."""
    parsed = []
    for block in body.strip().split("\n\n"):
        name, data = block.split("\n", 1)
        parsed.append((name.removeprefix("event: "), json.loads(data.removeprefix("data: "))))
    return parsed
