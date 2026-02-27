"""
Page-level screenshot validation: screenshots, accuracy scores, and validation log.
"""
from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, Float, Text, UniqueConstraint
from datetime import datetime
import uuid
from app.models.base import Base


def uuid_str():
    return str(uuid.uuid4())


class PageScreenshot(Base):
    __tablename__ = "page_screenshots"

    id = Column(String(36), primary_key=True, default=uuid_str)
    document_id = Column(String(36), ForeignKey("documents.id"), nullable=False)
    page_number = Column(Integer, nullable=False)
    file_path = Column(String(1024), nullable=False)  # relative e.g. {doc_id}/screenshots/page_{n}.png
    checksum = Column(String(64), nullable=True)  # SHA-256 hex
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("document_id", "page_number", name="uq_page_screenshots_doc_page"),)


class PageAccuracy(Base):
    __tablename__ = "page_accuracy"

    id = Column(String(36), primary_key=True, default=uuid_str)
    document_id = Column(String(36), ForeignKey("documents.id"), nullable=False)
    page_number = Column(Integer, nullable=False)
    accuracy_pct = Column(Float, nullable=False)
    word_match_pct = Column(Float, nullable=True)
    char_match_pct = Column(Float, nullable=True)
    structural_match_pct = Column(Float, nullable=True)
    ocr_text_length = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class PageValidationLog(Base):
    __tablename__ = "page_validation_log"

    id = Column(String(36), primary_key=True, default=uuid_str)
    document_id = Column(String(36), ForeignKey("documents.id"), nullable=False)
    page_number = Column(Integer, nullable=False)
    reviewer = Column(String(256), nullable=False)
    status = Column(String(64), nullable=False)  # verified, needs_review, layout_issue, table_issue, ocr_issue
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
