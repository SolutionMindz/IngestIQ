# IngestIQ — Document Ingestion & Extraction Platform

**IngestIQ** is an open-source **document ingestion** and **extraction** pipeline for technical books and PDFs. It provides a **PDF extractor**, **DOCX extractor**, structural comparison, validation, and an audit trail — built for zero data loss and verifiable **document processing** before AI training or publishing.

If you're searching for **document ingestion**, **text extraction**, **PDF extraction**, or a **document extractor** for books and technical content, this project gives you dual extraction (native DOCX + PDF via AWS Textract), side-by-side comparison, and a web-based admin console.

---

## What is document ingestion?

**Document ingestion** is the process of taking raw files (PDF, DOCX) and turning them into structured, queryable content. IngestIQ focuses on:

- **Ingestion pipeline**: Upload → extract → normalize → validate → store
- **Dual extractor**: Parse both DOCX (native) and PDF (Textract/OCR) and compare results
- **Extraction quality**: Page-level accuracy, screenshot validation, and human-in-the-loop review

Use cases: technical book pipelines, knowledge base ingestion, PDF-to-structured-data extraction, and pre-training data preparation.

---

## Features

| Feature | Description |
|--------|-------------|
| **Document ingestion** | Upload DOCX and PDF; automatic extraction and comparison |
| **PDF extractor** | AWS Textract integration + fallback OCR (Tesseract) for image-only pages |
| **DOCX extractor** | Native XML parsing for structure, headings, tables, and blocks |
| **Structural comparison** | Side-by-side DOCX vs PDF structure with mismatch highlighting |
| **Page explorer** | Tree view of Pages, sections, and content blocks with word counts |
| **Validation console** | Review conflicts, approve/reject, add comments |
| **Audit logs** | Full trail of parser versions, validation results, and reviewer actions |
| **Page accuracy** | Per-page screenshot + OCR accuracy scores for PDFs |

---

## Tech stack

- **Backend**: Python, FastAPI, PostgreSQL, SQLAlchemy
- **Frontend**: React, TypeScript, Vite
- **Extraction**: AWS Textract (PDF), python-docx (DOCX), Tesseract (OCR fallback)

---

## Prerequisites

- **Python 3.10+** (backend)
- **Node.js 18+** and npm (frontend)
- **PostgreSQL** (local or remote)
- **Optional**: AWS account (for Textract PDF extraction), Tesseract (for OCR fallback and page accuracy)

---

## Setup (step-by-step)

### 1. Clone the repository

```bash
git clone https://github.com/SolutionMindz/IngestIQ.git
cd IngestIQ
```

### 2. Backend setup (document ingestion API)

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Create the database (PostgreSQL). Example with default DB name `Textract` and user `sanjeev`:

```bash
createdb Textract
```

Copy environment file and set the database URL:

```bash
cp .env.example .env
# Edit .env: DATABASE_URL=postgresql://USER@127.0.0.1/Textract
```

Start the ingestion API:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8889
```

- API docs: http://127.0.0.1:8889/docs  
- Health: http://127.0.0.1:8889/health  

### 3. Frontend setup (admin console)

In a new terminal:

```bash
cd frontend
npm install
```

Point the frontend at the real API (optional; otherwise it uses mock data):

```bash
cp .env.example .env
# Set: VITE_USE_API=true and VITE_API_BASE=http://127.0.0.1:8889
```

Start the dev server:

```bash
npm run dev
```

Open the app (adjust host/port if you use a different config, e.g. nginx):

- http://localhost:5173 or http://new.packt.localhost:8003  

### 4. Optional: PDF extraction with AWS Textract

For real **PDF extraction** (not mock), set in `backend/.env`:

```env
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
AWS_REGION=us-east-1
```

Multi-page PDFs can use async Textract; set `AWS_S3_BUCKET` if you use that path. See [Docs/setup/aws_textract_setup.md](Docs/setup/aws_textract_setup.md) for details.

### 5. Optional: Tesseract OCR (fallback and page accuracy)

For OCR fallback and page-level accuracy on PDFs, install Tesseract:

- **macOS**: `brew install tesseract`
- **Ubuntu/Debian**: `sudo apt-get install tesseract-ocr`
- **Windows**: [Tesseract at UB-Mannheim](https://github.com/UB-Mannheim/tesseract/wiki)

The backend uses `pytesseract` (already in `requirements.txt`) to call the system Tesseract binary.

---

## Project structure

```
IngestIQ/
├── backend/          # FastAPI ingestion API, extractors, comparison, validation
├── frontend/         # React admin console (document intake, comparison, validation, audit)
├── Docs/             # Business requirements, setup guides (e.g. Textract, nginx)
├── config/           # launchd, nginx configs
└── scripts/          # Test and ingestion scripts
```

- **Backend README**: [backend/README.md](backend/README.md) — API endpoints, schema changes, screenshot validation  
- **Frontend README**: [frontend/README.md](frontend/README.md) — mock data, data contracts, features  

---

## Keywords (for search and discovery)

This project is designed for discoverability around **document ingestion**, **extraction**, and **pipelines**:

- Document ingestion · Ingestion pipeline · Document extractor  
- PDF extractor · PDF extraction · DOCX extractor · Text extraction  
- Document processing · Knowledge ingestion · Structural comparison  
- PDF to text · Document validation · Ingestion platform  

---

## License

See repository for license information.
