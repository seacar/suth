"""Local Control API — plan Phase 5. A FastAPI service wrapping the same
Orchestrator the CLI and MCP server use, so manual dev runs become
visual/ambient: REST endpoints mirror the MCP tool set, and a WebSocket
streams live step events (and, for step-through mode, gates the run on a
client "continue" message) to whatever's watching — the suth web app.

Run: specific exec cli -- .venv/bin/uvicorn suth.api.app:app
(or, once `specific dev` is up, it's already running as the "api" service.)
"""

import asyncio
import dataclasses
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ValidationError

from suth.api.events import bus
from suth.brain.interface import get_brain
from suth.compare import compare_runs as _compare_runs
from suth.config import load_config
from suth.db import Memory, get_engine
from suth.mcp_server.registry import ProjectRegistry, UnregisteredProjectError
from suth.orchestrator import BudgetExceededError, ConcurrencyLimitError, Orchestrator
from suth.personas.repository import list_personas as _list_personas
from suth.personas.repository import load_persona_from_db, save_persona
from suth.personas.schema import Persona
from suth.projects.filesystem import browse as _browse_projects
from suth.projects.service import (
    CreateProjectRequest,
    InvalidProjectRequestError,
    ProjectAlreadyExistsError,
    ProjectDeleteBlockedError,
    ProjectNotFoundError,
    UpdateProjectRequest,
    create_project as _create_project,
    delete_project as _delete_project,
    get_project as _get_project,
    inspect_config_dir as _inspect_config_dir,
    list_projects as _list_projects,
    update_project as _update_project,
)
from suth.session import SessionResult

_registry = ProjectRegistry()
_memory = Memory(get_engine())
_orchestrator = Orchestrator(memory=_memory)

POLL_INTERVAL_SECONDS = 2.0


async def _completion_watcher() -> None:
    """The only state every surface (CLI/MCP/API, each its own process)
    shares is Postgres — so "notify on any completion" is a poll, not a
    push. Good enough for a personal dev tool at a 2s cadence."""
    since = datetime.now(timezone.utc)
    while True:
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
        finished = _memory.list_recently_finished(since)
        for session in finished:
            bus.publish_global(
                {
                    "type": "session_finished",
                    "session_id": session["id"],
                    "project_id": session["project_id"],
                    "verdict": session["verdict"],
                    "friction_score": session["friction_score"],
                    "caller": session["caller"],
                }
            )
        if finished:
            since = max(s["ended_at"] for s in finished)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_completion_watcher())
    yield
    task.cancel()


app = FastAPI(title="suth Local Control API", lifespan=lifespan)

# The web app (service "web") is a separate origin from this API — allow it
# through CORS. Falls back to "*" so `uvicorn suth.api.app:app` still works
# when run standalone, outside `specific dev`.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.environ["CORS_ORIGIN"]] if os.environ.get("CORS_ORIGIN") else ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _result_dict(result: SessionResult) -> dict:
    return {
        "session_id": result.session_id,
        "verdict": result.verdict,
        "step_count": result.step_count,
        "final_frustration": result.final_frustration,
        "friction_score": result.friction_score,
        "failures": [dataclasses.asdict(h) for h in result.failures],
    }


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@app.get("/projects")
def list_projects() -> list[dict]:
    return [p.model_dump() for p in _list_projects(_registry, _memory)]


@app.get("/projects/browse")
def browse_project_dirs(path: str = ".") -> dict:
    try:
        return _browse_projects(_registry, path)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


@app.get("/projects/config-at")
def project_config_at(dir: str = ".") -> dict:
    try:
        return _inspect_config_dir(_registry, dir)
    except InvalidProjectRequestError as e:
        raise HTTPException(422, str(e)) from e
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


@app.get("/projects/{project_id}")
def get_project(project_id: str) -> dict:
    try:
        return _get_project(_registry, _memory, project_id).model_dump(mode="json")
    except ProjectNotFoundError as e:
        raise HTTPException(404, str(e)) from e


@app.post("/projects")
def create_project(req: CreateProjectRequest) -> dict:
    try:
        project = _create_project(_registry, _memory, req)
    except ProjectAlreadyExistsError as e:
        raise HTTPException(409, str(e)) from e
    except InvalidProjectRequestError as e:
        raise HTTPException(422, str(e)) from e
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return project.model_dump()


@app.put("/projects/{project_id}")
def update_project(project_id: str, req: UpdateProjectRequest) -> dict:
    try:
        project = _update_project(_registry, _memory, project_id, req)
    except ProjectNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except ValidationError as e:
        raise HTTPException(422, f"invalid config: {e}") from e
    return project.model_dump()


