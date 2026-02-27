"""
PDF extraction: two extractions for side-by-side comparison.
- source="pdf": native extraction (PyMuPDF), one chapter per page, block-level; no truncation.
- source="textract": AWS Textract — single-page bytes (screenshots or rendered page) or async S3 for multi-page; one chapter per page, LINE blocks.
See: https://aws.amazon.com/textract
"""
import logging
import time
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.extraction import Extraction
from app.models.audit import AuditLog
from app.config import get_settings
from app.schemas.structure import DocumentStructure, Chapter, ContentBlock, BoundingBox

logger = logging.getLogger(__name__)

# Tesseract PSM: 3 = fully automatic, 6 = single block of text. Use 6 for cover pages with one block.
TESSERACT_PSM_OCR_FALLBACK = "6"


def _ocr_screenshot_to_blocks(
    screenshot_path: Path, document_id: str, page_num: int
) -> list[ContentBlock]:
    """Run Tesseract OCR on a page screenshot; return one ContentBlock per non-empty line.
    Uses RGB image and PSM 6 for better results on cover/image-only pages. Returns [] if OCR unavailable or fails."""
    try:
        import pytesseract
        from PIL import Image
    except ImportError as e:
        logger.warning("OCR fallback skipped for page %s: pytesseract/PIL not available: %s", page_num, e)
        return []
    path_resolved = Path(screenshot_path).resolve()
    if not path_resolved.exists():
        logger.warning("OCR fallback skipped for page %s: screenshot not found at %s", page_num, path_resolved)
        return []
    try:
        img = Image.open(path_resolved)
        # Tesseract works more reliably with RGB; convert if necessary (e.g. RGBA, P)
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        config = f"--psm {TESSERACT_PSM_OCR_FALLBACK}"
        text = pytesseract.image_to_string(img, config=config)
        if not text.strip():
            text = pytesseract.image_to_string(img, config="--psm 3")
    except Exception as e:
        logger.warning("OCR fallback for page %s failed (path=%s): %s", page_num, path_resolved, e)
        return []
    blocks: list[ContentBlock] = []
    for i, line in enumerate(text.splitlines()):
        line = line.strip()
        if not line:
            continue
        wc = len(line.split())
        blocks.append(
            ContentBlock(
                id=f"{document_id}-p{page_num}-ocr-b{i}",
                type="text",
                content=line,
                orderIndex=i,
                wordCount=wc,
                bbox=None,
            )
        )
    if not blocks and text.strip():
        # Single block if no newlines but has text
        line = text.strip()
        wc = len(line.split())
        blocks.append(
            ContentBlock(
                id=f"{document_id}-p{page_num}-ocr-b0",
                type="text",
                content=line,
                orderIndex=0,
                wordCount=wc,
                bbox=None,
            )
        )
    if blocks:
        logger.info("OCR fallback for page %s: extracted %d blocks from %s", page_num, len(blocks), path_resolved)
    else:
        logger.info("OCR fallback for page %s: no text detected from %s (Tesseract may need install: apt install tesseract-ocr)", page_num, path_resolved)
    return blocks


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


def extract_pdf(db: Session, document_id: str, file_path: str, upload_path: Path | None = None) -> None:
    """Run PDF (native) and Textract extractions for side-by-side comparison.
    When upload_path is provided and screenshots exist, Textract uses them (single-page bytes per image).
    """
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise ValueError("Document not found")

    # 1) Always create "pdf" extraction (structural/fallback view); use screenshot OCR for image-only pages when available
    _create_pdf_fallback_extraction(db, document_id, doc.name, file_path, upload_path=upload_path)

    # 2) Always create "textract" extraction (AWS Textract or placeholder)
    _extract_textract(db, document_id, file_path, doc.name, upload_path=upload_path)


def _create_pdf_fallback_extraction(
    db: Session, document_id: str, doc_name: str, file_path: str, upload_path: Path | None = None
) -> None:
    """Extract PDF with native parser (PyMuPDF). One chapter per page, blocks per block; no truncation.
    When upload_path is set, run OCR on every page's screenshot and use OCR result when available (so image/diagram content is extracted)."""
    chapters, page_count, total_word_count = _extract_pdf_native_structured(
        file_path, document_id, upload_path=upload_path
    )
    if not chapters:
        # Fallback if PyMuPDF fails or returns nothing
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
            action="PDF extraction (native)",
            validation_result="Extracted",
            parser_version=get_settings().parser_version,
        )
    )
    doc = db.query(Document).filter(Document.id == document_id).first()
    if doc is not None:
        doc.page_count = page_count
    db.commit()


