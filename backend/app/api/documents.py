import logging
import uuid
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.base import get_db
from app.models.document import Document, DocumentVersion
from app.models.extraction import Extraction
from app.models.audit import AuditLog
from app.models.page_validation import PageScreenshot, PageAccuracy, PageValidationLog
from pydantic import BaseModel
from app.schemas.document import DocumentSummary, DocumentVersion as DocumentVersionSchema


class PageValidationBody(BaseModel):
    reviewer: str | None = None
    status: str | None = None
    comment: str | None = None
from app.services.ingestion import save_upload_and_create_document
from app.services.jobs import request_cancel, enqueue_extraction, enqueue_re_extract, get_queue_depth

router = APIRouter()
logger = logging.getLogger(__name__)


def _doc_to_summary(d: Document) -> DocumentSummary:
    return DocumentSummary(
        documentId=d.id,
        name=d.name,
        uploadStatus=d.upload_status,
        processingStage=d.processing_stage,
        validationStatus=d.validation_status,
        version=d.version,
        hash=d.file_hash_sha256 or "",
        createdAt=d.created_at.isoformat() + "Z" if d.created_at else "",
        author=d.author,
        fileSizeBytes=d.file_size_bytes,
        pageCount=d.page_count,
        errorType=d.error_type,
        errorMessage=d.error_message,
    )


@router.post("/documents/upload", response_model=DocumentSummary)
def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    if not file.filename:
        raise HTTPException(400, "No filename")
    ext = Path(file.filename).suffix.lower()
    if ext != ".pdf":
        raise HTTPException(400, "Only .pdf is allowed")
    doc_id = str(uuid.uuid4())
    settings = get_settings()
    upload_path = settings.get_upload_path()
    try:
        save_upload_and_create_document(db, file, doc_id, upload_path, ext)
    except Exception as e:
        logger.exception("Upload failed: %s", e)
        raise HTTPException(500, f"Upload failed: {e!s}") from e
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(500, "Document not created")
    enqueue_extraction(doc_id)
    logger.info("Upload: enqueued extraction for %s (queue depth=%d)", doc_id, get_queue_depth())
    return _doc_to_summary(doc)


@router.get("/documents", response_model=list[DocumentSummary])
def list_documents(db: Session = Depends(get_db)):
    docs = db.query(Document).order_by(Document.created_at.desc()).all()
    return [_doc_to_summary(d) for d in docs]


@router.get("/documents/{document_id}", response_model=DocumentSummary | None)
def get_document(document_id: str, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        return None
    return _doc_to_summary(doc)


@router.post("/documents/{document_id}/cancel", response_model=DocumentSummary)
def cancel_document_job(document_id: str, db: Session = Depends(get_db)):
    """Request cancellation of the current extraction/comparison job. Document will move to 'cancelled' stage."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")
    if doc.processing_stage not in ("pending", "extracting", "comparing"):
        raise HTTPException(400, f"Job not in progress (current stage: {doc.processing_stage})")
    request_cancel(document_id)
    doc.processing_stage = "cancelled"
    doc.error_type = None
    doc.error_message = None
    db.add(
        AuditLog(
            document_id=document_id,
            document_name=doc.name,
            reviewer="System",
            action="Job cancelled by user",
            validation_result="Cancelled",
            parser_version=get_settings().parser_version,
        )
    )
    db.commit()
    db.refresh(doc)
    return _doc_to_summary(doc)


@router.post("/documents/{document_id}/re-extract", response_model=DocumentSummary)
def re_extract_document(
    document_id: str,
    db: Session = Depends(get_db),
):
    """Re-run PDF extraction and comparison using the existing uploaded file and screenshots."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")
    if doc.processing_stage in ("pending", "extracting", "comparing"):
        raise HTTPException(400, f"Cannot re-extract while job is in progress (stage: {doc.processing_stage})")
    upload_path = get_settings().get_upload_path()
    file_path = upload_path / doc.file_path
    if not file_path.exists():
        raise HTTPException(404, "Uploaded file not found; cannot re-extract")
    if file_path.suffix.lower() != ".pdf":
        raise HTTPException(400, "Re-extract is only supported for PDF documents")
    doc.processing_stage = "extracting"
    doc.error_type = None
    doc.error_message = None
    db.commit()
    db.refresh(doc)
    enqueue_re_extract(document_id)
    logger.info("Re-extract: enqueued for %s (queue depth=%d)", document_id, get_queue_depth())
    return _doc_to_summary(doc)


