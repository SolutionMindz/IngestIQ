"""
Explicit validation rules (Section 7).
Document can move to APPROVED only when comparison checks pass or via logged manual override.
"""
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.comparison import Comparison


# Requirement status names (Section 7) for display/API; internal DB values unchanged
EXTRACTION_PENDING = "extraction_pending"
STRUCTURAL_MISMATCH = "structural_mismatch"
CONTENT_MISMATCH = "content_mismatch"
VALIDATION_PENDING = "validation_pending"
APPROVED = "approved"
REJECTED = "rejected"

# Map internal validation_status to requirement enum
INTERNAL_TO_REQUIREMENT = {
    "pending": VALIDATION_PENDING,
    "structurally_verified": VALIDATION_PENDING,  # passed comparison; awaiting approval
    "integrity_conflict": STRUCTURAL_MISMATCH,
    "training_approved": APPROVED,
    "rejected": REJECTED,
    "screenshot_failed": "screenshot_failed",
    "validation_failed": "validation_failed",
}


def requirement_status(internal_status: str | None) -> str:
    """Return requirement-aligned status for display."""
    if not internal_status:
        return VALIDATION_PENDING
    return INTERNAL_TO_REQUIREMENT.get(internal_status, internal_status)


def can_approve(doc: Document, db: Session, require_comment_on_override: bool = True) -> tuple[bool, str]:
    """
    Formal validation step: document may move to APPROVED only if
    - comparison passed (structurally_verified, no mismatches), or
    - manual override with logged approval (comment required when there was a conflict).
    Returns (allowed, reason).
    """
    if not doc:
        return False, "Document not found"
    if doc.validation_status in ("screenshot_failed", "validation_failed"):
        return False, "Screenshot or page accuracy check failed"
    # If there was a structural mismatch, treat as manual override
    if doc.validation_status == "integrity_conflict":
        return True, "manual_override"  # Caller must require comment and log
    if doc.validation_status == "structurally_verified":
        return True, "passed"
    if doc.validation_status == "pending":
        return False, "Comparison not yet run or document not verified"
    if doc.validation_status == "training_approved":
        return True, "already_approved"
    return False, f"Unknown status {doc.validation_status}"


def is_manual_override_approval(doc: Document) -> bool:
    """True if approving this document counts as manual override (had conflict)."""
    return doc is not None and doc.validation_status == "integrity_conflict"
