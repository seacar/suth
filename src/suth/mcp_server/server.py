"""The MCP server — wraps the Orchestrator's public functions as MCP tools
and resources, so any MCP-aware agent can call suth as a tool (plan Phase 4).

Run stdio (for Claude Code/Desktop):
    .venv/bin/python -m suth.mcp_server.server

Run HTTP (for remote/CI callers, bearer-token auth via suth.mcp_server.http_app):
    .venv/bin/uvicorn suth.mcp_server.http_app:app
"""

import dataclasses

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import ValidationError

from suth.brain.interface import get_brain
from suth.compare import compare_runs as _compare_runs
from suth.config import load_config
from suth.db import Memory, get_engine
from suth.mcp_server.caller import resolve_caller
from suth.mcp_server.registry import ProjectRegistry, UnregisteredProjectError
from suth.orchestrator import BudgetExceededError, ConcurrencyLimitError, Orchestrator
from suth.personas.repository import list_personas as _list_personas
from suth.personas.repository import load_persona_from_db, save_persona
from suth.personas.schema import Persona
from suth.session import SessionResult

mcp = MCPServer(
    "suth",
    instructions=(
        "Synthetic User Test Harness — run an automated UX audit of a registered "
        "web project with an LLM-backed persona and get back a structured verdict "
        "(taxonomy label, friction score, failure points). Use run_audit."
    ),
)

_registry = ProjectRegistry()
_memory = Memory(get_engine())
_orchestrator = Orchestrator(memory=_memory)

ALLOWED_MCP_ENVIRONMENTS = ("ci", "agent")


def _result_dict(result: SessionResult) -> dict:
    return {
        "session_id": result.session_id,
        "verdict": result.verdict,
        "step_count": result.step_count,
        "final_frustration": result.final_frustration,
        "friction_score": result.friction_score,
        "failures": [dataclasses.asdict(h) for h in result.failures],
    }


@mcp.tool()
def list_projects() -> list[str]:
    """List project_ids this server is allowed to audit."""
    return _registry.list_project_ids()


@mcp.tool()
def list_personas(project_id: str | None = None) -> list[dict]:
    """List available personas and their latest version. `project_id` is
    accepted for forward compatibility with per-project personas but unused
    today — Phase 2 only populated the global (project_id=NULL) library."""
    return _list_personas(_memory.engine)


@mcp.tool()
def create_persona(definition: dict) -> dict:
    """Register or update a persona. Validated against the persona schema
    before insert; a content change creates a new version rather than
    mutating history out from under past sessions."""
    try:
        persona = Persona.model_validate(definition)
    except ValidationError as e:
        raise ToolError(f"invalid persona definition: {e}") from e
    version, changed = save_persona(_memory.engine, persona)
    return {"id": persona.id, "version": version, "changed": changed}


@mcp.tool()
def run_audit(
    project_id: str, persona_id: str, objective: str, environment: str, mode: str = "sync"
) -> dict:
    """Run a UX audit against a registered project. `environment` must be
    'ci' or 'agent' — 'dev' is always rejected here regardless of what the
    caller asks for, since 'dev' is the human-supervised local-only mode.
    `mode='sync'` (default) blocks and returns the full report; `mode='async'`
    returns immediately with a session_id — poll it with get_session_status/
    get_session_report.
    """
    if environment not in ALLOWED_MCP_ENVIRONMENTS:
        raise ToolError(
            f"environment must be one of {ALLOWED_MCP_ENVIRONMENTS} over MCP, got {environment!r}"
        )
    if mode not in ("sync", "async"):
        raise ToolError(f"mode must be 'sync' or 'async', got {mode!r}")

    try:
        config_path = _registry.config_path(project_id)
    except UnregisteredProjectError as e:
        raise ToolError(str(e)) from e

    config = load_config(config_path)
    resolved = config.resolve(environment)
    persona = load_persona_from_db(_memory.engine, persona_id)
    brain = get_brain(resolved.provider_profile)
    caller = resolve_caller()

    try:
        session_id = _orchestrator.start_session(
            config=resolved,
            persona=persona,
            objective=objective,
            brain=brain,
            environment=environment,
            caller=caller,
        )
    except (ConcurrencyLimitError, BudgetExceededError) as e:
        raise ToolError(str(e)) from e

    if mode == "async":
        return {"session_id": session_id, "status": "running"}
    return _result_dict(_orchestrator.get_report(session_id))


