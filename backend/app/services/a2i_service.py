"""
Amazon Augmented AI (A2I) service.

Evaluates page accuracy + Textract confidence after extraction; automatically
creates A2I human review tasks for pages that fail defined thresholds.

When a2i_flow_definition_arn is configured in .env, tasks are submitted to
AWS A2I via sagemaker-a2i-runtime.create_human_loop().

When the ARN is NOT configured (default / local dev), tasks are created with
status='pending' for manual review via the /api/a2i/ endpoints.
"""
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.a2i import A2ITask
from app.models.audit import AuditLog
from app.models.document import Document
from app.models.extraction import Extraction
from app.models.page_validation import PageAccuracy, PageValidationLog
from app.services.diff_service import compute_diff_items

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Trigger evaluation
# ---------------------------------------------------------------------------

def should_trigger_review(
    accuracy_pct: float,
    textract_confidence: float | None,
    has_table_mismatch: bool = False,
    has_code_block: bool = False,
) -> tuple[bool, str]:
    """Return (should_trigger, reason_string) based on configured thresholds."""
    settings = get_settings()
    reasons: list[str] = []

    if accuracy_pct < settings.a2i_accuracy_threshold:
        reasons.append(f"accuracy_pct={accuracy_pct:.1f}")

    if textract_confidence is not None and textract_confidence < settings.a2i_confidence_threshold:
        reasons.append(f"textract_conf={textract_confidence:.1f}")

    if has_table_mismatch:
        reasons.append("table_structure_mismatch")

    if has_code_block:
        reasons.append("code_block_detected")

    return bool(reasons), ", ".join(reasons)


def _has_table_mismatch(pdf_structure: dict, textract_structure: dict, page_number: int) -> bool:
    """Return True if table block counts differ between PDF and Textract for this page."""
    def table_count(structure: dict, page_num: int) -> int:
        for ch in (structure.get("chapters") or []):
            if ch.get("heading") == f"Page {page_num}":
                return sum(1 for b in (ch.get("content_blocks") or []) if b.get("type") == "table")
        return 0

    pdf_tables = table_count(pdf_structure, page_number)
    textract_tables = table_count(textract_structure, page_number)
    return pdf_tables != textract_tables


def _has_code_block(textract_structure: dict, page_number: int) -> bool:
    """Heuristic: flag if any content block looks like a code block (starts with 4+ spaces or contains >>>/$ prompt)."""
    for ch in (textract_structure.get("chapters") or []):
        if ch.get("heading") == f"Page {page_number}":
            for b in (ch.get("content_blocks") or []):
                content = b.get("content") or ""
                if content.startswith("    ") or any(p in content for p in [">>>", "$ ", "# ", "</"]):
                    return True
    return False


def _get_page_text(structure: dict, page_number: int) -> str:
    """Concatenate all content block text for 'Page {n}' chapter."""
    for ch in (structure.get("chapters") or []):
        if ch.get("heading") == f"Page {page_number}":
            return " ".join((b.get("content") or "") for b in (ch.get("content_blocks") or []))
    return ""


def _get_textract_confidence(textract_ext: Extraction | None, page_number: int) -> float | None:
    """Extract per-page Textract confidence from extraction metadata."""
    if not textract_ext or not textract_ext.metadata_:
        return None
    meta = textract_ext.metadata_ if isinstance(textract_ext.metadata_, dict) else {}
    page_conf = (meta.get("page_confidence") or {}).get(page_number)
    if page_conf is not None:
        return float(page_conf)
    avg = meta.get("average_confidence")
    return float(avg) if avg is not None else None


# ---------------------------------------------------------------------------
# AWS A2I client
# ---------------------------------------------------------------------------

def _get_a2i_client():
    """Create a boto3 sagemaker-a2i-runtime client."""
    import boto3
    settings = get_settings()
    kwargs: dict = {"region_name": settings.aws_region}
    if settings.aws_access_key_id:
        kwargs["aws_access_key_id"] = settings.aws_access_key_id
        kwargs["aws_secret_access_key"] = settings.aws_secret_access_key
    if settings.aws_session_token:
        kwargs["aws_session_token"] = settings.aws_session_token
    return boto3.client("sagemaker-a2i-runtime", **kwargs)


def _get_s3_client():
    import boto3
    settings = get_settings()
    kwargs: dict = {"region_name": settings.aws_region}
    if settings.aws_access_key_id:
        kwargs["aws_access_key_id"] = settings.aws_access_key_id
        kwargs["aws_secret_access_key"] = settings.aws_secret_access_key
    if settings.aws_session_token:
        kwargs["aws_session_token"] = settings.aws_session_token
    return boto3.client("s3", **kwargs)


# ---------------------------------------------------------------------------
# Task creation
# ---------------------------------------------------------------------------

