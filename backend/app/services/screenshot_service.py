"""
Generate per-page PNG screenshots from PDFs at configurable DPI.
Stored under upload_dir/{document_id}/screenshots/page_{n}.png with DB mapping and checksum.
"""
import hashlib
import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.page_validation import PageScreenshot
from app.config import get_settings

logger = logging.getLogger(__name__)


def generate_screenshots(
    db: Session, document_id: str, pdf_path: str, upload_dir: Path
) -> list[tuple[int, str, str]]:
    """
    Render each PDF page at configured DPI (default 150), save as PNG, compute checksum, insert into page_screenshots.
    Returns [(page_number, relative_path, checksum), ...].
    Raises on failure (caller should set document status screenshot_failed).
    """
    try:
        import pymupdf
    except ImportError:
        raise RuntimeError("pymupdf is required for screenshot generation")

    dpi = get_settings().screenshot_dpi
    doc = pymupdf.open(pdf_path)
    try:
        screenshot_dir = upload_dir / document_id / "screenshots"
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        result: list[tuple[int, str, str]] = []
        scale = dpi / 72.0
        matrix = pymupdf.Matrix(scale, scale)

        for page_num in range(len(doc)):
            page = doc[page_num]
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            rel_path = f"{document_id}/screenshots/page_{page_num + 1}.png"
            out_path = upload_dir / rel_path
            png_bytes = pix.tobytes(output="png")
            del pix  # free pixmap buffer immediately
            out_path.write_bytes(png_bytes)
            checksum = hashlib.sha256(png_bytes).hexdigest()
            del png_bytes  # free encoded bytes after write + hash
            db.add(
                PageScreenshot(
                    document_id=document_id,
                    page_number=page_num + 1,
                    file_path=rel_path,
                    checksum=checksum,
                )
            )
            result.append((page_num + 1, rel_path, checksum))
        db.commit()
        logger.info("Generated %d screenshots for document %s", len(result), document_id)
        return result
    finally:
        doc.close()
