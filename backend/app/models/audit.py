from sqlalchemy import Column, String, DateTime, ForeignKey, JSON
from datetime import datetime
import uuid
from app.models.base import Base


def uuid_str():
    return str(uuid.uuid4())


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(String(36), primary_key=True, default=uuid_str)
    document_id = Column(String(36), ForeignKey("documents.id"), nullable=False)
    document_name = Column(String(512), nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    parser_version = Column(String(32), nullable=True)
    validation_result = Column(String(256), nullable=True)
    reviewer = Column(String(256), nullable=False)
    action = Column(String(256), nullable=False)
    comparison_id = Column(String(36), ForeignKey("comparisons.id"), nullable=True)  # link to comparison report
    metadata_ = Column("metadata", JSON, nullable=True)  # job_id, confidence summary, etc.