def _extract_pdf_native_structured(
    file_path: str, document_id: str, upload_path: Path | None = None
) -> tuple[list[Chapter], int, int]:
    """Extract PDF with PyMuPDF: one chapter per page, one content_block per line (match Textract LINE granularity).
    Uses get_text('dict') for line-level structure so comparison with Textract is easier.
    Disables TEXT_MEDIABOX_CLIP so header/footer and other content in clipped regions are included.
    When upload_path is set, run OCR on every page's screenshot and use the OCR result when available (extracts text from images/diagrams)."""
    try:
        import pymupdf
    except ImportError:
        return [], 1, 0
    # Include text in clipped regions (e.g. headers/footers); default clip excludes some PDFs' header/footer.
    flags_dict = (pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_MEDIABOX_CLIP) & ~pymupdf.TEXT_PRESERVE_IMAGES
    flags_blocks = pymupdf.TEXTFLAGS_BLOCKS & ~pymupdf.TEXT_MEDIABOX_CLIP
    try:
        doc = pymupdf.open(file_path)
        chapters: list[Chapter] = []
        total_word_count = 0
        try:
            for page_num in range(len(doc)):
                page = doc[page_num]
                content_blocks: list[ContentBlock] = []
                block_index = 0
                try:
                    dict_result = page.get_text("dict", flags=flags_dict, sort=True)
                except Exception:
                    dict_result = None
                if dict_result and dict_result.get("blocks"):
                    for block in dict_result["blocks"]:
                        lines = block.get("lines") or []
                        for line in lines:
                            spans = line.get("spans") or []
                            line_text = "".join(s.get("text", "") for s in spans).strip()
                            if not line_text:
                                continue
                            wc = len(line_text.split())
                            total_word_count += wc
                            bbox = None
                            rect = line.get("bbox") or (spans[0].get("bbox") if spans else None)
                            if rect and len(rect) >= 4:
                                x0, y0, x1, y1 = float(rect[0]), float(rect[1]), float(rect[2]), float(rect[3])
                                bbox = BoundingBox(left=x0, top=y0, width=x1 - x0, height=y1 - y0)
                            content_blocks.append(
                                ContentBlock(
                                    id=f"{document_id}-p{page_num + 1}-b{block_index}",
                                    type="text",
                                    content=line_text,
                                    orderIndex=block_index,
                                    wordCount=wc,
                                    bbox=bbox,
                                )
                            )
                            block_index += 1
                else:
                    blocks_raw = page.get_text("blocks", flags=flags_blocks, sort=True)
                    for block in blocks_raw:
                        x0, y0, x1, y1 = block[0], block[1], block[2], block[3]
                        text = (block[4] or "").strip()
                        if not text:
                            continue
                        for line in text.splitlines():
                            line = line.strip()
                            if not line:
                                continue
                            wc = len(line.split())
                            total_word_count += wc
                            bbox = BoundingBox(left=x0, top=y0, width=x1 - x0, height=y1 - y0)
                            content_blocks.append(
                                ContentBlock(
                                    id=f"{document_id}-p{page_num + 1}-b{block_index}",
                                    type="text",
                                    content=line,
                                    orderIndex=block_index,
                                    wordCount=wc,
                                    bbox=bbox,
                                )
                            )
                            block_index += 1
                # Run OCR on every page when screenshot is available (extract text from images/diagrams as well as native text)
                page_word_count = sum(b.wordCount or 0 for b in content_blocks)
                if upload_path is not None:
                    screenshot_path = (upload_path / document_id / "screenshots" / f"page_{page_num + 1}.png").resolve()
                    ocr_blocks = _ocr_screenshot_to_blocks(screenshot_path, document_id, page_num + 1)
                    if ocr_blocks:
                        total_word_count -= page_word_count
                        total_word_count += sum(b.wordCount or 0 for b in ocr_blocks)
                        content_blocks = ocr_blocks
                ch = Chapter(
                    chapter_id=f"ch-p{page_num + 1}",
                    heading=f"Page {page_num + 1}",
                    content_blocks=content_blocks,
                    order_index=page_num,
                    wordCount=sum(b.wordCount or 0 for b in content_blocks),
                )
                chapters.append(ch)
        finally:
            doc.close()
        return chapters, len(chapters), total_word_count
    except Exception:
        return [], 1, 0


