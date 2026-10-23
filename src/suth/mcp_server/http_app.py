"""HTTP transport for remote/CI callers, with per-caller bearer-token auth —
plan Phase 4. Tokens come from the `mcp_caller_tokens` Specific secret (§6.1),
a JSON object mapping token -> caller id, e.g. {"tok_abc123": "ci-runner"}.

Run: .venv/bin/uvicorn suth.mcp_server.http_app:app
"""

import hmac
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
    try:
        tokens = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            'MCP_CALLER_TOKENS must be a JSON object mapping token -> caller id, e.g. {"tok_abc": "ci"}'
        ) from e
    if not isinstance(tokens, dict):
        raise RuntimeError("MCP_CALLER_TOKENS must be a JSON object mapping token -> caller id")
    return {str(k): str(v) for k, v in tokens.items()}


def _match_caller(tokens: dict[str, str], presented: str) -> str | None:
    """Constant-time comparison against every token, so response timing
    doesn't leak how much of a guessed token was right."""
    caller = None
    for token, candidate in tokens.items():
        if hmac.compare_digest(token.encode(), presented.encode()):
            caller = candidate
    return caller


class BearerAuthMiddleware(BaseHTTPMiddleware):
    """Rejects any request without a valid `Authorization: Bearer <token>`
    header, and resolves the caller identity from it (read via
    suth.mcp_server.caller.resolve_caller() inside tool implementations)."""

    def __init__(self, app, tokens: dict[str, str]):
        super().__init__(app)
        self.tokens = tokens

    async def dispatch(self, request: Request, call_next):
        tokens = self.tokens
        if not tokens:
            return JSONResponse(
                {"error": "server has no MCP_CALLER_TOKENS configured — all HTTP calls rejected"},
                status_code=503,
            )

        auth = request.headers.get("authorization", "")
        if not auth.startswith("Bearer "):
            return JSONResponse({"error": "missing bearer token"}, status_code=401)

        token = auth.removeprefix("Bearer ").strip()
        caller = _match_caller(tokens, token)
        if caller is None:
            return JSONResponse({"error": "invalid bearer token"}, status_code=401)

        set_http_caller(caller)
        return await call_next(request)


mcp_asgi_app = mcp.streamable_http_app()

app = Starlette(
    routes=mcp_asgi_app.routes,
    # Parsed once at startup: a malformed value fails the boot loudly instead
    # of turning every request into a 500.
    middleware=[*mcp_asgi_app.user_middleware, Middleware(BearerAuthMiddleware, tokens=_load_tokens())],
    lifespan=mcp_asgi_app.router.lifespan_context,
)
