#!/usr/bin/env bash
# One command to bring up everything suth needs for local dev: applies
# pending migrations, syncs the persona library into Postgres, then hands
# off to `specific dev` (Postgres + storage + the api and web services).
#
# Run via: ./start.sh
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -x .venv/bin/python ]; then
  echo "No .venv found — set it up first:" >&2
  echo "  uv venv .venv --python 3.11" >&2
  echo "  uv pip install -e \".[dev]\" --python .venv/bin/python" >&2
  echo "  .venv/bin/playwright install chromium" >&2
  exit 1
fi

echo "==> applying migrations"
specific exec cli -- .venv/bin/python scripts/migrate.py

echo "==> syncing persona library"
specific exec cli -- .venv/bin/python scripts/sync_personas.py

echo "==> starting Postgres, storage, api, and web (specific dev)"
exec specific dev
