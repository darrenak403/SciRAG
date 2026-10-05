"""Reading what the models reply when asked for JSON: the kind of question,
a passage's worth as evidence, and a comparison table."""

import json
import uuid

import pytest

from scirag.providers.errors import ProviderError
from scirag.rag import evidence_summarizer
from scirag.rag.analyzer import parse_analysis
from scirag.rag.evidence_summarizer import Evidence, parse_evidence
from scirag.rag.paths.comparison import NOT_FOUND, NOT_STATED, parse_table
from scirag.rag.types import Source

QUESTION = "How do they differ?"


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        (
            '{"type": "comparison", "question": "How do A and B differ?"}',
            ("comparison", "How do A and B differ?"),
        ),
        (
            'Here you go:\n```json\n{"type": "synthesis", "question": "Trends?"}\n```',
            ("synthesis", "Trends?"),
        ),
        ('{"type": "factual", "question": "What is X?"}', ("factual", "What is X?")),
        # Anything that cannot be read, or names no known kind, is a factual question.
        ('{"type": "essay", "question": "What is X?"}', ("factual", "What is X?")),
        ('{"type": "comparison"}', ("comparison", QUESTION)),
        ('{"type": "comparison", "question": ""}', ("comparison", QUESTION)),
        ('{"type": "comparison", "question": 7}', ("comparison", QUESTION)),
        ("comparison", ("factual", QUESTION)),
        ("[1, 2]", ("factual", QUESTION)),
        ("{broken", ("factual", QUESTION)),
        ("", ("factual", QUESTION)),
    ],
)
def test_the_kind_of_question_is_read_from_the_reply(reply: str, expected: tuple[str, str]):
    assert parse_analysis(reply, QUESTION) == expected


def test_a_runaway_rewrite_is_not_used():
    reply = json.dumps({"type": "synthesis", "question": "x" * 5000})

    assert parse_analysis(reply, QUESTION) == ("synthesis", QUESTION)


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        (
            '{"relevance": 7, "summary": "It  sorts\\nby weight."}',
            Evidence(7, "It sorts by weight."),
        ),
        ('Sure: {"relevance": 14.6, "summary": "x"}', Evidence(10, "x")),
        ('{"relevance": -3}', Evidence(0, "")),
        ('{"relevance": 5, "summary": null}', Evidence(5, "")),
    ],
)
def test_a_passage_s_worth_is_read_from_the_reply(reply: str, expected: Evidence):
    assert parse_evidence(reply) == expected


@pytest.mark.parametrize(
    "reply",
    ["", "seven", '{"summary": "x"}', '{"relevance": true}', "[7]", '{"relevance": Infinity}'],
)
def test_a_reply_without_a_score_is_refused(reply: str):
    with pytest.raises(ValueError):
        parse_evidence(reply)


A, B, C = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
PAPERS = {"P1": A, "P2": B, "P3": C}
TITLES = {A: "Paper A", B: "Paper B", C: "Paper C"}


def source(marker: str, paper_id: uuid.UUID) -> Source:
    return Source(marker, uuid.uuid4(), paper_id, TITLES[paper_id], 1, [], "snippet")


SOURCES = [source("S1", A), source("S2", A), source("S3", B)]


def table(reply: dict) -> tuple[dict, str, list[str]]:
    return parse_table(json.dumps(reply), PAPERS, SOURCES, TITLES)


