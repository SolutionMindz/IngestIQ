#!/usr/bin/env python3
"""
Run AWS Textract on a PDF and write raw text to a file (like Sample Set/PDF20_extracted/rawText.txt).
Uses backend/.env for AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION.

Usage:
  python scripts/run_textract_raw_text.py "Sample Set/PDF1.pdf"
  python scripts/run_textract_raw_text.py "Sample Set/PDF1.pdf" -o "Sample Set/PDF1_extracted/rawText.txt"

Output default: {pdf_stem}_extracted/rawText.txt next to the PDF (or in cwd if path has no dir).
"""
import os
import sys
from pathlib import Path


def _load_backend_env() -> None:
    """Load backend/.env into os.environ so boto3 can find AWS credentials."""
    repo_root = Path(__file__).resolve().parent.parent
    env_file = repo_root / "backend" / ".env"
    if not env_file.exists():
        return
    with open(env_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip().rstrip("\r\n")
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip()
                if len(v) >= 2 and (v.startswith('"') and v.endswith('"') or v.startswith("'") and v.endswith("'")):
                    v = v[1:-1].strip()
                os.environ.setdefault(k, v)


def _get_client():
    """Build Textract client from backend/.env (supports temporary creds via AWS_SESSION_TOKEN)."""
    import boto3
    _load_backend_env()
    access = os.environ.get("AWS_ACCESS_KEY_ID")
    secret = os.environ.get("AWS_SECRET_ACCESS_KEY")
    region = os.environ.get("AWS_REGION", "us-east-1")
    if not access or not secret:
        raise RuntimeError(
            "AWS credentials not set. Add AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY to backend/.env"
        )
    kwargs = {
        "region_name": region,
        "aws_access_key_id": access,
        "aws_secret_access_key": secret,
    }
    token = os.environ.get("AWS_SESSION_TOKEN")
    if token:
        kwargs["aws_session_token"] = token
    return boto3.client("textract", **kwargs)


def extract_raw_text_from_pdf(pdf_path: str) -> str:
    """Call Textract per page (render to image) and return all LINE text joined by newlines.
    Supports single- and multi-page PDFs without S3."""
    from botocore.exceptions import ClientError

    client = _get_client()
    pdf_path = Path(pdf_path).resolve()
    if not pdf_path.is_file():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    try:
        import pymupdf
    except ImportError:
        raise RuntimeError("pymupdf is required for multi-page PDFs. Install with: pip install pymupdf") from None

    doc = pymupdf.open(pdf_path)
    all_lines = []
    try:
        for page_num in range(len(doc)):
            page = doc[page_num]
            pix = page.get_pixmap(dpi=150, alpha=False)
            img_bytes = pix.tobytes(output="png")
            try:
                response = client.detect_document_text(Document={"Bytes": img_bytes})
            except ClientError as e:
                code = e.response.get("Error", {}).get("Code", "")
                if code == "UnrecognizedClientException":
                    raise RuntimeError(
                        "AWS rejected the credentials (invalid security token).\n"
                        "Check backend/.env and set AWS_SESSION_TOKEN if using temporary credentials."
                    ) from e
                raise RuntimeError(f"Textract error on page {page_num + 1}: {e}") from e
            for block in response.get("Blocks", []):
                if block.get("BlockType") == "LINE":
                    all_lines.append(block.get("Text", ""))
    finally:
        doc.close()
    return "\n".join(all_lines)


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    pdf_path = Path(sys.argv[1])
    output_path = None
    if "-o" in sys.argv:
        i = sys.argv.index("-o")
        if i + 1 < len(sys.argv):
            output_path = Path(sys.argv[i + 1])

    if not output_path:
        # Default: {stem}_extracted/rawText.txt relative to PDF's parent
        parent = pdf_path.parent
        out_dir = parent / f"{pdf_path.stem}_extracted"
        out_dir.mkdir(parents=True, exist_ok=True)
        output_path = out_dir / "rawText.txt"

    pdf_path = Path(sys.argv[1]).resolve()
    if not pdf_path.is_file():
        print(f"Error: file not found: {pdf_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Running Textract on: {pdf_path}")
    text = extract_raw_text_from_pdf(str(pdf_path))
    output_path = Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8")
    print(f"Wrote {len(text)} chars to: {output_path}")


if __name__ == "__main__":
    main()
