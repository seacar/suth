import json
import os
import uuid

import pytest

requires_db = pytest.mark.skipif(
    "DATABASE_URL" not in os.environ,
    reason="needs a live Postgres — run via `specific exec cli -- .venv/bin/python -m pytest`",
)

# suth.api.app connects to Postgres at import time (module-level Memory/Orchestrator),
# so the import must happen lazily inside DB-gated tests, not at collection time.


@requires_db
def test_healthz():
    from fastapi.testclient import TestClient

    from suth.api.app import app

    with TestClient(app) as client:
        resp = client.get("/healthz")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


@requires_db
def test_list_projects_matches_registry():
    from fastapi.testclient import TestClient

    from suth.api.app import app

    with TestClient(app) as client:
        resp = client.get("/projects")
        assert resp.status_code == 200
        ids = {p["id"] for p in resp.json()}
        assert "suth-test-app" in ids


def _sample_project_payload(project_id: str, base_url: str = "http://localhost:9999") -> dict:
    return {
        "project_id": project_id,
        "name": "GUI Test App",
        "config_dir": f"./projects/{project_id}",
        "config": {
            "project_id": project_id,
            "base_url": base_url,
            "default_personas": [],
            "environments": {
                "dev": {"headed": True, "model": "default", "max_steps": 20},
            },
            "llm_providers": {
                "default": {
                    "provider": "ollama",
                    "model": "llama3.2:3b",
                    "base_url": "http://localhost:11434",
                }
            },
        },
    }


@requires_db
def test_create_project_registers_config_and_db_row():
    import shutil
    from pathlib import Path

    from fastapi.testclient import TestClient

    from suth.api.app import _memory, _registry, app

    project_id = f"gui-test-{uuid.uuid4().hex[:8]}"
    config_dir = Path("projects") / project_id
    try:
        with TestClient(app) as client:
            resp = client.post("/projects", json=_sample_project_payload(project_id))
            assert resp.status_code == 200
            body = resp.json()
            assert body["id"] == project_id
            assert body["name"] == "GUI Test App"
            assert body["base_url"] == "http://localhost:9999"

            listed = client.get("/projects").json()
            assert project_id in {p["id"] for p in listed}

        row = _memory.get_project(project_id)
        assert row is not None
        assert row["name"] == "GUI Test App"
        assert project_id in _registry.list_project_ids()
        assert (config_dir / "suth_config.json").is_file()
    finally:
        if project_id in _registry.list_project_ids():
            entries = {
                pid: path for pid, path in json.loads(_registry.path.read_text()).items() if pid != project_id
            }
            _registry.path.write_text(json.dumps(entries, indent=2) + "\n")
            _registry._entries = entries
        shutil.rmtree(config_dir, ignore_errors=True)


@requires_db
def test_create_project_rejects_duplicate():
    from fastapi.testclient import TestClient

    from suth.api.app import app

    with TestClient(app) as client:
        resp = client.post(
            "/projects",
            json={
                "project_id": "suth-test-app",
                "name": "Duplicate",
                "config_dir": "./suth-test-app",
                "config": {
                    "project_id": "suth-test-app",
                    "base_url": "http://localhost:3000",
                    "environments": {"dev": {"model": "default", "headed": True}},
                    "llm_providers": {"default": {"provider": "ollama", "model": "llama3.2:3b"}},
                },
            },
        )
        assert resp.status_code == 409


@requires_db
def test_create_project_rejects_invalid_id():
    from fastapi.testclient import TestClient

    from suth.api.app import app

    with TestClient(app) as client:
        resp = client.post(
            "/projects",
            json=_sample_project_payload("Bad_ID"),
        )
        assert resp.status_code == 422


@requires_db
def test_browse_projects_endpoint():
    from pathlib import Path

    from fastapi.testclient import TestClient

    from suth.api.app import app

    with TestClient(app) as client:
        resp = client.get("/projects/browse")
        assert resp.status_code == 200
        body = resp.json()
        assert body["path"] == "."
        assert (Path(body["abs_path"]) / "suth-test-app").is_dir()
        assert any(entry["name"] == "suth-test-app" for entry in body["entries"])


@requires_db
def test_config_at_existing_project():
    from fastapi.testclient import TestClient

    from suth.api.app import app

    with TestClient(app) as client:
        resp = client.get("/projects/config-at?dir=./suth-test-app")
        assert resp.status_code == 200
        body = resp.json()
        assert body["exists"] is True
        assert body["config"]["project_id"] == "suth-test-app"


@requires_db
def test_list_personas_returns_starter_library():
    from fastapi.testclient import TestClient

    from suth.api.app import app

    with TestClient(app) as client:
        resp = client.get("/personas")
        assert resp.status_code == 200
        ids = {p["id"] for p in resp.json()}
        assert "power-user-v1" in ids


@requires_db
def test_create_persona_rejects_invalid_definition():
    from fastapi.testclient import TestClient

    from suth.api.app import app

    with TestClient(app) as client:
        resp = client.post("/personas", json={"id": "bad", "digital_literacy": "expert", "device": "mobile"})
        assert resp.status_code == 422


@requires_db
def test_start_run_rejects_unregistered_project():
    from fastapi.testclient import TestClient

    from suth.api.app import app

    with TestClient(app) as client:
        resp = client.post(
            "/runs",
            json={
                "project_id": "not-a-real-project",
                "persona_id": "power-user-v1",
                "objective": "x",
                "environment": "dev",
            },
        )
        assert resp.status_code == 404


