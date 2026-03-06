#!/usr/bin/env python3
"""
Truncate all application tables in the database. Uses RESTART IDENTITY CASCADE so
sequences reset and foreign-key references are handled.

Uses DATABASE_URL from backend/.env (default: postgresql://sanjeev@127.0.0.1/Textract).
If truncate hangs, stop the backend (and any other process using the DB) and run again.

Run from backend dir:
  python3 scripts/truncate_all_tables.py
"""
import os
import sys

# Ensure app is importable and .env is loaded (run from backend dir)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.models.base import get_engine, Base
from app.models import (  # noqa: F401 - load all models so tables are registered
    document,
    extraction,
    comparison,
    validation,
    audit,
    page_validation,
    a2i,
)


def main():
    from app.config import get_settings
    settings = get_settings()
    url = settings.database_url or ""
    print("Database:", url.split("?")[0])
    engine = get_engine()
    table_names = list(Base.metadata.tables.keys())
    if not table_names:
        print("No tables found in metadata.")
        return
    print("Tables to truncate:", table_names)
    with engine.connect() as conn:
        quoted = ", ".join(f'"{t}"' for t in table_names)
        conn.execute(text(f"TRUNCATE TABLE {quoted} RESTART IDENTITY CASCADE"))
        conn.commit()
    print("Done. All tables truncated.")


if __name__ == "__main__":
    main()