def _extract_textract(
    db: Session, document_id: str, file_path: str, doc_name: str, upload_path: Path | None = None
) -> DocumentStructure | None:
    """Run AWS Textract: sync single-page (bytes), or multi-page via S3 (async) or per-page bytes (screenshots when available). Output: one chapter per page, LINE blocks."""
    try:
        import boto3
        from botocore.exceptions import ClientError
    except ImportError:
        _create_mock_textract_extraction(db, document_id, doc_name, None)
        return None

    settings = get_settings()
    if not settings.aws_access_key_id or not settings.aws_secret_access_key:
        _create_mock_textract_extraction(db, document_id, doc_name, None)
        return None

    page_count = _get_pdf_page_count(file_path)
    client_kw = {
        "region_name": settings.aws_region,
        "aws_access_key_id": settings.aws_access_key_id,
        "aws_secret_access_key": settings.aws_secret_access_key,
    }
    if settings.aws_session_token:
        client_kw["aws_session_token"] = settings.aws_session_token
    client = boto3.client("textract", **client_kw)

    blocks: list[dict]
    job_id: str | None = None
    page_count_from_response = page_count

    if page_count <= 1:
        # Sync: AnalyzeDocument (1 page only)
        with open(file_path, "rb") as f:
            data = f.read()
        try:
            response = client.analyze_document(
                Document={"Bytes": data},
                FeatureTypes=["TABLES", "FORMS"],
            )
        except ClientError as e:
            logger.warning("Textract AnalyzeDocument failed: %s", e)
            _create_mock_textract_extraction(db, document_id, doc_name, str(e))
            return None
        blocks = response.get("Blocks", [])
        page_count_from_response = response.get("DocumentMetadata", {}).get("Pages", 1)
    else:
        # Multi-page: prefer async (S3) if bucket set; else use screenshots if available, else render PDF per page
        if settings.aws_s3_bucket:
            blocks, job_id, page_count_from_response = _textract_async_detect(
                client, file_path, settings.aws_s3_bucket, document_id
            )
            if not blocks:
                _create_mock_textract_extraction(
                    db, document_id, doc_name,
                    "Textract async job failed or returned no blocks.",
                )
                return None
            job_id = job_id
        else:
            # Use screenshot images when available (DetectDocumentText/AnalyzeDocument accept single-page bytes only)
            per_page_error: str | None = None
            if upload_path is not None:
                screenshot_dir = upload_path / document_id / "screenshots"
                if screenshot_dir.exists():
                    blocks, page_count_from_response, per_page_error = _textract_from_screenshots(
                        client, screenshot_dir, page_count
                    )
                else:
                    blocks, page_count_from_response, per_page_error = _textract_sync_multipage(
                        client, file_path, page_count
                    )
            else:
                blocks, page_count_from_response, per_page_error = _textract_sync_multipage(
                    client, file_path, page_count
                )
            if not blocks:
                msg = (
                    per_page_error
                    if per_page_error
                    else "Textract per-page (screenshots/PDF) failed or returned no blocks."
                )
                _create_mock_textract_extraction(db, document_id, doc_name, msg)
                return None
            job_id = None

    structure = _textract_blocks_to_structure(document_id, blocks, page_count_from_response)
    confs = [b["Confidence"] for b in blocks if "Confidence" in b]
    avg_confidence = sum(confs) / len(confs) if confs else None
    # Per-page average confidence (so Chapter Explorer shows the correct value per page, not the same doc total)
    from collections import defaultdict
    page_confs: dict[int, list[float]] = defaultdict(list)
    for b in blocks:
        if "Confidence" not in b:
            continue
        p = b.get("Page", 1)
        page_confs[p].append(float(b["Confidence"]))
    page_confidence = {p: round(sum(c) / len(c), 2) for p, c in page_confs.items() if c}
    meta = {}
    if job_id:
        meta["textract_job_id"] = job_id
    if avg_confidence is not None:
        meta["average_confidence"] = round(avg_confidence, 2)
    if page_confidence:
        meta["page_confidence"] = page_confidence
    ext = Extraction(
        document_id=document_id,
        source="textract",
        structure=structure.model_dump(),
        parser_version=get_settings().parser_version,
        textract_job_id=job_id,
        metadata_=meta if meta else None,
    )
    db.add(ext)
    db.add(
        AuditLog(
            document_id=document_id,
            document_name=doc_name,
            reviewer="System",
            action="AWS Textract extraction completed",
            validation_result="Extracted",
            parser_version=get_settings().parser_version,
            metadata_=meta if meta else None,
        )
    )
    db.commit()
    return structure


