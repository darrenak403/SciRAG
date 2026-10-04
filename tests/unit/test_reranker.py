import pytest

from scientrag.rag.reranker import parse_ranking, rerank


@pytest.mark.parametrize(
    ("reply", "ranking"),
    [
        ('{"ranking": [2, 0, 1]}', [2, 0, 1]),
        ("[2, 0]", [2, 0]),
        # Repeats and numbers that name no passage are dropped.
        ('{"ranking": [2, 2, 9, -1, 0, "1", true, 1.5]}', [2, 0]),
        ("Here is the ranking:\n```json\n[1, 0]\n```", [1, 0]),
        ('{"ranking": []}', []),
    ],
)
def test_the_ranking_is_read_from_the_reply(reply: str, ranking: list[int]):
    assert parse_ranking(reply, 3) == ranking


@pytest.mark.parametrize("reply", ["", "none of them", '{"ranking": "2"}', '{"answer": 3}'])
def test_a_reply_without_a_ranking_is_an_error(reply: str):
    with pytest.raises(ValueError):
        parse_ranking(reply, 3)


class Provider:
    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.asked: dict = {}

    async def complete(self, messages, **options) -> str:
        self.asked = {"content": messages[0]["content"], **options}
        return self.reply


async def test_passages_the_model_did_not_name_follow_in_their_original_order():
    provider = Provider('{"ranking": [3, 1]}')

    order = await rerank(provider, "how is bias corrected?", ["a", "b", "c", "d", "e"], top_n=4)

    assert order == [3, 1, 0, 2]
    assert provider.asked["role"] == "fast"
    assert provider.asked["json_output"] is True
    assert "[3]\nd" in provider.asked["content"]


async def test_no_more_than_the_number_asked_for_is_returned():
    provider = Provider('{"ranking": [4, 3, 2, 1, 0]}')

    assert await rerank(provider, "q", ["a", "b", "c", "d", "e"], top_n=2) == [4, 3]
