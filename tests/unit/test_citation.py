from scientrag.rag.citation import validate, without_markers

VALID = {"S1", "S2", "S3"}


def test_markers_of_given_passages_are_kept_in_order_of_first_use():
    text, used = validate("Adam adapts the step size [S2]. It needs little tuning [S1][S2].", VALID)

    assert text == "Adam adapts the step size [S2]. It needs little tuning [S1][S2]."
    assert used == ["S2", "S1"]


def test_an_invented_marker_is_removed_without_leaving_a_gap():
    text, used = validate("The rate decays [S9]. Bias is corrected [S1], then [S7] used.", VALID)

    assert text == "The rate decays. Bias is corrected [S1], then used."
    assert used == ["S1"]


def test_markers_written_together_are_checked_one_by_one():
    text, used = validate("It converges [S1][S8][S3].", VALID)

    assert text == "It converges [S1][S3]."
    assert used == ["S1", "S3"]


def test_a_group_in_one_bracket_becomes_separate_markers():
    text, used = validate("It converges [S1, S3; S9] and [ S2 ].", VALID)

    assert text == "It converges [S1][S3] and [S2]."
    assert used == ["S1", "S3", "S2"]


def test_markers_inside_code_are_left_alone_and_not_counted():
    answer = "Index it as `x[S9]` [S1].\n```python\nrow = table[S2]  # [S8]\n```\nDone [S3]."

    text, used = validate(answer, VALID)

    assert text == answer
    assert used == ["S1", "S3"]


def test_an_answer_without_markers_cites_nothing():
    assert validate("I could not find this in the selected papers.", VALID) == (
        "I could not find this in the selected papers.",
        [],
    )


def test_other_bracketed_text_is_not_a_marker():
    text, used = validate("See [1], [Section 2] and array[S] [s1].", VALID)

    assert text == "See [1], [Section 2] and array[S] [s1]."
    assert used == []


def test_text_around_the_markers_keeps_its_spacing():
    text = "Points :\n- outer [S1]\n  - inner item [S9]\nBonjour !  \nvalue of .5 [S1, S9]"

    clean, used = validate(text, {"S1"})

    assert clean == "Points :\n- outer [S1]\n  - inner item\nBonjour !  \nvalue of .5 [S1]"
    assert used == ["S1"]


def test_an_earlier_answer_loses_all_its_markers():
    assert without_markers("Sorted by weight [S1][S2]. Floats [S3, S4].") == (
        "Sorted by weight. Floats."
    )
