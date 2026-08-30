#!/usr/bin/env python3
"""Throwaway connection-check script — Phase 0 exit criterion.

Confirms `specific dev`'s injected DATABASE_URL actually works end to end.
Run via: specific exec cli -- .venv/bin/python scripts/check_db.py
"""

import os
import sys

import psycopg


def main() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL is not set — run this via `specific exec cli -- ...`", file=sys.stderr)
        sys.exit(1)

    with psycopg.connect(database_url) as conn:
        result = conn.execute("SELECT 1").fetchone()
        assert result == (1,), f"unexpected result: {result}"

    print("OK: connected to Postgres and SELECT 1 round-tripped")


if __name__ == "__main__":
    main()
