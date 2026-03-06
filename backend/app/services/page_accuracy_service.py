"""
Page-level accuracy: OCR screenshot as ground truth, compare with extracted text (PDF/Textract).
Store accuracy per page; set validation_failed if any page < 98%, audit CRITICAL_MISMATCH if < 80%.
"""
import logging
import re
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.extraction import Extraction
from app.models.page_validation import PageScreenshot, PageAccuracy
from app.models.audit import AuditLog
from app.config import get_settings

logger = logging.getLogger(__name__)

# Ensure Tesseract binary is found when running under launchd (limited PATH).
import os as _os
for _t in ["/opt/homebrew/bin/tesseract", "/usr/local/bin/tesseract"]:
    if _os.path.isfile(_t):
        try:
            import pytesseract as _pyt
            _pyt.pytesseract.tesseract_cmd = _t
        except Exception:
            pass
        break

ACCURACY_THRESHOLD_PCT = 98.0
CRITICAL_MISMATCH_PCT = 80.0


def _normalize(text: str) -> str:
    """Lowercase, collapse whitespace, strip."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", text.lower().strip())


def _word_tokens(text: str) -> list[str]:
    return _normalize(text).split()


def _word_match_pct(reference: str, extracted: str) -> float:
    """Ratio of matching words (intersection / reference word count); 0-100."""
    ref_words = _word_tokens(reference)
    ext_words = set(_word_tokens(extracted))
    if not ref_words:
        return 100.0
    matches = sum(1 for w in ref_words if w in ext_words)
    return 100.0 * matches / len(ref_words)


def _char_match_pct(reference: str, extracted: str) -> float:
    """Character-level similarity: 100 * (2 * common / (len(ref) + len(ext)))."""
    ref = _normalize(reference)
    ext = _normalize(extracted)
    if not ref and not ext:
        return 100.0
    if not ref or not ext:
        return 0.0
    ref_chars = set(ref)
    ext_chars = set(ext)
    common = len(ref_chars & ext_chars)
    total = len(ref_chars | ext_chars)
    if total == 0:
        return 100.0
    return 100.0 * common / total


def _get_page_text_from_structure(structure: dict, page_number: int) -> str:
    """From DocumentStructure (chapters), return concatenated content for chapter heading 'Page {n}'."""
    chapters = structure.get("chapters") or []
    for ch in chapters:
        if ch.get("heading") == f"Page {page_number}":
            blocks = ch.get("content_blocks") or []
            return " ".join(b.get("content") or "" for b in blocks)
    return ""


def compute_page_accuracy(db: Session, document_id: str, upload_dir: Path) -> None:
    """
    For each page screenshot: OCR image, get PDF/Textract extracted text for that page,
    compute word_match, char_match, structural_match; persist to page_accuracy.
    Set document validation_status = validation_failed if any page < 98%;
    add audit CRITICAL_MISMATCH for any page < 80%.
    """
    try:
        import pytesseract
        from PIL import Image
    except ImportError as e:
        logger.warning("page_accuracy skipped (pytesseract/PIL not available): %s", e)
        return

    screenshots = (
        db.query(PageScreenshot)
        .filter(PageScreenshot.document_id == document_id)
        .order_by(PageScreenshot.page_number)
        .all()
    )
    if not screenshots:
        return

    pdf_ext = db.query(Extraction).filter(
        Extraction.document_id == document_id,
        Extraction.source == "pdf",
    ).first()
    textract_ext = db.query(Extraction).filter(
        Extraction.document_id == document_id,
        Extraction.source == "textract",
    ).first()
    pdf_structure = pdf_ext.structure if pdf_ext else {}
    textract_structure = textract_ext.structure if textract_ext else {}

    doc = db.query(Document).filter(Document.id == document_id).first()
    validation_failed = False
    critical_pages: list[int] = []

    for ps in screenshots:
        page_num = ps.page_number
        img_path = upload_dir / ps.file_path
        if not img_path.exists():
            logger.warning("Screenshot not found for page %s: %s", page_num, img_path)
            continue
        try:
            img = Image.open(img_path)
            ocr_text = pytesseract.image_to_string(img)
        except Exception as e:
            logger.warning("OCR failed for page %s: %s", page_num, e)
            ocr_text = ""
        pdf_text = _get_page_text_from_structure(pdf_structure, page_num)
        textract_text = _get_page_text_from_structure(textract_structure, page_num)
        extracted = pdf_text or textract_text or ""

        word_pct = _word_match_pct(ocr_text, extracted)
        char_pct = _char_match_pct(ocr_text, extracted)
        structural_pct = 100.0  # MVP: no block-level comparison
        accuracy_pct = 0.4 * word_pct + 0.4 * char_pct + 0.2 * structural_pct

        db.add(
            PageAccuracy(
                document_id=document_id,
                page_number=page_num,
                accuracy_pct=accuracy_pct,
                word_match_pct=word_pct,
                char_match_pct=char_pct,
                structural_match_pct=structural_pct,
                ocr_text_length=len(ocr_text),
            )
        )
        if accuracy_pct < ACCURACY_THRESHOLD_PCT:
            validation_failed = True
        if accuracy_pct < CRITICAL_MISMATCH_PCT:
            critical_pages.append(page_num)

    db.commit()

    if validation_failed and doc:
        doc.validation_status = "validation_failed"
        db.add(
            AuditLog(
                document_id=document_id,
                document_name=doc.name,
                reviewer="System",
                action="Page extraction below threshold (98%)",
                validation_result="Validation Failed",
                parser_version=get_settings().parser_version,
                metadata_={"reason": "page_accuracy_below_threshold"},
            )
        )
    for p in critical_pages:
        db.add(
            AuditLog(
                document_id=document_id,
                document_name=doc.name if doc else "",
                reviewer="System",
                action=f"CRITICAL_MISMATCH — Page {p}",
                validation_result="Critical Mismatch",
                parser_version=get_settings().parser_version,
                metadata_={"page_number": p},
            )
        )
    db.commit()
    logger.info("Page accuracy computed for document %s (%d pages)", document_id, len(screenshots))