def create_a2i_task(
    db: Session,
    document_id: str,
    page_number: int,
    original_text: str,
    confidence_score: float | None,
    trigger_reason: str,
    screenshot_path: Path | None = None,
    native_text: str | None = None,
) -> A2ITask:
    """
    Insert an A2ITask row and (if ARN is configured) submit to AWS A2I.
    Computes word-level diff items between native_text and original_text (Textract).
    Returns the saved task.
    """
    settings = get_settings()
    doc = db.query(Document).filter(Document.id == document_id).first()
    doc_name = doc.name if doc else document_id

    # Compute word-level diffs if both texts are available
    diff_items = None
    if native_text and original_text:
        try:
            diff_items = compute_diff_items(native_text, original_text)
        except Exception as e:
            logger.warning("Failed to compute diff items for doc %s page %s: %s", document_id, page_number, e)

    task = A2ITask(
        id=str(uuid.uuid4()),
        document_id=document_id,
        page_number=page_number,
        status="pending",
        trigger_reason=trigger_reason,
        original_textract_text=original_text[:10000] if original_text else None,
        native_text_snapshot=native_text[:10000] if native_text else None,
        diff_items=diff_items,
        confidence_score=confidence_score,
    )
    db.add(task)
    db.flush()  # get task.id before potential AWS call

    if settings.a2i_flow_definition_arn:
        loop_name = f"ingestiq-{document_id[:8]}-p{page_number}-{uuid.uuid4().hex[:6]}"
        try:
            a2i = _get_a2i_client()
            human_loop_input = {
                "taskObject": str(screenshot_path) if screenshot_path else "",
                "extractedText": original_text or "",
                "documentId": document_id,
                "pageNumber": page_number,
                "triggerReason": trigger_reason,
            }
            a2i.start_human_loop(
                HumanLoopName=loop_name,
                FlowDefinitionArn=settings.a2i_flow_definition_arn,
                HumanLoopInput={"InputContent": json.dumps(human_loop_input)},
            )
            task.human_loop_name = loop_name
            task.status = "under_review"
            logger.info("A2I: submitted human loop %s for doc %s page %s", loop_name, document_id, page_number)
        except Exception as e:
            logger.exception("A2I: create_human_loop failed for doc %s page %s: %s", document_id, page_number, e)
            task.status = "pending"

    db.add(
        AuditLog(
            document_id=document_id,
            document_name=doc_name,
            reviewer="System",
            action=f"A2I Review Triggered — Page {page_number} ({trigger_reason})",
            validation_result="Pending Review",
            parser_version=settings.parser_version,
            metadata_={"page_number": page_number, "trigger_reason": trigger_reason, "a2i_task_id": task.id},
        )
    )
    db.commit()
    return task


# ---------------------------------------------------------------------------
# Result polling and correction application
# ---------------------------------------------------------------------------

def apply_correction(
    db: Session,
    task: A2ITask,
    corrected_text: str,
    reviewer_id: str,
    comment: str | None = None,
) -> None:
    """
    Apply a human correction from A2I:
    1. Update A2ITask fields.
    2. Patch the Textract extraction for this page with corrected text.
    3. Append a PageValidationLog entry.
    4. Log to AuditLog.
    """
    settings = get_settings()
    doc = db.query(Document).filter(Document.id == task.document_id).first()
    doc_name = doc.name if doc else task.document_id

    # Update task
    task.human_corrected_text = corrected_text
    task.reviewer_id = reviewer_id
    task.review_timestamp = datetime.utcnow()
    task.status = "completed"
    db.add(task)

    # Patch Textract extraction structure for this page
    textract_ext = db.query(Extraction).filter(
        Extraction.document_id == task.document_id,
        Extraction.source == "textract",
    ).first()
    if textract_ext and textract_ext.structure:
        structure = dict(textract_ext.structure)
        chapters = list(structure.get("chapters") or [])
        heading = f"Page {task.page_number}"
        for i, ch in enumerate(chapters):
            if ch.get("heading") == heading:
                # Replace content blocks with single corrected block
                chapters[i] = dict(ch)
                chapters[i]["content_blocks"] = [
                    {
                        "id": f"{task.document_id}-p{task.page_number}-a2i-b0",
                        "type": "text",
                        "content": corrected_text,
                        "orderIndex": 0,
                        "wordCount": len(corrected_text.split()),
                        "bbox": None,
                    }
                ]
                chapters[i]["wordCount"] = len(corrected_text.split())
                break
        structure["chapters"] = chapters
        textract_ext.structure = structure
        db.add(textract_ext)

    # Append PageValidationLog
    db.add(
        PageValidationLog(
            document_id=task.document_id,
            page_number=task.page_number,
            reviewer=reviewer_id,
            status="verified",
            comment=comment or f"A2I correction applied by {reviewer_id}",
        )
    )

    # Audit entry
    db.add(
        AuditLog(
            document_id=task.document_id,
            document_name=doc_name,
            reviewer=reviewer_id,
            action=f"A2I Correction Applied — Page {task.page_number}",
            validation_result="Human Verified",
            parser_version=settings.parser_version,
            metadata_={
                "page_number": task.page_number,
                "a2i_task_id": task.id,
                "reviewer_id": reviewer_id,
            },
        )
    )
    db.commit()
    logger.info("A2I correction applied: doc %s page %s by %s", task.document_id, task.page_number, reviewer_id)


