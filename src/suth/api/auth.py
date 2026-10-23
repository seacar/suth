"""Bearer-token auth for the Local Control API.

The API can start browser sessions, write project configs and store provider
credentials, so any web page the user happens to visit must not be able to
drive it. When SUTH_API_TOKEN is set (specific.hcl generates one), every
request needs it — as an `Authorization: Bearer` header, or as a `token`
query parameter for the requests a browser can't attach headers to
(WebSocket upgrades, <img>/<video> src).
"""

import hmac
from urllib.parse import parse_qs

from starlette.types import ASGIApp, Receive, Scope, Send

# Health checks come from the platform, not a user, and leak nothing.
PUBLIC_PATHS = frozenset({"/healthz"})


def _presented_token(scope: Scope) -> str | None:
    for name, value in scope.get("headers", []):
        if name == b"authorization":
            auth = value.decode("latin-1")
            if auth.startswith("Bearer "):
                return auth.removeprefix("Bearer ").strip()
    query = parse_qs(scope.get("query_string", b"").decode("latin-1"))
    values = query.get("token")
    return values[0] if values else None


class ApiTokenMiddleware:
    def __init__(self, app: ASGIApp, token: str | None):
        self.app = app
        self.token = token or None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            self.token is None
            or scope["type"] not in ("http", "websocket")
            or scope["path"] in PUBLIC_PATHS
            # CORS preflights never carry credentials; CORSMiddleware answers them.
            or (scope["type"] == "http" and scope["method"] == "OPTIONS")
        ):
            await self.app(scope, receive, send)
            return

        presented = _presented_token(scope)
        if presented is not None and hmac.compare_digest(presented, self.token):
            await self.app(scope, receive, send)
            return

        if scope["type"] == "websocket":
            # Closing before accept makes the server answer the upgrade with 403.
            await send({"type": "websocket.close", "code": 1008})
            return
        body = b'{"detail":"missing or invalid API token"}'
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
