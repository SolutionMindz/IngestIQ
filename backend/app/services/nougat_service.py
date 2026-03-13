"""
Full-page formula OCR via Nougat (Meta).
Nougat is a transformer model trained on academic PDFs; it outputs markdown with LaTeX.
Ideal for formula-heavy pages where pytesseract fails on math symbols.

Install:  pip install nougat-ocr
Enable:   USE_NOUGAT_OCR=true  in backend/.env
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_nougat_model = None


def _get_nougat():
    """Lazy-init Nougat model singleton. Returns None if unavailable."""
    global _nougat_model
    if _nougat_model is not None:
        return _nougat_model
    try:
        from nougat import NougatModel
        from nougat.utils.device import move_to_device
        _nougat_model = NougatModel.from_pretrained("facebook/nougat-base")
        _nougat_model = move_to_device(_nougat_model, bf16=False, cuda=False)
        _nougat_model.eval()
        logger.info("Nougat model loaded (facebook/nougat-base)")
        return _nougat_model
    except Exception as e:
        logger.warning("Nougat not available: %s", e)
        return None


def nougat_ocr_page(image_path: Path) -> str:
    """
    Run Nougat on a full-page screenshot PNG.
    Returns markdown text with LaTeX formulas (e.g. $\\frac{a}{b}$).
    Returns '' if model unavailable or inference fails.
    """
    model = _get_nougat()
    if model is None:
        return ""
    try:
        import torch
        from PIL import Image
        img = Image.open(str(image_path)).convert("RGB")
        # Nougat expects a pre-processed tensor; use the model's built-in encoder prep
        with torch.no_grad():
            tensor = model.encoder.prepare_input(img, random_padding=False).unsqueeze(0)
            out = model.inference(image_tensors=tensor, early_stopping=False)
        predictions = out.get("predictions", [])
        if predictions:
            return str(predictions[0]).strip()
        return ""
    except Exception as e:
        logger.warning("Nougat OCR failed for %s: %s", image_path, e)
        return ""