def _textract_from_screenshots(
    client, screenshot_dir: Path, page_count: int
) -> tuple[list[dict], int, str | None]:
    """Run Textract on each screenshot image (single-page bytes). Returns (blocks, page_count, first_error)."""
    from botocore.exceptions import ClientError
    all_blocks: list[dict] = []
    first_error: str | None = None
    for page_num in range(1, page_count + 1):
        img_path = screenshot_dir / f"page_{page_num}.png"
        if not img_path.exists():
            logger.warning("Textract from screenshots: missing %s, skipping page %s", img_path, page_num)
            continue
        with open(img_path, "rb") as f:
            img_bytes = f.read()
        try:
            response = client.analyze_document(
                Document={"Bytes": img_bytes},
                FeatureTypes=["TABLES", "FORMS"],
            )
        except ClientError as e:
            err_msg = str(e)
            if first_error is None:
                first_error = err_msg
            logger.warning("Textract AnalyzeDocument (screenshot page %s) failed: %s", page_num, e)
            continue
        for block in response.get("Blocks", []):
            block = dict(block)
            block["Page"] = page_num
            all_blocks.append(block)
    return all_blocks, page_count, first_error


def _textract_sync_multipage(
    client, file_path: str, page_count: int
) -> tuple[list[dict], int, str | None]:
    """Run sync AnalyzeDocument per page (render each page to image). No S3 required. Returns (blocks, page_count, first_error)."""
    import pymupdf
    from botocore.exceptions import ClientError
    settings = get_settings()
    # Use same DPI as screenshots (min 300 for Textract input quality; 400 recommended for code-heavy pages)
    dpi = max(300, getattr(settings, "screenshot_dpi", 300))
    all_blocks: list[dict] = []
    first_error: str | None = None
    try:
        doc = pymupdf.open(file_path)
        try:
            for page_num in range(min(page_count, len(doc))):
                page = doc[page_num]
                pix = page.get_pixmap(dpi=dpi, alpha=False)
                img_bytes = pix.tobytes(output="png")
                try:
                    response = client.analyze_document(
                        Document={"Bytes": img_bytes},
                        FeatureTypes=["TABLES", "FORMS"],
                    )
                except ClientError as e:
                    err_msg = str(e)
                    if first_error is None:
                        first_error = err_msg
                    logger.warning("Textract AnalyzeDocument page %s failed: %s", page_num + 1, e)
                    continue
                for block in response.get("Blocks", []):
                    block = dict(block)
                    block["Page"] = page_num + 1
                    all_blocks.append(block)
        finally:
            doc.close()
    except Exception as e:
        logger.exception("Textract sync multipage failed: %s", e)
        return [], page_count, str(e)
    return all_blocks, page_count, first_error