@app.delete("/projects/{project_id}")
def delete_project(project_id: str) -> dict:
    try:
        return _delete_project(_registry, _memory, project_id)
    except ProjectNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except ProjectDeleteBlockedError as e:
        raise HTTPException(409, str(e)) from e


@app.get("/personas")
def list_personas() -> list[dict]:
    return _list_personas(_memory.engine)


@app.post("/personas")
def create_persona(definition: dict) -> dict:
    try:
        persona = Persona.model_validate(definition)
    except ValidationError as e:
        raise HTTPException(422, f"invalid persona definition: {e}") from e
    version, changed = save_persona(_memory.engine, persona)
    return {"id": persona.id, "version": version, "changed": changed}


class RunRequest(BaseModel):
    project_id: str
    persona_id: str
    objective: str
    environment: str = "dev"
    headed: bool | None = None
    step_through: bool = False
    caller: str | None = "api"


def _make_on_step(session_id: str, step_through: bool):
    def on_step(step_index, record):
        bus.publish(
            session_id,
            {
                "type": "step",
                "step_index": step_index,
                "thought": record.thought,
                "action_type": record.action_type,
                "target": record.target,
                "dom_changed": record.dom_changed,
                "url": record.url,
                "emotion": record.emotion,
                "frustration_delta": record.frustration_delta,
                "screenshot_ref": record.screenshot_ref,
            },
        )
        if step_through:
            gate = bus.gate_for(session_id)
            gate.clear()
            gate.wait()

    return on_step


@app.post("/runs")
def start_run(req: RunRequest) -> dict:
    try:
        config_path = _registry.config_path(req.project_id)
    except UnregisteredProjectError as e:
        raise HTTPException(404, str(e)) from e

    config = load_config(config_path)
    try:
        resolved = config.resolve(req.environment)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    if req.headed is not None:
        resolved.headed = req.headed

    persona = load_persona_from_db(_memory.engine, req.persona_id)
    brain = get_brain(resolved.provider_profile)

    session_id = str(uuid.uuid4())
    on_step = _make_on_step(session_id, req.step_through)

    try:
        _orchestrator.start_session(
            config=resolved,
            persona=persona,
            objective=req.objective,
            brain=brain,
            environment=req.environment,
            caller=req.caller,
            on_step=on_step,
            session_id=session_id,
        )
    except (ConcurrencyLimitError, BudgetExceededError) as e:
        raise HTTPException(429, str(e)) from e

    def _on_done(_future):
        bus.close(session_id)

    _orchestrator.add_completion_callback(session_id, _on_done)
    return {"session_id": session_id, "status": "running"}


@app.get("/runs/{session_id}/status")
def run_status(session_id: str) -> dict:
    try:
        return {"session_id": session_id, "status": _orchestrator.get_status(session_id)}
    except KeyError as e:
        raise HTTPException(404, str(e)) from e


@app.get("/runs/{session_id}/report")
def run_report(session_id: str) -> dict:
    try:
        return _result_dict(_orchestrator.get_report(session_id))
    except KeyError as e:
        raise HTTPException(404, str(e)) from e


def _with_offsets(session: dict, steps: list[dict]) -> list[dict]:
    """Seconds from the start of the replay video to each step's screenshot —
    None if this session predates video capture or never got one (e.g.
    record_video=False). Lets the GUI seek the player to any given step."""
    video_started_at = session.get("video_started_at")
    out = []
    for s in steps:
        offset = None
        if video_started_at and s.get("created_at"):
            offset = max(0.0, (s["created_at"] - video_started_at).total_seconds())
        out.append({**s, "offset_seconds": offset})
    return out


@app.get("/runs/{session_id}/transcript")
def run_transcript(session_id: str) -> dict:
    session = _memory.get_session(session_id)
    if session is None:
        raise HTTPException(404, f"unknown session_id: {session_id}")
    steps = _memory.get_steps(session_id)
    return {
        "session": session,
        "steps": _with_offsets(session, steps),
        "failures": _memory.get_failures(session_id),
    }


@app.post("/runs/{session_id}/continue")
def run_continue(session_id: str) -> dict:
    bus.gate_for(session_id).set()
    return {"ok": True}


@app.get("/runs/{session_id}/screenshots/{step_index}")
def run_screenshot(session_id: str, step_index: int):
    from fastapi.responses import Response

    from suth.storage import download_bytes

    steps = _memory.get_steps(session_id)
    matches = [s for s in steps if s["step_index"] == step_index]
    if not matches or not matches[0]["screenshot_ref"]:
        raise HTTPException(404, f"no screenshot for session {session_id} step {step_index}")
    return Response(content=download_bytes(matches[0]["screenshot_ref"]), media_type="image/png")


