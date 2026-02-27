#!/usr/bin/env python3
"""
Quick test: verify AWS credentials and Textract API connectivity.
Uses backend/.env for AWS_* variables. Exits 0 if both work.
"""
import os
import sys
from pathlib import Path

# Load backend/.env into os.environ so boto3 can use it
backend_dir = Path(__file__).resolve().parent.parent
env_file = backend_dir / ".env"
if env_file.exists():
    with open(env_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip().rstrip("\r\n")
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip()
                if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
                    v = v[1:-1]
                os.environ.setdefault(k, v)

def main():
    import boto3
    from botocore.exceptions import ClientError

    region = os.environ.get("AWS_REGION", "us-east-1")
    access = os.environ.get("AWS_ACCESS_KEY_ID")
    secret = os.environ.get("AWS_SECRET_ACCESS_KEY")
    token = os.environ.get("AWS_SESSION_TOKEN")

    if not access or not secret:
        print("FAIL: AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY must be set in backend/.env")
        sys.exit(1)

    kwargs = {
        "region_name": region,
        "aws_access_key_id": access,
        "aws_secret_access_key": secret,
    }
    if token:
        kwargs["aws_session_token"] = token

    # 1) Verify credentials via STS
    try:
        sts = boto3.client("sts", **kwargs)
        identity = sts.get_caller_identity()
        print(f"OK (STS): identity = {identity.get('Arn', '?')}")
    except ClientError as e:
        print(f"FAIL (STS): {e}")
        sys.exit(1)

    # 2) Verify Textract endpoint
    try:
        client = boto3.client("textract", **kwargs)
        # Minimal valid PNG (1x1 pixel) - Textract may reject as too small, but we reach the API
        import io
        try:
            from PIL import Image
            buf = io.BytesIO()
            img = Image.new("RGB", (100, 100), (255, 255, 255))
            img.save(buf, format="PNG")
            img_bytes = buf.getvalue()
        except Exception:
            # Fallback: create minimal PNG bytes (100x100 white)
            img_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50  # minimal header; may fail
        try:
            resp = client.detect_document_text(Document={"Bytes": img_bytes})
            blocks = resp.get("Blocks", [])
            print(f"OK (Textract): DetectDocumentText returned {len(blocks)} block(s)")
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            if code == "UnsupportedDocumentException":
                print("OK (Textract): API is reachable (document rejected as unsupported, which is expected for minimal image)")
            else:
                print(f"FAIL (Textract): {e}")
                sys.exit(1)
    except ClientError as e:
        print(f"FAIL (Textract): {e}")
        sys.exit(1)

    print("Textract connection test passed.")
    sys.exit(0)

if __name__ == "__main__":
    main()
