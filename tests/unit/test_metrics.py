import pytest

from scirag.evaluation.metrics import mrr, ndcg_at_k, percentile, recall_at_k, token_f1

RANKED = ["a", "b", "c", "d", "e"]


def test_recall_is_the_share_of_evidence_passages_found_in_the_first_k():
    evidence = [{"b"}, {"e"}, {"x"}]

    assert recall_at_k(RANKED, evidence, 3) == pytest.approx(1 / 3)
    assert recall_at_k(RANKED, evidence, 5) == pytest.approx(2 / 3)


def test_a_passage_split_over_two_chunks_is_found_by_either_one():
    assert recall_at_k(RANKED, [{"x", "c"}], 3) == 1.0
    assert recall_at_k(RANKED, [{"x", "c"}], 2) == 0.0


def test_mrr_is_one_over_the_rank_of_the_first_evidence_chunk():
    assert mrr(RANKED, {"c", "e"}) == pytest.approx(1 / 3)
    assert mrr(RANKED, {"x"}) == 0.0


def test_ndcg_rewards_evidence_near_the_top():
    # Two relevant chunks at ranks 1 and 3; the ideal order has them at ranks 1 and 2.
    expected = (1 + 1 / 2) / (1 + 1 / 1.5849625007211562)

    assert ndcg_at_k(RANKED, {"a", "c"}, 5) == pytest.approx(expected)
    assert ndcg_at_k(RANKED, {"a", "b"}, 5) == 1.0
    assert ndcg_at_k(RANKED, {"e"}, 3) == 0.0


def test_token_f1_ignores_case_punctuation_and_articles():
    assert token_f1("The BLEU score.", "bleu score") == 1.0
    assert token_f1("accuracy and BLEU", "BLEU") == pytest.approx(0.5)
    assert token_f1("nothing alike", "BLEU") == 0.0


def test_percentile_takes_the_nearest_rank():
    values = [50, 10, 40, 20, 30]

    assert percentile(values, 0.5) == 30
    assert percentile(values, 0.95) == 50
    assert percentile([7], 0.95) == 7