def poll_and_apply_results(db: Session, document_id: str) -> int:
    """
    Poll AWS A2I for completed human loops on under_review tasks.
    For each completed loop, fetch S3 result JSON and apply correction.
    Returns the count of tasks completed in this poll cycle.
    """
    tasks = (
        db.query(A2ITask)
        .filter(A2ITask.document_id == document_id, A2ITask.status == "under_review")
        .all()
    )
    if not tasks:
        return 0

    settings = get_settings()
    if not settings.a2i_flow_definition_arn:
        return 0

    completed = 0
    try:
        a2i = _get_a2i_client()
        s3 = _get_s3_client()
    except Exception as e:
        logger.exception("A2I poll: failed to create clients: %s", e)
        return 0

    for task in tasks:
        if not task.human_loop_name:
            continue
        try:
            resp = a2i.describe_human_loop(HumanLoopName=task.human_loop_name)
            loop_status = resp.get("HumanLoopStatus", "")
            if loop_status != "Completed":
                continue

            output_uri = (resp.get("HumanLoopOutput") or {}).get("OutputS3Uri", "")
            task.s3_output_uri = output_uri

            corrected_text = ""
            reviewer_id = "a2i-worker"
            if output_uri.startswith("s3://"):
                parts = output_uri[5:].split("/", 1)
                bucket, key = parts[0], parts[1] if len(parts) > 1 else ""
                try:
                    s3_obj = s3.get_object(Bucket=bucket, Key=key)
                    result_json = json.loads(s3_obj["Body"].read())
                    # A2I output schema: humanAnswers[0].answerContent
                    answers = result_json.get("humanAnswers") or []
                    if answers:
                        content = answers[0].get("answerContent") or {}
                        corrected_text = content.get("correctedText", "")
                        reviewer_id = answers[0].get("workerId", "a2i-worker")
                except Exception as s3_err:
                    logger.warning("A2I poll: failed to fetch S3 result for loop %s: %s", task.human_loop_name, s3_err)
                    corrected_text = ""

            apply_correction(db, task, corrected_text or task.original_textract_text or "", reviewer_id)
            completed += 1
        except Exception as e:
            logger.exception("A2I poll: error processing loop %s: %s", task.human_loop_name, e)

    return completed


# ---------------------------------------------------------------------------
# Task assignment
# ---------------------------------------------------------------------------

def assign_task(db: Session, task: A2ITask, reviewer_id: str) -> A2ITask:
    """Assign a pending task to a reviewer; update status to 'assigned'."""
    task.assigned_to = reviewer_id
    task.assigned_at = datetime.utcnow()
    if task.status == "pending":
        task.status = "assigned"
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


# ---------------------------------------------------------------------------
# Pipeline entry point
# ---------------------------------------------------------------------------

def evaluate_and_trigger_a2i(db: Session, document_id: str, upload_dir: Path | None = None) -> int:
    """
    Called from jobs.py after compute_page_accuracy().
    Evaluates every page and creates A2I tasks for pages that fail thresholds.
    Returns the number of tasks created.
    """
    accuracy_rows = (
        db.query(PageAccuracy)
        .filter(PageAccuracy.document_id == document_id)
        .all()
    )
    if not accuracy_rows:
        return 0

    textract_ext = db.query(Extraction).filter(
        Extraction.document_id == document_id,
        Extraction.source == "textract",
    ).first()
    pdf_ext = db.query(Extraction).filter(
        Extraction.document_id == document_id,
        Extraction.source == "pdf",
    ).first()
    textract_structure = textract_ext.structure if textract_ext else {}
    pdf_structure = pdf_ext.structure if pdf_ext else {}

    # Get existing task page numbers to avoid duplicates
    existing_pages: set[int] = {
        t.page_number
        for t in db.query(A2ITask.page_number).filter(A2ITask.document_id == document_id).all()
    }

    settings = get_settings()
    triggered = 0
    for row in accuracy_rows:
        if row.page_number in existing_pages:
            continue

        confidence = _get_textract_confidence(textract_ext, row.page_number)
        table_mismatch = _has_table_mismatch(pdf_structure, textract_structure, row.page_number)
        code_block = _has_code_block(textract_structure, row.page_number)

        should_trigger, reason = should_trigger_review(
            accuracy_pct=row.accuracy_pct,
            textract_confidence=confidence,
            has_table_mismatch=table_mismatch,
            has_code_block=code_block,
        )
        if not should_trigger:
            continue

        original_text = _get_page_text(textract_structure, row.page_number)
        native_text = _get_page_text(pdf_structure, row.page_number)
        screenshot_path: Path | None = None
        if upload_dir:
            sp = upload_dir / document_id / "screenshots" / f"page_{row.page_number}.png"
            if sp.exists():
                screenshot_path = sp

        create_a2i_task(
            db=db,
            document_id=document_id,
            page_number=row.page_number,
            original_text=original_text,
            native_text=native_text,
            confidence_score=confidence,
            trigger_reason=reason,
            screenshot_path=screenshot_path,
        )
        triggered += 1
        logger.info(
            "A2I: triggered review for doc %s page %s (reason: %s)",
            document_id, row.page_number, reason,
        )

    return triggered