@requires_db
def test_run_status_404_for_unknown_session():
    from fastapi.testclient import TestClient

    from suth.api.app import app

    with TestClient(app) as client:
        resp = client.get(f"/runs/{uuid.uuid4()}/status")
        assert resp.status_code == 404


@requires_db
def test_sessions_recent_filters_by_project():
    from suth.db import Memory, get_engine
    from fastapi.testclient import TestClient

    from suth.api.app import app

    memory = Memory(get_engine())
    project_id = f"api-test-{uuid.uuid4().hex[:8]}"
    session_id = str(uuid.uuid4())
    memory.ensure_project(project_id, project_id, "http://localhost:8765")
    memory.create_session(
        session_id=session_id, project_id=project_id, persona_id="power-user-v1",
        objective="x", environment="dev", model_used="test",
    )
    memory.finish_session(session_id, status="completed", verdict="objective_met", friction_score=1.0)

    with TestClient(app) as client:
        resp = client.get(f"/sessions/recent?project_id={project_id}")
        assert resp.status_code == 200
        rows = resp.json()
        assert len(rows) == 1
        assert rows[0]["id"] == session_id


@requires_db
def test_compare_endpoint_matches_direct_call():
    from suth.compare import compare_runs
    from suth.db import Memory, get_engine
    from fastapi.testclient import TestClient

    from suth.api.app import app

    memory = Memory(get_engine())
    project_id = f"api-compare-{uuid.uuid4().hex[:8]}"
    memory.ensure_project(project_id, project_id, "http://localhost:8765")

    def make(score, verdict):
        sid = str(uuid.uuid4())
        memory.create_session(
            session_id=sid, project_id=project_id, persona_id="power-user-v1",
            objective="x", environment="dev", model_used="test",
        )
        memory.finish_session(sid, status="completed", verdict=verdict, friction_score=score)
        return sid

    a = make(2.0, "objective_met")
    b = make(9.0, "dead_click")

    direct = compare_runs(memory, a, b, 1.0)
    with TestClient(app) as client:
        resp = client.get(f"/compare?session_id_a={a}&session_id_b={b}&regression_threshold=1.0")
        assert resp.status_code == 200
        assert resp.json()["regressed"] == direct.regressed
        assert resp.json()["friction_delta"] == direct.friction_delta


@requires_db
def test_transcript_includes_offset_seconds_synced_to_video():
    from datetime import datetime, timedelta, timezone

    from fastapi.testclient import TestClient

    from suth.api.app import app
    from suth.db import Memory, get_engine

    memory = Memory(get_engine())
    project_id = f"api-video-{uuid.uuid4().hex[:8]}"
    session_id = str(uuid.uuid4())
    memory.ensure_project(project_id, project_id, "http://localhost:8765")
    memory.create_session(
        session_id=session_id, project_id=project_id, persona_id="power-user-v1",
        objective="x", environment="dev", model_used="test",
    )

    video_started_at = datetime.now(timezone.utc)
    memory.set_video(session_id, f"sessions/{session_id}/replay.webm", video_started_at)
    memory.log_step(
        session_id=session_id, step_index=1, thought="t", emotion="neutral",
        frustration_delta=0, action={"type": "click"},
    )
    memory.finish_session(session_id, status="completed", verdict="objective_met", friction_score=1.0)

    with TestClient(app) as client:
        resp = client.get(f"/runs/{session_id}/transcript")
        assert resp.status_code == 200
        step = resp.json()["steps"][0]
        assert step["offset_seconds"] is not None
        assert step["offset_seconds"] >= 0


@requires_db
def test_video_endpoint_404_when_session_has_none():
    from fastapi.testclient import TestClient

    from suth.api.app import app
    from suth.db import Memory, get_engine

    memory = Memory(get_engine())
    project_id = f"api-novideo-{uuid.uuid4().hex[:8]}"
    session_id = str(uuid.uuid4())
    memory.ensure_project(project_id, project_id, "http://localhost:8765")
    memory.create_session(
        session_id=session_id, project_id=project_id, persona_id="power-user-v1",
        objective="x", environment="dev", model_used="test",
    )

    with TestClient(app) as client:
        resp = client.get(f"/runs/{session_id}/video")
        assert resp.status_code == 404


@requires_db
def test_start_batch_rejects_unregistered_project():
    from fastapi.testclient import TestClient

    from suth.api.app import app

    with TestClient(app) as client:
        resp = client.post(
            "/batches",
            json={
                "project_id": "not-a-real-project",
                "persona_ids": ["power-user-v1", "elderly-low-vision-v1"],
                "objective": "x",
                "environment": "dev",
            },
        )
        assert resp.status_code == 404


@requires_db
def test_start_batch_rejects_unknown_persona():
    from fastapi.testclient import TestClient

    from suth.api.app import app

    with TestClient(app) as client:
        resp = client.post(
            "/batches",
            json={
                "project_id": "suth-test-app",
                "persona_ids": ["power-user-v1", "definitely-not-a-real-persona"],
                "objective": "x",
                "environment": "dev",
            },
        )
        assert resp.status_code == 404


@requires_db
def test_get_batch_404_for_unknown_batch():
    from fastapi.testclient import TestClient

    from suth.api.app import app

    with TestClient(app) as client:
        resp = client.get(f"/batches/{uuid.uuid4()}")
        assert resp.status_code == 404
