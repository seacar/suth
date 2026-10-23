#!/usr/bin/env python3
"""Verifies the /events global WebSocket sees a completion from a run started
by a completely different process (e.g. the CLI or MCP server) — proving the
"notify on any completion" GUI feature works cross-process (Postgres-polled,
not in-process pubsub).
Run: specific exec cli -- .venv/bin/python scripts/api_global_events_demo.py
"""

import asyncio
import json
import os

import websockets


async def main() -> None:
    token = os.environ.get("SUTH_API_TOKEN", "")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with websockets.connect("ws://localhost:3001/events", additional_headers=headers) as ws:
        print("listening on /events for ANY session completion (from any process)...")
        raw = await ws.recv()
        print("received:", json.loads(raw))


if __name__ == "__main__":
    asyncio.run(main())