@app.get("/runs/{session_id}/video")
def run_video(session_id: str, range: str | None = Header(default=None)):
    """Serves the session's replay video with HTTP Range support, so the
    <video> element can seek without re-downloading the whole file — video
    files are much larger than the per-step screenshots the rest of this API
    serves whole."""
    from fastapi.responses import Response

    from suth.storage import download_range, object_size

    session = _memory.get_session(session_id)
    if session is None or not session.get("video_ref"):
        raise HTTPException(404, f"no video for session {session_id}")
    key = session["video_ref"]
    size = object_size(key)

    if range:
        try:
            start_s, end_s = range.removeprefix("bytes=").split("-")
            start = int(start_s)
            end = int(end_s) if end_s else size - 1
        except ValueError:
            raise HTTPException(400, f"malformed Range header: {range}") from None
        end = min(end, size - 1)
        body = download_range(key, start, end)
        return Response(
            content=body,
            status_code=206,
            media_type="video/webm",
            headers={
                "Content-Range": f"bytes {start}-{end}/{size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(len(body)),
            },
        )

    body = download_range(key, 0, size - 1)
    return Response(
        content=body,
        media_type="video/webm",
        headers={"Accept-Ranges": "bytes", "Content-Length": str(size)},
    )


@app.get("/sessions/recent")
def sessions_recent(project_id: str | None = None, limit: int = 20) -> list[dict]:
    return _memory.list_recent_sessions(project_id, limit)


class BatchRequest(BaseModel):
    project_id: str
    persona_ids: list[str]
    objective: str
    environment: str = "dev"
    headed: bool | None = None
    caller: str | None = "api"


@app.post("/batches")
def start_batch(req: BatchRequest) -> dict:
    """Multi-persona run: fans out `objective` across every persona_id in
    parallel (queued past the concurrency cap, not rejected), grouped under
    one batch_id. Each member gets its own /runs/{id}/stream WebSocket, same
    as a solo run — no new streaming plumbing needed for N-at-once."""
    try:
        config_path = _registry.config_path(req.project_id)
    except UnregisteredProjectError as e:
        raise HTTPException(404, str(e)) from e

    config = load_config(config_path)
    try:
        resolved = config.resolve(req.environment)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    if req.headed is not None:
        resolved.headed = req.headed

    try:
        personas = [load_persona_from_db(_memory.engine, pid) for pid in req.persona_ids]
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e

    def on_step_factory(session_id: str):
        return _make_on_step(session_id, step_through=False)

    try:
        batch_id = _orchestrator.start_batch(
            config=resolved,
            personas=personas,
            objective=req.objective,
            brain_factory=lambda: get_brain(resolved.provider_profile),
            environment=req.environment,
            caller=req.caller,
            on_step_factory=on_step_factory,
        )
    except BudgetExceededError as e:
        raise HTTPException(429, str(e)) from e

    session_ids = _orchestrator.get_batch_session_ids(batch_id)
    for sid in session_ids:
        _orchestrator.add_completion_callback(sid, lambda _f, sid=sid: bus.close(sid))

    return {
        "batch_id": batch_id,
        "sessions": [{"session_id": sid, "persona_id": pid} for sid, pid in zip(session_ids, req.persona_ids)],
    }


@app.get("/batches/{batch_id}")
def get_batch(batch_id: str) -> dict:
    batch = _memory.get_batch(batch_id)
    if batch is None:
        raise HTTPException(404, f"unknown batch_id: {batch_id}")
    return {"batch": batch, "sessions": _memory.get_batch_sessions(batch_id)}


@app.get("/compare")
def compare(session_id_a: str, session_id_b: str, regression_threshold: float = 0.0) -> dict:
    try:
        return dataclasses.asdict(
            _compare_runs(_memory, session_id_a, session_id_b, regression_threshold)
        )
    except KeyError as e:
        raise HTTPException(404, str(e)) from e


@app.websocket("/runs/{session_id}/stream")
async def stream_run(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()
    try:
        async for event in bus.subscribe(session_id):
            await websocket.send_json(event)
        await websocket.send_json({"type": "done"})
    except WebSocketDisconnect:
        pass


@app.websocket("/events")
async def stream_global_events(websocket: WebSocket) -> None:
    """Every session's completion, regardless of who started it — what the
    GUI subscribes to for its "notify on any completion" feature."""
    await websocket.accept()
    try:
        async for event in bus.subscribe_global():
            await websocket.send_json(event)
    except WebSocketDisconnect:
        pass
