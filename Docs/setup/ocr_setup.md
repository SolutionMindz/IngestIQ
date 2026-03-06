# OCR setup (pytesseract / Tesseract)

The backend uses **pytesseract** (Tesseract OCR) for the second PDF extraction (`source=ocr`), so you can compare native PDF structure with OCR-extracted structure. No AWS or cloud credentials are required.

## Install Tesseract

- **macOS (Homebrew):** `brew install tesseract`
- **Ubuntu/Debian:** `sudo apt-get install tesseract-ocr`
- **Windows:** [Tesseract at UB-Mannheim](https://github.com/UB-Mannheim/tesseract/wiki)

The Python package `pytesseract` is in `backend/requirements.txt`; it invokes the system Tesseract binary. If Tesseract is not installed, OCR extraction may still run but produce "(no text)" for pages when the binary is missing.

## Verify

From the backend directory:

```bash
python scripts/test_ocr_connection.py
```

Exits 0 if Tesseract is installed and callable.
