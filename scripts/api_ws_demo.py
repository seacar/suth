#!/usr/bin/env python3
"""Live-verification script for the Local Control API's WebSocket streaming
and step-through gating (Phase 5). Not part of the pytest suite — this
exercises real HTTP + WebSocket I/O against a running `specific dev` api
service, same as the macOS GUI would.

Run: specific exec cli -- .venv/bin/python scripts/api_ws_demo.py [--step]
(`specific exec` injects SUTH_API_TOKEN, which the API requires.)
"""

import asyncio
import os
import sys

import httpx
import websockets

API = "http://localhost:3001"
WS = "ws://localhost:3001"
TOKEN = os.environ.get("SUTH_API_TOKEN", "")
HEADERS = {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}


async def main() -> None:
    step_through = "--step" in sys.argv
    async with httpx.AsyncClient(headers=HEADERS) as client:
        resp = await client.post(
            f"{API}/runs",
            json={
                "project_id": "suth-test-app",
                "persona_id": "power-user-v1",
                "objective": "Filter the listings to find one under $50,000.",
                "environment": "agent",
                "headed": False,
                "step_through": step_through,
            },
        )
        resp.raise_for_status()
        session_id = resp.json()["session_id"]
        print(f"started session {session_id} (step_through={step_through})")

        async with websockets.connect(f"{WS}/runs/{session_id}/stream", additional_headers=HEADERS) as ws:
            async for raw in ws:
                import json

                event = json.loads(raw)
                print("event:", event)
                if event.get("type") == "step" and step_through:
                    print("  ...pausing (step-through) — sending /continue in 1s")
                    await asyncio.sleep(1)
                    await client.post(f"{API}/runs/{session_id}/continue")
                if event.get("type") == "done":
                    break

        report = await client.get(f"{API}/runs/{session_id}/report")
        print("\nfinal report:", report.json())


if __name__ == "__main__":
    asyncio.run(main())
