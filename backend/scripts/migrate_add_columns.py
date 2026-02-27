#!/usr/bin/env python3
"""Add new columns from PDF Ingestion Verification System plan. Safe to run multiple times."""
import sys
from pathlib import Path

# Run from backend/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from app.models.base import get_engine


SQL = [
    "ALTER TABLE documents ADD COLUMN IF NOT EXISTS file_size_bytes BIGINT",
    "ALTER TABLE documents ADD COLUMN IF NOT EXISTS page_count INTEGER",
    "ALTER TABLE documents ADD COLUMN IF NOT EXISTS error_type VARCHAR(64)",
    "ALTER TABLE documents ADD COLUMN IF NOT EXISTS error_message VARCHAR(2048)",
    "ALTER TABLE audit_log ADD COLUMN IF NOT EXISTS metadata JSONB",
    "ALTER TABLE extractions ADD COLUMN IF NOT EXISTS textract_job_id VARCHAR(256)",
    "ALTER TABLE extractions ADD COLUMN IF NOT EXISTS metadata JSONB",
]
# comparison_id references comparisons(id) - add after metadata so comparisons exists
SQL_FK = "ALTER TABLE audit_log ADD COLUMN IF NOT EXISTS comparison_id UUID REFERENCES comparisons(id)"


def main():
    engine = get_engine()
    with engine.begin() as conn:
        for stmt in SQL:
            try:
                conn.execute(text(stmt))
                print("OK:", stmt[:70])
            except Exception as e:
                print("SKIP:", e)
        try:
            conn.execute(text(SQL_FK))
            print("OK:", SQL_FK[:70])
        except Exception as e:
            print("SKIP (comparison_id):", e)
    print("Done.")


if __name__ == "__main__":
    main()
