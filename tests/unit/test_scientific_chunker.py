from scirag.chunking.scientific_chunker import chunk_document, count_tokens
from scirag.parsing.document import Block, ScientificDocument, Section

BOX = (0.1, 0.2, 0.9, 0.3)


def section(index: int, title: str, parent: int | None = None, level: int = 1) -> Section:
    return Section(index=index, parent=parent, level=level, title=title, page=1)


def block(text: str, kind: str = "text", section: int | None = 0, page: int = 1) -> Block:
    return Block(kind=kind, text=text, page=page, bbox=BOX, section=section)


def document(sections: list[Section], blocks: list[Block]) -> ScientificDocument:
    return ScientificDocument(
        title="Paper", page_count=3, sections=sections, blocks=blocks, warnings=[]
    )


def chunks(sections: list[Section], blocks: list[Block], max_tokens: int = 100):
    return chunk_document(document(sections, blocks), title="Paper", max_tokens=max_tokens)


def test_short_paragraphs_of_one_section_are_merged():
    result = chunks([section(0, "1 Introduction")], [block("First."), block("Second.", page=2)])

    assert len(result) == 1
    chunk = result[0]
    assert chunk.text == "First.\n\nSecond."
    assert chunk.kind == "text"
    assert (chunk.page_start, chunk.page_end) == (1, 2)
    assert chunk.bboxes == [
        {"page": 1, "bbox": list(BOX)},
        {"page": 2, "bbox": list(BOX)},
    ]
    assert chunk.token_count == count_tokens(chunk.text)


def test_a_chunk_never_crosses_a_heading():
    result = chunks(
        [section(0, "1 Introduction"), section(1, "2 Method")],
        [block("Intro."), block("Method.", section=1)],
    )

    assert [chunk.text for chunk in result] == ["Intro.", "Method."]
    assert [chunk.section_path for chunk in result] == [["1 Introduction"], ["2 Method"]]


def test_paragraphs_are_split_when_the_limit_is_reached():
    paragraph = "word " * 60  # 75 tokens
    result = chunks([section(0, "1 Introduction")], [block(paragraph)] * 3)

    assert len(result) == 3
    assert all(chunk.token_count <= 100 for chunk in result)


def test_a_paragraph_longer_than_the_limit_is_cut_at_sentence_ends():
    sentence = "This sentence is exactly forty chars ok. "
    result = chunks([section(0, "1 Introduction")], [block(sentence * 30)], max_tokens=50)

    assert len(result) > 1
    assert all(chunk.token_count <= 50 for chunk in result)
    assert all(chunk.text.endswith(".") for chunk in result)
    # Nothing is lost.
    assert "".join(chunk.text for chunk in result).count("forty") == 30


def test_tables_captions_and_formulas_are_chunks_of_their_own():
    result = chunks(
        [section(0, "3 Results")],
        [
            block("Before."),
            block("| a | b |", kind="table"),
            block("Table 1: Scores.", kind="caption"),
            block("E = mc^2", kind="formula"),
            block("After."),
        ],
    )

    assert [chunk.kind for chunk in result] == ["text", "table", "caption", "formula", "text"]
    assert [chunk.index for chunk in result] == [0, 1, 2, 3, 4]


def test_references_are_kept_apart_from_the_body():
    result = chunks(
        [section(0, "References")],
        [block("Body."), block("[1] A.", kind="reference"), block("[2] B.", kind="reference")],
    )

    assert [(chunk.kind, chunk.text) for chunk in result] == [
        ("text", "Body."),
        ("reference", "[1] A.\n\n[2] B."),
    ]


def test_the_embedded_text_carries_the_title_and_the_section_path():
    sections = [section(0, "3 Method"), section(1, "3.1 Training", parent=0, level=2)]
    result = chunks(sections, [block("We train.", section=1), block("Abstract.", section=None)])

    assert result[0].section_path == ["3 Method", "3.1 Training"]
    assert result[0].embed_text == "Paper\n3 Method > 3.1 Training\nWe train."
    # The stored text is what the paper says, nothing added.
    assert result[0].text == "We train."
    assert result[1].section_path == []
    assert result[1].embed_text == "Paper\nAbstract."


def test_an_empty_document_gives_no_chunks():
    assert chunks([], []) == []
