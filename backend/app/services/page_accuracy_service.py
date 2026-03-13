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
from app.services.page_type_detector import classify as classify_page_type
from app.services.ocr_router import get_page_text

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
    t = _normalize(text)
    # Normalize typographic apostrophes/quotes to ASCII (fixes who\u2019s vs who's mismatches)
    t = t.translate(str.maketrans("\u2018\u2019\u02bc\u02bb", "''''"))
    # Normalize URLs FIRST (before :// gets stripped by the non-alnum run removal below)
    t = re.sub(r"(?:https?://|www\.)\S+", "url", t)
    # Remove runs of 3+ non-alphanumeric chars (dashes, dots, OCR-garbled decorations)
    t = re.sub(r"[^a-z0-9 ']{3,}", " ", t)
    tokens = []
    for w in t.split():
        # Strip leading/trailing punctuation
        w = re.sub(r"^[^a-z0-9]+|[^a-z0-9]+$", "", w)
        if len(w) < 2 or not re.search(r"[a-z]", w):  # require length ≥ 2 and at least one letter
            continue
        # Filter OCR noise: tokens where >70% is the same character (e.g. "ee", "nnn", "nnennn")
        if max(w.count(c) for c in set(w)) / len(w) > 0.7:
            continue
        # Filter OCR garbage: real words don't exceed 25 characters (dotted leader lines OCR'd as long strings)
        if len(w) > 25:
            continue
        tokens.append(w)
    return tokens


def _soft_match(token: str, nospace_text: str) -> bool:
    """
    Substring match after stripping non-alphanumeric from token.
    Handles merged OCR words ('ATestDocument' → 'atestdocument')
    and code tokens with symbols ('n_neighbors=15' → 'nneighbors15').
    """
    if len(token) < 5:
        return False
    stripped = re.sub(r"[^a-z0-9]", "", token)
    return bool(stripped) and stripped in nospace_text


def _word_match_pct(reference: str, extracted: str) -> float:
    """
    Bidirectional word match — max(OCR→PDF, PDF→OCR) with soft merge matching.
    Taking the max prevents noise OCR tokens (e.g. 'wenn', diagram fragments)
    from deflating the score when the PDF content was correctly extracted.
    """
    ref_words = _word_tokens(reference)
    ext_words = set(_word_tokens(extracted))
    if not ref_words:
        return 100.0

    ext_nospace = re.sub(r"[^a-z0-9]", "", _normalize(extracted))
    ocr_nospace = re.sub(r"[^a-z0-9]", "", _normalize(reference))

    # Forward: for each OCR token, find it in PDF
    fwd = sum(
        1.0 if w in ext_words else (0.9 if _soft_match(w, ext_nospace) else 0.0)
        for w in ref_words
    )
    fwd_pct = fwd / len(ref_words) * 100.0

    # Reverse: for each PDF token, find it in OCR
    rev_words = _word_tokens(extracted)
    if not rev_words:
        return min(100.0, fwd_pct)
    ocr_set = set(ref_words)
    rev = sum(
        1.0 if w in ocr_set else (0.9 if _soft_match(w, ocr_nospace) else 0.0)
        for w in rev_words
    )
    rev_pct = rev / len(rev_words) * 100.0

    return min(100.0, max(fwd_pct, rev_pct))


def _char_match_pct(reference: str, extracted: str) -> float:
    """
    Character-level Jaccard similarity on alphanumeric characters only.
    Strips non-alphanumeric so Unicode math/Greek symbols in the PDF
    (e.g. 𝛼, 𝛽, ∫, ±) don't inflate the union when OCR produces only ASCII.
    """
    ref = re.sub(r"[^a-z0-9]", "", _normalize(reference))
    ext = re.sub(r"[^a-z0-9]", "", _normalize(extracted))
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
    For each page screenshot: detect page type, route to best OCR tool, compare with
    extracted text, compute word_match + char_match + structural_match; persist to page_accuracy.
    Set document validation_status = validation_failed if any page < 98%;
    add audit CRITICAL_MISMATCH for any page < 80%.
    """
    screenshots = (
        db.query(PageScreenshot)
        .filter(PageScreenshot.document_id == document_id)
        .order_by(PageScreenshot.page_number)
        .all()
    )
    if not screenshots:
        return

    exts = db.query(Extraction).filter(
        Extraction.document_id == document_id,
        Extraction.source.in_(["pdf", "textract"]),
    ).all()
    pdf_structure = next((e.structure for e in exts if e.source == "pdf"), {})
    textract_structure = next((e.structure for e in exts if e.source == "textract"), {})

    settings = get_settings()
    doc = db.query(Document).filter(Document.id == document_id).first()
    validation_failed = False
    critical_pages: list[int] = []
    _FLUSH_EVERY = 20

    for i, ps in enumerate(screenshots):
        page_num = ps.page_number
        img_path = upload_dir / ps.file_path
        if not img_path.exists():
            logger.warning("Screenshot not found for page %s: %s", page_num, img_path)
            continue
        # Detect page type (fast path from structure; screenshot fallback if structure absent)
        page_type = classify_page_type(
            pdf_structure, page_num, img_path,
            use_pp_structure=getattr(settings, "use_pp_structure", False),
        )
        # Route to best available OCR tool for this page type
        try:
            ocr_text = get_page_text(img_path, page_type, settings)
        except Exception as e:
            logger.warning("OCR routing failed for page %s: %s", page_num, e)
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
        if (i + 1) % _FLUSH_EVERY == 0:
            db.flush()  # release DB memory periodically; final commit below

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
