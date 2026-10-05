"""Questions over several papers, through the API: a comparison answered with a
table, and a synthesis written from findings gathered paper by paper.

Only the model provider is replaced: it answers from a script and records what
it was asked.
"""

import json
from collections.abc import AsyncIterator

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from scientrag.config import get_settings
from scientrag.db.models import Paper
from scientrag.rag import prompts
from scientrag.rag.engine import NO_EVIDENCE
from scientrag.rag.paths.comparison import NOT_FOUND
from tests.rag_factory import (
    CONNECTION,
    ScriptedProvider,
    drop_collections,
    events,
    ready_paper,
    user_id,
)

WIDGETS = ["Widgets are sorted by weight before packing.", "Widgets are counted twice a day."]
GADGETS = ["Gadgets are sorted by colour after washing.", "Gadgets are counted once a week."]
QUESTION = "How are widgets and gadgets sorted?"
# Widget Study brings S1 and S2, Gadget Study S3 and S4.
TABLE = {
    "columns": ["Sorted by"],
    "rows": [
        {"paper": "P1", "cells": ["Weight [S1]"]},
        # S1 is a passage of the other paper: it cannot back this row.
        {"paper": "P2", "cells": ["Colour [S3][S1]"]},
    ],
    "summary": "One sorts by weight [S1], the other by colour [S3].",
}


@pytest.fixture(scope="module", autouse=True)
async def collections() -> AsyncIterator[None]:
    yield
    await drop_collections()


@pytest.fixture(autouse=True)
def provider(monkeypatch: pytest.MonkeyPatch) -> None:
    ScriptedProvider.reset()
    monkeypatch.setattr("scientrag.providers.resolve.build_provider", ScriptedProvider)


@pytest.fixture
async def owner(alice: AsyncClient) -> AsyncClient:
    assert (await alice.post("/settings/providers", json=CONNECTION)).status_code == 201
    return alice


@pytest.fixture
async def papers(owner: AsyncClient, db: AsyncSession) -> list[Paper]:
    account = await user_id(owner)
    return [
        await ready_paper(db, account, "Widget Study", WIDGETS),
        await ready_paper(db, account, "Gadget Study", GADGETS),
    ]


async def ask(
    client: AsyncClient, papers: list[Paper], mode: str | None = None, question: str = QUESTION
) -> tuple[str, list[tuple]]:
    """Asks in a new chat on the papers. Returns the chat and the events received."""
    created = await client.post("/chats", json={"paper_ids": [str(paper.id) for paper in papers]})
    chat_id = created.json()["id"]
    payload = {"content": question} | ({"mode": mode} if mode else {})
    response = await client.post(f"/chats/{chat_id}/messages", json=payload)
    assert response.status_code == 200, response.text
    return chat_id, events(response.text)


def steps() -> list[str]:
    return [call["step"] for call in ScriptedProvider.calls]


def stages(received: list[tuple]) -> list[str]:
    """The stages reported, each one once, in order."""
    seen: list[str] = []
    for name, data in received:
        if name == "status" and data["stage"] not in seen:
            seen.append(data["stage"])
    return seen


