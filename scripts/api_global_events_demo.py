#!/usr/bin/env python3
"""Verifies the /events global WebSocket sees a completion from a run started
by a completely different process (e.g. the CLI or MCP server) — proving the
"notify on any completion" GUI feature works cross-process (Postgres-polled,
not in-process pubsub). Run: .venv/bin/python scripts/api_global_events_demo.py
"""

import asyncio
import json

import websockets


async def main() -> None:
    async with websockets.connect("ws://localhost:3001/events") as ws:
        print("listening on /events for ANY session completion (from any process)...")
        raw = await ws.recv()
        print("received:", json.loads(raw))


if __name__ == "__main__":
    asyncio.run(main())