@router.get("/documents/{document_id}/versions", response_model=list[DocumentVersionSchema])
def get_version_history(document_id: str, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        return []
    versions = db.query(DocumentVersion).filter(DocumentVersion.document_id == document_id).order_by(DocumentVersion.created_at.desc()).all()
    return [
        DocumentVersionSchema(
            documentId=v.document_id,
            version=v.version,
            name=v.name,
            createdAt=v.created_at.isoformat() + "Z" if v.created_at else "",
        )
        for v in versions
    ]


@router.get("/documents/{document_id}/canonical")
def get_canonical(document_id: str, db: Session = Depends(get_db)):
    from pathlib import Path
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        return None
    upload_path = get_settings().get_upload_path()
    path = upload_path / "canonical" / f"{document_id}_{doc.version}.json"
    if not path.exists():
        return None
    import json
    with open(path) as f:
        return json.load(f)


# --- Page screenshots (for PDFs) ---
@router.get("/documents/{document_id}/screenshots")
def list_screenshots(document_id: str, db: Session = Depends(get_db)):
    """List page screenshots: [{ pageNumber, path, checksum }, ...]. Only includes entries where the file exists on disk."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")
    upload_path = get_settings().get_upload_path()
    rows = db.query(PageScreenshot).filter(PageScreenshot.document_id == document_id).order_by(PageScreenshot.page_number).all()
    result = []
    for r in rows:
        full_path = upload_path / r.file_path
        if full_path.exists():
            result.append({"pageNumber": r.page_number, "path": r.file_path, "checksum": r.checksum})
        else:
            logger.warning("Screenshot file missing for document %s page %s: %s", document_id, r.page_number, full_path)
    return result


# CORS: same origins as main.py (FileResponse may not get middleware CORS headers)
CORS_ALLOWED_ORIGINS = {"http://new.packt.localhost:8003", "http://127.0.0.1:8003", "http://localhost:8003", "http://new.packt.localhost:8004", "http://127.0.0.1:8004", "http://localhost:8004"}


@router.get("/documents/{document_id}/screenshots/{page_number}", response_class=FileResponse)
def get_screenshot(
    request: Request,
    document_id: str,
    page_number: int,
    db: Session = Depends(get_db),
):
    """Return PNG file for the given page. CORS headers set so cross-origin img src works."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")
    row = db.query(PageScreenshot).filter(
        PageScreenshot.document_id == document_id,
        PageScreenshot.page_number == page_number,
    ).first()
    if not row:
        raise HTTPException(404, "Screenshot not found")
    upload_path = get_settings().get_upload_path()
    full_path = upload_path / row.file_path
    if not full_path.exists():
        raise HTTPException(404, "Screenshot file not found")
    origin = request.headers.get("origin")
    headers = {}
    if origin and origin in CORS_ALLOWED_ORIGINS:
        headers["Access-Control-Allow-Origin"] = origin
    else:
        # Fallback so cross-origin img src works even if Origin not sent or from another port
        headers["Access-Control-Allow-Origin"] = "*"
    return FileResponse(full_path, media_type="image/png", headers=headers)


# --- Page-type classification helpers (shared with page_accuracy_service) ---
from app.services.page_classifier import (
    page_blocks as _page_blocks,
    page_is_formula_heavy as _page_is_formula_heavy,
    page_has_images as _page_has_images,
    page_is_sparse as _page_is_sparse,
)


