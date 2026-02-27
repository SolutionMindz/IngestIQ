from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.models.base import get_db
from app.models.document import Document
from app.models.extraction import Extraction
from app.schemas.structure import DocumentStructure

router = APIRouter()


@router.get("/documents/{document_id}/structure", response_model=DocumentStructure | None)
def get_structure(document_id: str, source: str, db: Session = Depends(get_db)):
    if source not in ("docx", "pdf", "textract"):
        raise HTTPException(400, "source must be docx, pdf, or textract")
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        return None
    ext = db.query(Extraction).filter(Extraction.document_id == document_id, Extraction.source == source).first()
    if not ext:
        return None
    return DocumentStructure(**ext.structure)
