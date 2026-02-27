import logging
from app.models.base import get_engine, get_session_factory
from app.models.document import Document
from app.models.audit import AuditLog
from app.models.extraction import Extraction
from app.models.comparison import Comparison
from app.models.validation import ValidationItem
from app.models.page_validation import PageAccuracy
from app.services.docx_extractor import extract_docx
from app.services.pdf_extractor import extract_pdf
from app.services.comparison import run_comparison
from app.services.screenshot_service import generate_screenshots
from app.services.page_accuracy_service import compute_page_accuracy
from app.config import get_settings

logger = logging.getLogger(__name__)

# In-memory set of document IDs for which cancel was requested (job checks this between steps)
_cancel_requested: set[str] = set()


def request_cancel(document_id: str) -> None:
    _cancel_requested.add(document_id)


def clear_cancel(document_id: str) -> None:
    _cancel_requested.discard(document_id)


def is_cancel_requested(document_id: str) -> bool:
    return document_id in _cancel_requested


def _check_cancel(db, document_id: str, doc_name: str) -> bool:
    """If cancel requested, set document to cancelled, commit, clear flag, return True. Else return False."""
    if not is_cancel_requested(document_id):
        return False
    clear_cancel(document_id)
    doc = db.query(Document).filter(Document.id == document_id).first()
    if doc:
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
    logger.info("Background job: cancelled for document %s", document_id)
    return True


def run_extraction_and_comparison(document_id: str) -> None:
    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            logger.warning("Background job: document %s not found, skipping", document_id)
            return

        if _check_cancel(db, document_id, doc.name):
            return

        logger.info("Background job: starting extraction for document %s (%s)", document_id, doc.name)
        doc.processing_stage = "extracting"
        doc.error_type = None
        doc.error_message = None
        db.commit()

        upload_path = get_settings().get_upload_path()
        file_path = upload_path / doc.file_path

        if not file_path.exists():
            logger.error("Background job: file not found %s", file_path)
            doc.processing_stage = "error"
            doc.error_type = "extraction_failure"
            doc.error_message = "File not found after upload"
            doc.validation_status = "pending"
            db.add(AuditLog(document_id=document_id, document_name=doc.name, reviewer="System", action="Extraction failed: file not found", validation_result="Error", parser_version=get_settings().parser_version, metadata_={"error_type": "extraction_failure"}))
            db.commit()
            return

        if file_path.suffix.lower() == ".docx":
            extract_docx(db, document_id, str(file_path))
        elif file_path.suffix.lower() == ".pdf":
            try:
                logger.info("Generating screenshots for document %s (PDF: %s)", document_id, file_path)
                screens = generate_screenshots(db, document_id, str(file_path), upload_path)
                db.add(
                    AuditLog(
                        document_id=document_id,
                        document_name=doc.name,
                        reviewer="System",
                        action="Screenshot generation completed",
                        validation_result="OK",
                        parser_version=get_settings().parser_version,
                        metadata_={"page_count": len(screens)},
                    )
                )
                db.commit()
            except Exception as screenshot_err:
                logger.exception(
                    "Screenshot generation failed for %s: %s (path=%s, upload_path=%s)",
                    document_id, screenshot_err, file_path, upload_path
                )
                doc.processing_stage = "error"
                doc.validation_status = "screenshot_failed"
                doc.error_type = "screenshot_failed"
                doc.error_message = str(screenshot_err)[:2048]
                db.add(
                    AuditLog(
                        document_id=document_id,
                        document_name=doc.name,
                        reviewer="System",
                        action="Screenshot generation failed",
                        validation_result="Error",
                        parser_version=get_settings().parser_version,
                        metadata_={"error": str(screenshot_err)[:500]},
                    )
                )
                db.commit()
                return
            if _check_cancel(db, document_id, doc.name):
                return
            extract_pdf(db, document_id, str(file_path), upload_path=upload_path)
        else:
            logger.warning("Background job: unsupported extension for %s", file_path)
            doc.processing_stage = "error"
            doc.error_type = "extraction_failure"
            doc.error_message = "Unsupported file extension"
            db.add(AuditLog(document_id=document_id, document_name=doc.name, reviewer="System", action="Unsupported extension", validation_result="Error", parser_version=get_settings().parser_version, metadata_={"error_type": "extraction_failure"}))
            db.commit()
            return

        db.refresh(doc)
        doc.processing_stage = "comparing"
        db.commit()

        run_comparison(db, document_id)

        if _check_cancel(db, document_id, doc.name):
            return

        if file_path.suffix.lower() == ".pdf":
            try:
                compute_page_accuracy(db, document_id, upload_path)
            except Exception as acc_err:
                logger.exception("Page accuracy computation failed for %s: %s", document_id, acc_err)

        db.refresh(doc)
        doc.processing_stage = "done"
        db.commit()
        logger.info("Background job: completed for document %s", document_id)
    except Exception as e:
        logger.exception("Background job failed for %s: %s", document_id, e)
        try:
            doc = db.query(Document).filter(Document.id == document_id).first()
            if doc:
                doc.processing_stage = "error"
                err_msg = str(e)
                if "textract" in err_msg.lower() or "boto" in err_msg.lower() or "ClientError" in err_msg:
                    doc.error_type = "textract_failure"
                elif "timeout" in err_msg.lower() or "timed out" in err_msg.lower():
                    doc.error_type = "api_timeout"
                else:
                    doc.error_type = "extraction_failure"
                doc.error_message = err_msg[:2048]
                db.add(AuditLog(document_id=document_id, document_name=doc.name, reviewer="System", action=f"Error: {err_msg[:500]}", validation_result="Error", parser_version=get_settings().parser_version, metadata_={"error_type": doc.error_type}))
                db.commit()
        except Exception as commit_err:
            logger.exception("Failed to persist error state: %s", commit_err)
    finally:
        clear_cancel(document_id)
        db.close()


