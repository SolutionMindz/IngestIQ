"""
Word-level diff computation between native PDF and Textract extracted text.
Uses Python difflib.SequenceMatcher to find changed, missing, and extra words.
"""
import difflib
import uuid
import logging

logger = logging.getLogger(__name__)

MAX_DIFF_ITEMS = 200  # cap to avoid oversized JSONB


def _tokenize(text: str) -> list[str]:
    """Split text into word tokens, preserving order."""
    if not text:
        return []
    return text.split()


def compute_diff_items(native_text: str, textract_text: str) -> list[dict]:
    """
    Compare native PDF text and Textract text word by word.

    Returns a list of DiffItem dicts (JSON-serialisable) with up to MAX_DIFF_ITEMS entries:
      - changed_word  : word exists in both sides but with different value
      - missing_word  : word in native but absent from Textract
      - extra_word    : word in Textract but absent from native

    Each item:
      {
        "id": str (UUID),
        "diff_type": "changed_word" | "missing_word" | "extra_word",
        "native_value": str,
        "textract_value": str,
        "line_index": int   # position in the native word list
      }
    """
    native_words = _tokenize(native_text)
    textract_words = _tokenize(textract_text)

    if not native_words and not textract_words:
        return []

    matcher = difflib.SequenceMatcher(None, native_words, textract_words, autojunk=False)
    items: list[dict] = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue

        if tag == "replace":
            # Pair up words that were replaced; emit the rest as missing/extra
            native_chunk = native_words[i1:i2]
            textract_chunk = textract_words[j1:j2]
            for k, (nw, tw) in enumerate(zip(native_chunk, textract_chunk)):
                items.append({
                    "id": str(uuid.uuid4()),
                    "diff_type": "changed_word",
                    "native_value": nw,
                    "textract_value": tw,
                    "line_index": i1 + k,
                })
            # Remaining native words not matched by textract → missing
            for k in range(len(textract_chunk), len(native_chunk)):
                items.append({
                    "id": str(uuid.uuid4()),
                    "diff_type": "missing_word",
                    "native_value": native_chunk[k],
                    "textract_value": "",
                    "line_index": i1 + k,
                })
            # Remaining textract words not matched by native → extra
            for k in range(len(native_chunk), len(textract_chunk)):
                items.append({
                    "id": str(uuid.uuid4()),
                    "diff_type": "extra_word",
                    "native_value": "",
                    "textract_value": textract_chunk[k],
                    "line_index": i1,
                })

        elif tag == "delete":
            # Words present in native but missing from Textract
            for k, nw in enumerate(native_words[i1:i2]):
                items.append({
                    "id": str(uuid.uuid4()),
                    "diff_type": "missing_word",
                    "native_value": nw,
                    "textract_value": "",
                    "line_index": i1 + k,
                })

        elif tag == "insert":
            # Words present in Textract but absent from native
            for tw in textract_words[j1:j2]:
                items.append({
                    "id": str(uuid.uuid4()),
                    "diff_type": "extra_word",
                    "native_value": "",
                    "textract_value": tw,
                    "line_index": i1,
                })

        if len(items) >= MAX_DIFF_ITEMS:
            logger.info("diff_service: truncated diff items at %d", MAX_DIFF_ITEMS)
            break

    return items[:MAX_DIFF_ITEMS]
