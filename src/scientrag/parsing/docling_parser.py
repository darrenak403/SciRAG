"""PDF to ScientificDocument with Docling.

Imported only by the worker: Docling pulls in PyTorch. The layout and table
models are loaded when the first paper arrives, so an idle worker holds no
model in memory.
"""

import re
from functools import lru_cache
from pathlib import Path

import pypdfium2
from docling.datamodel.base_models import ConversionStatus, InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc import DocItemLabel, DoclingDocument, TableItem

from scientrag.ingestion.errors import PermanentIngestionError
from scientrag.parsing.document import BBox, Block, BlockKind, ScientificDocument, Section

# Below this many characters per page on average, the PDF is page images without a text layer.
MIN_CHARS_PER_PAGE = 100
# A paper that takes longer is cut off there, so one file cannot hold the worker forever.
PARSE_TIMEOUT_SECONDS = 900
NOT_A_TITLE = re.compile(r"^\W*(\d+\.?\s*)?(abstract|introduction)\W*$", re.IGNORECASE)
REFERENCES_TITLE = re.compile(r"^\W*(\d+\.?\s*)?(references|bibliography)\W*$", re.IGNORECASE)
# "3.1.2 Training" is three levels deep.
SECTION_NUMBER = re.compile(r"^\s*(\d+(?:\.\d+)*)\.?\s")

KINDS: dict[DocItemLabel, BlockKind] = {
    DocItemLabel.TEXT: "text",
    DocItemLabel.PARAGRAPH: "text",
    DocItemLabel.LIST_ITEM: "text",
    DocItemLabel.FOOTNOTE: "text",
    DocItemLabel.CODE: "text",
    DocItemLabel.REFERENCE: "reference",
    DocItemLabel.CAPTION: "caption",
    DocItemLabel.FORMULA: "formula",
    DocItemLabel.TABLE: "table",
}


def check_pdf(path: Path, max_pages: int) -> int:
    """Rejects a PDF that cannot be ingested, before any model is loaded. Returns its page count."""
    try:
        pdf = pypdfium2.PdfDocument(path)
    except pypdfium2.PdfiumError as error:
        if "password" in str(error).lower():
            raise PermanentIngestionError(
                "unreadable_pdf", "The PDF is password-protected. Upload a copy without a password."
            ) from error
        raise PermanentIngestionError(
            "unreadable_pdf", "The file is damaged or is not a valid PDF."
        ) from error
    try:
        pages = len(pdf)
    finally:
        pdf.close()
    if pages == 0:
        raise PermanentIngestionError("unreadable_pdf", "The PDF has no pages.")
    if pages > max_pages:
        raise PermanentIngestionError(
            "too_many_pages", f"The PDF has {pages} pages; the limit is {max_pages}."
        )
    return pages


@lru_cache
def _converter() -> DocumentConverter:
    # OCR is off: scanned PDFs are rejected instead of being read slowly and badly.
    options = PdfPipelineOptions(
        do_ocr=False, do_table_structure=True, document_timeout=PARSE_TIMEOUT_SECONDS
    )
    return DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
    )


def parse_pdf(path: Path, max_pages: int) -> ScientificDocument:
    check_pdf(path, max_pages)
    result = _converter().convert(path, raises_on_error=False, max_num_pages=max_pages)
    if result.status not in (ConversionStatus.SUCCESS, ConversionStatus.PARTIAL_SUCCESS):
        raise PermanentIngestionError("parse_failed", "The PDF could not be parsed.")
    document = from_docling(result.document)
    if result.status == ConversionStatus.PARTIAL_SUCCESS:
        document.warnings.append("Some pages could not be parsed.")
    return document


def _bbox(document: DoclingDocument, provenance) -> BBox:
    size = document.pages[provenance.page_no].size
    box = provenance.bbox.to_top_left_origin(page_height=size.height)

    def fraction(value: float, total: float) -> float:
        return round(min(max(value / total, 0.0), 1.0), 4)

    return (
        fraction(box.l, size.width),
        fraction(box.t, size.height),
        fraction(box.r, size.width),
        fraction(box.b, size.height),
    )


def _level(title: str) -> int:
    numbered = SECTION_NUMBER.match(title)
    return numbered.group(1).count(".") + 1 if numbered else 1


def from_docling(document: DoclingDocument) -> ScientificDocument:
    """Docling's document as ours. Page headers and footers are left out."""
    title: str | None = None
    sections: list[Section] = []
    blocks: list[Block] = []
    current: int | None = None
    in_references = False
    formulas_without_text = 0
    tables_without_text = 0

    for item, _ in document.iterate_items():
        provenance = item.prov[0] if getattr(item, "prov", None) else None
        if provenance is None:
            continue
        label = item.label

        if label == DocItemLabel.TITLE:
            title = title or item.text.strip() or None
            continue
        if label == DocItemLabel.SECTION_HEADER:
            heading = item.text.strip()
            if not heading:
                continue
            if (
                title is None
                and not sections
                and not blocks
                and provenance.page_no == 1
                and not NOT_A_TITLE.match(heading)
            ):
                # Docling often labels the paper's title as the first heading.
                title = heading
                continue
            level = _level(heading)
            parent = current
            while parent is not None and sections[parent].level >= level:
                parent = sections[parent].parent
            sections.append(
                Section(
                    index=len(sections),
                    parent=parent,
                    level=level,
                    title=heading,
                    page=provenance.page_no,
                )
            )
            current = len(sections) - 1
            in_references = bool(REFERENCES_TITLE.match(heading))
            continue

        kind = KINDS.get(label)
        if kind is None:
            continue
        if isinstance(item, TableItem):
            text = item.export_to_markdown(doc=document).strip()
            tables_without_text += not text
        else:
            # A formula Docling could not turn into LaTeX keeps its raw characters in orig.
            text = (item.text or getattr(item, "orig", "") or "").strip()
            if kind == "formula":
                formulas_without_text += not item.text
        if not text:
            continue
        if in_references and kind == "text":
            kind = "reference"
        blocks.append(
            Block(
                kind=kind,
                text=text,
                page=provenance.page_no,
                bbox=_bbox(document, provenance),
                section=current,
            )
        )

    pages = len(document.pages)
    if sum(len(block.text) for block in blocks) < MIN_CHARS_PER_PAGE * max(pages, 1):
        raise PermanentIngestionError(
            "scanned_pdf",
            "No text could be read from the PDF. Scanned documents are not supported: "
            "upload a PDF with selectable text.",
        )

    warnings = []
    if formulas_without_text:
        warnings.append(
            f"{formulas_without_text} formulas were read as plain characters, not as formulas."
        )
    if tables_without_text:
        warnings.append(f"{tables_without_text} tables could not be read.")
    if not sections:
        warnings.append("No section headings were found.")
    return ScientificDocument(
        title=title, page_count=pages, sections=sections, blocks=blocks, warnings=warnings
    )
