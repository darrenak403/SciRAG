"""Searching the index. This is the only place that asks Qdrant for passages.

The caller decides which papers may be searched and has to pass them: there is
no way to search a collection as a whole.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from qdrant_client import models

from scientrag.index.qdrant_index import BM25_MODEL, DENSE, SPARSE, get_client


@dataclass(frozen=True)
class Hit:
    chunk_id: uuid.UUID
    paper_id: uuid.UUID
    score: float


async def search(
    collection: str,
    *,
    owner_id: uuid.UUID,
    paper_ids: Sequence[uuid.UUID],
    query_text: str,
    query_vector: list[float],
    candidates: int,
    limit: int,
) -> list[Hit]:
    """The passages of these papers closest to the query, best first.

    Two searches, by meaning and by keywords, each bring back `candidates`
    passages; their rankings are merged and the first `limit` returned.
    Reference-list entries are left out.
    """
    if not paper_ids:
        return []
    allowed = models.Filter(
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
    result = await get_client().query_points(
        collection,
        prefetch=[
            models.Prefetch(query=query_vector, using=DENSE, filter=allowed, limit=candidates),
            models.Prefetch(
                query=models.Document(text=query_text, model=BM25_MODEL),
                using=SPARSE,
                filter=allowed,
                limit=candidates,
            ),
        ],
        query=models.FusionQuery(fusion=models.Fusion.RRF),
        limit=limit,
        with_payload=["paper_id"],
    )
    return [
        Hit(uuid.UUID(str(point.id)), uuid.UUID(point.payload["paper_id"]), point.score)
        for point in result.points
    ]