def _textract_async_detect(
    client, file_path: str, bucket: str, document_id: str
) -> tuple[list[dict], str | None, int]:
    """Upload PDF to S3, start StartDocumentTextDetection, poll GetDocumentTextDetection, return (blocks, job_id, page_count)."""
    import uuid
    key = f"textract-input/{document_id}/{uuid.uuid4().hex}.pdf"
    try:
        import boto3
        s = get_settings()
        s3_kw = {
            "region_name": client.meta.region_name,
            "aws_access_key_id": s.aws_access_key_id,
            "aws_secret_access_key": s.aws_secret_access_key,
        }
        if s.aws_session_token:
            s3_kw["aws_session_token"] = s.aws_session_token
        s3_client = boto3.client("s3", **s3_kw)
    except Exception as e:
        logger.warning("S3 client failed: %s", e)
        return [], None, 1
    with open(file_path, "rb") as f:
        data = f.read()
    try:
        s3_client.put_object(Bucket=bucket, Key=key, Body=data, ContentType="application/pdf")
    except Exception as e:
        logger.warning("S3 upload failed: %s", e)
        return [], None, 1
    try:
        start_resp = client.start_document_text_detection(
            DocumentLocation={"S3Object": {"Bucket": bucket, "Name": key}},
        )
        job_id = start_resp.get("JobId")
        if not job_id:
            return [], None, 1
        page_count = 1
        while True:
            time.sleep(2)
            get_resp = client.get_document_text_detection(JobId=job_id)
            status = get_resp.get("JobStatus")
            if status == "SUCCEEDED":
                page_count = get_resp.get("DocumentMetadata", {}).get("Pages", 1)
                break
            if status in ("FAILED", "PARTIAL_SUCCESS"):
                logger.warning("Textract job %s status: %s", job_id, status)
                return [], job_id, 1
        blocks = list(get_resp.get("Blocks", []))
        next_token = get_resp.get("NextToken")
        while next_token:
            get_resp = client.get_document_text_detection(JobId=job_id, NextToken=next_token)
            blocks.extend(get_resp.get("Blocks", []))
            next_token = get_resp.get("NextToken")
        if not page_count and blocks:
            pages = {b.get("Page") for b in blocks if b.get("Page")}
            page_count = max(pages) if pages else 1
        return blocks, job_id, page_count
    except Exception as e:
        logger.exception("Textract async failed: %s", e)
        return [], None, 1
    finally:
        try:
            s3_client.delete_object(Bucket=bucket, Key=key)
        except Exception:
            pass


def _textract_cell_text(blocks_by_id: dict[str, dict], cell_block: dict) -> str:
    """Get concatenated text from a CELL block's WORD children."""
    parts: list[str] = []
    for rel in cell_block.get("Relationships") or []:
        if rel.get("Type") != "CHILD":
            continue
        for child_id in rel.get("Ids") or []:
            child = blocks_by_id.get(child_id)
            if child and child.get("BlockType") == "WORD":
                parts.append((child.get("Text") or "").strip())
    return " ".join(parts).strip()


def _textract_table_to_plain_text(blocks_by_id: dict[str, dict], table_block: dict) -> str:
    """Convert a Textract TABLE block (and its CELL children) to plain text: tab-separated columns, newline-separated rows. No markdown pipes or separator row."""
    cell_ids: list[str] = []
    for rel in table_block.get("Relationships") or []:
        if rel.get("Type") == "CHILD":
            cell_ids.extend(rel.get("Ids") or [])
    if not cell_ids:
        return ""
    cells: list[dict] = []
    for cid in cell_ids:
        cell = blocks_by_id.get(cid)
        if not cell or cell.get("BlockType") != "CELL":
            continue
        row_idx = cell.get("RowIndex", 0)
        col_idx = cell.get("ColumnIndex", 0)
        text = _textract_cell_text(blocks_by_id, cell)
        cells.append({"row": row_idx, "col": col_idx, "text": text or ""})
    if not cells:
        return ""
    max_row = max(c["row"] for c in cells)
    max_col = max(c["col"] for c in cells)
    grid: dict[int, dict[int, str]] = {}
    for c in cells:
        r, col, text = c["row"], c["col"], c["text"]
        if r not in grid:
            grid[r] = {}
        grid[r][col] = text
    rows: list[str] = []
    for r in range(1, max_row + 1):
        row_cells = [(grid.get(r) or {}).get(col) or "" for col in range(1, max_col + 1)]
        rows.append("\t".join(row_cells))
    return "\n".join(rows)


