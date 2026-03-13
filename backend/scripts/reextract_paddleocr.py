#!/usr/bin/env python3
"""
Re-run PaddleOCR extraction for a document (all pages, including page 1).
Uses existing uploaded file and screenshots. Does not run Textract or comparison.

Requires: Activate the backend venv and have paddleocr installed (pip install paddleocr).
Otherwise extraction may complete with 0 words.

Usage (from backend dir):
  source .venv/bin/activate   # or: .venv\\Scripts\\activate on Windows
  python3 scripts/reextract_paddleocr.py [document_id]
  If document_id is omitted, uses the first PDF document in the database.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import get_settings
from app.models.base import get_session_factory
from app.models.document import Document
from app.models.extraction import Extraction
from app.services.pdf_extractor import extract_pdf


def main():
    settings = get_settings()
    upload_path = settings.get_upload_path()
    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        doc_id = (sys.argv[1:] or [None])[0]
        if doc_id:
            doc = db.query(Document).filter(Document.id == doc_id).first()
            if not doc:
                print(f"Document not found: {doc_id}", file=sys.stderr)
                sys.exit(1)
        else:
            doc = db.query(Document).filter(Document.file_path.like("%.pdf")).first()
            if not doc:
                print("No PDF document found in database.", file=sys.stderr)
                sys.exit(1)
            doc_id = doc.id
            print(f"Using first PDF: {doc_id} ({doc.name})")

        file_path = upload_path / doc.file_path
        if not file_path.exists():
            print(f"File not found: {file_path}", file=sys.stderr)
            sys.exit(1)

        # Remove existing pdf extraction so we store a fresh one
        db.query(Extraction).filter(
            Extraction.document_id == doc_id,
            Extraction.source == "pdf",
        ).delete(synchronize_session=False)
        db.commit()

        print(f"Re-extracting with PaddleOCR: {doc_id} ...")
        extract_pdf(db, doc_id, str(file_path), upload_path=upload_path)
        print("Done. PaddleOCR extraction updated for all pages (including page 1).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
