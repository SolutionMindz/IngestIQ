#!/usr/bin/env python3
"""
Test structured extraction on page 1 only.
Prints each detected block with its type, content preview, and bbox.

Usage (from backend dir):
  python3 scripts/test_page1_structure.py <doc_uuid>
  python3 scripts/test_page1_structure.py cbe1610d-fd37-4a6b-a753-c5dccea593cc
"""
import os
import sys
import json
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))
os.chdir(backend_dir)

try:
    os.nice(10)
except Exception:
    pass

os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("MKL_NUM_THREADS", "4")
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

def main():
    doc_id = sys.argv[1] if len(sys.argv) > 1 else "cbe1610d-fd37-4a6b-a753-c5dccea593cc"
    image_path = Path(f"uploads/{doc_id}/screenshots/page_1.png")
    if not image_path.exists():
        print(f"Screenshot not found: {image_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Running structured extraction on: {image_path}\n")

    from app.services.pdf_extractor import _get_paddle, _parse_paddle_result, _classify_ocr_lines_to_blocks

    ocr = _get_paddle()
    result = ocr.predict(str(image_path))
    lines = _parse_paddle_result(result)
    print(f"Raw OCR lines: {len(lines)}\n")

    blocks = _classify_ocr_lines_to_blocks(lines, doc_id, 1)

    print(f"Structured blocks: {len(blocks)}\n")
    print("=" * 70)

    output = []
    for b in blocks:
        preview = b.content[:120].replace("\n", " ")
        bbox_str = ""
        if b.bbox:
            bbox_str = f"  bbox=(L:{b.bbox.left:.0f} T:{b.bbox.top:.0f} W:{b.bbox.width:.0f} H:{b.bbox.height:.0f})"
        print(f"[{b.type:12s}] {preview}")
        if bbox_str:
            print(f"             {bbox_str}")
        print()
        output.append({
            "type": b.type,
            "content": b.content,
            "wordCount": b.wordCount,
            "bbox": {"left": b.bbox.left, "top": b.bbox.top, "width": b.bbox.width, "height": b.bbox.height} if b.bbox else None,
        })

    print("=" * 70)
    print(f"\nJSON output (page 1, {len(blocks)} blocks):")
    print(json.dumps({"page": 1, "elements": output}, indent=2))

if __name__ == "__main__":
    main()
