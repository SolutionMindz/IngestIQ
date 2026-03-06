from pydantic import BaseModel
from typing import Literal


class BoundingBox(BaseModel):
    """Optional geometry for chip/raw-text layout (e.g. from OCR or PyMuPDF)."""
    left: float = 0
    top: float = 0
    width: float = 0
    height: float = 0


class ContentBlock(BaseModel):
    id: str
    type: Literal["text", "code", "table", "image"]
    content: str
    orderIndex: int
    wordCount: int | None = None
    bbox: BoundingBox | None = None  # optional geometry for raw-text chip view


class Section(BaseModel):
    id: str
    heading: str
    level: int
    contentBlocks: list[ContentBlock]
    orderIndex: int
    wordCount: int | None = None


class Chapter(BaseModel):
    chapter_id: str
    heading: str
    content_blocks: list[ContentBlock]
    sections: list[Section] | None = None
    order_index: int
    wordCount: int | None = None


class DocumentStructure(BaseModel):
    documentId: str
    source: Literal["docx", "pdf", "textract", "ocr"]
    chapters: list[Chapter]
    totalWordCount: int | None = None
    pageCount: int | None = None