def test_every_paper_gets_exactly_one_row_in_the_order_it_was_given():
    parsed, summary, used = table(
        {
            "columns": ["Method", "Data"],
            "rows": [
                {"paper": "P2", "cells": ["Sorts by colour [S3].", "Not stated"]},
                {"paper": "P1", "cells": ["Sorts by weight [S1][S2]", "Ten widgets [S2]"]},
                # A second row for the same paper, and a row for a paper nobody gave.
                {"paper": "P1", "cells": ["Again", "Again"]},
                {"paper": "P9", "cells": ["Unknown", "Unknown"]},
            ],
            "summary": "A sorts by weight [S1], B by colour [S3].",
        }
    )

    assert parsed["columns"] == ["Method", "Data"]
    assert [row["paper_title"] for row in parsed["rows"]] == ["Paper A", "Paper B", "Paper C"]
    assert [row["paper_id"] for row in parsed["rows"]] == [str(A), str(B), str(C)]
    assert parsed["rows"][0]["cells"] == [
        {"text": "Sorts by weight", "markers": ["S1", "S2"]},
        {"text": "Ten widgets", "markers": ["S2"]},
    ]
    assert parsed["rows"][1]["cells"][0] == {"text": "Sorts by colour.", "markers": ["S3"]}
    # The paper the model left out is still listed, as not found.
    assert parsed["rows"][2]["cells"] == [{"text": NOT_FOUND, "markers": []}] * 2
    assert summary == "A sorts by weight [S1], B by colour [S3]."
    assert sorted(used) == ["S1", "S2", "S3"]


def test_a_cell_cannot_cite_a_passage_of_another_paper_or_one_that_was_not_given():
    parsed, summary, used = table(
        {
            "columns": ["Method"],
            "rows": [{"paper": "P2", "cells": ["Sorts by weight [S1][S3][S8]"]}],
            "summary": "See [S8].",
        }
    )

    assert parsed["rows"][1]["cells"] == [{"text": "Sorts by weight", "markers": ["S3"]}]
    assert (summary, used) == ("See.", ["S3"])


def test_missing_and_malformed_cells_are_filled_in_as_not_stated():
    parsed, _, used = table(
        {
            "columns": ["Method", "Data", "Result"],
            "rows": [{"paper": "P1", "cells": ["[S1]", None]}, {"paper": "P2", "cells": "none"}],
        }
    )

    empty = {"text": NOT_STATED, "markers": []}
    # A cell that is only a marker says nothing: the marker goes with it.
    assert parsed["rows"][0]["cells"] == [empty, empty, empty]
    assert parsed["rows"][1]["cells"] == [empty, empty, empty]
    assert used == []


def test_no_more_than_six_columns_are_kept():
    parsed, _, _ = table(
        {
            "columns": [f"C{n}" for n in range(9)] + ["", 4],
            "rows": [{"paper": "P1", "cells": [f"v{n}" for n in range(9)]}],
        }
    )

    assert parsed["columns"] == [f"C{n}" for n in range(6)]
    assert len(parsed["rows"][0]["cells"]) == 6


@pytest.mark.parametrize(
    "reply",
    [
        "not json",
        "[]",
        '{"rows": [{"paper": "P1", "cells": ["x"]}]}',
        '{"columns": [], "rows": [{"paper": "P1", "cells": ["x"]}]}',
        '{"columns": ["Method"], "rows": []}',
        '{"columns": ["Method"], "rows": [{"paper": "P9", "cells": ["x"]}]}',
        '{"columns": ["Method"], "rows": ["P1"]}',
        '{"columns": "Method", "rows": [{"paper": "P1", "cells": ["x"]}]}',
        '{"columns": ["Method"], "rows": 5}',
        '{"columns": ["Method"], "rows": [{"paper": ["P1"], "cells": ["x"]}]}',
    ],
)
def test_a_reply_without_a_usable_table_is_refused(reply: str):
    with pytest.raises(ValueError):
        parse_table(reply, PAPERS, SOURCES, TITLES)


async def test_a_fast_model_that_is_down_is_not_asked_about_every_passage():
    class Down:
        calls = 0

        async def complete(self, *_, **__) -> str:
            Down.calls += 1
            raise ProviderError("provider_unreachable")

    gathering = evidence_summarizer.gather(Down(), "q", ["passage"] * 30, parallel=2, timeout=5)
    results = [evidence async for _, evidence in gathering]

    assert results == [None] * 30
    assert Down.calls == evidence_summarizer.GIVE_UP_AFTER


def test_the_ids_papers_had_in_the_prompt_do_not_reach_the_reader():
    _, summary, _ = table(
        {
            "columns": ["Method"],
            "rows": [{"paper": "P1", "cells": ["x"]}],
            "summary": "Adam (P1) adapts the step [S1]; the other (paper P2) does not.",
        }
    )

    assert summary == "Adam adapts the step [S1]; the other does not."
