"""
Layout detection using PaddleOCR PP-Structure (Section 7.1).
Returns per-page regions with type and bbox so each region can be sent to the
appropriate recognizer (text OCR, table extraction, formula OCR, code OCR).
When PP-Structure is unavailable or disabled, returns a single full-image text region.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Internal region types aligned with ContentBlock and plan
REGION_TEXT = "text"
REGION_TITLE = "title"
REGION_TABLE = "table"
REGION_FIGURE = "figure"
REGION_FORMULA = "formula"
REGION_CODE = "code_block"
REGION_CAPTION = "caption"


@dataclass
class LayoutRegion:
    """One detected region on a page."""
    type: str  # text, title, table, figure, formula, code_block, caption
    bbox: tuple[float, float, float, float]  # left, top, width, height (or x0, y0, x1, y1)
    score: float = 1.0
    raw_label: str | None = None


# Map PP-Structure / layout model labels to our region types
LABEL_TO_TYPE = {
    "text": REGION_TEXT,
    "title": REGION_TITLE,
    "document title": REGION_TITLE,
    "paragraph title": REGION_TITLE,
    "table": REGION_TABLE,
    "figure": REGION_FIGURE,
    "image": REGION_FIGURE,
    "formula": REGION_FORMULA,
    "algorithm": REGION_CODE,
    "code": REGION_CODE,
    "caption": REGION_CAPTION,
    "figure caption": REGION_CAPTION,
    "table caption": REGION_CAPTION,
    "list": REGION_TEXT,
    "abstract": REGION_TEXT,
    "header": REGION_TEXT,
    "footer": REGION_TEXT,
    "page number": REGION_TEXT,
}


_pp_structure_engine: Any = None


def _get_pp_structure():
    """
    Lazy-init PPStructureV3 engine (lightweight config).
    Disabled modules: doc preprocessor, chart recognition, formula recognition.
    These load heavy models (UVDoc, PP-Chart2Table LLM, PP-FormulaNet) that are
    not needed for layout detection and OCR on embedded image blocks.
    Returns None if unavailable.
    """
    global _pp_structure_engine
    if _pp_structure_engine is not None:
        return _pp_structure_engine
    try:
        import os
        os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
        from paddleocr import PPStructureV3
        _pp_structure_engine = PPStructureV3(
            use_doc_orientation_classify=False,  # skip PP-LCNet orientation model
            use_doc_unwarping=False,             # skip UVDoc (document dewarping LLM)
            use_chart_recognition=False,         # skip PP-Chart2Table (multi-modal LLM)
            use_formula_recognition=False,       # skip PP-FormulaNet
            use_seal_recognition=False,          # skip seal/stamp detection
            use_textline_orientation=False,      # skip textline orientation classifier
        )
        logger.info("PPStructureV3 loaded (lightweight: layout+OCR only)")
        return _pp_structure_engine
    except Exception as e:
        logger.warning("PPStructureV3 not available: %s", e)
        return None


def _image_size(image_path: Path) -> tuple[int, int]:
    """Return (width, height) of image."""
    try:
        import cv2
        img = cv2.imread(str(image_path))
        if img is not None:
            h, w = img.shape[:2]
            return w, h
    except Exception:
        pass
    try:
        from PIL import Image
        with Image.open(image_path) as im:
            return im.size[0], im.size[1]
    except Exception:
        return 1200, 1600  # fallback


def detect_layout(
    image_path: Path,
    use_pp_structure: bool = True,
) -> list[LayoutRegion]:
    """
    Detect layout regions on a page image.
    Returns list of LayoutRegion (type, bbox). Bbox is (x0, y0, x1, y1) in image coordinates.
    When use_pp_structure is False or PP-Structure fails, returns one region covering the full image.
    """
    if not use_pp_structure:
        w, h = _image_size(image_path)
        return [LayoutRegion(type=REGION_TEXT, bbox=(0, 0, float(w), float(h)), raw_label="full_page")]

    engine = _get_pp_structure()
    if engine is None:
        w, h = _image_size(image_path)
        return [LayoutRegion(type=REGION_TEXT, bbox=(0, 0, float(w), float(h)), raw_label="fallback")]

    try:
        import cv2
        img = cv2.imread(str(image_path))
        if img is None:
            w, h = _image_size(image_path)
            return [LayoutRegion(type=REGION_TEXT, bbox=(0, 0, float(w), float(h)))]

        result = engine.predict(str(image_path))
        regions: list[LayoutRegion] = []
        if not result:
            h, w = img.shape[:2]
            return [LayoutRegion(type=REGION_TEXT, bbox=(0, 0, float(w), float(h)))]

        # Normalize: PP-Structure 2.x returns list of dicts; some APIs return dict with 'boxes' or layout_det_res
        items: list[dict] = []
        if isinstance(result, list):
            items = [r for r in result if isinstance(r, dict)]
        elif isinstance(result, dict):
            layout_res = result.get("layout_det_res")
            if isinstance(layout_res, dict) and "boxes" in layout_res:
                for b in layout_res["boxes"]:
                    if isinstance(b, dict):
                        items.append(b)
                    elif isinstance(b, (list, tuple)) and len(b) >= 5:
                        items.append({"coordinate": b[:4], "type": b[4] if len(b) > 4 else "text", "score": b[5] if len(b) > 5 else 1.0})
            elif "boxes" in result:
                for b in result["boxes"]:
                    if isinstance(b, dict):
                        items.append(b)

        for line in items if items else (result if isinstance(result, list) else []):
            if not isinstance(line, dict):
                continue
            # PPStructure 2.x: 'type' or 'layout', 'bbox' or 'box' or 'coordinate'
            label = (line.get("type") or line.get("layout") or "text").lower().strip()
            score = float(line.get("score", 1.0))
            box = line.get("bbox") or line.get("box") or line.get("coordinate")
            if box is None and "res" in line:
                # Some versions put bbox inside res
                res = line["res"]
                if isinstance(res, dict):
                    box = res.get("bbox") or res.get("box")
            if not box or len(box) < 4:
                continue
            # Normalize to (x0, y0, x1, y1): support [x0,y0,x1,y1] or [[x,y],[x,y],[x,y],[x,y]]
            try:
                if isinstance(box[0], (list, tuple)):
                    xs = [float(p[0]) for p in box[:4]]
                    ys = [float(p[1]) for p in box[:4]]
                    x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
                else:
                    x0, y0, x1, y1 = float(box[0]), float(box[1]), float(box[2]), float(box[3])
            except (TypeError, IndexError):
                continue
            region_type = LABEL_TO_TYPE.get(label, REGION_TEXT)
            regions.append(
                LayoutRegion(
                    type=region_type,
                    bbox=(x0, y0, x1, y1),
                    score=score,
                    raw_label=label,
                )
            )

        # Sort by reading order (top to bottom, then left to right)
        if len(regions) > 1:
            regions.sort(key=lambda r: (r.bbox[1], r.bbox[0]))
        return regions if regions else [LayoutRegion(type=REGION_TEXT, bbox=(0, 0, float(img.shape[1]), float(img.shape[0])))]

    except Exception as e:
        logger.warning("Layout detection failed for %s: %s", image_path, e)
        w, h = _image_size(image_path)
        return [LayoutRegion(type=REGION_TEXT, bbox=(0, 0, float(w), float(h)))]
