from pydantic import BaseModel
from typing import Literal


class Mismatch(BaseModel):
    id: str
    type: Literal["chapter", "heading", "paragraph", "table", "page", "word_count"]
    docxRef: str | None = None
    pdfRef: str | None = None
    message: str
    chapterIndex: int | None = None
    blockId: str | None = None


class ComparisonResult(BaseModel):
    documentId: str
    chapterCountMatch: bool
    headingMatch: bool
    paragraphCountMatch: bool
    tableCountMatch: bool
    pageCountMatch: bool
    wordCountMatch: bool
    mismatches: list[Mismatch]
    docxChapterCount: int
    pdfChapterCount: int
    docxWordCount: int
    pdfWordCount: int
