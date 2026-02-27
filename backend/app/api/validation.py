from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.models.base import get_db
from app.models.document import Document
from app.models.validation import ValidationItem as ValidationItemModel, ValidationComment as ValidationCommentModel
from app.models.audit import AuditLog
from app.schemas.validation import ValidationItem, ValidationComment
from app.config import get_settings
from app.services.canonical import write_canonical
from app.services.validation_rules import can_approve, is_manual_override_approval

router = APIRouter()


class ApproveRejectBody(BaseModel):
    reviewer: str | None = None
    comment: str | None = None


def _item_to_schema(v: ValidationItemModel) -> ValidationItem:
    comments = [ValidationComment(id=c.id, author=c.author, text=c.text, createdAt=c.created_at.isoformat() + "Z" if c.created_at else "") for c in v.comments]
    doc = v.document
    return ValidationItem(
        id=v.id,
        documentId=v.document_id,
        documentName=doc.name if doc else "",
        confidence=v.confidence,
        conflictReason=v.conflict_reason,
        reviewer=v.reviewer,
        status=v.status,
        comments=comments,
        createdAt=v.created_at.isoformat() + "Z" if v.created_at else "",
    )


@router.get("/validation", response_model=list[ValidationItem])
def list_validation(documentId: str | None = None, db: Session = Depends(get_db)):
    q = db.query(ValidationItemModel)
    if documentId:
        q = q.filter(ValidationItemModel.document_id == documentId)
    items = q.order_by(ValidationItemModel.created_at.desc()).all()
    return [_item_to_schema(v) for v in items]


@router.post("/validation/{item_id}/approve", response_model=ValidationItem)
def approve_validation(item_id: str, body: ApproveRejectBody | None = Body(None), db: Session = Depends(get_db)):
    item = db.query(ValidationItemModel).filter(ValidationItemModel.id == item_id).first()
    if not item:
        raise HTTPException(404, "Validation item not found")
    doc = db.query(Document).filter(Document.id == item.document_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")
    allowed, reason = can_approve(doc, db)
    if not allowed:
        raise HTTPException(400, f"Cannot approve: {reason}")
    # Manual override: require comment and log explicitly (Section 7)
    if is_manual_override_approval(doc):
        comment = (body.comment if body else "").strip()
        if not comment:
            raise HTTPException(400, "Manual override requires a comment (document had structural mismatch)")
        db.add(AuditLog(document_id=item.document_id, document_name=doc.name, reviewer=(body.reviewer if body else None) or "User", action="Manual override: approved despite structural mismatch", validation_result="Override", parser_version=get_settings().parser_version))
    item.status = "approved"
    item.reviewer = (body.reviewer if body else None) or "User"
    if body and body.comment:
        import uuid
        c = ValidationCommentModel(id=str(uuid.uuid4()), validation_item_id=item_id, author=item.reviewer, text=body.comment)
        db.add(c)
    doc.validation_status = "training_approved"
    write_canonical(db, item.document_id)
    db.add(AuditLog(document_id=item.document_id, document_name=doc.name, reviewer=item.reviewer, action="Approved", validation_result="Training Approved", parser_version=get_settings().parser_version))
    db.commit()
    db.refresh(item)
    return _item_to_schema(item)


@router.post("/validation/{item_id}/reject", response_model=ValidationItem)
def reject_validation(item_id: str, body: ApproveRejectBody | None = Body(None), db: Session = Depends(get_db)):
    item = db.query(ValidationItemModel).filter(ValidationItemModel.id == item_id).first()
    if not item:
        raise HTTPException(404, "Validation item not found")
    item.status = "rejected"
    item.reviewer = (body.reviewer if body else None) or "User"
    if body and body.comment:
        import uuid
        c = ValidationCommentModel(id=str(uuid.uuid4()), validation_item_id=item_id, author=item.reviewer, text=body.comment)
        db.add(c)
    doc = db.query(Document).filter(Document.id == item.document_id).first()
    if doc:
        db.add(AuditLog(document_id=item.document_id, document_name=doc.name, reviewer=item.reviewer, action="Rejected", validation_result="Rejected", parser_version=get_settings().parser_version))
    db.commit()
    db.refresh(item)
    return _item_to_schema(item)
