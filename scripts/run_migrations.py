#!/usr/bin/env python
"""
Simple migration runner for Postgres that executes all *.sql files in db/migrations in lexical order.
Usage:
  DB_URL=postgres://... python scripts/run_migrations.py
"""

from __future__ import annotations
import os
import sys
from pathlib import Path


def main():
    db_url = os.getenv("DB_URL")
    if not db_url or not (db_url.startswith("postgres://") or db_url.startswith("postgresql://")):
        print("DB_URL must be set to a Postgres DSN", file=sys.stderr)
        sys.exit(2)
    try:
        import psycopg
    except Exception:
        print("psycopg not installed. pip install 'psycopg[binary]'", file=sys.stderr)
        sys.exit(3)
    mig_dir = Path("db/migrations")
    files = sorted([p for p in mig_dir.glob("*.sql") if p.is_file()])
    if not files:
        print("No migrations found. Nothing to do.")
        return
    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            for f in files:
                print(f"Applying {f} ...")
                cur.execute(f.read_text())
    print("Migrations applied.")


if __name__ == "__main__":
    main()
