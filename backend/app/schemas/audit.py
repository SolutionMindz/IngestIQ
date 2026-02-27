from pydantic import BaseModel


class AuditLogEntry(BaseModel):
    id: str
    documentId: str
    documentName: str | None = None
    timestamp: str
    parserVersion: str
    validationResult: str
    reviewer: str
    action: str
