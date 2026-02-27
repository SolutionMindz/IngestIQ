# Technical Book Extraction & AI Training Pipeline
## Zero Data Loss Document Processing Architecture

---

# 1. Project Goal

Build a document ingestion pipeline that extracts structured content from `.docx` and `.pdf` technical books stored in SharePoint with guaranteed completeness and validation before training an AI model.

Primary Objective:
- Zero chapter loss
- Zero structural corruption
- Deterministic validation
- Full audit trail

We are not optimizing for speed.
We are optimizing for integrity.

---

# 2. High-Level Architecture

SharePoint (.docx source)/File upload
        ↓
Document Ingestion Service
        ↓
Dual Extraction Layer
    ├── Native DOCX Parser
    └── PDF Structural Extractor (AWS Textract)
        ↓
Structural Normalization Engine
        ↓
Validation Engine (Rule + Human-in-loop)
        ↓
Canonical Content Store
        ↓
Chunking + Metadata Builder
        ↓
Vectorization Layer
        ↓
AI Training Dataset Builder

---

# 3. Why Dual Extraction?

Never trust a single parser.

DOCX is structured XML.
PDF is rendered layout.

We extract from BOTH and compare.

If mismatch detected → Flag for review.

---

# 4. Step-by-Step Workflow

---

## Step 1: Document Intake

Source:
- SharePoint document library
- File upload

Implementation:
- Use SharePoint webhook to trigger ingestion
- Store document in raw document storage (S3 or Blob)
- Assign unique Document ID (UUID)
- Log metadata:
    - Author
    - Version
    - Timestamp
    - File hash (SHA-256)

Hash ensures file integrity.

---

## Step 2: Dual Extraction Layer

### 2.1 DOCX Extraction

Use:
- python-docx or OpenXML SDK

Extract:
- Chapters (Heading 1)
- Subsections (Heading 2/3)
- Paragraphs
- Code blocks
- Tables
- Images references
- Footnotes

Preserve:
- Heading hierarchy
- Page breaks
- Captions

Store as structured JSON:
{
  chapter_id,
  heading,
  content_blocks,
  order_index
}

---

### 2.2 PDF Extraction (Textract)

Use:
- AWS Textract AnalyzeDocument (FORMS + TABLES)

Extract:
- Text blocks
- Table structures
- Layout blocks
- Page numbers

Reconstruct logical flow using:
- Block relationships
- Geometry positioning

Normalize into same JSON schema as DOCX.

---

## Step 3: Structural Comparison Engine

Compare:
- Chapter count
- Heading hierarchy
- Paragraph count
- Table count
- Page count
- Total word count

If any mismatch:
- Mark document status = "Integrity Conflict"
- Send to Review Queue

If match:
- Status = "Structurally Verified"

---

# 5. Validation Layer (Critical for 100%)

100% accuracy is achieved by validation, not extraction.

Three validation mechanisms:

### A. Hash Validation
- Ensure no corruption in transfer.

### B. Structural Integrity Rules
- Every Heading 1 must have content.
- Chapter order must be sequential.
- No missing page numbers.
- Table row count consistency.

### C. Human-in-the-Loop (Selective)

Trigger human review only if:
- Confidence < 98%
- Structural mismatch detected
- Missing content blocks

Use MTurk-style micro validation:
- Present side-by-side comparison
- Reviewer confirms completeness

---

# 6. Canonical Content Store

After validation, store in canonical schema:

Document
 ├── Chapters
 │     ├── Sections
 │     │     ├── Content Blocks
 │     │     │      ├── Text
 │     │     │      ├── Code
 │     │     │      ├── Table
 │     │     │      └── Image
 │
 ├── Metadata
 ├── Version History
 └── Validation Log

Store in:
- PostgreSQL (structured metadata)
- Object storage (raw content)

---

# 7. UI Design (Admin Console)

## Dashboard

Sections:

1. Document Intake Panel
   - Upload status
   - Processing stage
   - Validation status
   - Version history

2. Structural Comparison Viewer
   - Left: DOCX structure
   - Right: PDF structure
   - Highlight mismatches

3. Chapter Explorer
   - Expandable hierarchy tree
   - Visual diff viewer
   - Word count indicator

4. Validation Console
   - Conflict queue
   - Confidence score
   - Approve / Reject buttons
   - Comment log

5. Audit Logs
   - Extraction timestamp
   - Parser version
   - Validation results
   - Reviewer name

---

# 8. Training Dataset Preparation

After validation:

## Step 1: Semantic Chunking

Rules:
- Split by section boundaries
- Preserve code blocks intact
- Never split mid-table
- Max token limit (configurable)

Attach metadata:
{
  chapter,
  section,
  page_range,
  book_version,
  author,
  hash_reference
}

---

## Step 2: Vector Embedding

- Send chunk to embedding model
- Store vector in vector DB
- Maintain pointer to canonical content ID

---

## Step 3: AI Model Fine-Tuning / RAG Index

Option A: Fine-tune model
Option B: RAG (recommended for updates)

RAG Pipeline:
User Query
   ↓
Vector Search
   ↓
Retrieve validated chunks
   ↓
LLM Response
   ↓
Citation back to Chapter + Page

---

# 9. Version Control Strategy

Books evolve.

Implement:
- Versioned document storage
- Delta comparison engine
- Retrain only modified sections
- Maintain version-specific embeddings

Never delete previous versions.

Trust requires traceability.

---

# 10. Error Handling Strategy

Define error states:

- Extraction Failure
- Structural Mismatch
- Validation Pending
- Manual Override
- Final Approved

System must block training if:
status != "Final Approved"

---

# 11. Security Considerations

- Encrypt raw documents
- Role-based access control
- Reviewer access logs
- Mask sensitive data if required
- No training on unverified content

---

# 12. Tech Stack Recommendation

Backend:
- Python (FastAPI)
- PostgreSQL
- Redis (job queue)
- AWS Textract
- S3

Frontend:
- React
- Diff viewer component
- Tree explorer UI

AI Layer:
- Embedding model
- Vector DB (postgres with)
- LLM layer

---

# 13. Key Principle

We are not building extraction software.

We are building a:

Verifiable Knowledge Ingestion System

Extraction is probabilistic.
Validation is deterministic.
Trust is engineered.

---

# 14. Success Criteria

A document can move to training only when:

- Structural match confirmed
- All chapters present
- Word count within tolerance
- Validation rules passed
- Manual review completed (if triggered)
- Audit log generated

Only then:
status = "Training Approved"