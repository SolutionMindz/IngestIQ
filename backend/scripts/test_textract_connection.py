#!/usr/bin/env python3
"""
Quick test: verify AWS Textract connection using credentials from backend/.env.
Exits 0 if detect_document_text succeeds (credentials and region are valid).
"""
import io
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))


def main():
    try:
        from app.config import get_settings
        import boto3
        from PIL import Image
    except ImportError as e:
        print(f"FAIL: missing dependency: {e}")
        sys.exit(1)

    settings = get_settings()
    if not settings.aws_access_key_id or not settings.aws_secret_access_key:
        print("FAIL: AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY must be set in backend/.env")
        sys.exit(1)

    kwargs = {
        "region_name": settings.aws_region,
        "aws_access_key_id": settings.aws_access_key_id,
        "aws_secret_access_key": settings.aws_secret_access_key,
    }
    if settings.aws_session_token:
        kwargs["aws_session_token"] = settings.aws_session_token

    try:
        client = boto3.client("textract", **kwargs)
    except Exception as e:
        print(f"FAIL: could not create Textract client: {e}")
        sys.exit(1)

    # Minimal PNG (small white image) so we only test API/credential reach
    buf = io.BytesIO()
    img = Image.new("RGB", (100, 100), color="white")
    img.save(buf, format="PNG")
    image_bytes = buf.getvalue()

    try:
        response = client.detect_document_text(Document={"Bytes": image_bytes})
        blocks = response.get("Blocks", [])
        print(f"OK: Textract connection successful (region={settings.aws_region})")
        print(f"    detect_document_text returned {len(blocks)} blocks (expected 0 for blank image).")
    except client.exceptions.InvalidParameterException as e:
        # Some regions/settings may reject tiny images; we still reached AWS
        print(f"OK: Textract connection successful (API responded; parameter warning: {e})")
    except Exception as e:
        print(f"FAIL: Textract API call failed: {e}")
        sys.exit(1)

    print("AWS Textract connection test passed.")
    sys.exit(0)


if __name__ == "__main__":
    main()
