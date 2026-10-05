"""Searching the index. This is the only place that asks Qdrant for passages.

The caller decides which papers may be searched and has to pass them: there is
no way to search a collection as a whole.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from qdrant_client import models

from scientrag.index.qdrant_index import (
    BM25_MODEL,
    DENSE,
    SPARSE,
    get_client,
    papers_collection,
)

# How the two searches are merged. rrf: by rank. dbsf: by score, normalised per search.
# none: no keyword search at all, only the search by meaning.
Fusion = Literal["rrf", "dbsf", "none"]


@dataclass(frozen=True)
class Hit:
    chunk_id: uuid.UUID
    paper_id: uuid.UUID
    score: float


def _allowed(owner_id: uuid.UUID, paper_ids: Sequence[uuid.UUID]) -> models.Filter:
    return models.Filter(
        must=[
            # The owner as well as the papers: a paper id that belongs to someone
            # else finds nothing even if a caller lets it through.
            models.FieldCondition(key="owner_id", match=models.MatchValue(value=str(owner_id))),
            models.FieldCondition(
                key="paper_id", match=models.MatchAny(any=[str(paper_id) for paper_id in paper_ids])
            ),
        ],
        must_not=[models.FieldCondition(key="kind", match=models.MatchValue(value="reference"))],
    )


def _request(
    allowed: models.Filter,
    query_text: str,
    query_vector: list[float],
    candidates: int,
    limit: int,
    fusion: Fusion,
) -> models.QueryRequest:
    """One search: by meaning and by keywords, each bringing back `candidates`
    points, their rankings merged."""
    if fusion == "none":
        return models.QueryRequest(
            query=query_vector, using=DENSE, filter=allowed, limit=limit, with_payload=["paper_id"]
        )
    return models.QueryRequest(
        prefetch=[
            models.Prefetch(query=query_vector, using=DENSE, filter=allowed, limit=candidates),
            models.Prefetch(
                query=models.Document(text=query_text, model=BM25_MODEL),
                using=SPARSE,
                filter=allowed,
                limit=candidates,
            ),
        ],
        query=models.FusionQuery(
            fusion=models.Fusion.DBSF if fusion == "dbsf" else models.Fusion.RRF
        ),
        # Everything the two searches brought back: the cut to `limit` is made by the
        # caller, after equal scores have been put in a fixed order.
        limit=2 * candidates,
        with_payload=["paper_id"],
    )


def _hits(points: Sequence[models.ScoredPoint], limit: int) -> list[Hit]:
    hits = [
        Hit(uuid.UUID(str(point.id)), uuid.UUID(point.payload["paper_id"]), point.score)
        for point in points
    ]
    # Merging by rank gives equal scores often (first and fourth, fourth and first), and
    # Qdrant returns equals in an order that changes from one call to the next.
    return sorted(hits, key=lambda hit: (-hit.score, hit.chunk_id))[:limit]


async def search(
    collection: str,
    *,
    owner_id: uuid.UUID,
    paper_ids: Sequence[uuid.UUID],
    query_text: str,
    query_vector: list[float],
    candidates: int,
    limit: int,
    fusion: Fusion = "rrf",
) -> list[Hit]:
    """The passages of these papers closest to the query, best first.

    Two searches, by meaning and by keywords, each bring back `candidates`
    passages; their rankings are merged and the first `limit` returned.
    Reference-list entries are left out.
    """
    if not paper_ids:
        return []
    request = _request(
        _allowed(owner_id, paper_ids), query_text, query_vector, candidates, limit, fusion
    )
    result = await get_client().query_points(
        collection,
        prefetch=request.prefetch,
        query=request.query,
        using=request.using,
        query_filter=request.filter,
        limit=request.limit,
        with_payload=request.with_payload,
    )
    return _hits(result.points, limit)


async def search_grouped(
    collection: str,
    *,
    owner_id: uuid.UUID,
    paper_ids: Sequence[uuid.UUID],
    query_text: str,
    query_vector: list[float],
    candidates: int,
    group_size: int,
    fusion: Fusion = "rrf",
) -> dict[uuid.UUID, list[Hit]]:
    """For each of these papers, its own `group_size` passages closest to the query.

    Each paper is searched by itself, in one round trip: a paper that says little
    about the question still brings its best passages, instead of losing every
    place to the papers that say most. A paper with no passage at all is left out.
    """
    if not paper_ids:
        return {}
    requests = [
        _request(
            _allowed(owner_id, [paper_id]), query_text, query_vector, candidates, group_size, fusion
        )
        for paper_id in paper_ids
    ]
    results = await get_client().query_batch_points(collection, requests=requests)
    groups = {
        paper_id: _hits(result.points, group_size)
        for paper_id, result in zip(paper_ids, results, strict=True)
    }
    return {paper_id: hits for paper_id, hits in groups.items() if hits}


async def search_papers(
    collection: str,
    *,
    owner_id: uuid.UUID,
    paper_ids: Sequence[uuid.UUID],
    query_text: str,
    query_vector: list[float],
    limit: int,
    fusion: Fusion = "rrf",
) -> list[uuid.UUID]:
    """Those of these papers that are, as a whole, closest to the query, best first.

    collection is the chunk collection the papers are indexed in; the search runs
    on the whole-paper points that go with it.
    """
    if not paper_ids:
        return []
    request = _request(
        _allowed(owner_id, paper_ids), query_text, query_vector, limit, limit, fusion
    )
    result = await get_client().query_batch_points(
        papers_collection(collection), requests=[request]
    )
    return [hit.paper_id for hit in _hits(result[0].points, limit)]
