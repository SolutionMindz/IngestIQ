import json
from pathlib import Path
from sqlalchemy.orm import Session
from app.models.document import Document
from app.models.extraction import Extraction
from app.config import get_settings


def invalidate_approval(db: Session, document_id: str) -> None:
    """Invalidate approval when document is modified; requires re-extraction (Section 12)."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        return
    if doc.validation_status == "training_approved":
        doc.validation_status = "pending"
        # Optionally delete canonical file so downstream does not use stale data
        upload_path = get_settings().get_upload_path()
        canonical_dir = upload_path / "canonical"
        pattern = f"{document_id}_*.json"
        for p in canonical_dir.glob(pattern):
            try:
                p.unlink()
            except OSError:
                pass


def write_canonical(db: Session, document_id: str) -> Path | None:
    """Write canonical JSON only when document is approved (downstream gate)."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        return None
    if doc.validation_status != "training_approved":
        return None  # Gate: do not write canonical for unapproved documents
    ext = db.query(Extraction).filter(Extraction.document_id == document_id, Extraction.source == "pdf").first()
    if not ext:
        return None
    upload_path = get_settings().get_upload_path()
    canonical_dir = upload_path / "canonical"
    canonical_dir.mkdir(parents=True, exist_ok=True)
    path = canonical_dir / f"{document_id}_{doc.version}.json"
    with open(path, "w") as f:
        json.dump(ext.structure, f, indent=2)
    return path
