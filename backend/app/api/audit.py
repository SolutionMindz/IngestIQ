from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.models.base import get_db
from app.models.audit import AuditLog
from app.schemas.audit import AuditLogEntry

router = APIRouter()


@router.get("/audit", response_model=list[AuditLogEntry])
def list_audit(documentId: str | None = None, db: Session = Depends(get_db)):
    q = db.query(AuditLog).order_by(AuditLog.timestamp.desc())
    if documentId:
        q = q.filter(AuditLog.document_id == documentId)
    rows = q.all()
    return [
        AuditLogEntry(
            id=r.id,
            documentId=r.document_id,
            documentName=r.document_name,
            timestamp=r.timestamp.isoformat() + "Z" if r.timestamp else "",
            parserVersion=r.parser_version or "",
            validationResult=r.validation_result or "",
            reviewer=r.reviewer,
            action=r.action,
        )
        for r in rows
    ]
