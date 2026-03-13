"""
Screenshot-based page type detection + structure-based fast path.

Usage:
    from app.services.page_type_detector import PageType, classify

    page_type = classify(pdf_structure, page_number, image_path, use_pp_structure)
"""
from __future__ import annotations

import logging
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


class PageType(str, Enum):
    TEXT    = "text"
    FORMULA = "formula"
    IMAGE   = "image"
    TABLE   = "table"
    CODE    = "code"
    SPARSE  = "sparse"


def classify_from_structure(structure: dict, page_number: int) -> PageType:
    """
    Fast path: classify page type using already-extracted PDF structure.
    No image loading required.
    """
    from app.services.page_classifier import (
        page_is_formula_heavy, page_is_image_heavy, page_is_sparse, page_blocks,
    )
    if page_is_sparse(structure, page_number):
        return PageType.SPARSE
    if page_is_formula_heavy(structure, page_number):
        return PageType.FORMULA
    if page_is_image_heavy(structure, page_number):   # >40% image blocks (not just any image)
        return PageType.IMAGE
    blocks = page_blocks(structure, page_number)
    if any(b.get("type") == "table" for b in blocks):
        return PageType.TABLE
    if any(b.get("type") in ("code_block", "code") for b in blocks):
        return PageType.CODE
    return PageType.TEXT


def classify_from_screenshot(image_path: Path, use_pp_structure: bool = False) -> PageType:
    """
    Visual path: detect page type from screenshot image alone.

    With PP-Structure enabled: runs detect_layout() and counts region types.
    Without PP-Structure: uses pytesseract word count + avg confidence as a heuristic.
      - word_count < 10        → SPARSE
      - avg_confidence < 40%   → FORMULA  (math symbols confuse Tesseract badly)
      - avg_confidence < 60%   → IMAGE    (diagram labels → partial reads)
      - otherwise              → TEXT
    """
    if use_pp_structure:
        try:
            from app.services.layout_detector import detect_layout
            regions = detect_layout(image_path, use_pp_structure=True)
            total = len(regions)
            if total == 0:
                return PageType.TEXT
            counts: dict[str, int] = {}
            for r in regions:
                counts[r.type] = counts.get(r.type, 0) + 1
            formula_ratio = counts.get("formula", 0) / total
            figure_ratio  = counts.get("figure",  0) / total
            table_ratio   = counts.get("table",   0) / total
            if formula_ratio >= 0.3:
                return PageType.FORMULA
            if figure_ratio >= 0.4:
                return PageType.IMAGE
            if table_ratio >= 0.4:
                return PageType.TABLE
            # Sparse: very few regions with no meaningful text
            if total <= 3 and counts.get("text", 0) + counts.get("title", 0) <= 1:
                return PageType.SPARSE
            return PageType.TEXT
        except Exception as e:
            logger.warning("PP-Structure layout detection failed: %s", e)
            # fall through to heuristic

    # Heuristic: pytesseract word count + average confidence
    try:
        import pytesseract
        from PIL import Image
        data = pytesseract.image_to_data(
            Image.open(image_path), output_type=pytesseract.Output.DICT
        )
        words = [w for w, c in zip(data["text"], data["conf"]) if w.strip() and int(c) > 0]
        confs = [int(c) for c in data["conf"] if int(c) > 0]
        word_count = len(words)
        avg_conf   = sum(confs) / len(confs) if confs else 0

        if word_count < 10:
            return PageType.SPARSE
        if avg_conf < 40:
            return PageType.FORMULA   # math symbols → very low Tesseract confidence
        if avg_conf < 60:
            return PageType.IMAGE     # diagram labels → moderate confidence
        return PageType.TEXT
    except Exception as e:
        logger.warning("Screenshot classification heuristic failed: %s", e)
        return PageType.TEXT


def classify(
    structure: dict,
    page_number: int,
    image_path: Path,
    use_pp_structure: bool = False,
) -> PageType:
    """
    Primary entry point.
    Uses structure (fast, no image I/O) when available; falls back to screenshot analysis.
    """
    if structure:
        return classify_from_structure(structure, page_number)
    return classify_from_screenshot(image_path, use_pp_structure)