async def test_a_comparison_is_answered_with_a_table_that_has_a_row_for_every_paper(
    owner: AsyncClient, papers: list[Paper]
):
    ScriptedProvider.tables = [json.dumps(TABLE)]

    chat_id, received = await ask(owner, papers, "comparison")

    assert [name for name, _ in received] == [
        "status",
        "status",
        "sources",
        "status",
        "table",
        "delta",
        "done",
    ]
    assert stages(received) == ["selecting", "gathering", "comparing"]
    assert received[0][1] == {
        "stage": "selecting",
        "done": None,
        "total": None,
        "mode": "comparison",
    }
    sources = received[2][1]
    # Every paper brought its own passages, however little it says about the question.
    assert [source["paper_title"] for source in sources] == ["Widget Study"] * 2 + [
        "Gadget Study"
    ] * 2
    table = received[4][1]
    assert table["columns"] == ["Sorted by"]
    assert [(row["paper_id"], row["paper_title"]) for row in table["rows"]] == [
        (str(papers[0].id), "Widget Study"),
        (str(papers[1].id), "Gadget Study"),
    ]
    assert table["rows"][0]["cells"] == [{"text": "Weight", "markers": ["S1"]}]
    assert table["rows"][1]["cells"] == [{"text": "Colour", "markers": ["S3"]}]
    done = received[-1][1]
    assert (done["mode"], done["outcome"], done["table"]) == ("comparison", "answered", table)
    assert done["text"] == received[5][1]["text"] == TABLE["summary"]
    assert done["citations"] == ["S1", "S3"]

    # One call writes the table and its summary; nothing is reranked or streamed.
    assert steps() == ["embed", "table"]
    asked = ScriptedProvider.calls[-1]
    assert asked["role"] == "answer"
    content = asked["messages"][-1]["content"]
    assert content.startswith('<paper id="P1" title="Widget Study">\n<source id="S1"')
    assert '<paper id="P2" title="Gadget Study">' in content

    answer = (await owner.get(f"/chats/{chat_id}/messages")).json()[1]
    assert (answer["mode"], answer["table"], answer["notice"]) == ("comparison", table, None)
    assert [source["marker"] for source in answer["citations"]] == ["S1", "S3"]
    retrieval = (await owner.get(f"/chats/messages/{answer['id']}/retrieval")).json()["retrieval"]
    assert (retrieval["mode"], retrieval["table"]) == ("comparison", "model")
    assert retrieval["papers_considered"] == 2


async def test_a_paper_the_model_left_out_of_the_table_is_still_listed(
    owner: AsyncClient, papers: list[Paper]
):
    ScriptedProvider.tables = [json.dumps({**TABLE, "rows": TABLE["rows"][:1], "summary": ""})]

    _, received = await ask(owner, papers, "comparison")

    table = next(data for name, data in received if name == "table")
    assert table["rows"][1]["paper_title"] == "Gadget Study"
    assert table["rows"][1]["cells"] == [{"text": NOT_FOUND, "markers": []}]
    # Without a summary there is no text to stream, only the table.
    assert "delta" not in [name for name, _ in received]
    assert received[-1][1]["text"] == "Comparison of 2 papers."


async def test_a_table_that_cannot_be_read_is_asked_for_once_more(
    owner: AsyncClient, papers: list[Paper]
):
    ScriptedProvider.tables = ["Sure, here is the table you asked for.", json.dumps(TABLE)]

    _, received = await ask(owner, papers, "comparison")

    assert steps() == ["embed", "table", "table"]
    assert received[-1][1]["table"]["columns"] == ["Sorted by"]


async def test_without_a_usable_table_the_comparison_is_written_as_text(
    owner: AsyncClient, papers: list[Paper]
):
    ScriptedProvider.answer = "Widgets go by weight [S1], gadgets by colour [S3]. Also [S9]."

    chat_id, received = await ask(owner, papers, "comparison")

    assert steps() == ["embed", "table", "table", "generate"]
    assert ScriptedProvider.calls[-1]["system"] == prompts.COMPARE_TEXT_SYSTEM
    assert stages(received) == ["selecting", "gathering", "comparing", "writing"]
    assert "table" not in [name for name, _ in received]
    done = received[-1][1]
    assert (done["mode"], done["table"], done["outcome"]) == ("comparison", None, "answered")
    assert done["text"] == "Widgets go by weight [S1], gadgets by colour [S3]. Also."
    assert done["citations"] == ["S1", "S3"]
    answer = (await owner.get(f"/chats/{chat_id}/messages")).json()[1]
    assert (answer["mode"], answer["table"]) == ("comparison", None)


async def test_the_kind_of_question_is_worked_out_when_it_is_not_given(
    owner: AsyncClient, papers: list[Paper]
):
    ScriptedProvider.analysis = json.dumps({"type": "comparison", "question": QUESTION})
    ScriptedProvider.tables = [json.dumps(TABLE)]

    _, received = await ask(owner, papers)

    assert sorted(steps()) == ["analyze", "embed", "table"]
    assert received[-1][1]["mode"] == "comparison"


