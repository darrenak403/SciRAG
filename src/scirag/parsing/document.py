"""The parsed form of a paper, independent of which parser produced it."""

from typing import Literal

from pydantic import BaseModel

BlockKind = Literal["text", "table", "caption", "formula", "reference"]
# Fractions of the page, origin top-left: (left, top, right, bottom).
BBox = tuple[float, float, float, float]


class Section(BaseModel):
    """A heading. index is its position in ScientificDocument.sections."""

    index: int
    parent: int | None
    level: int
    title: str
    page: int


class Block(BaseModel):
    """A piece of content in reading order: a paragraph, a table, a caption or a formula."""

    kind: BlockKind
    text: str
    page: int
    bbox: BBox
    # Index of the section the block sits under; None before the first heading.
    section: int | None


class ScientificDocument(BaseModel):
    title: str | None
    page_count: int
    sections: list[Section]
    blocks: list[Block]
    # Things that did not parse well but do not stop the paper from being used.
    warnings: list[str]

    def section_path(self, index: int | None) -> list[str]:
        """Titles from the top-level section down to this one."""
        path: list[str] = []
        while index is not None:
            section = self.sections[index]
            path.append(section.title)
            index = section.parent
        return path[::-1]
