from scirag.evaluation.evidence_mapping import coverage, covering_chunks

PASSAGE = (
    "We train the model on the WMT 2014 English-German dataset consisting of about 4.5 million "
    "sentence pairs. Sentences were encoded using byte-pair encoding, which has a shared "
    "source-target vocabulary of about 37000 tokens."
)
OTHER = "The model was trained on eight GPUs for twelve hours with the Adam optimizer."


def test_a_chunk_that_contains_the_passage_holds_it():
    chunks = [("c1", f"Training data.\n\n{PASSAGE}\n\nHardware."), ("c2", OTHER)]

    assert covering_chunks(PASSAGE, chunks) == {"c1"}


def test_a_passage_cut_in_two_is_held_by_both_chunks():
    words = PASSAGE.split()
    half = len(words) // 2
    chunks = [("c1", " ".join(words[:half])), ("c2", " ".join(words[half:])), ("c3", OTHER)]

    assert covering_chunks(PASSAGE, chunks) == {"c1", "c2"}


def test_sharing_common_words_is_not_holding_the_passage():
    scattered = "The dataset of the model was about the source of the encoding which has pairs."

    assert coverage(PASSAGE, scattered) < 0.1
    assert covering_chunks(PASSAGE, [("c1", scattered)]) == set()


def test_spacing_case_and_line_breaks_do_not_matter():
    reflowed = PASSAGE.upper().replace(" ", "\n", 5).replace(".", " . ")

    assert coverage(PASSAGE, reflowed) == 1.0


def test_a_short_quote_is_matched_whole():
    assert covering_chunks("beta1 = 0.9", [("c1", "we set beta1 = 0.9 and"), ("c2", "beta1")]) == {
        "c1"
    }


def test_an_empty_passage_is_held_by_nothing():
    assert covering_chunks("", [("c1", PASSAGE)]) == set()
