from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.models.base import get_db
from app.models.document import Document
from app.models.comparison import Comparison
from app.schemas.comparison import ComparisonResult

router = APIRouter()


@router.get("/documents/{document_id}/comparison", response_model=ComparisonResult | None)
def get_comparison(document_id: str, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        return None
    comp = db.query(Comparison).filter(Comparison.document_id == document_id).order_by(Comparison.created_at.desc()).first()
    if not comp:
        return None
    return ComparisonResult(**comp.result)
