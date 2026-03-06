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

# A2I tasks table — created once; safe to run if already exists
SQL_A2I_TABLE = """
CREATE TABLE IF NOT EXISTS a2i_tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id),
    page_number INTEGER NOT NULL,
    human_loop_name VARCHAR(256),
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    trigger_reason VARCHAR(512) NOT NULL DEFAULT '',
    original_textract_text TEXT,
    human_corrected_text TEXT,
    reviewer_id VARCHAR(256),
    review_timestamp TIMESTAMP,
    confidence_score FLOAT,
    s3_output_uri VARCHAR(1024),
    created_at TIMESTAMP DEFAULT NOW()
)
"""

# Cross-reference column: page_validation_log → a2i_tasks
SQL_A2I_FK = "ALTER TABLE page_validation_log ADD COLUMN IF NOT EXISTS a2i_task_id UUID REFERENCES a2i_tasks(id)"

# Human Review UI — extend a2i_tasks with assignment + diff columns
SQL_A2I_REVIEW_COLS = [
    "ALTER TABLE a2i_tasks ADD COLUMN IF NOT EXISTS assigned_to VARCHAR(256)",
    "ALTER TABLE a2i_tasks ADD COLUMN IF NOT EXISTS assigned_at TIMESTAMP",
    "ALTER TABLE a2i_tasks ADD COLUMN IF NOT EXISTS diff_items JSONB",
    "ALTER TABLE a2i_tasks ADD COLUMN IF NOT EXISTS native_text_snapshot TEXT",
]


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
        try:
            conn.execute(text(SQL_A2I_TABLE))
            print("OK: CREATE TABLE IF NOT EXISTS a2i_tasks")
        except Exception as e:
            print("SKIP (a2i_tasks):", e)
        try:
            conn.execute(text(SQL_A2I_FK))
            print("OK:", SQL_A2I_FK[:70])
        except Exception as e:
            print("SKIP (a2i_task_id):", e)
        for stmt in SQL_A2I_REVIEW_COLS:
            try:
                conn.execute(text(stmt))
                print("OK:", stmt[:70])
            except Exception as e:
                print("SKIP:", e)
    print("Done.")


if __name__ == "__main__":
    main()
