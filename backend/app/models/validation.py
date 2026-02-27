from sqlalchemy import Column, String, DateTime, ForeignKey, Float
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from app.models.base import Base


def uuid_str():
    return str(uuid.uuid4())


class ValidationItem(Base):
    __tablename__ = "validation_items"

    id = Column(String(36), primary_key=True, default=uuid_str)
    document_id = Column(String(36), ForeignKey("documents.id"), nullable=False)
    confidence = Column(Float, nullable=False)
    conflict_reason = Column(String(2048), nullable=False)
    status = Column(String(32), default="pending")  # pending | approved | rejected
    reviewer = Column(String(256), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    document = relationship("Document", back_populates="validation_items")
    comments = relationship("ValidationComment", back_populates="validation_item")


class ValidationComment(Base):
    __tablename__ = "validation_comments"

    id = Column(String(36), primary_key=True, default=uuid_str)
    validation_item_id = Column(String(36), ForeignKey("validation_items.id"), nullable=False)
    author = Column(String(256), nullable=False)
    text = Column(String(4096), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    validation_item = relationship("ValidationItem", back_populates="comments")
