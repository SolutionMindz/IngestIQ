"""
Page-level screenshot validation: screenshots, accuracy scores, and validation log.
"""
from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, Float, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid
from app.models.base import Base


def uuid_str():
    return str(uuid.uuid4())


class PageScreenshot(Base):
    __tablename__ = "page_screenshots"

    id = Column(UUID(as_uuid=False), primary_key=True, default=uuid_str)
    document_id = Column(UUID(as_uuid=False), ForeignKey("documents.id"), nullable=False)
    page_number = Column(Integer, nullable=False)
    file_path = Column(String(1024), nullable=False)
    checksum = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("document_id", "page_number", name="uq_page_screenshots_doc_page"),)


class PageAccuracy(Base):
    __tablename__ = "page_accuracy"

    id = Column(UUID(as_uuid=False), primary_key=True, default=uuid_str)
    document_id = Column(UUID(as_uuid=False), ForeignKey("documents.id"), nullable=False)
    page_number = Column(Integer, nullable=False)
    accuracy_pct = Column(Float, nullable=False)
    word_match_pct = Column(Float, nullable=True)
    char_match_pct = Column(Float, nullable=True)
    structural_match_pct = Column(Float, nullable=True)
    ocr_text_length = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class PageValidationLog(Base):
    __tablename__ = "page_validation_log"

    id = Column(UUID(as_uuid=False), primary_key=True, default=uuid_str)
    document_id = Column(UUID(as_uuid=False), ForeignKey("documents.id"), nullable=False)
    page_number = Column(Integer, nullable=False)
    reviewer = Column(String(256), nullable=False)
    status = Column(String(64), nullable=False)
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
