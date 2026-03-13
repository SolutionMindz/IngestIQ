"""
Structure builder (Section 7.5): merge layout regions and per-region OCR/extraction
results into DocumentStructure (chapters, content_blocks with types text/code/table/image).
"""
from __future__ import annotations

from typing import Iterable

from app.schemas.structure import (
    BoundingBox,
    Chapter,
    ContentBlock,
    DocumentStructure,
)


def build_document_structure(
    document_id: str,
    page_results: Iterable[list[dict]],
) -> DocumentStructure:
    """
    Build DocumentStructure from per-page region results.

    page_results: list of pages; each page is a list of element dicts:
      - type: "text" | "title" | "code" | "table" | "image" | "formula"
      - content: str (for text/title/code/formula) or table markdown/JSON string for table
      - bbox: optional (left, top, width, height) or (x0, y0, x1, y1)
      - word_count: optional int
    """
    chapters: list[Chapter] = []
    total_word_count = 0
    for page_index, elements in enumerate(page_results):
        content_blocks: list[ContentBlock] = []
        page_word_count = 0
        for idx, el in enumerate(elements):
            block_type = el.get("type", "text")
            content = el.get("content") or ""
            if not content and block_type != "image":
                continue
            wc = el.get("word_count")
            if wc is None and isinstance(content, str):
                wc = len(content.split())
            page_word_count += wc or 0
            bbox = _bbox_from_el(el.get("bbox"))
            block_id = f"{document_id}-p{page_index + 1}-b{idx}"
            # Map internal types to schema: text, code, table, image
            if block_type == "formula":
                schema_type = "formula"
            elif block_type in ("code_block", "code"):
                schema_type = "code"
            elif block_type == "table":
                schema_type = "table"
            elif block_type == "figure":
                schema_type = "image"
            else:
                schema_type = "text"
            content_blocks.append(
                ContentBlock(
                    id=block_id,
                    type=schema_type,
                    content=content if isinstance(content, str) else str(content),
                    orderIndex=idx,
                    wordCount=wc or 0,
                    bbox=bbox,
                )
            )
        total_word_count += page_word_count
        chapters.append(
            Chapter(
                chapter_id=f"ch-p{page_index + 1}",
                heading=f"Page {page_index + 1}",
                content_blocks=content_blocks,
                order_index=page_index,
                wordCount=page_word_count,
            )
        )
    return DocumentStructure(
        documentId=document_id,
        source="pdf",
        chapters=chapters,
        totalWordCount=total_word_count,
        pageCount=len(chapters),
    )


def _bbox_from_el(bbox: list | tuple | None) -> BoundingBox | None:
    if not bbox or len(bbox) < 4:
        return None
    a, b, c, d = bbox[0], bbox[1], bbox[2], bbox[3]
    if c >= a and d >= b:
        # (x0, y0, x1, y1)
        return BoundingBox(left=float(a), top=float(b), width=float(c - a), height=float(d - b))
    # (left, top, width, height)
    return BoundingBox(left=float(a), top=float(b), width=float(c), height=float(d))