@pytest.mark.parametrize("analysis", ['{"type": "factual", "question": "x"}', "no idea", None])
async def test_a_question_that_is_not_recognised_as_more_is_answered_as_a_plain_one(
    owner: AsyncClient, papers: list[Paper], analysis: str | None
):
    ScriptedProvider.analysis = analysis
    ScriptedProvider.fail_at = None if analysis else "analyze"

    _, received = await ask(owner, papers)

    assert sorted(steps()) == ["analyze", "embed", "generate", "rerank"]
    done = received[-1][1]
    assert (done["mode"], done["table"], done["outcome"]) == ("factual", None, "answered")
    assert [name for name, _ in received if name == "status"] == []


@pytest.mark.parametrize("mode", [None, "comparison", "synthesis"])
async def test_one_paper_is_always_answered_as_a_plain_question(
    owner: AsyncClient, papers: list[Paper], mode: str | None
):
    _, received = await ask(owner, papers[:1], mode)

    # Nothing to tell apart: the kind of question is not even asked for.
    assert steps() == ["embed", "rerank", "generate"]
    assert received[-1][1]["mode"] == "factual"


async def test_a_kind_that_was_asked_for_is_not_second_guessed(
    owner: AsyncClient, papers: list[Paper]
):
    ScriptedProvider.analysis = json.dumps({"type": "comparison", "question": QUESTION})

    _, received = await ask(owner, papers, "factual")

    assert steps() == ["embed", "rerank", "generate"]
    assert received[-1][1]["mode"] == "factual"
    refused = await owner.post(
        f"/chats/{(await owner.get('/chats')).json()[0]['id']}/messages",
        json={"content": QUESTION, "mode": "essay"},
    )
    assert refused.status_code == 422


async def test_a_synthesis_is_written_from_what_each_passage_says_about_the_question(
    owner: AsyncClient, papers: list[Paper]
):
    ScriptedProvider.evidence = {
        "weight": json.dumps({"relevance": 7, "summary": "Weight decides the order."}),
        "colour": json.dumps({"relevance": 9, "summary": "Colour decides the order."}),
        # Below the bar: these passages are left out of the answer.
        "counted": json.dumps({"relevance": 2, "summary": "About counting."}),
    }
    ScriptedProvider.answer = "## Overview\nColour [S1] and weight [S2] decide. Never [S3]."

    chat_id, received = await ask(owner, papers, "synthesis")

    assert stages(received) == ["selecting", "gathering", "comparing", "writing"]
    progress = [
        (data["done"], data["total"])
        for name, data in received
        if name == "status" and data["stage"] == "gathering"
    ]
    assert progress == [(0, 4), (1, 4), (2, 4), (3, 4), (4, 4)]
    sources = next(data for name, data in received if name == "sources")
    # The most useful finding first; each source is the passage itself, not its summary.
    assert [(source["marker"], source["snippet"]) for source in sources] == [
        ("S1", GADGETS[0]),
        ("S2", WIDGETS[0]),
    ]
    assert steps() == ["embed", "judge", "judge", "judge", "judge", "generate"]
    assert {call["role"] for call in ScriptedProvider.calls if call["step"] == "judge"} == {"fast"}
    generate = ScriptedProvider.calls[-1]
    assert generate["system"] == prompts.SYNTHESIS_SYSTEM
    content = generate["messages"][-1]["content"]
    assert "Colour decides the order." in content
    assert "Weight decides the order." in content
    assert "counted" not in content and GADGETS[0] not in content
    assert content.endswith(f"Question: {QUESTION}")

    done = received[-1][1]
    assert (done["mode"], done["outcome"], done["table"]) == ("synthesis", "answered", None)
    assert done["text"] == "## Overview\nColour [S1] and weight [S2] decide. Never."
    assert done["citations"] == ["S1", "S2"]
    answer = (await owner.get(f"/chats/{chat_id}/messages")).json()[1]
    assert answer["mode"] == "synthesis"
    assert [source["snippet"] for source in answer["citations"]] == [GADGETS[0], WIDGETS[0]]
    retrieval = (await owner.get(f"/chats/messages/{answer['id']}/retrieval")).json()["retrieval"]
    assert sorted(item["relevance"] for item in retrieval["evidence"]) == [2, 2, 7, 9]
    assert retrieval["evidence_unjudged"] == 0


