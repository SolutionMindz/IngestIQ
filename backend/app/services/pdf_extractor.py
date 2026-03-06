"""
PDF extraction: two extractions for side-by-side comparison.
- source="pdf": native extraction (PyMuPDF), one chapter per page, block-level; no truncation.
- source="textract": AWS Textract extraction (see textract_extractor.py).

# ---------------------------------------------------------------------------
# OCR ENGINE CODE DISABLED — replaced by AWS Textract (textract_extractor.py)
# ---------------------------------------------------------------------------
# The following OCR pipeline (PaddleOCR → EasyOCR → Tesseract) has been
# commented out. AWS Textract is now used for the second extraction panel.
# To re-enable, uncomment the sections marked [OCR_DISABLED].
# ---------------------------------------------------------------------------
"""
import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.extraction import Extraction
from app.models.audit import AuditLog
from app.config import get_settings
from app.schemas.structure import DocumentStructure, Chapter, ContentBlock, BoundingBox

logger = logging.getLogger(__name__)

# [OCR_DISABLED] Tesseract binary path setup for launchd (restricted PATH)
# import os
# for _t in ["/opt/homebrew/bin/tesseract", "/usr/local/bin/tesseract"]:
#     if os.path.isfile(_t):
#         try:
#             import pytesseract as _pyt
#             _pyt.pytesseract.tesseract_cmd = _t
#         except Exception:
#             pass
#         break
#
# PSM_FULL_PAGE = 3
# PSM_SINGLE_COLUMN = 4
# PSM_SINGLE_BLOCK = 6
# OCR_CONF_THRESHOLD = 0.95

# [OCR_DISABLED] Engine singletons
# _paddle_ocr = None
# _easyocr_reader = None
#
# def _get_paddle(): ...
# def _get_easyocr(): ...

# [OCR_DISABLED] Per-engine extraction helpers
# def _run_paddle(image_path): ...
# def _run_easyocr(image_path): ...
# def _run_tesseract(image_path, page_num): ...

# [OCR_DISABLED] Main OCR dispatcher
# def _ocr_image_to_blocks(image_path, document_id, page_num): ...


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
    """Run PDF (native) and OCR extractions for side-by-side comparison.
    When upload_path is provided and screenshots exist, OCR uses them; else renders each PDF page to image.
    """
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise ValueError("Document not found")

    # 1) Always create "pdf" extraction (native PyMuPDF)
    _create_pdf_fallback_extraction(db, document_id, doc.name, file_path, upload_path=upload_path)

    # [OCR_DISABLED] OCR extraction replaced by AWS Textract (called from jobs.py)
    # _extract_ocr(db, document_id, file_path, doc.name, upload_path=upload_path)


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


def _render_pdf_page_to_image(file_path: str, page_num: int, dpi: int = 300) -> Path | None:
    """Render a single PDF page to a temporary PNG file. Returns path or None on failure."""
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
            import os
            os.close(fd)
            pix.save(path)
            return Path(path)
        finally:
            doc.close()
    except Exception as e:
        logger.warning("Failed to render PDF page %s to image: %s", page_num, e)
        return None


# [OCR_DISABLED] _extract_ocr — pytesseract/PaddleOCR/EasyOCR extraction
# This function has been replaced by extract_textract() in textract_extractor.py.
# To restore OCR, uncomment this function and re-enable its call in extract_pdf().
#
# def _extract_ocr(db, document_id, file_path, doc_name, upload_path=None):
#     """Run pytesseract OCR on every page screenshot; store as source='ocr'."""
#     ... (see git history)


def _extract_pdf_native_structured(
    file_path: str, document_id: str, upload_path: Path | None = None
) -> tuple[list[Chapter], int, int]:
    """Extract PDF with PyMuPDF: one chapter per page, one content_block per line.
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
                # [OCR_DISABLED] Image-only page fallback removed (OCR replaced by Textract).
                # Native text pages keep their PyMuPDF blocks; image-only pages will show empty in pdf panel.
                # page_word_count = sum(b.wordCount or 0 for b in content_blocks)
                # if page_word_count == 0 and upload_path is not None:
                #     screenshot_path = (upload_path / document_id / "screenshots" / f"page_{page_num + 1}.png").resolve()
                #     ocr_blocks = _ocr_image_to_blocks(screenshot_path, document_id, page_num + 1)
                #     if ocr_blocks:
                #         total_word_count += sum(b.wordCount or 0 for b in ocr_blocks)
                #         content_blocks = ocr_blocks
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