def run_re_extract(document_id: str) -> None:
    """Re-run PDF extraction and comparison using existing file and screenshots. Use after fixing AWS credentials or to refresh Textract/Native output."""
    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            logger.warning("Re-extract: document %s not found", document_id)
            return
        upload_path = get_settings().get_upload_path()
        file_path = upload_path / doc.file_path
        if not file_path.exists():
            logger.error("Re-extract: file not found %s", file_path)
            doc.processing_stage = "error"
            doc.error_type = "extraction_failure"
            doc.error_message = "File not found"
            db.commit()
            return
        if file_path.suffix.lower() != ".pdf":
            logger.warning("Re-extract: only PDF is supported, got %s", file_path.suffix)
            return
        # Remove existing pdf/textract extractions and comparison data so we get a clean result
        db.query(Extraction).filter(
            Extraction.document_id == document_id,
            Extraction.source.in_(["pdf", "textract"]),
        ).delete(synchronize_session=False)
        # Null audit_log.comparison_id so we can delete comparisons
        comp_ids = [c.id for c in db.query(Comparison).filter(Comparison.document_id == document_id).all()]
        if comp_ids:
            db.query(AuditLog).filter(AuditLog.comparison_id.in_(comp_ids)).update(
                {AuditLog.comparison_id: None}, synchronize_session=False
            )
        db.query(Comparison).filter(Comparison.document_id == document_id).delete(synchronize_session=False)
        db.query(ValidationItem).filter(ValidationItem.document_id == document_id).delete(synchronize_session=False)
        db.query(PageAccuracy).filter(PageAccuracy.document_id == document_id).delete(synchronize_session=False)
        doc.processing_stage = "extracting"
        doc.error_type = None
        doc.error_message = None
        db.add(
            AuditLog(
                document_id=document_id,
                document_name=doc.name,
                reviewer="System",
                action="Re-extract started (using existing file and screenshots)",
                validation_result="OK",
                parser_version=get_settings().parser_version,
            )
        )
        db.commit()
        logger.info("Re-extract: running extraction for document %s (%s)", document_id, doc.name)
        extract_pdf(db, document_id, str(file_path), upload_path=upload_path)
        db.refresh(doc)
        doc.processing_stage = "comparing"
        db.commit()
        run_comparison(db, document_id)
        try:
            compute_page_accuracy(db, document_id, upload_path)
        except Exception as acc_err:
            logger.exception("Re-extract: page accuracy failed for %s: %s", document_id, acc_err)
        db.refresh(doc)
        doc.processing_stage = "done"
        db.commit()
        logger.info("Re-extract: completed for document %s", document_id)
    except Exception as e:
        logger.exception("Re-extract failed for %s: %s", document_id, e)
        try:
            doc = db.query(Document).filter(Document.id == document_id).first()
            if doc:
                doc.processing_stage = "error"
                doc.error_type = "extraction_failure"
                doc.error_message = str(e)[:2048]
                db.commit()
        except Exception as commit_err:
            logger.exception("Failed to persist re-extract error: %s", commit_err)
    finally:
        db.close()
