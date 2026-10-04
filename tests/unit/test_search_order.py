import uuid
from types import SimpleNamespace

from scientrag.index import search as index_search

PAPER = uuid.uuid4()
FIRST, SECOND, THIRD = sorted(uuid.uuid4() for _ in range(3))


class _Index:
    """Answers a query with the points it was given, in the order it was given them."""

    def __init__(self, points: list[tuple[uuid.UUID, float]]) -> None:
        self.points = [
            SimpleNamespace(id=str(chunk_id), score=score, payload={"paper_id": str(PAPER)})
            for chunk_id, score in points
        ]

    async def query_points(self, collection: str, **query) -> SimpleNamespace:
        return SimpleNamespace(points=self.points)


async def _order(
    monkeypatch, points: list[tuple[uuid.UUID, float]], limit: int = 30
) -> list[uuid.UUID]:
    monkeypatch.setattr(index_search, "get_client", lambda: _Index(points))
    hits = await index_search.search(
        "chunks",
        owner_id=uuid.uuid4(),
        paper_ids=[PAPER],
        query_text="question",
        query_vector=[0.0],
        candidates=50,
        limit=limit,
    )
    return [hit.chunk_id for hit in hits]


async def test_passages_with_equal_scores_come_back_in_the_same_order_every_time(monkeypatch):
    one_way = await _order(monkeypatch, [(THIRD, 0.9), (SECOND, 0.5), (FIRST, 0.5)])
    other_way = await _order(monkeypatch, [(THIRD, 0.9), (FIRST, 0.5), (SECOND, 0.5)])

    assert one_way == other_way == [THIRD, FIRST, SECOND]


async def test_equal_scores_at_the_cut_keep_the_same_passage_every_time(monkeypatch):
    one_way = await _order(monkeypatch, [(THIRD, 0.9), (SECOND, 0.5), (FIRST, 0.5)], limit=2)
    other_way = await _order(monkeypatch, [(THIRD, 0.9), (FIRST, 0.5), (SECOND, 0.5)], limit=2)

    assert one_way == other_way == [THIRD, FIRST]
