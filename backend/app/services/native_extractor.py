"""
Tier-1 PDF extraction using PyMuPDF native text (font analysis) + pdfplumber tables.

For text-based PDFs this gives near-perfect structure classification:
  - font_size > body_size × 1.35  →  title
  - monospace font (Courier, Consolas, Mono…)  →  code_block
  - image block + small bbox  →  formula or image
  - pdfplumber page.extract_tables()  →  table (uses PDF line/rect borders, not OCR)
  - everything else  →  paragraph

Returns None for a page that has < MIN_TEXT_COVERAGE (scanned/image-only) so the
caller can fall back to PaddleOCR for that page.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# Unicode math character ranges for formula block detection.
# NOTE: no raw-string prefix — Python must process \u/\U escapes before regex compilation.
# Supplementary plane chars (above U+FFFF) require 8-digit \U escapes.
#
# _MATH_STRONG_RE — unambiguous math indicators (operators, plain/italic Greek).
#   A block must contain at least one of these to be considered a formula.
#   This prevents false positives from text rendered with Mathematical Italic fonts
#   (e.g. the PDF stores "Matthew Moore" as 𝑀𝑎𝑡𝑡ℎ𝑒𝑤 𝑀𝑜𝑜𝑟𝑒 using U+1D400 italic caps).
_MATH_STRONG_RE = re.compile(
    "[\u2200-\u22FF"           # Mathematical Operators block (∫, ±, ∑, √, ∀, ∃, ∈…)
    "\u0391-\u03C9"            # Plain Greek letters (α, β, γ…)
    "\U0001D6C1-\U0001D7CB]"   # Math italic/bold Greek (𝛼, 𝛽, 𝜇, 𝜋…)
)
# _MATH_ALL_RE — all Unicode math ranges (for the >40% ratio check)
_MATH_ALL_RE = re.compile(
    "[\u2200-\u22FF"           # Mathematical Operators
    "\U0001D400-\U0001D7FF"    # All Mathematical Alphanumeric Symbols (Latin italic, Greek italic…)
    "\u0391-\u03C9"            # Plain Greek
    "\u2100-\u214F]"           # Letterlike symbols (ℝ, ℕ, ℎ…)
)

# Monospace font name fragments (case-insensitive)
_MONO_FRAGMENTS = re.compile(
    r"courier|consolas|monospace|mono|inconsolata|firacode|sourcecodepro"
    r"|dejavumono|notomono|liberationmono|ubuntumono|cascadia|jetbrains",
    re.IGNORECASE,
)

# Inline formula: image block narrower than this many points
_MAX_FORMULA_WIDTH_PT = 300
_MAX_FORMULA_HEIGHT_PT = 80

# If native text covers less than this fraction of page area → scanned page
MIN_TEXT_COVERAGE = 0.05


def _is_mono(font_name: str) -> bool:
    return bool(_MONO_FRAGMENTS.search(font_name or ""))


def _is_math_heavy(text: str) -> bool:
    """True when >40% of non-whitespace chars are Unicode math symbols AND the block
    contains at least one unambiguous math indicator (operator, Greek, math-italic Greek).

    The two-condition check prevents false positives from text styled with Mathematical
    Italic fonts — PDFs sometimes encode 'Matthew Moore' as 𝑀𝑎𝑡𝑡ℎ𝑒𝑤 𝑀𝑜𝑜𝑟𝑒 (all in
    U+1D400 Latin italic range) which passes a naive ratio test but has no operators.
    """
    non_ws = [c for c in text if not c.isspace()]
    if len(non_ws) < 3:
        return False
    if not any(_MATH_STRONG_RE.match(c) for c in non_ws):
        return False  # No unambiguous math — likely styled italic text
    math_count = sum(1 for c in non_ws if _MATH_ALL_RE.match(c))
    return math_count / len(non_ws) > 0.4


def _bbox_overlap_ratio(block_bbox: tuple, table_bbox: tuple) -> float:
    """Return fraction of block_bbox area covered by table_bbox (0.0–1.0)."""
    bx0, by0, bx1, by1 = block_bbox
    tx0, ty0, tx1, ty1 = table_bbox
    ix0, iy0 = max(bx0, tx0), max(by0, ty0)
    ix1, iy1 = min(bx1, tx1), min(by1, ty1)
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    overlap = (ix1 - ix0) * (iy1 - iy0)
    block_area = max((bx1 - bx0) * (by1 - by0), 1.0)
    return overlap / block_area


def _median(values: list[float]) -> float:
    if not values:
        return 12.0
    s = sorted(values)
    return s[len(s) // 2]


def _block_text(block: dict) -> str:
    """Concatenate all span text in a text block."""
    parts: list[str] = []
    for line in block.get("lines", []):
        for span in line.get("spans", []):
            t = (span.get("text") or "").strip()
            if t:
                parts.append(t)
    return " ".join(parts).strip()


def _block_font_info(block: dict) -> tuple[float, bool, str]:
    """Return (max_font_size, majority_monospace, dominant_font_name) for a text block.

    majority_monospace is True only when >50% of characters in the block are in a
    monospace font. This prevents paragraphs with a few inline code snippets
    (e.g. `func()` in Consolas) from being misclassified as code_block.
    """
    sizes: list[float] = []
    fonts: list[str] = []
    mono_chars = 0
    total_chars = 0
    for line in block.get("lines", []):
        for span in line.get("spans", []):
            sz = span.get("size", 0.0)
            fn = span.get("font", "")
            text = span.get("text", "")
            n = len(text)
            if sz > 0:
                sizes.append(sz)
            if fn:
                fonts.append(fn)
            total_chars += n
            if _is_mono(fn):
                mono_chars += n
    max_sz = max(sizes) if sizes else 0.0
    dominant_font = fonts[0] if fonts else ""
    # Require majority monospace (>50% of chars) to avoid false positives from inline snippets
    majority_mono = total_chars > 0 and (mono_chars / total_chars) > 0.5
    return max_sz, majority_mono, dominant_font


def _extract_page_native(
    fitz_page,
    document_id: str,
    page_num: int,
    body_size: float,
    plumber_page,
    use_pdfplumber: bool,
    use_pix2tex: bool,
    use_pp_structure: bool = False,
) -> list[dict]:
    """
    Extract one page using PyMuPDF font metadata + pdfplumber tables.
    Returns list of element dicts: {type, content, bbox, word_count}.
    """
    import pymupdf  # fitz

    page_rect = fitz_page.rect
    page_area = page_rect.width * page_rect.height

    # ------------------------------------------------------------------
    # 1. Get table bboxes from pdfplumber so we can skip those text blocks
    # ------------------------------------------------------------------
    table_bboxes: list[tuple[float, float, float, float]] = []
    table_elements: list[dict] = []

    if use_pdfplumber and plumber_page is not None:
        try:
            # find_tables() returns Table objects with per-table .bbox (x0, top, x1, bottom)
            # This is the correct API — extract_tables() gives row data only (no bbox per table)
            found = plumber_page.find_tables()
            for tbl in found:
                data = tbl.extract()
                if not data:
                    continue
                # Require ≥2 rows and ≥2 non-empty cells to filter false positives
                non_empty_rows = [r for r in data if any(str(c or "").strip() for c in r)]
                max_cells = max(
                    (sum(1 for c in r if str(c or "").strip()) for r in non_empty_rows),
                    default=0,
                )
                if len(non_empty_rows) < 2 or max_cells < 2:
                    logger.debug(
                        "Skipping pdfplumber table (rows=%d, max_cells=%d) on page %d",
                        len(non_empty_rows), max_cells, page_num,
                    )
                    continue
                content = "\n".join(
                    " | ".join(str(c or "").strip() for c in row) for row in data
                )
                if not content.strip():
                    continue
                # tbl.bbox is (x0, top, x1, bottom) in pdfplumber's top-left coordinate system
                # — same system as PyMuPDF, so no conversion needed
                x0, top, x1, bottom = tbl.bbox
                tbbox = (x0, top, x1, bottom)
                table_bboxes.append(tbbox)
                table_elements.append({
                    "type": "table",
                    "content": content,
                    "bbox": tbbox,
                    "word_count": len(content.split()),
                })
        except Exception as e:
            logger.debug("pdfplumber table extraction failed page %d: %s", page_num, e)

    # ------------------------------------------------------------------
    # 2. PyMuPDF block extraction
    # ------------------------------------------------------------------
    raw_dict = fitz_page.get_text(
        "dict",
        flags=pymupdf.TEXT_PRESERVE_WHITESPACE | pymupdf.TEXT_PRESERVE_IMAGES,
    )
    blocks = raw_dict.get("blocks", [])

    text_area = 0.0
    elements: list[dict] = []

    for block in blocks:
        btype = block.get("type", -1)
        bbox = block.get("bbox")  # (x0, y0, x1, y1)

        # ---- IMAGE BLOCK ----
        if btype == 1:
            bw = (bbox[2] - bbox[0]) if bbox else 999
            bh = (bbox[3] - bbox[1]) if bbox else 999
            # Small inline image → likely inline formula
            if bw <= _MAX_FORMULA_WIDTH_PT and bh <= _MAX_FORMULA_HEIGHT_PT:
                content = "[Formula]"
                if use_pix2tex:
                    content = _pix2tex_from_block(fitz_page, block) or "[Formula]"
                elements.append({
                    "type": "formula",
                    "content": content,
                    "bbox": bbox,
                    "word_count": 1,
                })
            else:
                extracted = _extract_image_region(fitz_page, bbox, use_pp_structure)
                if extracted:
                    ocr_text, el_type = extracted
                    elements.append({
                        "type": el_type,
                        "content": ocr_text,
                        "bbox": bbox,
                        "word_count": len(ocr_text.split()),
                    })
                else:
                    elements.append({
                        "type": "image",
                        "content": "[figure]",
                        "bbox": bbox,
                        "word_count": 0,
                    })
            continue

        # ---- TEXT BLOCK ----
        if btype == 0:
            text = _block_text(block)
            if not text:
                continue

            # Skip text that falls inside a pdfplumber table region (deduplication)
            if bbox and any(_bbox_overlap_ratio(bbox, tb) > 0.5 for tb in table_bboxes):
                continue

            text_area += (bbox[2] - bbox[0]) * (bbox[3] - bbox[1]) if bbox else 0.0

            max_sz, is_mono, font_name = _block_font_info(block)
            wc = len(text.split())

            # Classify using font metadata + Unicode math detection
            if _is_math_heavy(text):
                el_type = "formula"
            elif is_mono:
                el_type = "code_block"
            elif max_sz > body_size * 1.35 and wc <= 25:
                el_type = "title"
            else:
                el_type = "paragraph"

            elements.append({
                "type": el_type,
                "content": text,
                "bbox": bbox,
                "word_count": wc,
            })

    # ------------------------------------------------------------------
    # 3. Check text coverage (scanned page guard)
    # ------------------------------------------------------------------
    coverage = text_area / page_area if page_area > 0 else 0.0
    if coverage < MIN_TEXT_COVERAGE and not table_elements:
        logger.debug(
            "Page %d: low text coverage %.1f%% — marking as scanned",
            page_num, coverage * 100
        )
        return []  # Signal: use OCR fallback

    # ------------------------------------------------------------------
    # 4. Merge all elements and sort by top-left reading order (y0 then x0).
    #    PyMuPDF returns blocks in content-stream order which can differ from
    #    visual top-to-bottom order; sorting by bbox ensures correct page flow.
    # ------------------------------------------------------------------
    all_elements = elements + table_elements
    all_elements.sort(key=lambda e: (e["bbox"][1], e["bbox"][0]) if e.get("bbox") else (0, 0))
    return all_elements


def _extract_image_region(fitz_page, bbox, use_pp_structure: bool = False) -> tuple[str, str] | None:
    """
    Render page region at 2× and extract text with type classification.
    Tries PP-Structure first (layout-aware, detects code vs text vs figure);
    falls back to plain PaddleOCR with avg-words-per-line heuristic.
    Returns (text, element_type) or None if no readable text found.
    element_type: 'paragraph' or 'code_block'
    """
    try:
        import tempfile, os
        import pymupdf
        clip = pymupdf.Rect(bbox)
        pix = fitz_page.get_pixmap(matrix=pymupdf.Matrix(2, 2), clip=clip, alpha=False)
        fd, tmp_path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        pix.save(tmp_path)
        try:
            return _classify_and_extract_image(tmp_path, use_pp_structure)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
    except Exception as e:
        logger.debug("Image region extraction failed: %s", e)
        return None


def _classify_and_extract_image(image_path: str, use_pp_structure: bool = False) -> tuple[str, str] | None:
    """
    Extract text from an image region and classify it.
    Returns (text, element_type) or None if no text detected.
    element_type:
      'code_block' — code screenshot
      'paragraph'  — readable prose / caption
      'image'      — diagram/figure; content holds OCR labels as alt-text

    PP-Structure v3 is opt-in (use_pp_structure=True) — it loads layout+OCR
    models (~12s on first call) and does accurate region typing (code/figure/text).
    Default: fast PaddleOCR mobile + avg_wpl + _CODE_KEYWORDS heuristic.
    """
    # --- Optional: PP-Structure v3 (accurate, ~12s first-load, 2-5s/image) ---
    if use_pp_structure:
        try:
            from app.services.layout_detector import _get_pp_structure
            engine = _get_pp_structure()
            if engine is not None:
                results = engine.predict(image_path)
                if results:
                    parsed = _parse_pp_structure_v3(results[0])
                    if parsed is not None:
                        return parsed
        except Exception as e:
            logger.debug("PP-Structure image extraction failed: %s", e)

    # --- Default: plain PaddleOCR + avg_wpl heuristic (fast, ~0.5s/image) ---
    try:
        from app.services.pdf_extractor import _get_paddle, _parse_paddle_result, _CODE_KEYWORDS
        ocr = _get_paddle()
        result = ocr.predict(image_path)
        lines = _parse_paddle_result(result)
        if not lines:
            return None
        total_words = sum(len(t.split()) for _, t, _ in lines)
        avg_wpl = total_words / len(lines)
        text = " ".join(t for _, t, _ in lines).strip()
        if not text:
            return None
        if avg_wpl < 1.5:
            labels = [t for _, t, _ in lines if len(t.strip()) >= 2]
            return (" | ".join(labels) or text), "image"
        el_type = "code_block" if _CODE_KEYWORDS.search(text) else "paragraph"
        return text, el_type
    except Exception as e:
        logger.debug("OCR image extraction failed: %s", e)
        return None


def _parse_pp_structure_v3(item) -> tuple[str, str] | None:
    """
    Parse a PPStructureV3 LayoutParsingResultV2 result item.

    PP-Structure v3 result structure (item.json["res"]):
      layout_det_res.boxes  → [{label, score, coordinate}, ...]
      overall_ocr_res       → {rec_texts, rec_scores, ...}
      parsing_res_list      → [{block_type, text, ...}, ...]

    - Figure/diagram: layout label is 'image'/'figure' → extract OCR labels
      as alt-text, return as type 'image'
    - Text/code layout: extract from parsing_res_list, classify by block_type
    - Fallback: use overall_ocr_res.rec_texts
    """
    try:
        res = item.json.get("res", {})
    except Exception:
        return None

    # Check if entire layout is figure/diagram
    layout_boxes = res.get("layout_det_res", {}).get("boxes", [])
    figure_labels = {"image", "figure", "chart", "diagram"}
    is_all_figure = bool(layout_boxes) and all(
        b.get("label", "").lower() in figure_labels for b in layout_boxes
    )

    if is_all_figure:
        # Extract OCR label text as alt-text for the figure
        ocr = res.get("overall_ocr_res", {})
        texts = ocr.get("rec_texts", [])
        scores = ocr.get("rec_scores", [])
        labels = [t.strip() for t, s in zip(texts, scores)
                  if s >= 0.7 and len(t.strip()) >= 3]
        if not labels:
            return None
        return " | ".join(labels), "image"

    # Text/code layout: use parsing_res_list
    has_code = False
    parsed_texts: list[str] = []
    for block in res.get("parsing_res_list", []):
        btype = (block.get("block_type") or "").lower()
        text = (block.get("text") or "").strip()
        if btype in ("code", "algorithm"):
            has_code = True
        if text:
            parsed_texts.append(text)

    if parsed_texts:
        return " ".join(parsed_texts), "code_block" if has_code else "paragraph"

    # Final fallback: overall_ocr_res
    ocr = res.get("overall_ocr_res", {})
    texts = ocr.get("rec_texts", [])
    scores = ocr.get("rec_scores", [])
    filtered = [t.strip() for t, s in zip(texts, scores) if s >= 0.7 and len(t.strip()) >= 2]
    if not filtered:
        return None
    from app.services.pdf_extractor import _CODE_KEYWORDS
    combined = " ".join(filtered)
    el_type = "code_block" if _CODE_KEYWORDS.search(combined) else "paragraph"
    return combined, el_type


def _pix2tex_from_block(fitz_page, block: dict) -> str | None:
    """Crop the image block from the page, run pix2tex on it. Returns LaTeX or None."""
    try:
        from PIL import Image
        from pix2tex.cli import LatexOCR
        import io

        bbox = block.get("bbox")
        if not bbox:
            return None
        clip = fitz_page.parent.load_page(fitz_page.number).get_pixmap(
            clip=bbox, dpi=150
        )
        img = Image.open(io.BytesIO(clip.tobytes("png")))
        model = _get_pix2tex_model()
        if model is None:
            return None
        return model(img) or None
    except Exception as e:
        logger.debug("pix2tex block extraction failed: %s", e)
        return None


_pix2tex_singleton = None


def _get_pix2tex_model():
    """Lazy-init pix2tex LatexOCR singleton."""
    global _pix2tex_singleton
    if _pix2tex_singleton is not None:
        return _pix2tex_singleton
    try:
        from pix2tex.cli import LatexOCR
        _pix2tex_singleton = LatexOCR()
        logger.info("pix2tex LatexOCR model loaded")
        return _pix2tex_singleton
    except Exception as e:
        logger.warning("pix2tex not available: %s", e)
        return None


def extract_pdf_native(
    file_path: str,
    document_id: str,
    upload_path: Path | None = None,
    use_pdfplumber: bool = True,
    use_pix2tex: bool = False,
    use_pp_structure: bool = False,
) -> tuple | None:
    """
    Extract PDF structure using PyMuPDF font metadata + pdfplumber tables.

    Returns (chapters, page_count, total_word_count) or None if no text found
    (indicating a scanned PDF that needs OCR fallback).
    """
    from app.schemas.structure import Chapter, ContentBlock, BoundingBox

    try:
        import pymupdf
    except ImportError:
        logger.warning("pymupdf not available; skipping native extraction")
        return None

    try:
        doc = pymupdf.open(file_path)
    except Exception as e:
        logger.warning("PyMuPDF failed to open %s: %s", file_path, e)
        return None

    page_count = len(doc)

    # ------------------------------------------------------------------
    # Pre-compute body font size: median of all span sizes across the doc
    # (sample first 5 pages for speed)
    # ------------------------------------------------------------------
    all_sizes: list[float] = []
    sample_pages = min(5, page_count)
    for i in range(sample_pages):
        pg = doc[i]
        raw = pg.get_text("dict", flags=0)
        for blk in raw.get("blocks", []):
            if blk.get("type") != 0:
                continue
            for ln in blk.get("lines", []):
                for sp in ln.get("spans", []):
                    sz = sp.get("size", 0.0)
                    if 6.0 < sz < 30.0:
                        all_sizes.append(sz)
    body_size = _median(all_sizes) if all_sizes else 11.0
    logger.info("Native extractor: body_size=%.1f pt (sampled %d pages)", body_size, sample_pages)

    # ------------------------------------------------------------------
    # Open pdfplumber once for all pages
    # ------------------------------------------------------------------
    plumber_pdf = None
    if use_pdfplumber:
        try:
            import pdfplumber
            plumber_pdf = pdfplumber.open(file_path)
        except Exception as e:
            logger.warning("pdfplumber open failed: %s", e)

    # ------------------------------------------------------------------
    # Per-page extraction
    # ------------------------------------------------------------------
    chapters = []
    total_word_count = 0
    any_content = False

    try:
        for page_idx in range(page_count):
            page_num = page_idx + 1
            fitz_page = doc[page_idx]
            plumber_page = None
            if plumber_pdf is not None:
                try:
                    plumber_page = plumber_pdf.pages[page_idx]
                except Exception:
                    pass

            elements = _extract_page_native(
                fitz_page, document_id, page_num, body_size,
                plumber_page, use_pdfplumber, use_pix2tex, use_pp_structure,
            )

            if elements is None or (not elements and page_idx == 0):
                # First page has no text → scanned PDF
                logger.info("Native extractor: page %d empty → treating as scanned", page_num)
                doc.close()
                if plumber_pdf:
                    plumber_pdf.close()
                return None

            content_blocks: list[ContentBlock] = []
            page_wc = 0
            for el_idx, el in enumerate(elements):
                el_type = el["type"]
                content = el.get("content") or ""
                if not content and el_type != "image":
                    continue
                wc = el.get("word_count") or len(content.split())
                page_wc += wc
                raw_bbox = el.get("bbox")
                bbox = None
                if raw_bbox and len(raw_bbox) >= 4:
                    x0, y0, x1, y1 = raw_bbox[:4]
                    bbox = BoundingBox(
                        left=float(x0), top=float(y0),
                        width=float(x1 - x0), height=float(y1 - y0)
                    )
                content_blocks.append(ContentBlock(
                    id=f"{document_id}-p{page_num}-n{el_idx}",
                    type=el_type,
                    content=content,
                    orderIndex=el_idx,
                    wordCount=wc,
                    bbox=bbox,
                ))
                if content:
                    any_content = True

            total_word_count += page_wc
            chapters.append(Chapter(
                chapter_id=f"ch-p{page_num}",
                heading=f"Page {page_num}",
                content_blocks=content_blocks,
                order_index=page_idx,
                wordCount=page_wc,
            ))
    finally:
        doc.close()
        if plumber_pdf:
            try:
                plumber_pdf.close()
            except Exception:
                pass

    if not any_content:
        logger.info("Native extractor: no content found → scanned PDF, fall back to OCR")
        return None

    logger.info(
        "Native extractor: %d pages, %d total words",
        len(chapters), total_word_count
    )
    return chapters, len(chapters), total_word_count
