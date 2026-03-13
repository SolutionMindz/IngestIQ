"""
PDF extraction: two extractions for side-by-side comparison.
- source="pdf": PaddleOCR extraction. When use_pp_structure is True (Section 7), runs
  layout detection (PP-Structure) first, then region-specific processing (text, table,
  formula, code) and structure builder. Otherwise full-page OCR only.
- source="textract": AWS Textract extraction (see textract_extractor.py).

PyMuPDF is used only for page count and for rendering pages to images when
screenshots are unavailable. Native PDF text extraction has been removed.
"""
import logging
import os
import re
import tempfile
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.extraction import Extraction
from app.models.audit import AuditLog
from app.config import get_settings
from app.schemas.structure import DocumentStructure, Chapter, ContentBlock, BoundingBox

logger = logging.getLogger(__name__)

_paddle_ocr = None


def _get_paddle():
    """Lazy-init PaddleOCR singleton. Raises on import/init failure."""
    global _paddle_ocr
    if _paddle_ocr is None:
        # Cap inference threads to ~50% of cores so the uvicorn event loop stays responsive.
        # NOTE: os.nice() is intentionally NOT used here — it would lower the entire
        # uvicorn process priority and cause HTTP request timeouts under load.
        # Thread-level caps are sufficient.
        os.environ.setdefault("OMP_NUM_THREADS", "4")
        os.environ.setdefault("MKL_NUM_THREADS", "4")
        os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
        try:
            import paddle
            paddle.set_num_threads(4)
        except Exception:
            pass
        try:
            from paddleocr import PaddleOCR
            _paddle_ocr = PaddleOCR(
                lang="en",
                ocr_version="PP-OCRv4",  # PP-OCRv4 mobile det+rec: lighter than default server model
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
            )
        except Exception as e:
            logger.exception("PaddleOCR init failed: %s", e)
            raise
    return _paddle_ocr


def _get_pdf_page_count(file_path: str) -> int:
    """Return number of pages in PDF using PyMuPDF; 1 on error."""
    try:
        import pymupdf
        doc = pymupdf.open(file_path)
        try:
            return len(doc)
        finally:
            doc.close()
    except Exception:
        return 1


def _crop_image_to_temp(
    image_path: Path, bbox: tuple[float, float, float, float]
) -> Path | None:
    """Crop image by (x0, y0, x1, y1), save to temp file. Returns path or None."""
    try:
        import cv2
        img = cv2.imread(str(image_path))
        if img is None:
            return None
        return _crop_ndarray_to_temp(img, bbox)
    except Exception as e:
        logger.debug("Crop failed: %s", e)
        return None


def _crop_ndarray_to_temp(
    img, bbox: tuple[float, float, float, float]
) -> Path | None:
    """Crop an already-loaded numpy image array by (x0, y0, x1, y1), save to temp file."""
    try:
        import cv2
        h, w = img.shape[:2]
        x0, y0, x1, y1 = bbox
        x0, x1 = max(0, int(x0)), min(w, int(x1))
        y0, y1 = max(0, int(y0)), min(h, int(y1))
        if x1 <= x0 or y1 <= y0:
            return None
        crop = img[y0:y1, x0:x1]
        fd, path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        cv2.imwrite(path, crop)
        return Path(path)
    except Exception as e:
        logger.debug("Crop (ndarray) failed: %s", e)
        return None


def _parse_paddle_result(result) -> list[tuple[list, str, float]]:
    """
    Parse PaddleOCR 3.x predict() result into list of (box_points, text, score) tuples.
    PaddleOCR 3.x returns list of OCRResult dicts: {"rec_texts": [...], "rec_scores": [...], "rec_polys": [...]}.
    """
    lines = []
    for res in (result or []):
        try:
            texts = res["rec_texts"]
            scores = res["rec_scores"]
            polys = res["rec_polys"]
        except (KeyError, TypeError):
            continue
        for i, text in enumerate(texts):
            text = (text or "").strip()
            if not text:
                continue
            score = float(scores[i]) if i < len(scores) else 1.0
            box = list(polys[i]) if i < len(polys) else []
            lines.append((box, text, score))
    return lines


# ─── Heuristic structure classifier ─────────────────────────────────────────

