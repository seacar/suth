"""HTTP transport for remote/CI callers, with per-caller bearer-token auth —
plan Phase 4. Tokens come from the `mcp_caller_tokens` Specific secret (§6.1),
a JSON object mapping token -> caller id, e.g. {"tok_abc123": "ci-runner"}.

Run: .venv/bin/uvicorn suth.mcp_server.http_app:app
"""

import json
import os

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from suth.mcp_server.caller import set_http_caller
from suth.mcp_server.server import mcp


def _load_tokens() -> dict[str, str]:
    raw = os.environ.get("MCP_CALLER_TOKENS", "")
    if not raw:
        return {}
    return json.loads(raw)


class BearerAuthMiddleware(BaseHTTPMiddleware):
    """Rejects any request without a valid `Authorization: Bearer <token>`
    header, and resolves the caller identity from it (read via
    suth.mcp_server.caller.resolve_caller() inside tool implementations)."""

    async def dispatch(self, request: Request, call_next):
        tokens = _load_tokens()
        if not tokens:
            return JSONResponse(
                {"error": "server has no MCP_CALLER_TOKENS configured — all HTTP calls rejected"},
                status_code=503,
            )

        auth = request.headers.get("authorization", "")
        if not auth.startswith("Bearer "):
            return JSONResponse({"error": "missing bearer token"}, status_code=401)

        token = auth.removeprefix("Bearer ").strip()
        caller = tokens.get(token)
        if caller is None:
            return JSONResponse({"error": "invalid bearer token"}, status_code=401)

        set_http_caller(caller)
        return await call_next(request)


mcp_asgi_app = mcp.streamable_http_app()

app = Starlette(
    routes=mcp_asgi_app.routes,
    middleware=[*mcp_asgi_app.user_middleware, Middleware(BearerAuthMiddleware)],
    lifespan=mcp_asgi_app.router.lifespan_context,
)
