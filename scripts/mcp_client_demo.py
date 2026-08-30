#!/usr/bin/env python3
"""A real MCP client — no shared Python state with the server, talks only
over the stdio JSON-RPC protocol — standing in for "a separate agent" in the
Phase 4 dogfooding exit criteria. Spawns the server as a subprocess (it
inherits DATABASE_URL/S3_*/etc. from this process's env, so run this via
`specific exec cli -- ...` same as the server itself needs).

Run: specific exec cli -- .venv/bin/python scripts/mcp_client_demo.py
"""

import asyncio
import json
import os
import sys

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


async def main() -> None:
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "suth.mcp_server.server"], env=dict(os.environ)
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print("connected. tools:", [t.name for t in tools.tools])

            print("\ncalling run_audit unprompted, as an external agent would...")
            result = await session.call_tool(
                "run_audit",
                {
                    "project_id": "suth-test-app",
                    "persona_id": "power-user-v1",
                    "objective": "Filter the listings to find one under $50,000.",
                    "environment": "agent",
                    "mode": "sync",
                },
            )
            report = json.loads(result.content[0].text)
            print("\nrun_audit report:")
            print(json.dumps(report, indent=2))

            print("\ncalling get_session_report on the same session_id (as if a second tool call)...")
            result2 = await session.call_tool(
                "get_session_report", {"session_id": report["session_id"]}
            )
            report2 = json.loads(result2.content[0].text)
            assert report2["session_id"] == report["session_id"]
            print("get_session_report round-trip OK — verdict:", report2["verdict"])


if __name__ == "__main__":
    asyncio.run(main())