# --- Page accuracy ---
@router.get("/documents/{document_id}/page-accuracy")
def get_page_accuracy(document_id: str, db: Session = Depends(get_db)):
    """List page accuracy: [{ pageNumber, accuracyPct, wordMatchPct, charMatchPct, structuralMatchPct, status }, ...]."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")
    rows = db.query(PageAccuracy).filter(PageAccuracy.document_id == document_id).order_by(PageAccuracy.page_number).all()
    # Fetch PDF extraction structure once for page-type classification
    pdf_extraction = db.query(Extraction).filter(
        Extraction.document_id == document_id,
        Extraction.source == "pdf",
    ).first()
    pdf_structure = (pdf_extraction.structure or {}) if pdf_extraction else {}

    result = []
    for r in rows:
        sparse  = _page_is_sparse(pdf_structure, r.page_number)
        formula = _page_is_formula_heavy(pdf_structure, r.page_number)
        has_img = _page_has_images(pdf_structure, r.page_number)

        if sparse:
            status = "SPARSE"                                          # metric unreliable on near-blank pages
        elif formula:
            status = "FORMULA"  # Tesseract can't score Unicode math — low accuracy is expected
        elif has_img:
            # Image-aware tiers: high accuracy pages still show OK/WARNING
            if r.accuracy_pct >= 98.0:
                status = "OK"
            elif r.accuracy_pct >= 95.0:
                status = "WARNING"
            elif r.accuracy_pct >= 75.0:
                status = "IMAGE"   # Below threshold: image content Tesseract can't read
            else:
                status = "ERROR"   # Genuinely bad accuracy despite image content
        elif r.accuracy_pct >= 98.0:
            status = "OK"
        elif r.accuracy_pct >= 95.0:
            status = "WARNING"
        else:
            status = "ERROR"
        result.append({
            "pageNumber": r.page_number,
            "accuracyPct": round(r.accuracy_pct, 2),
            "wordMatchPct": round(r.word_match_pct, 2) if r.word_match_pct is not None else None,
            "charMatchPct": round(r.char_match_pct, 2) if r.char_match_pct is not None else None,
            "structuralMatchPct": round(r.structural_match_pct, 2) if r.structural_match_pct is not None else None,
            "status": status,
        })
    return result


# --- Page validation log (Chapter Explorer) ---
@router.get("/documents/{document_id}/pages/{page_number}/comparison-summary")
def get_page_comparison_summary(document_id: str, page_number: int, db: Session = Depends(get_db)):
    """Return per-page comparison summary: word counts, block counts, table counts, accuracy, validation status."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")
    pdf_ext = db.query(Extraction).filter(Extraction.document_id == document_id, Extraction.source == "pdf").first()
    ocr_ext = db.query(Extraction).filter(Extraction.document_id == document_id, Extraction.source == "ocr").first()
    if not pdf_ext and not ocr_ext:
        raise HTTPException(404, "No PDF or OCR extraction found")
    heading = f"Page {page_number}"
    pdf_ch = None
    ocr_ch = None
    if pdf_ext and pdf_ext.structure:
        for ch in pdf_ext.structure.get("chapters") or []:
            if ch.get("heading") == heading:
                pdf_ch = ch
                break
    if ocr_ext and ocr_ext.structure:
        for ch in ocr_ext.structure.get("chapters") or []:
            if ch.get("heading") == heading:
                ocr_ch = ch
                break
    blocks_native = (pdf_ch.get("content_blocks") or []) if pdf_ch else []
    blocks_ocr = (ocr_ch.get("content_blocks") or []) if ocr_ch else []
    tables_native = sum(1 for b in blocks_native if b.get("type") == "table")
    tables_ocr = sum(1 for b in blocks_ocr if b.get("type") == "table")
    word_count_native = sum((b.get("wordCount") or 0) for b in blocks_native) or sum(len((b.get("content") or "").split()) for b in blocks_native)
    word_count_ocr = sum((b.get("wordCount") or 0) for b in blocks_ocr) or sum(len((b.get("content") or "").split()) for b in blocks_ocr)
    missing_block_count = abs(len(blocks_native) - len(blocks_ocr))
    acc_row = db.query(PageAccuracy).filter(PageAccuracy.document_id == document_id, PageAccuracy.page_number == page_number).first()
    accuracy_score = round(acc_row.accuracy_pct, 2) if acc_row else None
    val_row = (
        db.query(PageValidationLog)
        .filter(PageValidationLog.document_id == document_id, PageValidationLog.page_number == page_number)
        .order_by(PageValidationLog.created_at.desc())
        .first()
    )
    validation_status = val_row.status if val_row else None
    confidence_avg_ocr = None
    if ocr_ext and ocr_ext.metadata_ and isinstance(ocr_ext.metadata_, dict):
        page_conf = (ocr_ext.metadata_.get("page_confidence") or {}).get(page_number)
        confidence_avg_ocr = page_conf if page_conf is not None else ocr_ext.metadata_.get("average_confidence")
    return {
        "pageNumber": page_number,
        "wordCountNative": word_count_native,
        "wordCountTextract": word_count_ocr,
        "blockCountNative": len(blocks_native),
        "blockCountTextract": len(blocks_ocr),
        "tableCountNative": tables_native,
        "tableCountTextract": tables_ocr,
        "missingBlockCount": missing_block_count,
        "accuracyScore": accuracy_score,
        "validationStatus": validation_status,
        "confidenceAvgTextract": confidence_avg_ocr,
    }


