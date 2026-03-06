# Knowledge Ingestion Backend (Phase 2)

FastAPI backend for document upload, DOCX/PDF extraction, structural comparison, and validation. Uses local PostgreSQL and local upload folder.

## Setup

1. Create a virtualenv and install dependencies:

   ```bash
   cd backend
   python3 -m venv .venv
   source .venv/bin/activate  # or .venv\Scripts\activate on Windows
   pip install -r requirements.txt
   ```

2. Ensure PostgreSQL is running. Create the database and user if needed (e.g. `createdb Textract` and user `sanjeev` with no password). Default: host `127.0.0.1`, database `Textract`, user `sanjeev`. Override with `DATABASE_URL` in `.env`.

3. Copy `.env.example` to `.env` and adjust if needed. Default `DATABASE_URL=postgresql://sanjeev@127.0.0.1/Textract`.

4. Run the API (use port 8889 if 8888 is already in use, e.g. by Apache):

   ```bash
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8889
   ```

   Health: http://127.0.0.1:8889/health

## API

- `POST /api/documents/upload` — upload .docx or .pdf (multipart); returns DocumentSummary; triggers background extraction and comparison.
- `GET /api/documents` — list documents.
- `GET /api/documents/{id}` — get document.
- `GET /api/documents/{id}/versions` — version history.
- `GET /api/documents/{id}/structure?source=docx|pdf|ocr` — get extraction structure.
- `GET /api/documents/{id}/comparison` — get comparison result.
- `GET /api/documents/{id}/screenshots` — list page screenshots (PDF only).
- `GET /api/documents/{id}/screenshots/{page}` — full-resolution PNG for a page.
- `GET /api/documents/{id}/page-accuracy` — list page accuracy scores (PDF only).
- `GET /api/documents/{id}/pages/{page}/validation` — get latest page validation log for a page.
- `POST /api/documents/{id}/pages/{page}/validation` — append page validation (body: `{ "reviewer": "...", "status": "verified|needs_review|...", "comment": "..." }`).
- `GET /api/validation?documentId=` — list validation items.
- `POST /api/validation/{id}/approve` — approve (body: `{ "reviewer": "...", "comment": "..." }` optional).
- `POST /api/validation/{id}/reject` — reject (same optional body).
- `GET /api/audit?documentId=` — audit log.

## Frontend

Set `VITE_USE_API=true` and `VITE_API_BASE=http://127.0.0.1:8000` in the frontend `.env`, then run the frontend. It will use the real API instead of mock data.

## Upload folder

Uploaded files are stored under `backend/uploads/` (or `UPLOAD_DIR`). The folder is created on startup. Add `uploads/` to `.gitignore` (already in backend `.gitignore`).

## PDF extraction

PDF extraction produces two structures for comparison: **native** (PyMuPDF) and **OCR** (pytesseract on page screenshots or rendered pages). Install Tesseract for OCR extraction (see below). The pipeline always runs; OCR uses screenshots when available, otherwise renders each PDF page to an image.

## Page-level screenshot validation (PDFs)

For PDFs, the pipeline generates one PNG screenshot per page (300 DPI, configurable via `SCREENSHOT_DPI` in `.env`) and runs page-level accuracy using OCR. **Tesseract OCR** must be installed on the server for accuracy computation:

- **macOS (Homebrew):** `brew install tesseract`
- **Ubuntu/Debian:** `sudo apt-get install tesseract-ocr`
- **Windows:** install from [GitHub tesseract](https://github.com/UB-Mannheim/tesseract/wiki)

The Python package `pytesseract` is in `requirements.txt`; it invokes the system Tesseract binary. If Tesseract is not installed, screenshot generation still runs, but page-accuracy computation is skipped and no accuracy rows are stored. **Native PDF extraction** also uses Tesseract as a fallback when a page has no or minimal text (e.g. image-only cover page): the pipeline runs OCR on that page's screenshot and uses the result for the "PDF" extraction. Install Tesseract so cover pages and image-only pages get text from OCR.

## Schema changes (PDF Ingestion Verification System)

If you have an existing database, add new columns to match the plan:

```sql
ALTER TABLE documents ADD COLUMN IF NOT EXISTS file_size_bytes BIGINT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS page_count INTEGER;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS error_type VARCHAR(64);
ALTER TABLE documents ADD COLUMN IF NOT EXISTS error_message VARCHAR(2048);
ALTER TABLE audit_log ADD COLUMN IF NOT EXISTS comparison_id UUID REFERENCES comparisons(id);
ALTER TABLE audit_log ADD COLUMN IF NOT EXISTS metadata JSONB;
ALTER TABLE extractions ADD COLUMN IF NOT EXISTS textract_job_id VARCHAR(256);
ALTER TABLE extractions ADD COLUMN IF NOT EXISTS metadata JSONB;
```

For **page-level screenshot validation**, `init_db()` creates these tables if they do not exist: `page_screenshots`, `page_accuracy`, `page_validation_log`. Document `validation_status` may be set to `screenshot_failed` or `validation_failed` when screenshot generation fails or any page accuracy is below 98%.
