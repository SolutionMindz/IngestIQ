#!/usr/bin/env python3
"""
Upload a file to the API and poll until processing completes or errors.
Usage: python scripts/test_upload_and_ingestion.py [path/to/file.pdf]
"""
import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error

API_BASE = os.environ.get("API_BASE", "http://127.0.0.1:8889")


def upload(path: str) -> dict | None:
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        return None
    result = subprocess.run(
        [
            "curl",
            "-s",
            "-X",
            "POST",
            f"{API_BASE}/api/documents/upload",
            "-F",
            f"file=@{path}",
        ],
        capture_output=True,
        text=True,
        timeout=60
    )
    if result.returncode != 0:
        print(f"curl failed: {result.stderr or result.stdout}")
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        print("Response was not JSON:", result.stdout[:500])
        return None


def get_document(doc_id: str) -> dict | None:
    req = urllib.request.Request(f"{API_BASE}/api/documents/{doc_id}")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        print(f"Get document failed: {e}")
        return None


def get_screenshots(doc_id: str) -> list:
    """GET /api/documents/{id}/screenshots - returns list of { pageNumber, path, checksum }."""
    req = urllib.request.Request(f"{API_BASE}/api/documents/{doc_id}/screenshots")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        print(f"Get screenshots failed: {e}")
        return []


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else None
    if not path or not os.path.isfile(path):
        print("Usage: python scripts/test_upload_and_ingestion.py <file.pdf|file.docx>")
        print("Example: python scripts/test_upload_and_ingestion.py 'Sample Set/PDF1.pdf'")
        sys.exit(1)
    print(f"Uploading {path} to {API_BASE}...")
    doc = upload(path)
    if not doc:
        sys.exit(2)
    doc_id = doc["documentId"]
    print(f"Upload OK. documentId={doc_id}")
    print(f"  processingStage={doc.get('processingStage', '?')} validationStatus={doc.get('validationStatus', '?')}")
    for i in range(30):
        time.sleep(1)
        doc = get_document(doc_id)
        if not doc:
            continue
        stage = doc.get("processingStage", "?")
        status = doc.get("validationStatus", "?")
        print(f"  [{i+1}s] processingStage={stage} validationStatus={status}")
        if stage == "done":
            print("Ingestion completed successfully.")
            screens = get_screenshots(doc_id)
            print(f"Screenshots: {len(screens)} pages")
            if screens:
                print(f"  First: {screens[0].get('path', '?')}")
            break
        if stage == "error":
            print("Ingestion ended in error. Check backend logs.")
            sys.exit(3)
    else:
        print("Timed out waiting for processing_stage=done. Check backend logs.")
        sys.exit(4)


if __name__ == "__main__":
    main()
