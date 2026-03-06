"""
A2I (Amazon Augmented AI) API endpoints.
"""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.models.base import get_db
from app.models.a2i import A2ITask
from app.models.document import Document
from app.models.page_validation import PageAccuracy
from app.models.extraction import Extraction
from app.schemas.a2i import (
    A2ITaskSummary,
    A2ITaskDetail,
    DiffItemSchema,
    A2ICompleteBody,
    AssignTaskBody,
    ReviewerStatsResponse,
)
from app.services.a2i_service import (
    create_a2i_task,
    apply_correction,
    poll_and_apply_results,
    assign_task,
    should_trigger_review,
    _get_textract_confidence,
    _has_table_mismatch,
    _has_code_block,
    _get_page_text,
)
from app.config import get_settings

router = APIRouter()
logger = logging.getLogger(__name__)


def _task_to_summary(task: A2ITask) -> A2ITaskSummary:
    return A2ITaskSummary(
        id=task.id,
        documentId=task.document_id,
        pageNumber=task.page_number,
        humanLoopName=task.human_loop_name,
        status=task.status,
        triggerReason=task.trigger_reason,
        reviewerId=task.reviewer_id,
        reviewTimestamp=task.review_timestamp.isoformat() + "Z" if task.review_timestamp else None,
        correctionApplied=bool(task.human_corrected_text),
        confidenceScore=task.confidence_score,
        s3OutputUri=task.s3_output_uri,
        assignedTo=task.assigned_to,
        assignedAt=task.assigned_at.isoformat() + "Z" if task.assigned_at else None,
        createdAt=task.created_at.isoformat() + "Z" if task.created_at else "",
    )


def _task_to_detail(task: A2ITask) -> A2ITaskDetail:
    raw_diff = task.diff_items or []
    diff_items = [
        DiffItemSchema(
            id=d.get("id", ""),
            diffType=d.get("diff_type", ""),
            nativeValue=d.get("native_value", ""),
            textractValue=d.get("textract_value", ""),
            lineIndex=d.get("line_index", 0),
        )
        for d in raw_diff
    ]
    return A2ITaskDetail(
        **_task_to_summary(task).model_dump(),
        diffItems=diff_items,
        nativeTextSnapshot=task.native_text_snapshot,
        originalTextractText=task.original_textract_text,
    )


# ---------------------------------------------------------------------------
# Per-document endpoints
# ---------------------------------------------------------------------------

@router.get("/a2i/documents/{document_id}/tasks", response_model=list[A2ITaskSummary])
def list_a2i_tasks(document_id: str, db: Session = Depends(get_db)):
    """List all A2I review tasks for a document, ordered by page number."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")
    tasks = (
        db.query(A2ITask)
        .filter(A2ITask.document_id == document_id)
        .order_by(A2ITask.page_number)
        .all()
    )
    return [_task_to_summary(t) for t in tasks]


@router.get("/a2i/documents/{document_id}/tasks/{page_number}", response_model=A2ITaskSummary)
def get_a2i_task(document_id: str, page_number: int, db: Session = Depends(get_db)):
    """Get the A2I task for a specific page of a document."""
    task = (
        db.query(A2ITask)
        .filter(A2ITask.document_id == document_id, A2ITask.page_number == page_number)
        .first()
    )
    if not task:
        raise HTTPException(404, "No A2I task found for this page")
    return _task_to_summary(task)


@router.post("/a2i/documents/{document_id}/tasks/{page_number}/trigger", response_model=A2ITaskSummary)
def trigger_a2i_review(document_id: str, page_number: int, db: Session = Depends(get_db)):
    """Manually trigger an A2I human review task for a specific page."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")

    existing = (
        db.query(A2ITask)
        .filter(A2ITask.document_id == document_id, A2ITask.page_number == page_number)
        .first()
    )
    if existing:
        raise HTTPException(409, f"A2I task already exists for page {page_number} (status={existing.status})")

    textract_ext = db.query(Extraction).filter(
        Extraction.document_id == document_id, Extraction.source == "textract"
    ).first()
    pdf_ext = db.query(Extraction).filter(
        Extraction.document_id == document_id, Extraction.source == "pdf"
    ).first()
    textract_structure = textract_ext.structure if textract_ext else {}
    pdf_structure = pdf_ext.structure if pdf_ext else {}

    accuracy_row = db.query(PageAccuracy).filter(
        PageAccuracy.document_id == document_id,
        PageAccuracy.page_number == page_number,
    ).first()
    accuracy_pct = accuracy_row.accuracy_pct if accuracy_row else 100.0
    confidence = _get_textract_confidence(textract_ext, page_number)
    table_mismatch = _has_table_mismatch(pdf_structure, textract_structure, page_number)
    code_block = _has_code_block(textract_structure, page_number)

    _, reason = should_trigger_review(accuracy_pct, confidence, table_mismatch, code_block)
    if not reason:
        reason = f"manual_trigger (accuracy={accuracy_pct:.1f})"

    original_text = _get_page_text(textract_structure, page_number)
    native_text = _get_page_text(pdf_structure, page_number)
    settings = get_settings()
    upload_path = settings.get_upload_path()
    screenshot_path = upload_path / document_id / "screenshots" / f"page_{page_number}.png"

    task = create_a2i_task(
        db=db,
        document_id=document_id,
        page_number=page_number,
        original_text=original_text,
        native_text=native_text,
        confidence_score=confidence,
        trigger_reason=reason,
        screenshot_path=screenshot_path if screenshot_path.exists() else None,
    )
    return _task_to_summary(task)


