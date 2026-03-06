
# IngestIQ – Amazon Augmented AI (A2I) Integration Requirement

## Project Name
IngestIQ – Human Verified Document Ingestion System

---

# 1. Objective

Integrate **Amazon Augmented AI (A2I)** into the IngestIQ ingestion pipeline to enable **human-in-the-loop validation** for low-confidence extraction results produced by **Amazon Textract**.

This integration will ensure:

- Higher document extraction accuracy
- Human verification of critical content
- Reduced OCR errors in code blocks and tables
- Enterprise-grade audit trail
- Scalable human review workflows

The goal is to combine **machine extraction + human verification** to achieve near-perfect document integrity.

---

# 2. Scope

The integration will apply to:

- PDF ingestion pipeline
- Textract extraction results
- Page-level accuracy validation
- Human review for problematic pages

Human review should be triggered **only when automated confidence falls below defined thresholds**.

---

# 3. High-Level Architecture

PDF Upload
↓
Screenshot Generator (per page)
↓
Textract Document Analysis
↓
Confidence Evaluation Engine
↓
Trigger Rules
↓
A2I Human Review Workflow
↓
Human Corrected Output
↓
IngestIQ Validation Engine
↓
Page Extraction Accuracy Calculation
↓
Final Approved Document

---

# 4. Components

## 4.1 Textract Extraction Layer

Use Textract API:

- AnalyzeDocument
- FeatureTypes:
  - TABLES
  - FORMS

Output:

- Textract JSON Blocks
- Text
- Tables
- Confidence scores
- Geometry

This output will be passed to the **confidence evaluation module**.

---

# 5. Human Review Trigger Rules

Human review will only be triggered when specific conditions occur.

### Confidence Threshold Rules

Trigger A2I if:

- Textract confidence < 97%
- Page extraction accuracy < 98%
- OCR vs Textract mismatch > 3%
- Table structure mismatch detected
- Code block extraction detected
- Mathematical equations detected

Example rule:

IF page_accuracy < 98%  
OR textract_confidence < 97%  
THEN send page to A2I human review

---

# 6. Amazon A2I Flow Configuration

Create a **Human Review Flow Definition**.

Components required:

- Human task UI template
- Workforce configuration
- Output storage
- Review trigger logic

Flow Definition Example:

Flow Name: IngestIQ-Human-Validation  
Task Type: Document Review  
Workforce: Private Workforce  
S3 Output Location: ingestiq/human-reviews/

---

# 7. Human Review Task UI

Reviewers will see:

### Panel Layout

Left Side
- Screenshot of the page

Center
- Textract extracted text

Right Side
- Editable correction field

Reviewer actions:

- Accept extraction
- Correct text
- Flag structural issue
- Submit corrected output

---

# 8. Human Review Workflow

Step 1  
Textract processes page.

Step 2  
Confidence evaluation runs.

Step 3  
If threshold violated → create A2I task.

Step 4  
Human reviewer receives task.

Step 5  
Reviewer corrects extraction.

Step 6  
Corrected result returned to IngestIQ pipeline.

Step 7  
Page accuracy recalculated.

Step 8  
Page marked as:

Verified by Human

---

# 9. Data Flow

Input:

- PDF Page Screenshot
- Textract Output
- Confidence Scores

Human Review Output:

- Corrected Text
- Table Corrections
- Reviewer Comments
- Reviewer ID
- Timestamp

---

# 10. Storage

Human review outputs must be stored in:

S3 Bucket  
ingestiq-human-review/

Metadata stored in database:

- page_number
- document_id
- original_textract_text
- human_corrected_text
- confidence_score
- reviewer_id
- review_timestamp

---

# 11. IngestIQ Validation Integration

After human review:

1. Replace Textract extraction with corrected output
2. Recalculate Page Extraction Accuracy
3. Update Validation Console

Example output:

Page 42

Textract Confidence: 95%  
Human Review: Completed

Correction Applied:  
"NSTRUCTOR" → "INSTRUCTOR"

Final Accuracy: 99.8%

---

# 12. Validation Console Enhancements

Add fields:

- Human Review Status
- Reviewer Name
- Correction Summary
- Review Timestamp

Statuses:

- Pending Review
- Under Review
- Human Verified
- Auto Verified
- Rejected

---

# 13. Audit Logging

Every review must be logged.

Example log record:

{
  document_id: "DOC123",
  page_number: 42,
  original_textract_text: "...",
  corrected_text: "...",
  reviewer_id: "user_001",
  action: "Correction Applied",
  timestamp: "2026-03-06T10:30:00Z"
}

Logs must be immutable.

---

# 14. Security Requirements

- Use private workforce for sensitive documents
- Restrict reviewer access via IAM roles
- Encrypt review data in S3
- Maintain reviewer activity logs

---

# 15. Performance Strategy

To control costs:

Human review should only trigger for **problematic pages**, not entire documents.

Typical distribution:

400 page book  
→ 380 pages auto approved  
→ 20 pages human review

---

# 16. Success Metrics

System considered successful when:

- Human review resolves extraction errors
- Page accuracy > 98%
- Code blocks extracted correctly
- Table structures preserved
- Audit logs available for all human reviews

---

# 17. Future Enhancements

Potential improvements:

- ML model training using human corrections
- Smart routing based on page complexity
- Automatic reviewer assignment
- Reviewer quality scoring

---

# 18. Design Philosophy

Machines perform large-scale extraction.

Humans verify edge cases.

IngestIQ orchestrates both layers to ensure **document integrity and trust**.

The goal is not just extraction.

The goal is **verifiable ingestion**.
