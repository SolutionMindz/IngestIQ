"""
Full-page OCR via Surya (Datalab).
Surya is a layout-aware multi-language OCR model; faster than Nougat (~3-5s CPU),
better than pytesseract on image-heavy and diagram pages.

Install:  pip install surya-ocr
Enable:   USE_SURYA_OCR=true  in backend/.env
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_surya_model = None
_surya_processor = None


def _get_surya():
    """Lazy-init Surya OCR model + processor singleton. Returns (model, processor) or (None, None)."""
    global _surya_model, _surya_processor
    if _surya_model is not None:
        return _surya_model, _surya_processor
    try:
        from surya.model.recognition.model import load_model
        from surya.model.recognition.processor import load_processor
        _surya_processor = load_processor()
        _surya_model = load_model()
        logger.info("Surya OCR model loaded")
        return _surya_model, _surya_processor
    except Exception as e:
        logger.warning("Surya not available: %s", e)
        return None, None


def surya_ocr_page(image_path: Path) -> str:
    """
    Run Surya OCR on a full-page screenshot PNG.
    Returns plain text concatenated from all detected text lines.
    Returns '' if model unavailable or inference fails.
    """
    model, processor = _get_surya()
    if model is None:
        return ""
    try:
        from PIL import Image
        from surya.ocr import run_ocr
        img = Image.open(str(image_path)).convert("RGB")
        # Surya run_ocr takes list of images + langs
        results = run_ocr([img], [["en"]], model, processor)
        if not results:
            return ""
        # Each result has .text_lines list with .text attribute
        lines = [line.text for line in (results[0].text_lines or []) if line.text]
        return " ".join(lines).strip()
    except Exception as e:
        logger.warning("Surya OCR failed for %s: %s", image_path, e)
        return ""
