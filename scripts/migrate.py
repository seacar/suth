#!/usr/bin/env python3
"""Apply migrations/*.sql, in filename order, against DATABASE_URL.

Idempotent: statements use CREATE TABLE IF NOT EXISTS, so re-running is safe.
Run via: specific exec cli -- .venv/bin/python scripts/migrate.py
"""

import os
import sys
from pathlib import Path

import psycopg

MIGRATIONS_DIR = Path(__file__).parent.parent / "migrations"


def main() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL is not set — run this via `specific exec cli -- ...`", file=sys.stderr)
        sys.exit(1)

    with psycopg.connect(database_url, autocommit=True) as conn:
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            print(f"applying {path.name}")
            conn.execute(path.read_text())
    print("migrations applied")


if __name__ == "__main__":
    main()
