"""
Shared page-type classification helpers based on extracted PDF structure.
Used by both documents.py (API status) and page_accuracy_service.py (OCR routing).
"""
from __future__ import annotations


def page_blocks(structure: dict, page_number: int) -> list:
    """Return content_blocks for the given page, or [] if not found."""
    if not structure:
        return []
    for ch in (structure.get("chapters") or []):
        if ch.get("heading") == f"Page {page_number}":
            return ch.get("content_blocks") or []
    return []


def page_is_formula_heavy(structure: dict, page_number: int) -> bool:
    """True if >30% of blocks on the page are formula type with real math text content.
    Excludes image-placeholder formula blocks (content='[Formula]') to avoid false positives
    from decorative inline image elements.
    30% threshold catches pages where many math tokens are short/mixed (e.g. 'sin θ')
    and don't individually cross the _is_math_heavy() ratio, but the page is clearly formula-dense."""
    blocks = page_blocks(structure, page_number)
    if not blocks:
        return False
    math_blocks = sum(
        1 for b in blocks
        if b.get("type") == "formula"
        and (b.get("content") or "").strip().lower() not in ("[formula]", "")
    )
    return math_blocks / len(blocks) > 0.3


def page_has_images(structure: dict, page_number: int) -> bool:
    """True if the page has any image block. Used for status badge display."""
    blocks = page_blocks(structure, page_number)
    return any(b.get("type") == "image" for b in blocks)


def page_is_image_heavy(structure: dict, page_number: int, threshold: float = 0.4) -> bool:
    """True if images make up ≥ threshold fraction of blocks. Used for OCR routing.
    Stricter than page_has_images — prevents routing text-heavy pages with one figure to Surya."""
    blocks = page_blocks(structure, page_number)
    if not blocks:
        return False
    image_count = sum(1 for b in blocks if b.get("type") == "image")
    return image_count / len(blocks) >= threshold


def page_is_sparse(structure: dict, page_number: int) -> bool:
    """True if the page has fewer than 15 total content words — metric is unreliable."""
    blocks = page_blocks(structure, page_number)
    total_words = sum(
        len((b.get("content") or b.get("text") or "").split())
        for b in blocks
        if b.get("type") not in ("image",)
    )
    return total_words < 15
