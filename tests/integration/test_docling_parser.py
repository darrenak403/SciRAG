"""The real PDF parser. Only runs where it is installed: the worker image."""

from pathlib import Path

import pytest

pytest.importorskip("docling")

from scirag.ingestion.errors import PermanentIngestionError  # noqa: E402
from scirag.parsing.docling_parser import check_pdf, parse_pdf  # noqa: E402
from tests.conftest import pdf_bytes  # noqa: E402
from tests.pdf_factory import text_pdf  # noqa: E402

LINES = [
    "A Study of Widgets",
    "",
    "1 Introduction",
    "Widgets are small parts that are used in many machines around the world.",
    "This paper studies how the weight of a widget changes how long it lasts.",
    "We measure four thousand widgets over three years in two factories.",
    "",
    "2 Results",
    "Heavier widgets last longer, but only up to a weight of forty grams.",
    "Beyond that weight the lifetime falls again, which earlier work missed.",
]


def write(tmp_path: Path, content: bytes) -> Path:
    path = tmp_path / "paper.pdf"
    path.write_bytes(content)
    return path


def test_a_pdf_with_text_is_parsed_into_blocks_with_positions(tmp_path: Path):
    document = parse_pdf(write(tmp_path, text_pdf(LINES)), max_pages=10)

    assert document.page_count == 1
    text = " ".join(block.text for block in document.blocks)
    assert "four thousand widgets" in text
    assert "forty grams" in text
    for block in document.blocks:
        left, top, right, bottom = block.bbox
        # Fractions of the page, measured from the top-left corner.
        assert 0 <= left < right <= 1
        assert 0 <= top < bottom <= 1
        assert block.page == 1
    # The text starts near the top of the page, not the bottom.
    assert document.blocks[0].bbox[1] < 0.5


def test_a_pdf_without_a_text_layer_is_refused_as_scanned(tmp_path: Path):
    with pytest.raises(PermanentIngestionError) as raised:
        parse_pdf(write(tmp_path, text_pdf([])), max_pages=10)

    assert raised.value.code == "scanned_pdf"


def test_a_damaged_file_is_refused_before_any_model_runs(tmp_path: Path):
    with pytest.raises(PermanentIngestionError) as raised:
        check_pdf(write(tmp_path, pdf_bytes("not really a pdf")), max_pages=10)

    assert raised.value.code == "unreadable_pdf"


def test_a_pdf_over_the_page_limit_is_refused(tmp_path: Path):
    with pytest.raises(PermanentIngestionError) as raised:
        check_pdf(write(tmp_path, text_pdf(LINES)), max_pages=0)

    assert raised.value.code == "too_many_pages"