def _textract_blocks_to_structure(
    document_id: str, blocks: list[dict], page_count: int
) -> DocumentStructure:
    """Build one chapter per page: content_blocks from LINE blocks and TABLE blocks (plain text from Textract, no markdown)."""
    from collections import defaultdict
    blocks_by_id = {b["Id"]: b for b in blocks if b.get("Id")}
    by_page: dict[int, list[dict]] = defaultdict(list)
    for b in blocks:
        bt = b.get("BlockType")
        if bt == "LINE":
            by_page[b.get("Page", 1)].append(("line", b))
        elif bt == "TABLE":
            by_page[b.get("Page", 1)].append(("table", b))
    total_word_count = 0
    chapters: list[Chapter] = []
    for page_num in range(1, page_count + 1):
        page_items = by_page.get(page_num, [])
        # Sort by vertical position (top) for reading order
        def top_key(item):
            kind, blk = item
            geom = blk.get("Geometry", {}).get("BoundingBox") or {}
            return float(geom.get("Top", 0))
        page_items.sort(key=top_key)
        content_blocks: list[ContentBlock] = []
        block_index = 0
        for kind, b in page_items:
            if kind == "line":
                text = (b.get("Text") or "").strip()
                if not text:
                    continue
                wc = len(text.split())
                total_word_count += wc
                geom = b.get("Geometry", {}).get("BoundingBox") or {}
                bbox = None
                if geom:
                    bbox = BoundingBox(
                        left=float(geom.get("Left", 0)),
                        top=float(geom.get("Top", 0)),
                        width=float(geom.get("Width", 0)),
                        height=float(geom.get("Height", 0)),
                    )
                content_blocks.append(
                    ContentBlock(
                        id=f"{document_id}-textract-p{page_num}-b{block_index}",
                        type="text",
                        content=text,
                        orderIndex=block_index,
                        wordCount=wc,
                        bbox=bbox,
                    )
                )
                block_index += 1
            else:
                table_text = _textract_table_to_plain_text(blocks_by_id, b)
                if not table_text.strip():
                    continue
                wc = len(table_text.split())
                total_word_count += wc
                content_blocks.append(
                    ContentBlock(
                        id=f"{document_id}-textract-p{page_num}-t{block_index}",
                        type="table",
                        content=table_text,
                        orderIndex=block_index,
                        wordCount=wc,
                        bbox=None,
                    )
                )
                block_index += 1
        ch = Chapter(
            chapter_id=f"ch-p{page_num}",
            heading=f"Page {page_num}",
            content_blocks=content_blocks,
            order_index=page_num - 1,
            wordCount=sum(cb.wordCount or 0 for cb in content_blocks),
        )
        chapters.append(ch)
    if not chapters:
        chapters = [
            Chapter(
                chapter_id="ch-p1",
                heading="Page 1",
                content_blocks=[
                    ContentBlock(
                        id=f"{document_id}-textract-b0",
                        type="text",
                        content="(no text)",
                        orderIndex=0,
                        wordCount=0,
                    )
                ],
                order_index=0,
                wordCount=0,
            )
        ]
        total_word_count = 0
        page_count = 1
    return DocumentStructure(
        documentId=document_id,
        source="textract",
        chapters=chapters,
        totalWordCount=total_word_count,
        pageCount=page_count,
    )


def _create_mock_textract_extraction(
    db: Session, document_id: str, doc_name: str, message: str | None = None
) -> None:
    """Placeholder when AWS Textract is not configured or multi-page without S3."""
    default_msg = "AWS Textract not configured. Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY for real extraction."
    content = message if message else default_msg
    ch = Chapter(
        chapter_id="ch-p1",
        heading="Page 1",
        content_blocks=[
            ContentBlock(
                id=f"{document_id}-textract-b0",
                type="text",
                content=content,
                orderIndex=0,
                wordCount=len(content.split()),
            )
        ],
        order_index=0,
        wordCount=len(content.split()),
    )
    wc = len(content.split())
    structure = DocumentStructure(
        documentId=document_id,
        source="textract",
        chapters=[ch],
        totalWordCount=wc,
        pageCount=1,
    )
    ext = Extraction(
        document_id=document_id,
        source="textract",
        structure=structure.model_dump(),
        parser_version=get_settings().parser_version,
    )
    db.add(ext)
    db.add(
        AuditLog(
            document_id=document_id,
            document_name=doc_name,
            reviewer="System",
            action="Textract extraction (mock – no AWS credentials)" if not message else "Textract extraction (mock)",
            validation_result="Mock",
            parser_version=get_settings().parser_version,
        )
    )
    db.commit()
