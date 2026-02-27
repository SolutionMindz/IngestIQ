import hashlib
from pathlib import Path
from sqlalchemy.orm import Session

import uuid
from app.models.document import Document, DocumentVersion
from app.models.audit import AuditLog
from app.config import get_settings


def save_upload_and_create_document(
    db: Session,
    file,
    doc_id: str,
    upload_path: Path,
    ext: str,
) -> tuple[str, str]:
    # Per-document folder: uploads/{doc_id}/ so we have uploads/{id}/file.pdf and uploads/{id}/screenshots/
    doc_dir = upload_path / doc_id
    doc_dir.mkdir(parents=True, exist_ok=True)
    filename = (file.filename or f"document{ext}").strip() or f"document{ext}"
    path = doc_dir / filename
    h = hashlib.sha256()
    size_bytes = 0
    with open(path, "wb") as f:
        while chunk := file.file.read(8192):
            f.write(chunk)
            size_bytes += len(chunk)
            h.update(chunk)
    file_hash = h.hexdigest()
    file_path = f"{doc_id}/{filename}"
    doc = Document(
        id=doc_id,
        name=file.filename or file_path,
        file_path=file_path,
        file_hash_sha256=file_hash,
        file_size_bytes=size_bytes,
        upload_status="uploaded",
        processing_stage="pending",
        validation_status="pending",
        version="1.0",
    )
    db.add(doc)
    db.flush()  # ensure document row exists before FKs from document_versions and audit_log
    db.add(DocumentVersion(id=str(uuid.uuid4()), document_id=doc_id, version="1.0", name=doc.name))
    db.add(AuditLog(document_id=doc_id, document_name=doc.name, reviewer="System", action="Uploaded", validation_result="Pending", parser_version=get_settings().parser_version))
    db.commit()
    return file_path, file_hash
