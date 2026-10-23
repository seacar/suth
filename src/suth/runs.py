"""Run setup shared by every surface that starts sessions (REST API, MCP
server): registry lookup -> config load -> environment resolve -> persona
load -> brain construction. Each step's failure maps to one typed error so
callers translate it once (HTTP status, MCP ToolError) instead of leaking a
500 or a raw traceback.
"""

import dataclasses

from sqlalchemy.engine import Engine

from suth.brain.interface import Brain, ProviderProfile, get_brain
from suth.config import ResolvedRunConfig, load_config
from suth.mcp_server.registry import ProjectRegistry, UnregisteredProjectError
from suth.personas.repository import load_persona_from_db
from suth.personas.schema import Persona
from suth.session import SessionResult


class RunSetupError(Exception):
    """Base for a run that can't start because of what the caller asked for."""

    status = 400


class UnknownProjectError(RunSetupError):
    status = 404


class InvalidRunConfigError(RunSetupError):
    status = 400


class UnknownPersonaError(RunSetupError):
    status = 404


class ProviderUnavailableError(RunSetupError):
    status = 422


def resolve_run_config(
    registry: ProjectRegistry, project_id: str, environment: str, headed: bool | None = None
) -> ResolvedRunConfig:
    try:
        config_path = registry.resolved_config_path(project_id)
    except UnregisteredProjectError as e:
        raise UnknownProjectError(str(e)) from e
    try:
        config = load_config(config_path)
        resolved = config.resolve(environment)
    except FileNotFoundError as e:
        raise InvalidRunConfigError(f"config file for '{project_id}' not found: {e}") from e
    except ValueError as e:  # bad JSON, schema errors, unknown environment/profile
        raise InvalidRunConfigError(str(e)) from e
    if headed is not None:
        resolved.headed = headed
    return resolved


def load_personas(engine: Engine, persona_ids: list[str]) -> list[Persona]:
    try:
        return [load_persona_from_db(engine, pid) for pid in persona_ids]
    except FileNotFoundError as e:
        raise UnknownPersonaError(str(e)) from e


def make_brain(profile: ProviderProfile) -> Brain:
    try:
        return get_brain(profile)
    except (NotImplementedError, RuntimeError, ValueError) as e:
        # No adapter for this provider, or its credential is missing/malformed.
        raise ProviderUnavailableError(str(e)) from e


def result_dict(result: SessionResult) -> dict:
    return {
        "session_id": result.session_id,
        "verdict": result.verdict,
        "step_count": result.step_count,
        "final_frustration": result.final_frustration,
        "friction_score": result.friction_score,
        "failures": [dataclasses.asdict(h) for h in result.failures],
    }
