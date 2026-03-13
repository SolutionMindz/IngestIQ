#!/usr/bin/env python3
"""
Run PaddleOCR on a single image and print extracted text.

Usage (from backend dir):
  python3 scripts/extract_image.py <path_to_image.png>
  e.g. python3 scripts/extract_image.py uploads/6c6102ad-5c4c-4564-beab-575cc8f445fc/screenshots/page_1.png
"""
import os
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))
os.chdir(backend_dir)

# CLI script: lower process priority so Cursor/IDE stays responsive
try:
    os.nice(10)
except Exception:
    pass

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/extract_image.py <image_path>", file=sys.stderr)
        sys.exit(1)
    image_path = Path(sys.argv[1])
    if not image_path.is_absolute():
        image_path = Path.cwd() / image_path
    if not image_path.exists():
        print(f"File not found: {image_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Extracting: {image_path}")

    # Try PaddleOCR first (app default)
    try:
        from app.services.pdf_extractor import _ocr_region_to_text
        text = _ocr_region_to_text(image_path)
    except Exception as e:
        print(f"PaddleOCR failed: {e}", file=sys.stderr)
        text = ""

    # Fallback to pytesseract if available
    if not text:
        try:
            import pytesseract
            from PIL import Image
            img = Image.open(image_path)
            text = pytesseract.image_to_string(img).strip()
        except Exception as e:
            print(f"Tesseract fallback failed: {e}", file=sys.stderr)

    if not text:
        print("(No text extracted. Install paddleocr or tesseract.)")
    else:
        print(text)

if __name__ == "__main__":
    main()