@mcp.tool()
def run_audit_matrix(
    project_id: str, persona_ids: list[str], objective: str, environment: str, mode: str = "sync"
) -> dict:
    """Run the same objective across multiple personas in parallel (queued
    past the concurrency cap, not rejected), grouped as one batch. Same
    `environment` restriction as run_audit ('dev' always rejected). One
    persona's failure doesn't hide the others' results — check each
    member's `error` field. `mode='async'` returns immediately with a
    batch_id and each member's session_id, for polling via
    get_session_status/get_session_report on the individual sessions.
    """
    if environment not in ALLOWED_MCP_ENVIRONMENTS:
        raise ToolError(
            f"environment must be one of {ALLOWED_MCP_ENVIRONMENTS} over MCP, got {environment!r}"
        )
    if mode not in ("sync", "async"):
        raise ToolError(f"mode must be 'sync' or 'async', got {mode!r}")
    if not persona_ids:
        raise ToolError("persona_ids must be non-empty")

    try:
        config_path = _registry.config_path(project_id)
    except UnregisteredProjectError as e:
        raise ToolError(str(e)) from e

    config = load_config(config_path)
    resolved = config.resolve(environment)
    try:
        personas = [load_persona_from_db(_memory.engine, pid) for pid in persona_ids]
    except FileNotFoundError as e:
        raise ToolError(str(e)) from e
    caller = resolve_caller()

    try:
        batch_id = _orchestrator.start_batch(
            config=resolved,
            personas=personas,
            objective=objective,
            brain_factory=lambda: get_brain(resolved.provider_profile),
            environment=environment,
            caller=caller,
        )
    except BudgetExceededError as e:
        raise ToolError(str(e)) from e

    if mode == "async":
        session_ids = _orchestrator.get_batch_session_ids(batch_id)
        return {
            "batch_id": batch_id,
            "sessions": [{"session_id": sid, "persona_id": pid} for sid, pid in zip(session_ids, persona_ids)],
        }

    members = _orchestrator.get_batch_report(batch_id)
    return {
        "batch_id": batch_id,
        "results": [
            {
                "session_id": m.session_id,
                "persona_id": m.persona_id,
                "report": _result_dict(m.result) if m.result else None,
                "error": m.error,
            }
            for m in members
        ],
    }


@mcp.tool()
def get_session_status(session_id: str) -> dict:
    """Poll a session started with mode='async'."""
    return {"session_id": session_id, "status": _orchestrator.get_status(session_id)}


@mcp.tool()
def get_session_report(session_id: str) -> dict:
    """Block until `session_id` finishes (if still running) and return its report."""
    return _result_dict(_orchestrator.get_report(session_id))


@mcp.tool()
def compare_runs(session_id_a: str, session_id_b: str, regression_threshold: float = 0.0) -> dict:
    """Diff two sessions' friction scores + taxonomy hits."""
    comparison = _compare_runs(_memory, session_id_a, session_id_b, regression_threshold)
    return dataclasses.asdict(comparison)


@mcp.resource("session://{id}/transcript")
def session_transcript(id: str) -> dict:
    session = _memory.get_session(id)
    if session is None:
        raise ValueError(f"unknown session_id: {id}")
    return {"session": session, "steps": _memory.get_steps(id), "failures": _memory.get_failures(id)}


@mcp.resource("session://{id}/screenshots/{step}")
def session_screenshot(id: str, step: str) -> bytes:
    from suth.storage import download_bytes

    steps = _memory.get_steps(id)
    matches = [s for s in steps if str(s["step_index"]) == step]
    if not matches or not matches[0]["screenshot_ref"]:
        raise ValueError(f"no screenshot for session {id} step {step}")
    return download_bytes(matches[0]["screenshot_ref"])


@mcp.resource("session://{id}/video")
def session_video(id: str) -> bytes:
    from suth.storage import download_bytes

    session = _memory.get_session(id)
    if session is None or not session.get("video_ref"):
        raise ValueError(f"no video for session {id}")
    return download_bytes(session["video_ref"])


@mcp.resource("persona://{id}")
def persona_resource(id: str) -> dict:
    return load_persona_from_db(_memory.engine, id).model_dump(mode="json")


if __name__ == "__main__":
    mcp.run(transport="stdio")
