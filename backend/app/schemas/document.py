from datetime import datetime
from pydantic import BaseModel, Field


class DocumentSummary(BaseModel):
    documentId: str
    name: str
    uploadStatus: str  # idle | uploading | uploaded | failed
    processingStage: str  # pending | extracting | comparing | done | error
    validationStatus: str  # pending | structurally_verified | integrity_conflict | training_approved
    version: str
    hash: str
    createdAt: str
    author: str | None = None
    fileSizeBytes: int | None = None
    pageCount: int | None = None
    errorType: str | None = None
    errorMessage: str | None = None


class DocumentVersion(BaseModel):
    documentId: str
    version: str
    name: str
    createdAt: str
