#!/usr/bin/env python3
"""
Re-run full extraction (PaddleOCR + Textract + comparison + page accuracy + A2I)
for all PDF documents in the upload directory that have an existing file.

Requires: Backend venv with paddleocr (and AWS credentials for Textract if used).

Usage (from backend dir):
  source .venv/bin/activate
  python3 scripts/rerun_all_extractions.py [document_id]
  If document_id is omitted, runs for every PDF document in the DB that has a file in the upload directory.
"""
import os
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))
os.chdir(backend_dir)

from app.config import get_settings
from app.models.base import get_session_factory
from app.models.document import Document
from app.services.jobs import run_re_extract


def main():
    settings = get_settings()
    upload_path = settings.get_upload_path()
    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        doc_id_arg = (sys.argv[1:] or [None])[0]
        if doc_id_arg:
            docs = db.query(Document).filter(Document.id == doc_id_arg).all()
            if not docs:
                print(f"Document not found: {doc_id_arg}", file=sys.stderr)
                sys.exit(1)
        else:
            docs = db.query(Document).all()
            docs = [d for d in docs if (upload_path / d.file_path).exists() and str(d.file_path).lower().endswith(".pdf")]

        if not docs:
            print("No PDF documents with existing files in upload directory.", file=sys.stderr)
            sys.exit(0)

        print(f"Re-running full extraction for {len(docs)} document(s).")
        for doc in docs:
            print(f"  {doc.id} ({doc.name}) ...")
            run_re_extract(doc.id)
            print(f"  Done: {doc.id}")
        print("All done.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
