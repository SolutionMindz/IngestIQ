#!/usr/bin/env python3
"""
Quick test: verify pytesseract and Tesseract OCR are available.
Exits 0 if OCR can be run (e.g. for PDF extraction). Install: brew install tesseract / apt install tesseract-ocr
"""
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))


def main():
    try:
        import pytesseract
        from PIL import Image
    except ImportError as e:
        print(f"FAIL: pytesseract or PIL not installed: {e}")
        print("  pip install pytesseract Pillow")
        sys.exit(1)
    try:
        # Minimal 1x1 image; get_version or image_to_string will fail if Tesseract binary missing
        ver = pytesseract.get_tesseract_version()
        print(f"OK: Tesseract version {ver}")
    except Exception as e:
        print(f"FAIL: Tesseract not found or not runnable: {e}")
        print("  macOS: brew install tesseract")
        print("  Ubuntu: sudo apt-get install tesseract-ocr")
        sys.exit(1)
    img = Image.new("RGB", (200, 50), color="white")
    try:
        text = pytesseract.image_to_string(img)
        print("OK: pytesseract.image_to_string ran successfully")
    except Exception as e:
        print(f"FAIL: image_to_string failed: {e}")
        sys.exit(1)
    print("OCR connection test passed.")
    sys.exit(0)


if __name__ == "__main__":
    main()
