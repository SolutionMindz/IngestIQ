
# IngestIQ – Human Review UI (Textract Diff Validation)

## Feature
Human Validation Interface for Textract Extraction Differences

## Objective

Build a **Human Review UI** inside IngestIQ similar to the task interface used in Amazon Mechanical Turk.  

This interface will allow human reviewers to:

- Inspect differences between Textract extraction and OCR/Native extraction
- Accept or reject extracted values
- Correct incorrect extraction results
- Approve final page-level extraction

The goal is to enable **human-in-the-loop validation for document ingestion accuracy**.

---

# 1. Context

Current pipeline:

PDF Upload  
→ Textract Extraction  
→ OCR Extraction  
→ Diff Engine  
→ Accuracy Engine  
→ A2I Trigger (low confidence)  
→ Human Review UI  
→ Corrected Output  
→ Final Validation

The Human Review UI is triggered when:

- Page extraction accuracy < 98%
- Textract confidence < threshold
- Diff engine detects mismatches
- Tables or code blocks have structural issues

---

# 2. Human Review Task UI

The UI should follow a **three-column comparison layout**.

## Layout

Left Column
- Page screenshot (visual reference)

Middle Column
- Native PDF extractor output (markdown/text)

Right Column
- Textract extracted text

Below the columns:

Diff viewer showing mismatches.

---

# 3. Diff Highlighting

Differences between the two extractors must be highlighted.

Types of diffs:

- Missing characters
- Missing words
- Table mismatches
- Header/footer differences
- Code block corruption

Example:

Textract Output
model = NSTRUCTOR("hkunlp/instructor-base")

Expected Output
model = INSTRUCTOR("hkunlp/instructor-base")

The UI must highlight:

NSTRUCTOR → INSTRUCTOR

---

# 4. Reviewer Actions

Each diff item must provide actions:

### Accept Textract Output
Reviewer confirms Textract result is correct.

### Accept Native Extract
Reviewer confirms Native extractor is correct.

### Edit Value
Reviewer manually corrects the value.

### Reject Extraction
Reviewer flags extraction as incorrect.

---

# 5. Reviewer Interaction Workflow

Step 1  
Reviewer opens review task.

Step 2  
UI displays:

- Screenshot
- Native extraction
- Textract extraction
- Highlighted diff

Step 3  
Reviewer selects action:

- Accept
- Reject
- Edit

Step 4  
Reviewer submits correction.

Step 5  
System updates extraction result.

---

# 6. Task Metadata

Each review task must include metadata:

document_id  
page_number  
diff_type  
confidence_score  
textract_output  
native_output  
ocr_reference  
reviewer_id  
review_timestamp  

---

# 7. Task Queue Management

Review tasks should appear in a **review queue**.

Statuses:

Pending  
Assigned  
In Review  
Completed  
Rejected  

Tasks should be assignable to reviewers.

---

# 8. Reviewer Dashboard

Dashboard should show:

- Pending review tasks
- Tasks assigned to reviewer
- Completed tasks
- Accuracy metrics

Metrics:

- Pages reviewed
- Corrections made
- Acceptance rate

---

# 9. Editing Interface

When reviewer edits extraction:

Provide text input field with correction.

Example:

Original Textract:
NSTRUCTOR

Corrected:
INSTRUCTOR

Changes must be tracked.

---

# 10. Audit Logging

All reviewer actions must be logged.

Example log:

{
 document_id: "doc_001",
 page_number: 10,
 diff_type: "missing_character",
 textract_value: "NSTRUCTOR",
 corrected_value: "INSTRUCTOR",
 reviewer_id: "reviewer_21",
 action: "manual_correction",
 timestamp: "2026-03-06T11:20:00Z"
}

Logs must be immutable.

---

# 11. Accuracy Recalculation

After human review:

Re-run page accuracy calculation.

page_accuracy = 99.8%

Update validation console.

---

# 12. UI Features

### Diff Highlighting
Color-coded diff display.

Red → incorrect extraction  
Green → corrected value

### Expand Section
Allow reviewers to expand paragraphs or tables.

### Page Navigation
Reviewers can move between pages.

---

# 13. Security

- Only authorized reviewers can access tasks
- IAM authentication
- Reviewer activity logs
- Data encryption

---

# 14. Performance

- Lazy load large documents
- Only load page under review
- Cache diff results

---

# 15. Success Criteria

System should allow reviewers to:

- Detect extraction errors quickly
- Correct small OCR mistakes
- Validate table structure
- Confirm code block accuracy

Goal:

Human-verified document ingestion with >99% accuracy.

---

# 16. Design Philosophy

Automation extracts data.

Humans validate edge cases.

IngestIQ coordinates both layers to guarantee document integrity.

The system is not just extraction.

It is **verifiable document ingestion**.
