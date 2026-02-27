from pathlib import Path
from sqlalchemy.orm import Session
from docx import Document as DocxDocument
from docx.document import Document as DocxDocumentType
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.models.document import Document
from app.models.extraction import Extraction
from app.models.audit import AuditLog
from app.config import get_settings
from app.schemas.structure import DocumentStructure, Chapter, Section, ContentBlock


def _is_heading(para: Paragraph, level: int) -> bool:
    if not para.style or not para.style.name:
        return False
    name = para.style.name.lower()
    if level == 1:
        return "heading 1" in name or "heading1" in name or para.style.name == "Heading 1"
    if level == 2:
        return "heading 2" in name or "heading2" in name or para.style.name == "Heading 2"
    if level == 3:
        return "heading 3" in name or "heading3" in name or para.style.name == "Heading 3"
    return False


def _block_id(prefix: str, idx: int) -> str:
    return f"{prefix}-b{idx}"


def extract_docx(db: Session, document_id: str, file_path: str) -> DocumentStructure:
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise ValueError("Document not found")
    docx = DocxDocument(file_path)
    chapters: list[Chapter] = []
    current_chapter: Chapter | None = None
    current_section: Section | None = None
    block_idx = 0
    order_chapter = 0
    order_section = 0
    total_words = 0

    for element in docx.element.body:
        if element.tag.endswith("p"):
            para = Paragraph(element, docx)
            text = (para.text or "").strip()
            if not text:
                continue
            if _is_heading(para, 1):
                if current_chapter:
                    chapters.append(current_chapter)
                ch_id = f"ch-{order_chapter}"
                current_chapter = Chapter(chapter_id=ch_id, heading=text, content_blocks=[], order_index=order_chapter, wordCount=len(text.split()))
                current_section = None
                order_chapter += 1
                order_section = 0
                block_idx += 1
                total_words += len(text.split())
            elif _is_heading(para, 2) or _is_heading(para, 3):
                level = 2 if _is_heading(para, 2) else 3
                sec_id = f"sec-{order_chapter}-{order_section}"
                sec = Section(id=sec_id, heading=text, level=level, contentBlocks=[], orderIndex=order_section, wordCount=len(text.split()))
                if current_chapter:
                    if current_chapter.sections is None:
                        current_chapter.sections = []
                    current_chapter.sections.append(sec)
                    current_section = sec
                order_section += 1
                block_idx += 1
                total_words += len(text.split())
            else:
                bid = _block_id(document_id, block_idx)
                block = ContentBlock(id=bid, type="text", content=text, orderIndex=block_idx, wordCount=len(text.split()))
                block_idx += 1
                total_words += len(text.split())
                if current_section is not None:
                    current_section.contentBlocks.append(block)
                elif current_chapter is not None:
                    current_chapter.content_blocks.append(block)
        elif element.tag.endswith("tbl"):
            table = Table(element, docx)
            rows_text = []
            for row in table.rows:
                cells = [cell.text.strip() for cell in row.cells]
                rows_text.append(" | ".join(cells))
            text = "\n".join(rows_text)
            bid = _block_id(document_id, block_idx)
            block = ContentBlock(id=bid, type="table", content=text, orderIndex=block_idx, wordCount=len(text.split()))
            block_idx += 1
            total_words += len(text.split())
            if current_section is not None:
                current_section.contentBlocks.append(block)
            elif current_chapter is not None:
                current_chapter.content_blocks.append(block)

    if current_chapter:
        chapters.append(current_chapter)

    structure = DocumentStructure(documentId=document_id, source="docx", chapters=chapters, totalWordCount=total_words)
    ext = Extraction(document_id=document_id, source="docx", structure=structure.model_dump(), parser_version=get_settings().parser_version)
    db.add(ext)
    db.add(AuditLog(document_id=document_id, document_name=doc.name, reviewer="System", action="DOCX extraction completed", validation_result="Extracted", parser_version=get_settings().parser_version))
    db.commit()
    return structure