@router.get("/documents/{document_id}/pages/{page_number}/markdown")
def get_page_markdown(
    document_id: str,
    page_number: int,
    source: str | None = None,
    db: Session = Depends(get_db),
):
    """Return the page's content as a single markdown string (paragraphs + markdown tables) for easy preview.
    source: 'pdf' | 'ocr' to choose extraction; if omitted, prefers OCR when available."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")
    ocr_ext = db.query(Extraction).filter(
        Extraction.document_id == document_id,
        Extraction.source == "ocr",
    ).first()
    textract_ext = db.query(Extraction).filter(
        Extraction.document_id == document_id,
        Extraction.source == "textract",
    ).first()
    pdf_ext = db.query(Extraction).filter(
        Extraction.document_id == document_id,
        Extraction.source == "pdf",
    ).first()
    structure = None
    if source == "pdf" and pdf_ext and pdf_ext.structure:
        structure = pdf_ext.structure
    elif source == "ocr" and ocr_ext and ocr_ext.structure:
        structure = ocr_ext.structure
    elif source == "textract" and textract_ext and textract_ext.structure:
        structure = textract_ext.structure
    elif source is None:
        if ocr_ext and ocr_ext.structure:
            structure = ocr_ext.structure
        elif textract_ext and textract_ext.structure:
            structure = textract_ext.structure
        elif pdf_ext and pdf_ext.structure:
            structure = pdf_ext.structure
    if not structure:
        raise HTTPException(404, "No extraction structure found for this document")
    heading = f"Page {page_number}"
    chapters = structure.get("chapters") or []
    chapter = None
    for ch in chapters:
        if ch.get("heading") == heading:
            chapter = ch
            break
    if not chapter:
        raise HTTPException(404, f"Page {page_number} not found in extraction")
    blocks = chapter.get("content_blocks") or []
    parts: list[str] = []
    for b in blocks:
        content = (b.get("content") or "").strip()
        if not content:
            continue
        if b.get("type") == "table":
            parts.append(content)
        else:
            parts.append(content)
    markdown = "\n\n".join(parts) if parts else ""
    return {"markdown": markdown, "pageNumber": page_number}


@router.get("/documents/{document_id}/pages/{page_number}/validation")
def get_page_validation(document_id: str, page_number: int, db: Session = Depends(get_db)):
    """Return latest validation log entry for this page."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")
    row = (
        db.query(PageValidationLog)
        .filter(
            PageValidationLog.document_id == document_id,
            PageValidationLog.page_number == page_number,
        )
        .order_by(PageValidationLog.created_at.desc())
        .first()
    )
    if not row:
        return None
    return {
        "reviewer": row.reviewer,
        "status": row.status,
        "comment": row.comment,
        "timestamp": row.created_at.isoformat() + "Z" if row.created_at else None,
    }


@router.post("/documents/{document_id}/pages/{page_number}/validation", status_code=201)
def post_page_validation(
    document_id: str,
    page_number: int,
    db: Session = Depends(get_db),
    body: PageValidationBody | None = None,
):
    """Append a page validation log entry. Body: { reviewer?, status, comment? }."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")
    b = body or PageValidationBody()
    reviewer = b.reviewer or "User"
    status = b.status or "needs_review"
    comment = b.comment
    db.add(
        PageValidationLog(
            document_id=document_id,
            page_number=page_number,
            reviewer=reviewer,
            status=status,
            comment=comment,
        )
    )
    db.commit()
    return {"ok": True}
