"""
Tests for PDF extraction: full-page and word/block-level structure.
Asserts: page count and word count match, no single "Ch 1: PDF (native extraction)" block.
"""
import tempfile
import unittest
from pathlib import Path


def _make_multipage_pdf(path: str, num_pages: int = 3) -> None:
    """Create a minimal multi-page PDF with text using PyMuPDF."""
    import pymupdf
    doc = pymupdf.open()
    for i in range(num_pages):
        page = doc.new_page()
        page.insert_text((50, 50), f"Page {i + 1} content. Line one and line two.")
    doc.save(path)
    doc.close()


def _make_blank_page_pdf(path: str) -> None:
    """Create a 1-page PDF with no text (e.g. image-only cover)."""
    import pymupdf
    doc = pymupdf.open()
    doc.new_page()  # blank page
    doc.save(path)
    doc.close()


class TestPdfExtraction(unittest.TestCase):
    """Multi-page PDF extraction (native PyMuPDF and OCR structure)."""

    def test_extract_pdf_native_structured_multipage(self):
        """Multi-page PDF yields one chapter per page, no single 'PDF (native extraction)' block."""
        from app.services.pdf_extractor import _extract_pdf_native_structured

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            tmp_path = f.name
        try:
            _make_multipage_pdf(tmp_path, num_pages=3)
            document_id = "test-doc-id"
            chapters, page_count, total_word_count = _extract_pdf_native_structured(tmp_path, document_id)

            self.assertEqual(page_count, 3, "expected 3 pages")
            self.assertEqual(len(chapters), 3, "expected 3 chapters (one per page)")
            self.assertGreater(total_word_count, 0, "expected some words")

            for i, ch in enumerate(chapters):
                self.assertEqual(ch.heading, f"Page {i + 1}", f"chapter heading should be 'Page {i + 1}'")
                self.assertEqual(ch.chapter_id, f"ch-p{i + 1}")
                self.assertGreaterEqual(len(ch.content_blocks), 1, f"page {i + 1} should have at least one content block")

            headings = [ch.heading for ch in chapters]
            self.assertNotIn("PDF (native extraction)", headings)

            first_text = " ".join(b.content for b in chapters[0].content_blocks)
            self.assertIn("Page 1", first_text)
            self.assertIn("content", first_text)
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_extract_pdf_native_structured_blocks_have_bbox(self):
        """Content blocks from native PDF have optional bbox for chip layout."""
        from app.services.pdf_extractor import _extract_pdf_native_structured

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            tmp_path = f.name
        try:
            _make_multipage_pdf(tmp_path, num_pages=1)
            chapters, _, _ = _extract_pdf_native_structured(tmp_path, "id")
            self.assertEqual(len(chapters), 1)
            self.assertGreaterEqual(len(chapters[0].content_blocks), 1)
            first_block = chapters[0].content_blocks[0]
            self.assertIsNotNone(first_block.bbox)
            self.assertGreaterEqual(first_block.bbox.width, 0)
            self.assertGreaterEqual(first_block.bbox.height, 0)
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_native_ocr_fallback_for_image_only_page(self):
        """When page 1 has no text and a screenshot exists, native extraction uses OCR from screenshot."""
        from app.services.pdf_extractor import _extract_pdf_native_structured

        try:
            from PIL import Image, ImageDraw, ImageFont
            import pytesseract
        except ImportError:
            self.skipTest("pytesseract and PIL required for OCR fallback test")
        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = Path(tmpdir) / "cover.pdf"
            _make_blank_page_pdf(str(pdf_path))
            doc_id = "ocr-test-doc"
            screenshot_dir = Path(tmpdir) / doc_id / "screenshots"
            screenshot_dir.mkdir(parents=True)
            # Create a small image with text so Tesseract can extract it
            img = Image.new("RGB", (400, 80), color="white")
            draw = ImageDraw.Draw(img)
            try:
                font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 24)
            except Exception:
                font = ImageFont.load_default()
            draw.text((20, 20), "EXPERT INSIGHT", fill="black", font=font)
            img.save(screenshot_dir / "page_1.png")
            upload_path = Path(tmpdir)
            chapters, page_count, total_word_count = _extract_pdf_native_structured(
                str(pdf_path), doc_id, upload_path=upload_path
            )
            self.assertEqual(page_count, 1)
            self.assertEqual(len(chapters), 1)
            self.assertEqual(chapters[0].heading, "Page 1")
            self.assertGreaterEqual(
                len(chapters[0].content_blocks),
                1,
                "OCR fallback should add content for image-only page 1",
            )
            first_text = " ".join(b.content for b in chapters[0].content_blocks)
            self.assertIn("EXPERT", first_text.upper(), "OCR should extract text from screenshot")


if __name__ == "__main__":
    unittest.main()
