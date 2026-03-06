from sqlalchemy import Column, String, DateTime, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from app.models.base import Base


def uuid_str():
    return str(uuid.uuid4())


class Extraction(Base):
    __tablename__ = "extractions"

    id = Column(UUID(as_uuid=False), primary_key=True, default=uuid_str)
    document_id = Column(UUID(as_uuid=False), ForeignKey("documents.id"), nullable=False)
    source = Column(String(16), nullable=False)  # docx | pdf | ocr | textract
    structure = Column(JSON, nullable=False)
    parser_version = Column(String(32), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    textract_job_id = Column(String(256), nullable=True)
    metadata_ = Column("metadata", JSON, nullable=True)

    document = relationship("Document", back_populates="extractions")
