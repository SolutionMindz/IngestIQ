from pydantic import BaseModel


class A2ITaskSummary(BaseModel):
    id: str
    documentId: str
    pageNumber: int
    humanLoopName: str | None
    status: str
    triggerReason: str
    reviewerId: str | None
    reviewTimestamp: str | None
    correctionApplied: bool
    confidenceScore: float | None
    s3OutputUri: str | None
    assignedTo: str | None
    assignedAt: str | None
    createdAt: str


class DiffItemSchema(BaseModel):
    id: str
    diffType: str        # changed_word | missing_word | extra_word | table_mismatch
    nativeValue: str
    textractValue: str
    lineIndex: int


class A2ITaskDetail(A2ITaskSummary):
    """Full task detail including diff items and text snapshots for the review UI."""
    diffItems: list[DiffItemSchema]
    nativeTextSnapshot: str | None
    originalTextractText: str | None


class A2ICompleteBody(BaseModel):
    correctedText: str
    reviewerId: str
    comment: str | None = None


class AssignTaskBody(BaseModel):
    reviewerId: str


class ReviewerStatsResponse(BaseModel):
    reviewerId: str
    totalAssigned: int
    completed: int
    pending: int
    correctionsApplied: int
    acceptanceRate: float   # percentage 0-100