async def test_a_synthesis_with_nothing_worth_keeping_says_so_without_writing(
    owner: AsyncClient, papers: list[Paper]
):
    low = json.dumps({"relevance": 1, "summary": "Not about this."})
    ScriptedProvider.evidence = {"sorted": low, "counted": low}

    _, received = await ask(owner, papers, "synthesis")

    assert "generate" not in steps()
    done = received[-1][1]
    assert (done["outcome"], done["text"], done["citations"]) == ("no_evidence", NO_EVIDENCE, [])


async def test_nothing_worth_keeping_among_the_few_passages_judged_is_not_nothing_found(
    owner: AsyncClient, papers: list[Paper]
):
    low = json.dumps({"relevance": 1, "summary": "Not about this."})
    ScriptedProvider.evidence = {"sorted by weight": low, "counted": low, "colour": "No idea."}

    _, received = await ask(owner, papers, "synthesis")

    # One passage was never read: the answer is written from the passages as they stand.
    sources = next(data for name, data in received if name == "sources")
    assert [source["snippet"] for source in sources] == [WIDGETS[0], GADGETS[0]]
    assert received[-1][1]["outcome"] == "answered"


async def test_one_passage_that_cannot_be_judged_does_not_cost_the_answer(
    owner: AsyncClient, papers: list[Paper]
):
    ScriptedProvider.evidence = {"colour": "I cannot rate this."}

    _, received = await ask(owner, papers, "synthesis")

    sources = next(data for name, data in received if name == "sources")
    assert GADGETS[0] not in [source["snippet"] for source in sources]
    assert len(sources) == 3
    done = received[-1][1]
    assert done["outcome"] == "answered"
    retrieval = (await owner.get(f"/chats/messages/{done['message_id']}/retrieval")).json()
    assert retrieval["retrieval"]["evidence_unjudged"] == 1


async def test_when_no_passage_can_be_judged_the_synthesis_uses_the_passages_as_they_are(
    owner: AsyncClient, papers: list[Paper]
):
    ScriptedProvider.fail_at = "judge"

    _, received = await ask(owner, papers, "synthesis")

    sources = next(data for name, data in received if name == "sources")
    # Each paper's best passage, word for word.
    assert [source["snippet"] for source in sources] == [WIDGETS[0], GADGETS[0]]
    content = ScriptedProvider.calls[-1]["messages"][-1]["content"]
    assert WIDGETS[0] in content and GADGETS[0] in content
    done = received[-1][1]
    assert (done["mode"], done["outcome"]) == ("synthesis", "answered")


@pytest.mark.parametrize("mode", ["comparison", "synthesis"])
async def test_a_scope_over_the_limit_is_cut_to_the_most_relevant_papers_and_says_so(
    owner: AsyncClient,
    papers: list[Paper],
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
):
    lunch = await ready_paper(db, await user_id(owner), "Lunch Menu", ["Soup is served at noon."])
    limited = get_settings().model_copy(update={"multi_paper_max_papers": 2})
    monkeypatch.setattr("scientrag.rag.engine.get_settings", lambda: limited)
    ScriptedProvider.tables = [json.dumps(TABLE)]
    question = "Widget study and gadget study: how are they sorted?"

    chat_id, received = await ask(owner, [lunch, *papers], mode, question)

    notice = "Only the 2 most relevant of the 3 papers in scope were considered."
    assert received[-1][1]["notice"] == notice
    sources = next(data for name, data in received if name == "sources")
    assert {source["paper_title"] for source in sources} == {"Widget Study", "Gadget Study"}
    answer = (await owner.get(f"/chats/{chat_id}/messages")).json()[1]
    assert answer["notice"] == notice


async def test_papers_that_say_nothing_at_all_end_the_comparison_without_a_model_call(
    owner: AsyncClient, db: AsyncSession
):
    account = await user_id(owner)
    empty = [await ready_paper(db, account, f"Empty {n}", []) for n in range(2)]

    _, received = await ask(owner, empty, "comparison")

    assert steps() == ["embed"]
    done = received[-1][1]
    assert (done["outcome"], done["text"], done["mode"]) == (
        "no_evidence",
        NO_EVIDENCE,
        "comparison",
    )
