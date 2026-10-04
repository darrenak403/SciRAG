"""The search index in Qdrant: one point per chunk, and one per paper.

Vectors of different embedding models cannot share a collection, so each model
(and vector size) gets its own. A paper's collection is recorded on the paper.
"""

import hashlib
import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache

from qdrant_client import AsyncQdrantClient, models

from scientrag.config import get_settings

DENSE = "dense"
# Keyword search, scored by Qdrant itself from the text sent with each point.
SPARSE = "bm25"
BM25_MODEL = "Qdrant/bm25"
UPSERT_BATCH = 64
_NAMESPACE = uuid.UUID("6f1d5a52-5c0e-4d8a-9b53-6b6f6a1c1f10")


@dataclass(frozen=True)
class IndexedChunk:
    id: uuid.UUID
    chunk_index: int
    kind: str
    text: str
    vector: list[float]


@lru_cache
def get_client() -> AsyncQdrantClient:
    return AsyncQdrantClient(url=get_settings().qdrant_url, timeout=30)


def point_id(paper_id: uuid.UUID, chunk_index: int, chunking_version: int) -> uuid.UUID:
    """The same chunk always gets the same id, so indexing a paper again replaces its points."""
    return uuid.uuid5(_NAMESPACE, f"{paper_id}:{chunk_index}:{chunking_version}")


def chunks_collection(embedding_model: str, dimension: int) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", embedding_model.lower()).strip("-")[:60]
    # The slug is for people; the hash keeps two model names from sharing a collection.
    digest = hashlib.sha256(embedding_model.encode()).hexdigest()[:8]
    return f"chunks__{slug}-{digest}__{dimension}__v1"


def papers_collection(chunks_collection_name: str) -> str:
    """The collection of whole-paper points that goes with a chunk collection."""
    return "papers__" + chunks_collection_name.removeprefix("chunks__")


def _of_paper(paper_id: uuid.UUID) -> models.Filter:
    return models.Filter(
        must=[models.FieldCondition(key="paper_id", match=models.MatchValue(value=str(paper_id)))]
    )


async def ensure_collection(name: str, dimension: int) -> None:
    client = get_client()
    if not await client.collection_exists(name):
        try:
            await client.create_collection(
                name,
                vectors_config={
                    DENSE: models.VectorParams(size=dimension, distance=models.Distance.COSINE)
                },
                sparse_vectors_config={
                    SPARSE: models.SparseVectorParams(modifier=models.Modifier.IDF)
                },
            )
        except Exception:
            # Another worker may have created it in between.
            if not await client.collection_exists(name):
                raise
    # Asked for every time, not only on creation: a worker that died right after
    # creating the collection would otherwise leave it without them for good.
    # Every search filters by owner; is_tenant lets Qdrant keep each owner's points together.
    await client.create_payload_index(
        name, "owner_id", models.KeywordIndexParams(type="keyword", is_tenant=True)
    )
    await client.create_payload_index(name, "paper_id", models.PayloadSchemaType.KEYWORD)
    await client.create_payload_index(name, "kind", models.PayloadSchemaType.KEYWORD)


def _vectors(vector: list[float], text: str) -> dict:
    return {DENSE: vector, SPARSE: models.Document(text=text, model=BM25_MODEL)}


async def replace_paper(
    collection: str,
    *,
    owner_id: uuid.UUID,
    paper_id: uuid.UUID,
    chunks: Sequence[IndexedChunk],
    paper_text: str,
    paper_vector: list[float],
) -> None:
    """Makes the index hold exactly these chunks for the paper, plus the paper's own point."""
    client = get_client()
    dimension = len(paper_vector)
    summaries = papers_collection(collection)
    await ensure_collection(collection, dimension)
    await ensure_collection(summaries, dimension)

    owner = {"owner_id": str(owner_id), "paper_id": str(paper_id)}
    # Points left from an earlier run with more chunks would otherwise stay behind.
    await client.delete(collection, _of_paper(paper_id), wait=True)
    for start in range(0, len(chunks), UPSERT_BATCH):
        points = [
            models.PointStruct(
                id=str(chunk.id),
                vector=_vectors(chunk.vector, chunk.text),
                payload={**owner, "chunk_index": chunk.chunk_index, "kind": chunk.kind},
            )
            for chunk in chunks[start : start + UPSERT_BATCH]
        ]
        await client.upsert(collection, points, wait=True)
    await client.upsert(
        summaries,
        [
            models.PointStruct(
                id=str(paper_id), vector=_vectors(paper_vector, paper_text), payload=owner
            )
        ],
        wait=True,
    )


async def delete_paper(collection: str, paper_id: uuid.UUID) -> None:
    """Removes the paper from a chunk collection and from its paper collection."""
    client = get_client()
    for name in (collection, papers_collection(collection)):
        if await client.collection_exists(name):
            await client.delete(name, _of_paper(paper_id), wait=True)


async def count_chunks(collection: str, paper_id: uuid.UUID) -> int:
    result = await get_client().count(collection, count_filter=_of_paper(paper_id), exact=True)
    return result.count
