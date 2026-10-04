import json

from scientrag.ingestion.steps import DOI, _clean_metadata, _summary_input
from scientrag.parsing.document import Block, ScientificDocument, Section


def clean(value) -> dict:
    return _clean_metadata(json.dumps(value))


def test_metadata_from_the_model_is_kept_only_in_the_expected_shape():
    assert clean({"title": " A Paper ", "authors": [" Ada ", "", 7, "Alan"], "year": 2021}) == {
        "title": "A Paper",
        "authors": ["Ada", "Alan"],
        "year": 2021,
    }
    assert clean({"title": None, "authors": None, "year": None}) == {}
    assert clean({"title": "", "authors": "Ada", "year": "2021"}) == {}
    assert clean(["not", "an", "object"]) == {}
    assert _clean_metadata("Sure! Here is the JSON you asked for") == {}


def test_metadata_values_are_bounded():
    found = clean({"title": "t" * 5000, "authors": ["a" * 900] * 500, "year": 2021})
    assert len(found["title"]) == 1000
    assert len(found["authors"]) == 200
    assert len(found["authors"][0]) == 255
    for year in (999, 2101, True, 20.21):
        assert "year" not in clean({"year": year})
    assert clean({"year": 1000})["year"] == 1000
    assert clean({"year": 2100})["year"] == 2100


def test_a_doi_is_found_in_running_text():
    assert DOI.search("see https://doi.org/10.48550/arXiv.1706.03762 for more").group() == (
        "10.48550/arXiv.1706.03762"
    )
    assert DOI.search("version 10.5 of the tool") is None


def test_the_summary_input_is_the_opening_of_each_section_and_is_bounded():
    sections = [Section(index=i, parent=None, level=1, title=f"S{i}", page=1) for i in range(40)]
    blocks = [
        Block(kind="text", text=f"{i}-" + "x" * 2000, page=1, bbox=(0, 0, 1, 1), section=i // 2)
        for i in range(80)
    ]
    blocks.insert(0, Block(kind="table", text="| t |", page=1, bbox=(0, 0, 1, 1), section=0))
    document = ScientificDocument(
        title="T", page_count=1, sections=sections, blocks=blocks, warnings=[]
    )

    text = _summary_input(document)

    assert len(text) <= 8000
    assert text.startswith("S0\n0-x")
    # One paragraph per section, and no tables.
    assert "1-x" not in text
    assert "| t |" not in text
    assert "S1\n2-x" in text
