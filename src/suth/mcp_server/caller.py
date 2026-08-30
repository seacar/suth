import os
from contextvars import ContextVar

# Set by the HTTP transport's bearer-auth middleware for the duration of a
# request; stdio has no such request boundary, so it falls back to a
# server-launch-time env var instead.
_http_caller: ContextVar[str | None] = ContextVar("suth_mcp_http_caller", default=None)


def set_http_caller(caller: str) -> None:
    _http_caller.set(caller)


def resolve_caller() -> str:
    return _http_caller.get() or os.environ.get("SUTH_MCP_CALLER", "unknown-mcp-caller")
