"""
Formula OCR (Section 7.3): optional LaTeX recognition for formula regions.
When disabled or unavailable, falls back to standard OCR and stores as text.
Uses pix2tex (LatexOCR) when use_formula_ocr=True.
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_pix2tex_model = None


def _get_pix2tex():
    """Lazy-init pix2tex LatexOCR singleton. Returns None if unavailable."""
    global _pix2tex_model
    if _pix2tex_model is not None:
        return _pix2tex_model
    try:
        from pix2tex.cli import LatexOCR
        _pix2tex_model = LatexOCR()
        logger.info("pix2tex LatexOCR model loaded")
        return _pix2tex_model
    except Exception as e:
        logger.warning("pix2tex not available: %s", e)
        return None


def formula_to_latex(image_path: Path, use_formula_ocr: bool = False) -> str:
    """
    Extract formula region image to LaTeX string.
    When use_formula_ocr is True, uses pix2tex LatexOCR.
    Falls back to standard OCR text when disabled or unavailable.
    """
    if not use_formula_ocr:
        return _ocr_region_as_text(image_path)

    try:
        from PIL import Image
        model = _get_pix2tex()
        if model is None:
            return _ocr_region_as_text(image_path)
        img = Image.open(str(image_path))
        result = model(img)
        if result:
            return str(result).strip()
        return _ocr_region_as_text(image_path)
    except Exception as e:
        logger.warning("pix2tex formula OCR failed: %s", e)
        return _ocr_region_as_text(image_path)


def _ocr_region_as_text(image_path: Path) -> str:
    """Fallback: run standard PaddleOCR on crop and return concatenated text."""
    try:
        from app.services.pdf_extractor import _get_paddle
        ocr = _get_paddle()
        result = ocr.ocr(str(image_path))
        if result and result[0]:
            lines = [line[1][0] for line in result[0] if line and len(line) >= 2]
            return " ".join(str(t).strip() for t in lines).strip()
    except Exception as e:
        logger.warning("Formula fallback OCR failed: %s", e)
    return ""
