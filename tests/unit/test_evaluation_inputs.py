import pytest

from scientrag.chunking.scientific_chunker import chunk_document
from scientrag.config import get_settings
from scientrag.evaluation import judges, metrics, report, runner
from scientrag.evaluation.datasets import qasper

PAPER = {
    "title": "A Study of Widgets",
    "abstract": "We study widgets.",
    "full_text": [
        {"section_name": "Introduction", "paragraphs": ["Widgets matter.", ""]},
        {"section_name": "Method ::: Data", "paragraphs": ["We use the WIDGET-1 corpus."]},
    ],
    "qas": [
        {
            "question_id": "q1",
            "question": "Which corpus is used?",
            "answers": [
                {
                    "answer": {
                        "unanswerable": False,
                        "extractive_spans": ["WIDGET-1"],
                        "yes_no": None,
                        "free_form_answer": "",
                        "evidence": ["FLOAT SELECTED: Table 1", "We use the WIDGET-1 corpus."],
                    }
                }
            ],
        },
        {
            "question_id": "q2",
            "question": "What is shown in the figure?",
            "answers": [
                {
                    "answer": {
                        "unanswerable": False,
                        "extractive_spans": [],
                        "yes_no": None,
                        "free_form_answer": "A widget",
                        "evidence": ["FLOAT SELECTED: Figure 1"],
                    }
                }
            ],
        },
    ],
}


def test_a_qasper_paper_keeps_its_sections_and_goes_through_the_chunker():
    document = qasper.to_document(PAPER)

    assert [section.title for section in document.sections] == [
        "Abstract",
        "Introduction",
        "Method",
        "Data",
    ]
    assert document.section_path(document.blocks[-1].section) == ["Method", "Data"]
    chunks = chunk_document(document, title=PAPER["title"], max_tokens=400)
    assert [chunk.text for chunk in chunks] == [
        "We study widgets.",
        "Widgets matter.",
        "We use the WIDGET-1 corpus.",
    ]


def test_only_questions_answerable_from_text_are_kept():
    kept = [qasper._question("p1", item) for item in PAPER["qas"]]

    assert kept[0].evidence == ["We use the WIDGET-1 corpus."]
    assert kept[0].reference == "WIDGET-1"
    assert kept[1] is None


def test_sentences_are_paired_with_the_passages_they_cite():
    answer = "Widgets float [S1][S2]. They are blue.\n- Sorted by weight [S2, S9]."

    assert judges.cited_sentences(answer, {"S1": "one", "S2": "two"}) == [
        {"sentence": "Widgets float [S1][S2].", "markers": ["S1", "S2"]},
        {"sentence": "- Sorted by weight [S2, S9].", "markers": ["S2"]},
    ]


def test_a_judge_reply_of_the_wrong_shape_is_not_used():
    assert judges._flags({"useful": [True, False]}, "useful", None, 2) == [True, False]
    assert judges._flags({"useful": [True]}, "useful", None, 2) is None
    assert judges._flags({"useful": ["yes"]}, "useful", None) is None
    assert judges._flags([True], "useful", None) is None
    assert judges._flags({"claims": [{"supported": True}]}, "claims", "supported") == [True]


def _result(name: str, recalls: dict[str, float | None]) -> dict:
    """A saved run. None stands for a question the provider refused."""
    rows = [
        {"id": question, "error": "rate_limited"}
        if recall is None
        else {"id": question, "recall@8": recall, "total_ms": 900}
        for question, recall in recalls.items()
    ]
    return {
        "name": name,
        "commit": "abc1234",
        "dataset": {"name": "qasper", "papers": 2, "questions": len(rows), "errors": 0},
        "metrics": metrics.summary(rows),
        "rows": rows,
    }


def test_two_runs_are_compared_on_the_questions_both_answered():
    baseline = _result("baseline", {"a": 1.0, "b": 0.0, "c": 1.0})
    fewer = _result("rerank-15", {"a": 1.0, "b": 0.5, "c": None})

    text = report.comparison(baseline, fewer)

    assert "On the 2 questions both runs answered." in text
    assert "| recall@8 | 0.500 | 0.750 | +0.250 |" in text
    assert "| total_ms | 900 / 900 | 900 / 900 | +0 |" in text
    assert "| recall@8 | 0.667 | 3 |" in report.table(baseline)


def test_a_mistyped_experiment_is_refused():
    with pytest.raises(ValueError):
        runner.RunConfig(name="a", dataset="qaspr")
    with pytest.raises(ValueError):
        runner._apply(
            runner.RunConfig(name="a", dataset="qasper", settings={"search_fusion": "dense"})
        )
    with pytest.raises(ValueError):
        runner._apply(
            runner.RunConfig(name="a", dataset="qasper", settings={"rerank_enabled": "no"})
        )


def test_an_experiment_does_not_inherit_the_settings_of_the_one_before(monkeypatch):
    settings = get_settings().model_copy()
    monkeypatch.setattr(runner, "get_settings", lambda: settings)
    monkeypatch.setattr(runner, "_APPLICATION", {})
    before = (settings.rerank_enabled, settings.search_fusion)

    changed = runner.RunConfig(
        name="a", dataset="qasper", settings={"rerank_enabled": False, "search_fusion": "dbsf"}
    )
    assert runner._apply(changed)["search_fusion"] == "dbsf"

    in_force = runner._apply(runner.RunConfig(name="b", dataset="qasper"))
    assert (in_force["rerank_enabled"], in_force["search_fusion"]) == before


def test_measures_are_averaged_over_the_questions_that_have_them():
    rows = [
        {
            "id": "a",
            "answerable": True,
            "mrr": 1.0,
            "retrieved_ms": 100,
            "tokens": {"fast": [10, 2]},
        },
        {"id": "b", "answerable": True, "mrr": 0.5, "retrieved_ms": 300, "faithfulness": None},
        # A question the provider refused has no measures and counts in none of them.
        {"id": "c", "answerable": True, "error": "rate_limited"},
    ]

    summary = metrics.summary(rows)

    assert summary["mrr"] == {"mean": 0.75, "n": 2}
    assert summary["retrieved_ms"] == {"p50": 100, "p95": 300, "n": 2}
    assert summary["tokens_fast_input"] == {"mean": 10, "n": 1}
    assert "faithfulness" not in summary
    assert "answerable" not in summary


def test_a_question_is_scored_on_the_passages_ranked_and_on_those_found_before_ranking():
    scores = runner._retrieval_scores(
        ranked=["x", "a", "y"],
        candidates=["a", "x", "y", "b"],
        evidence=[{"a"}, {"b"}],
        context_chunks=3,
    )

    assert scores["recall@1"] == 0.0
    assert scores["recall@3"] == 0.5
    assert scores["mrr"] == 0.5
    assert scores["candidate_recall"] == 1.0
    # Only as many passages as reach the model are scored.
    assert "recall@5" not in scores
