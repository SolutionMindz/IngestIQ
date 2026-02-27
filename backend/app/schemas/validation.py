from pydantic import BaseModel
from typing import Literal


class ValidationComment(BaseModel):
    id: str
    author: str
    text: str
    createdAt: str


class ValidationItem(BaseModel):
    id: str
    documentId: str
    documentName: str
    confidence: float
    conflictReason: str
    reviewer: str | None = None
    status: Literal["pending", "approved", "rejected"]
    comments: list[ValidationComment]
    createdAt: str
