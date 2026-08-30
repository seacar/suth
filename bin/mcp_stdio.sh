#!/usr/bin/env bash
# stdio launcher for `claude mcp add` / Claude Desktop config — resolves to
# an absolute path regardless of the MCP client's own working directory, and
# runs through `specific exec` so DATABASE_URL/S3_*/secrets get injected.
set -euo pipefail
cd "$(dirname "$0")/.."
exec specific exec cli -- .venv/bin/python -m suth.mcp_server.server
