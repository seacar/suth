#!/usr/bin/env bash
# CI-less local test runner. Runs the DB smoke test too if DATABASE_URL is
# already in the environment (e.g. invoked via `specific exec cli -- ...`).
set -euo pipefail
cd "$(dirname "$0")/.."
.venv/bin/python -m pytest "$@"
