from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, BigInteger
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from app.models.base import Base


def uuid_str():
    return str(uuid.uuid4())


class Document(Base):
    __tablename__ = "documents"

    id = Column(String(36), primary_key=True, default=uuid_str)
    name = Column(String(512), nullable=False)
    file_path = Column(String(1024), nullable=False)
    file_hash_sha256 = Column(String(64), nullable=True)
    file_size_bytes = Column(BigInteger, nullable=True)  # file size in bytes (Section 4.1)
    page_count = Column(Integer, nullable=True)  # total page count after extraction or from metadata
    upload_status = Column(String(32), default="uploaded")
    processing_stage = Column(String(32), default="pending")
    validation_status = Column(String(32), default="pending")
    error_type = Column(String(64), nullable=True)  # extraction_failure | textract_failure | api_timeout | structural_mismatch | content_mismatch
    error_message = Column(String(2048), nullable=True)
    version = Column(String(32), default="1.0")
    author = Column(String(256), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    versions = relationship("DocumentVersion", back_populates="document")
    extractions = relationship("Extraction", back_populates="document")
    comparisons = relationship("Comparison", back_populates="document")
    validation_items = relationship("ValidationItem", back_populates="document")


class DocumentVersion(Base):
    __tablename__ = "document_versions"

    id = Column(String(36), primary_key=True, default=uuid_str)
    document_id = Column(String(36), ForeignKey("documents.id"), nullable=False)
    version = Column(String(32), nullable=False)
    name = Column(String(512), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    document = relationship("Document", back_populates="versions")
