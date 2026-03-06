"""
A2I (Amazon Augmented AI) task tracking model.
One row per page that has been submitted for human review.
"""
from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, Float, Text, JSON
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid
from app.models.base import Base


class A2ITask(Base):
    __tablename__ = "a2i_tasks"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id = Column(UUID(as_uuid=False), ForeignKey("documents.id"), nullable=False)
    page_number = Column(Integer, nullable=False)

    # AWS A2I human loop identifier (null if A2I not configured — manual review mode)
    human_loop_name = Column(String(256), nullable=True)

    # pending / assigned / in_review / under_review / completed / auto_verified / failed
    status = Column(String(32), nullable=False, default="pending")

    # Why this page was flagged (e.g. "accuracy_pct=94.2, textract_conf=91.0")
    trigger_reason = Column(String(512), nullable=False, default="")

    # Textract text as it existed when the task was created
    original_textract_text = Column(Text, nullable=True)

    # Corrected text submitted by the human reviewer
    human_corrected_text = Column(Text, nullable=True)

    # Reviewer info (from A2I worker or manual reviewer)
    reviewer_id = Column(String(256), nullable=True)
    review_timestamp = Column(DateTime, nullable=True)

    # Textract average confidence for this page at trigger time
    confidence_score = Column(Float, nullable=True)

    # S3 URI of the A2I output JSON (null in manual review mode)
    s3_output_uri = Column(String(1024), nullable=True)

    # Assignment tracking
    assigned_to = Column(String(256), nullable=True)
    assigned_at = Column(DateTime, nullable=True)

    # Word-level diff items between native PDF and Textract (list of DiffItem dicts)
    diff_items = Column(JSON, nullable=True)

    # Native PDF text snapshot at trigger time (for display in review UI)
    native_text_snapshot = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