@router.post("/a2i/documents/{document_id}/poll")
def poll_a2i_results(document_id: str, db: Session = Depends(get_db)):
    """Poll AWS A2I for completed human loops on this document and apply any corrections found."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")
    completed = poll_and_apply_results(db, document_id)
    return {"documentId": document_id, "completed": completed}


# ---------------------------------------------------------------------------
# Global task queue
# ---------------------------------------------------------------------------

@router.get("/a2i/tasks", response_model=list[A2ITaskSummary])
def list_all_a2i_tasks(
    status: Optional[str] = Query(None, description="Filter by status"),
    reviewer_id: Optional[str] = Query(None, description="Filter by assigned_to"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Global task queue: list A2I tasks across all documents."""
    q = db.query(A2ITask)
    if status:
        q = q.filter(A2ITask.status == status)
    if reviewer_id:
        q = q.filter(A2ITask.assigned_to == reviewer_id)
    tasks = q.order_by(A2ITask.created_at.desc()).offset(offset).limit(limit).all()
    return [_task_to_summary(t) for t in tasks]


@router.get("/a2i/tasks/{task_id}/detail", response_model=A2ITaskDetail)
def get_a2i_task_detail(task_id: str, db: Session = Depends(get_db)):
    """Get full task detail including diff items and text snapshots."""
    task = db.query(A2ITask).filter(A2ITask.id == task_id).first()
    if not task:
        raise HTTPException(404, "A2I task not found")
    return _task_to_detail(task)


@router.post("/a2i/tasks/{task_id}/assign", response_model=A2ITaskSummary)
def assign_a2i_task(task_id: str, body: AssignTaskBody, db: Session = Depends(get_db)):
    """Assign a task to a reviewer; status transitions to 'assigned'."""
    task = db.query(A2ITask).filter(A2ITask.id == task_id).first()
    if not task:
        raise HTTPException(404, "A2I task not found")
    if task.status in ("completed", "failed"):
        raise HTTPException(409, f"Cannot assign task with status={task.status}")
    updated = assign_task(db, task, body.reviewerId)
    return _task_to_summary(updated)


@router.post("/a2i/tasks/{task_id}/complete")
def complete_a2i_task(task_id: str, body: A2ICompleteBody, db: Session = Depends(get_db)):
    """Submit corrected output for an A2I task (manual review or webhook)."""
    task = db.query(A2ITask).filter(A2ITask.id == task_id).first()
    if not task:
        raise HTTPException(404, "A2I task not found")
    if task.status == "completed":
        raise HTTPException(409, "Task already completed")
    apply_correction(db, task, body.correctedText, body.reviewerId, comment=body.comment)
    return {"status": "completed", "taskId": task_id}


# ---------------------------------------------------------------------------
# Reviewer stats
# ---------------------------------------------------------------------------

@router.get("/a2i/reviewer/{reviewer_id}/stats", response_model=ReviewerStatsResponse)
def get_reviewer_stats(reviewer_id: str, db: Session = Depends(get_db)):
    """Aggregate stats for a reviewer."""
    assigned = db.query(A2ITask).filter(A2ITask.assigned_to == reviewer_id).all()
    total_assigned = len(assigned)
    completed = sum(1 for t in assigned if t.status == "completed")
    pending = sum(1 for t in assigned if t.status in ("assigned", "pending", "in_review"))
    corrections_applied = sum(1 for t in assigned if t.human_corrected_text and t.status == "completed")
    acceptance_rate = (
        round(100.0 * (completed - corrections_applied) / completed, 1)
        if completed > 0 else 0.0
    )
    return ReviewerStatsResponse(
        reviewerId=reviewer_id,
        totalAssigned=total_assigned,
        completed=completed,
        pending=pending,
        correctionsApplied=corrections_applied,
        acceptanceRate=acceptance_rate,
    )
