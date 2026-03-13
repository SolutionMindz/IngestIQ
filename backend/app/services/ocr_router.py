"""
OCR router: given a detected PageType, select and run the best available OCR tool.

Routing table:
  FORMULA → Nougat (full-page LaTeX)
              └─ fallback: pix2tex per formula region (if pp_structure + pix2tex enabled)
              └─ fallback: pytesseract
  IMAGE   → Surya (layout-aware OCR)
              └─ fallback: PaddleOCR
              └─ fallback: pytesseract
  TABLE   → pytesseract  (PP-Structure table OCR is handled at extraction time)
  CODE    → pytesseract
  TEXT    → pytesseract
  SPARSE  → ""  (metric unreliable — skip)

All tools are config-gated and degrade gracefully when not installed.
"""
from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from app.services.page_type_detector import PageType

logger = logging.getLogger(__name__)


def get_page_text(image_path: Path, page_type: PageType, settings) -> str:
    """
    Route to the best available OCR tool for this page type.
    Falls back through the chain until something returns non-empty text.

    :param image_path: Path to the full-page PNG screenshot.
    :param page_type:  PageType detected by page_type_detector.classify().
    :param settings:   app.config.Settings instance.
    :returns: Extracted text string (may be empty on failure).
    """
    if page_type == PageType.SPARSE:
        return ""   # metric unreliable; returning empty avoids skewing the comparison

    if page_type == PageType.FORMULA:
        # Tier 1: Nougat — full-page academic OCR with LaTeX output
        if getattr(settings, "use_nougat_ocr", False):
            try:
                from app.services.nougat_service import nougat_ocr_page
                text = nougat_ocr_page(image_path)
                if text:
                    return text
            except Exception as e:
                logger.warning("Nougat failed, falling back: %s", e)
        # Tier 2: pix2tex per detected formula region (requires pp_structure + pix2tex)
        if getattr(settings, "use_pix2tex", False) and getattr(settings, "use_pp_structure", False):
            text = _pix2tex_formula_regions(image_path)
            if text:
                return text

    if page_type == PageType.IMAGE:
        # Tier 1: Surya — layout-aware OCR, better than pytesseract on diagram labels
        if getattr(settings, "use_surya_ocr", False):
            try:
                from app.services.surya_service import surya_ocr_page
                text = surya_ocr_page(image_path)
                if text:
                    return text
            except Exception as e:
                logger.warning("Surya failed, falling back: %s", e)
        # Tier 2: PaddleOCR (already used during extraction)
        text = _paddle_ocr(image_path)
        if text:
            return text

    # Default / final fallback: pytesseract
    return _pytesseract_ocr(image_path)


# ---------------------------------------------------------------------------
# Internal OCR helpers
# ---------------------------------------------------------------------------

def _pytesseract_ocr(image_path: Path) -> str:
    try:
        import pytesseract
        from PIL import Image
        with Image.open(image_path) as img:
            return pytesseract.image_to_string(img)
    except Exception as e:
        logger.warning("pytesseract failed for %s: %s", image_path, e)
        return ""


def _paddle_ocr(image_path: Path) -> str:
    try:
        from app.services.pdf_extractor import _get_paddle
        ocr = _get_paddle()
        result = ocr.ocr(str(image_path))
        if result and result[0]:
            lines = [line[1][0] for line in result[0] if line and len(line) >= 2]
            return " ".join(str(t).strip() for t in lines).strip()
    except Exception as e:
        logger.warning("PaddleOCR failed for %s: %s", image_path, e)
    return ""


def _pix2tex_formula_regions(image_path: Path) -> str:
    """
    Detect formula regions via PP-Structure layout detector, crop each,
    run pix2tex on the crop, concatenate results.
    """
    try:
        import cv2
        from app.services.layout_detector import detect_layout
        from app.services.formula_ocr import formula_to_latex

        regions = detect_layout(image_path, use_pp_structure=True)
        formula_regions = [r for r in regions if r.type == "formula"]
        if not formula_regions:
            return ""

        img = cv2.imread(str(image_path))
        if img is None:
            return ""

        parts: list[str] = []
        for r in formula_regions:
            x0, y0, x1, y1 = (int(v) for v in r.bbox)
            crop = img[y0:y1, x0:x1]
            if crop.size == 0:
                continue
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                cv2.imwrite(tmp.name, crop)
                result = formula_to_latex(Path(tmp.name), use_formula_ocr=True)
            if result:
                parts.append(result)
        return " ".join(parts)
    except Exception as e:
        logger.warning("pix2tex region OCR failed: %s", e)
        return ""