_CODE_KEYWORDS = re.compile(
    # Actual language keywords — reliable code signals
    r'\b(def |class |import |return |if |else:|elif |for |while |try:|except |with |'
    r'from |async |await |const |let |var |function |print\(|console\.log)\b'
    r'|\b(None|True|False|null|undefined)\b'
    # Code operators — only strong unambiguous forms (removed bare `(){}` which match normal prose)
    r'|=>|->|:=|!=|==|<=|>=|\+='
    r'|\{[^}]{0,60}\}'  # {...} block (curly braces containing content)
    r'|;{2,}'            # multiple semicolons in a row
)
_FORMULA_CHARS = re.compile(
    r'[∑∫∂∇∆√∞≤≥≠±×÷αβγδεζηθλμνπρσφψωΑΒΓΔΘΛΞΠΣΦΨΩ]'
    r'|\\[a-zA-Z]+\{'
    r'|[_^]\{'
    r'|\$[^$]+\$'
)
_LIST_PREFIX = re.compile(
    r'^\s*(?:[-•*·▪▸►]\s+|\d+[.)]\s+|[a-zA-Z][.)]\s+|[ivxlIVXL]+[.)]\s+)'
)


def _line_top(box: list) -> float:
    if not box:
        return 0.0
    try:
        return min(float(p[1]) for p in box)
    except (TypeError, IndexError):
        return 0.0


def _line_height(box: list) -> float:
    if not box or len(box) < 2:
        return 0.0
    try:
        ys = [float(p[1]) for p in box]
        return max(ys) - min(ys)
    except (TypeError, IndexError):
        return 0.0


def _box_to_bbox(box: list) -> BoundingBox | None:
    if not box:
        return None
    try:
        xs = [float(p[0]) for p in box]
        ys = [float(p[1]) for p in box]
        return BoundingBox(left=min(xs), top=min(ys), width=max(xs) - min(xs), height=max(ys) - min(ys))
    except (TypeError, IndexError):
        return None


def _boxes_to_bbox(boxes: list[list]) -> BoundingBox | None:
    all_pts = [p for b in boxes if b for p in b]
    if not all_pts:
        return None
    try:
        xs = [float(p[0]) for p in all_pts]
        ys = [float(p[1]) for p in all_pts]
        return BoundingBox(left=min(xs), top=min(ys), width=max(xs) - min(xs), height=max(ys) - min(ys))
    except (TypeError, IndexError):
        return None


def _line_left(box: list) -> float:
    """Return leftmost x of a bounding box."""
    if not box:
        return 0.0
    try:
        return min(float(p[0]) for p in box)
    except (TypeError, IndexError):
        return 0.0


