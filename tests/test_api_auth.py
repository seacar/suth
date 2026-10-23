import pytest
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from suth.api.auth import ApiTokenMiddleware

TOKEN = "s3cret-token"


def _client(token: str | None) -> TestClient:
    app = FastAPI()
    app.add_middleware(ApiTokenMiddleware, token=token)

    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}

    @app.get("/projects")
    def projects():
        return []

    @app.websocket("/events")
    async def events(ws: WebSocket):
        await ws.accept()
        await ws.send_json({"type": "hello"})
        await ws.close()

    return TestClient(app)


def test_no_token_configured_leaves_api_open():
    assert _client(None).get("/projects").status_code == 200


def test_rejects_missing_and_wrong_token():
    client = _client(TOKEN)
    assert client.get("/projects").status_code == 401
    assert client.get("/projects", headers={"Authorization": "Bearer nope"}).status_code == 401
    assert client.get("/projects?token=nope").status_code == 401


def test_accepts_bearer_header_and_query_token():
    client = _client(TOKEN)
    assert client.get("/projects", headers={"Authorization": f"Bearer {TOKEN}"}).status_code == 200
    assert client.get(f"/projects?token={TOKEN}").status_code == 200


def test_healthz_and_preflight_stay_public():
    client = _client(TOKEN)
    assert client.get("/healthz").status_code == 200
    assert client.options("/projects").status_code != 401


def test_websocket_requires_token():
    client = _client(TOKEN)
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/events") as ws:
            ws.receive_json()
    with client.websocket_connect(f"/events?token={TOKEN}") as ws:
        assert ws.receive_json() == {"type": "hello"}
