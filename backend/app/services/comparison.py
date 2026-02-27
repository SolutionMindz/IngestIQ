from sqlalchemy.orm import Session
from app.models.document import Document
from app.models.extraction import Extraction
from app.models.comparison import Comparison
from app.models.validation import ValidationItem
from app.models.audit import AuditLog
from app.config import get_settings
from app.schemas.structure import DocumentStructure
from app.schemas.comparison import ComparisonResult, Mismatch


def run_comparison(db: Session, document_id: str) -> ComparisonResult | None:
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        return None
    docx_ext = db.query(Extraction).filter(Extraction.document_id == document_id, Extraction.source == "docx").first()
    pdf_ext = db.query(Extraction).filter(Extraction.document_id == document_id, Extraction.source == "pdf").first()
    textract_ext = db.query(Extraction).filter(Extraction.document_id == document_id, Extraction.source == "textract").first()

    # Prefer docx vs pdf when both exist; else compare pdf vs textract for PDF-only docs
    if docx_ext and pdf_ext:
        left_struct = DocumentStructure(**docx_ext.structure)
        right_struct = DocumentStructure(**pdf_ext.structure)
        left_label, right_label = "docx", "pdf"
    elif pdf_ext and textract_ext:
        left_struct = DocumentStructure(**pdf_ext.structure)
        right_struct = DocumentStructure(**textract_ext.structure)
        left_label, right_label = "pdf", "textract"
    else:
        doc.validation_status = "structurally_verified"
        db.add(AuditLog(document_id=document_id, document_name=doc.name, reviewer="System", action="Single extraction only; no comparison", validation_result="Structurally Verified", parser_version=get_settings().parser_version))
        db.commit()
        return None
    result = compare_structures(document_id, left_struct, right_struct, left_label, right_label)
    comp = Comparison(document_id=document_id, result=result.model_dump())
    db.add(comp)
    db.flush()  # get comp.id for audit link
    if result.mismatches:
        doc.validation_status = "integrity_conflict"
        conf = _confidence_from_result(result)
        vi = ValidationItem(document_id=document_id, confidence=conf, conflict_reason="; ".join(m.message for m in result.mismatches[:5]), status="pending")
        db.add(vi)
        db.add(AuditLog(document_id=document_id, document_name=doc.name, reviewer="System", action="Flagged for review: structural mismatch", validation_result="Integrity Conflict", parser_version=get_settings().parser_version, comparison_id=comp.id, metadata_={"mismatch_count": len(result.mismatches)}))
    else:
        doc.validation_status = "structurally_verified"
        db.add(AuditLog(document_id=document_id, document_name=doc.name, reviewer="System", action="Comparison passed", validation_result="Structurally Verified", parser_version=get_settings().parser_version, comparison_id=comp.id))
    db.commit()
    return result


def _confidence_from_result(result: ComparisonResult) -> float:
    """Compute 0–100 confidence from comparison result. Dynamic: no match → low, full match → 100%."""
    if not result.mismatches:
        return 100.0
    # Each failed check (chapter, heading, word count, paragraph) reduces score
    checks = [
        result.chapterCountMatch,
        result.headingMatch,
        result.wordCountMatch,
        result.paragraphCountMatch,
    ]
    failed_checks = sum(1 for c in checks if not c)
    n = len(result.mismatches)
    # Base: 100 minus 20 per failed check, minus 15 per mismatch (capped)
    score = 100.0 - (failed_checks * 20) - min(40, n * 15)
    return max(0.0, min(100.0, round(score, 1)))


def compare_structures(
    document_id: str,
    left: DocumentStructure,
    right: DocumentStructure,
    left_label: str = "docx",
    right_label: str = "pdf",
) -> ComparisonResult:
    mismatches: list[Mismatch] = []
    mid = 0
    def add_mismatch(t: str, msg: str, **kwargs):
        nonlocal mid
        mid += 1
        mismatches.append(Mismatch(id=f"m{mid}", type=t, message=msg, **kwargs))

    left_ch = len(left.chapters)
    right_ch = len(right.chapters)
    chapter_count_match = left_ch == right_ch
    if not chapter_count_match:
        add_mismatch("chapter", f"Chapter count differs: {left_label}={left_ch}, {right_label}={right_ch}", docxRef=str(left_ch), pdfRef=str(right_ch))

    left_words = left.totalWordCount or sum(c.wordCount or 0 for c in left.chapters)
    right_words = right.totalWordCount or sum(c.wordCount or 0 for c in right.chapters)
    word_count_match = abs((left_words or 0) - (right_words or 0)) <= 50
    if not word_count_match:
        add_mismatch("word_count", f"Word count differs: {left_label}={left_words}, {right_label}={right_words}", docxRef=str(left_words), pdfRef=str(right_words))

    heading_match = True
    for i, (lc, rc) in enumerate(zip(left.chapters, right.chapters)):
        if (lc.heading or "").strip() != (rc.heading or "").strip():
            heading_match = False
            add_mismatch("heading", f"Heading differs in chapter {i+1}", chapterIndex=i, docxRef=lc.heading, pdfRef=rc.heading)
    if len(left.chapters) != len(right.chapters):
        heading_match = False

    left_paras = sum(len(c.content_blocks) + sum(len(s.contentBlocks) for s in (c.sections or [])) for c in left.chapters)
    right_paras = sum(len(c.content_blocks) + sum(len(s.contentBlocks) for s in (c.sections or [])) for c in right.chapters)
    paragraph_count_match = abs(left_paras - right_paras) <= 10
    if not paragraph_count_match:
        add_mismatch("paragraph", f"Paragraph count differs: {left_label}={left_paras}, {right_label}={right_paras}", docxRef=str(left_paras), pdfRef=str(right_paras))

    return ComparisonResult(
        documentId=document_id,
        chapterCountMatch=chapter_count_match,
        headingMatch=heading_match,
        paragraphCountMatch=paragraph_count_match,
        tableCountMatch=True,
        pageCountMatch=True,
        wordCountMatch=word_count_match,
        mismatches=mismatches,
        docxChapterCount=left_ch,
        pdfChapterCount=right_ch,
        docxWordCount=left_words or 0,
        pdfWordCount=right_words or 0,
    )