def _get_column_count(group: list[tuple[list, str, float]]) -> int:
    """Estimate distinct text columns in a group from left-x position distribution.
    Returns 1 for normal paragraphs; >=2 for table-like multi-column layouts."""
    if len(group) < 3:
        return 1
    left_xs: list[float] = []
    widths: list[float] = []
    for box, _, _ in group:
        if not box:
            continue
        try:
            xs = [float(p[0]) for p in box]
            left_xs.append(min(xs))
            widths.append(max(xs) - min(xs))
        except (TypeError, IndexError):
            continue
    if len(left_xs) < 3:
        return 1
    median_w = sorted(widths)[len(widths) // 2] if widths else 100.0
    # A new column starts when x jumps by more than 40% of median line width
    col_gap = max(median_w * 0.4, 40.0)
    left_xs.sort()
    columns = 1
    for i in range(1, len(left_xs)):
        if left_xs[i] - left_xs[i - 1] > col_gap:
            columns += 1
    return columns


def _format_table_lines(group: list[tuple[list, str, float]], median_h: float) -> str:
    """Format table OCR lines as pipe-separated rows by grouping on y-position."""
    # Sort lines top-to-bottom, then left-to-right within each row
    sorted_lines = sorted(group, key=lambda l: (_line_top(l[0]), _line_left(l[0])))
    row_gap = median_h * 1.2  # lines within this vertical distance share a row
    rows: list[list[tuple[float, str]]] = []
    current_row: list[tuple[float, str]] = []
    current_y: float | None = None
    for box, text, _ in sorted_lines:
        text = text.strip()
        if not text:
            continue
        top = _line_top(box)
        left = _line_left(box)
        if current_y is None or abs(top - current_y) <= row_gap:
            current_row.append((left, text))
            if current_y is None:
                current_y = top
        else:
            if current_row:
                rows.append(sorted(current_row, key=lambda p: p[0]))
            current_row = [(left, text)]
            current_y = top
    if current_row:
        rows.append(sorted(current_row, key=lambda p: p[0]))
    if not rows:
        return " ".join(t for _, t, _ in group)
    return "\n".join(" | ".join(text for _, text in row) for row in rows if row)


def _classify_group(group: list[tuple[list, str, float]], median_h: float) -> str:
    """Classify a group of OCR lines into a block type using heuristics."""
    texts = [t for _, t, _ in group]
    full_text = " ".join(texts).strip()
    first_text = texts[0].strip() if texts else ""

    # Title: noticeably taller lines + short text
    heights = [_line_height(box) for box, _, _ in group if box]
    avg_h = sum(heights) / len(heights) if heights else 0.0
    if avg_h > median_h * 1.25 and len(full_text.split()) <= 20:
        return "title"

    # List item: starts with a bullet or numbering prefix
    if _LIST_PREFIX.match(first_text):
        return "list_item"

    # Formula: contains math/formula symbols or LaTeX
    if _FORMULA_CHARS.search(full_text):
        return "formula"

    # Table: lines arranged in 2+ distinct x-columns
    if _get_column_count(group) >= 2:
        return "table"

    # Code block: multiple lines with actual code-keyword patterns
    code_hits = sum(1 for t in texts if _CODE_KEYWORDS.search(t))
    if code_hits >= 2 or (code_hits >= 1 and len(texts) >= 4):
        return "code_block"

    return "paragraph"


def _classify_ocr_lines_to_blocks(
    lines: list[tuple[list, str, float]],
    document_id: str,
    page_num: int,
) -> list[ContentBlock]:
    """
    Classify PaddleOCR text lines into structured ContentBlocks using heuristics:
    - line height ratio → title detection
    - text patterns → list_item / formula / code_block
    - vertical proximity → paragraph grouping
    Falls back gracefully when bounding boxes are missing.
    """
    if not lines:
        return []

    # Sort top-to-bottom
    lines = sorted(lines, key=lambda l: _line_top(l[0]))

    # Median line height across all lines
    heights = [h for h in (_line_height(b) for b, _, _ in lines) if h > 0]
    median_h = sorted(heights)[len(heights) // 2] if heights else 16.0

    # Group lines into proximity blocks
    gap_threshold = median_h * 1.5
    groups: list[list[tuple[list, str, float]]] = []
    current: list[tuple[list, str, float]] = []
    prev_bottom: float | None = None

    for box, text, score in lines:
        top = _line_top(box)
        h = _line_height(box) or median_h
        bottom = top + h
        if prev_bottom is None or (top - prev_bottom) <= gap_threshold:
            current.append((box, text, score))
        else:
            if current:
                groups.append(current)
            current = [(box, text, score)]
        prev_bottom = max(prev_bottom or bottom, bottom)
    if current:
        groups.append(current)

    # Classify and build ContentBlocks
    blocks: list[ContentBlock] = []
    for g_idx, group in enumerate(groups):
        group_text = " ".join(t for _, t, _ in group).strip()
        if not group_text:
            continue

        block_type = _classify_group(group, median_h)

        # List items → one ContentBlock per line so each item is individually reviewable
        if block_type == "list_item" and len(group) > 1:
            for line_idx, (box, text, _) in enumerate(group):
                text = text.strip()
                if not text:
                    continue
                blocks.append(ContentBlock(
                    id=f"{document_id}-p{page_num}-b{g_idx}-l{line_idx}",
                    type="list_item",
                    content=text,
                    orderIndex=len(blocks),
                    wordCount=len(text.split()),
                    bbox=_box_to_bbox(box),
                ))
            continue

        # Tables → format lines as pipe-separated rows (preserves cell structure)
        if block_type == "table":
            content = _format_table_lines(group, median_h)
        else:
            content = group_text

        blocks.append(ContentBlock(
            id=f"{document_id}-p{page_num}-b{g_idx}",
            type=block_type,
            content=content,
            orderIndex=len(blocks),
            wordCount=len(content.split()),
            bbox=_boxes_to_bbox([b for b, _, _ in group]),
        ))

    return blocks


# ─── End heuristic classifier ─────────────────────────────────────────────────


def _ocr_region_to_text(image_path: Path) -> str:
    """Run PaddleOCR on image and return concatenated text."""
    try:
        ocr = _get_paddle()
        result = ocr.predict(str(image_path))
        lines = _parse_paddle_result(result)
        if not lines:
            logger.debug("PaddleOCR returned no lines for %s", image_path)
            return ""
        return " ".join(text for _, text, _ in lines).strip()
    except Exception as e:
        logger.warning("PaddleOCR failed for %s: %s", image_path, e)
        return ""


def _ocr_region_to_blocks(
    image_path: Path, document_id: str, page_num: int, block_type: str, base_idx: int
) -> list[ContentBlock]:
    """Run PaddleOCR on image; return ContentBlocks with given block_type."""
    blocks: list[ContentBlock] = []
    try:
        ocr = _get_paddle()
        result = ocr.predict(str(image_path))
    except Exception:
        return blocks
    lines = _parse_paddle_result(result)
    for idx, (box, text, _) in enumerate(lines):
        bbox = None
        if box:
            try:
                pts = [box[i] for i in range(4)] if len(box) >= 4 else box
                xs = [float(p[0]) for p in pts]
                ys = [float(p[1]) for p in pts]
                bbox = BoundingBox(left=min(xs), top=min(ys), width=max(xs) - min(xs), height=max(ys) - min(ys))
            except (TypeError, IndexError):
                pass
        wc = len(text.split())
        blocks.append(
            ContentBlock(
                id=f"{document_id}-p{page_num}-b{base_idx + idx}",
                type=block_type,
                content=text,
                orderIndex=base_idx + idx,
                wordCount=wc,
                bbox=bbox,
            )
        )
    return blocks


def _paddle_image_to_blocks(
    image_path: Path, document_id: str, page_num: int
) -> list[ContentBlock]:
    """Run PaddleOCR on an image; classify lines into structured ContentBlocks."""
    try:
        ocr = _get_paddle()
        result = ocr.predict(str(image_path))
    except Exception:
        return []
    lines = _parse_paddle_result(result)
    return _classify_ocr_lines_to_blocks(lines, document_id, page_num)


def _extract_page_with_layout(
    image_path: Path,
    document_id: str,
    page_num: int,
) -> list[dict]:
    """
    Section 7: Layout detection → per-region processing → list of elements for one page.
    Each element: {type, content, bbox?, word_count?}.
    Each region is processed by a single handler (table / formula / code / text) to avoid
    running all models on every region.
    """
    from app.services.layout_detector import detect_layout
    from app.services.layout_detector import (
        REGION_TEXT,
        REGION_TITLE,
        REGION_TABLE,
        REGION_FIGURE,
        REGION_FORMULA,
        REGION_CODE,
        REGION_CAPTION,
    )
    from app.services.formula_ocr import formula_to_latex
    from app.services.table_extractor import extract_table_region

    settings = get_settings()
    use_pp = getattr(settings, "use_pp_structure", True)
    use_formula = getattr(settings, "use_formula_ocr", False)
    use_code = getattr(settings, "use_code_ocr", False)

    regions = detect_layout(image_path, use_pp_structure=use_pp)
    elements: list[dict] = []
    temp_crops: list[Path] = []

    # Load the page image once; reuse the numpy array for all region crops.
    try:
        import cv2 as _cv2
        _page_img = _cv2.imread(str(image_path))
    except Exception:
        _page_img = None

    try:
        for idx, region in enumerate(regions):
            crop_path: Path | None = None
            if region.type in (REGION_TABLE, REGION_FORMULA, REGION_CODE):
                if _page_img is not None:
                    crop_path = _crop_ndarray_to_temp(_page_img, region.bbox)
                else:
                    crop_path = _crop_image_to_temp(image_path, region.bbox)
                if crop_path:
                    temp_crops.append(crop_path)

            # Routing: one region type → one processor; do not run multiple models per region.
            if region.type == REGION_TABLE:
                content = extract_table_region(crop_path) if crop_path else _ocr_region_to_text(image_path)
                elements.append({
                    "type": "table",
                    "content": content,
                    "bbox": region.bbox,
                    "word_count": len(content.split()),
                })
            elif region.type == REGION_FORMULA:
                content = formula_to_latex(crop_path or image_path, use_formula_ocr=use_formula)
                if content:
                    elements.append({
                        "type": "formula",
                        "content": content,
                        "bbox": region.bbox,
                        "word_count": len(content.split()),
                    })
            elif region.type == REGION_CODE:
                content = _ocr_region_to_text(crop_path) if crop_path else _ocr_region_to_text(image_path)
                if content:
                    elements.append({
                        "type": "code",
                        "content": content,
                        "bbox": region.bbox,
                        "word_count": len(content.split()),
                    })
            elif region.type == REGION_FIGURE:
                elements.append({
                    "type": "image",
                    "content": "[figure]",
                    "bbox": region.bbox,
                    "word_count": 0,
                })
            else:
                # text, title, caption — crop from already-loaded ndarray
                if _page_img is not None:
                    crop_path2 = _crop_ndarray_to_temp(_page_img, region.bbox)
                else:
                    crop_path2 = _crop_image_to_temp(image_path, region.bbox)
                if crop_path2:
                    temp_crops.append(crop_path2)
                    content = _ocr_region_to_text(crop_path2)
                else:
                    content = _ocr_region_to_text(image_path)
                if content:
                    el_type = "title" if region.type == REGION_TITLE else "text"
                    elements.append({
                        "type": el_type,
                        "content": content,
                        "bbox": region.bbox,
                        "word_count": len(content.split()),
                    })
    finally:
        _page_img = None  # release numpy array
        for p in temp_crops:
            try:
                if p and p.exists():
                    p.unlink()
            except OSError:
                pass

    # Fallback: if layout path produced no content, run full-page OCR so we don't return 0 words
    if not elements:
        full_text = _ocr_region_to_text(image_path)
        if full_text:
            logger.info("Layout path produced no elements for page %s; using full-page OCR fallback", page_num)
            elements.append({
                "type": "text",
                "content": full_text,
                "bbox": None,
                "word_count": len(full_text.split()),
            })

    return elements


def _extract_pdf_structured_with_layout(
    file_path: str, document_id: str, upload_path: Path | None = None
) -> tuple[list[Chapter], int, int]:
    """
    Section 7 full pipeline: for each page image → layout detection → per-region
    processing → structure builder. Returns (chapters, page_count, total_word_count).
    Pages are streamed one at a time into the structure builder to avoid holding all
    per-page element dicts in memory simultaneously.
    """
    from app.services.structure_builder import build_document_structure

    page_count = _get_pdf_page_count(file_path)

    def _page_elements_iter():
        for n in range(1, page_count + 1):
            image_path: Path | None = None
            is_temp = False
            if upload_path:
                screenshot = upload_path / document_id / "screenshots" / f"page_{n}.png"
                if screenshot.exists():
                    image_path = screenshot
            if image_path is None:
                image_path = _render_pdf_page_to_image(file_path, n)
                if image_path is None:
                    yield []
                    continue
                is_temp = True
            try:
                yield _extract_page_with_layout(image_path, document_id, n)
            finally:
                if is_temp and image_path and image_path.exists():
                    try:
                        image_path.unlink()
                    except OSError:
                        pass
            import time; time.sleep(0)  # yield GIL so uvicorn can process HTTP requests

    structure = build_document_structure(document_id, _page_elements_iter())
    import gc; gc.collect()
    chapters = structure.chapters
    total_word_count = structure.totalWordCount or 0
    return chapters, len(chapters), total_word_count


def _extract_pdf_paddle_structured(
    file_path: str, document_id: str, upload_path: Path | None = None
) -> tuple[list[Chapter], int, int]:
    """Extract PDF using PaddleOCR on each page image (screenshot or rendered).
    Returns (chapters, page_count, total_word_count)."""
    page_count = _get_pdf_page_count(file_path)
    chapters: list[Chapter] = []
    total_word_count = 0
    for n in range(1, page_count + 1):
        image_path: Path | None = None
        is_temp = False
        if upload_path:
            screenshot = upload_path / document_id / "screenshots" / f"page_{n}.png"
            if screenshot.exists():
                image_path = screenshot
        if image_path is None:
            image_path = _render_pdf_page_to_image(file_path, n)
            if image_path is None:
                chapters.append(
                    Chapter(
                        chapter_id=f"ch-p{n}",
                        heading=f"Page {n}",
                        content_blocks=[],
                        order_index=n - 1,
                        wordCount=0,
                    )
                )
                continue
            is_temp = True
        try:
            content_blocks = _paddle_image_to_blocks(image_path, document_id, n)
        finally:
            if is_temp and image_path and image_path.exists():
                try:
                    image_path.unlink()
                except OSError:
                    pass
        import time; time.sleep(0)  # yield GIL so uvicorn can process HTTP requests
        wc = sum(b.wordCount or 0 for b in content_blocks)
        total_word_count += wc
        chapters.append(
            Chapter(
                chapter_id=f"ch-p{n}",
                heading=f"Page {n}",
                content_blocks=content_blocks,
                order_index=n - 1,
                wordCount=wc,
            )
        )
    return chapters, len(chapters), total_word_count


def extract_pdf(db: Session, document_id: str, file_path: str, upload_path: Path | None = None) -> None:
    """Run PDF (PaddleOCR) extraction for source='pdf'. Textract is run separately in jobs.py."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise ValueError("Document not found")
    _create_pdf_fallback_extraction(db, document_id, doc.name, file_path, upload_path=upload_path)


def _create_pdf_fallback_extraction(
    db: Session, document_id: str, doc_name: str, file_path: str, upload_path: Path | None = None
) -> None:
    """
    3-tier PDF extraction:
      Tier 1: PyMuPDF native (font analysis + pdfplumber tables) — text-based PDFs
      Tier 2: Layout pipeline (PP-Structure / LayoutParser) — if use_pp_structure enabled
      Tier 3: PaddleOCR full-page OCR — scanned PDFs / fallback
    """
    settings = get_settings()
    chapters: list | None = None
    page_count = 0
    total_word_count = 0

    # ── Tier 1: PyMuPDF native extraction ─────────────────────────────────────
    if getattr(settings, "use_native_extraction", True):
        try:
            from app.services.native_extractor import extract_pdf_native
            result = extract_pdf_native(
                file_path, document_id, upload_path,
                use_pdfplumber=getattr(settings, "use_pdfplumber_tables", True),
                use_pix2tex=getattr(settings, "use_pix2tex", False),
                use_pp_structure=getattr(settings, "use_pp_structure", False),
            )
            if result is not None:
                chapters, page_count, total_word_count = result
                logger.info(
                    "Tier 1 (native) extraction: %d pages, %d words",
                    page_count, total_word_count,
                )
        except Exception as e:
            logger.warning("Tier 1 native extraction failed: %s", e)
            chapters = None

    # ── Tier 2: Layout pipeline (PP-Structure / LayoutParser) ─────────────────
    if chapters is None and getattr(settings, "use_pp_structure", False):
        try:
            chapters, page_count, total_word_count = _extract_pdf_structured_with_layout(
                file_path, document_id, upload_path=upload_path
            )
            logger.info(
                "Tier 2 (layout) extraction: %d pages, %d words",
                page_count, total_word_count,
            )
        except Exception as e:
            logger.warning("Tier 2 layout pipeline failed: %s", e)
            chapters = None

    # ── Tier 3: PaddleOCR full-page OCR ────────────────────────────────────────
    if chapters is None:
        chapters, page_count, total_word_count = _extract_pdf_paddle_structured(
            file_path, document_id, upload_path=upload_path
        )
        logger.info(
            "Tier 3 (PaddleOCR) extraction: %d pages, %d words",
            page_count, total_word_count,
        )

    if not chapters:
        chapters = [
            Chapter(
                chapter_id="ch-0",
                heading="Page 1",
                content_blocks=[
                    ContentBlock(
                        id=f"{document_id}-pdf-b0",
                        type="text",
                        content="(No text could be extracted from this PDF.)",
                        orderIndex=0,
                        wordCount=0,
                    )
                ],
                order_index=0,
                wordCount=0,
            )
        ]
        page_count = 1
        total_word_count = 0
    structure = DocumentStructure(
        documentId=document_id,
        source="pdf",
        chapters=chapters,
        totalWordCount=total_word_count,
        pageCount=page_count,
    )
    ext = Extraction(
        document_id=document_id,
        source="pdf",
        structure=structure.model_dump(),
        parser_version=get_settings().parser_version,
    )
    db.add(ext)
    db.add(
        AuditLog(
            document_id=document_id,
            document_name=doc_name,
            reviewer="System",
            action="PaddleOCR extraction",
            validation_result="Extracted",
            parser_version=get_settings().parser_version,
        )
    )
    db.query(Document).filter(Document.id == document_id).update(
        {"page_count": page_count}, synchronize_session=False
    )
    db.commit()


def _render_pdf_page_to_image(file_path: str, page_num: int, dpi: int | None = None) -> Path | None:
    """Render a single PDF page to a temporary PNG file. Returns path or None on failure."""
    if dpi is None:
        dpi = get_settings().screenshot_dpi
    try:
        import pymupdf
    except ImportError:
        return None
    try:
        doc = pymupdf.open(file_path)
        try:
            if page_num < 1 or page_num > len(doc):
                return None
            page = doc[page_num - 1]
            pix = page.get_pixmap(dpi=dpi, alpha=False)
            fd, path = tempfile.mkstemp(suffix=".png")
            os.close(fd)
            pix.save(path)
            return Path(path)
        finally:
            doc.close()
    except Exception as e:
        logger.warning("Failed to render PDF page %s to image: %s", page_num, e)
        return None
