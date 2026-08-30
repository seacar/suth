import json
import re
from pathlib import Path

from pydantic import BaseModel, ValidationError

from suth.config import SuthConfig, load_config
from suth.db import Memory
from suth.credentials import (
    credential_is_configured,
    save_credentials,
)
from suth.mcp_server.registry import ProjectRegistry
from suth.projects.filesystem import (
    config_at,
    config_file_in_dir,
    project_root,
    relative_path,
    resolve_registered_config_path,
    resolve_under_root,
)

PROJECT_ID_PATTERN = re.compile(r"^[a-z][a-z0-9-]*$")
DEFAULT_LLM_MODEL = "gemma4"
DEFAULT_LLM_BASE_URL = "http://localhost:11434"
DEFAULT_DEV_MODEL = "default"


class ProjectSummary(BaseModel):
    id: str
    name: str
    base_url: str
    config_path: str
    config_dir: str


class ProjectDetail(ProjectSummary):
    config: SuthConfig
    provider_credentials_configured: dict[str, bool] = {}


class CreateProjectRequest(BaseModel):
    project_id: str
    name: str
    config_dir: str
    config: SuthConfig
    provider_credentials: dict[str, str] = {}


class UpdateProjectRequest(BaseModel):
    name: str | None = None
    config: SuthConfig
    provider_credentials: dict[str, str] = {}


class ProjectAlreadyExistsError(Exception):
    pass


class ProjectNotFoundError(Exception):
    pass


class ProjectDeleteBlockedError(Exception):
    pass


class InvalidProjectRequestError(Exception):
    pass


def _validate_project_id(project_id: str) -> None:
    if not PROJECT_ID_PATTERN.match(project_id):
        raise InvalidProjectRequestError(
            "project_id must start with a letter and contain only lowercase letters, digits, and hyphens"
        )


def _provider_credentials_status(config: SuthConfig, root: Path) -> dict[str, bool]:
    status: dict[str, bool] = {}
    for profile in config.llm_providers.values():
        if profile.credential:
            status[profile.credential] = credential_is_configured(profile.credential, root)
    return status


def _persist_provider_credentials(
    registry: ProjectRegistry,
    config: SuthConfig,
    provider_credentials: dict[str, str],
) -> None:
    if not provider_credentials:
        return

    allowed_refs = {
        profile.credential
        for profile in config.llm_providers.values()
        if profile.credential
    }
    to_save: dict[str, str] = {}
    for ref, value in provider_credentials.items():
        if ref not in allowed_refs:
            raise InvalidProjectRequestError(f"unknown provider credential reference '{ref}'")
        if not value.strip():
            continue
        env_var = ref.removeprefix("env:")
        to_save[env_var] = value.strip()

    if to_save:
        save_credentials(to_save, project_root(registry))


def default_config(project_id: str, base_url: str) -> SuthConfig:
    return SuthConfig.model_validate(
        {
            "project_id": project_id,
            "base_url": base_url.rstrip("/"),
            "default_personas": [],
            "environments": {
                "dev": {
                    "headed": True,
                    "model": DEFAULT_DEV_MODEL,
                    "max_steps": 20,
                }
            },
            "llm_providers": {
                DEFAULT_DEV_MODEL: {
                    "provider": "ollama",
                    "model": DEFAULT_LLM_MODEL,
                    "base_url": DEFAULT_LLM_BASE_URL,
                }
            },
        }
    )


def _summary_from_paths(
    registry: ProjectRegistry,
    memory: Memory,
    project_id: str,
    config_path: Path,
    config: SuthConfig,
) -> ProjectSummary:
    root = project_root(registry)
    row = memory.get_project(project_id)
    name = row["name"] if row else project_id
    base_url = row["base_url"] if row else config.base_url
    return ProjectSummary(
        id=project_id,
        name=name,
        base_url=base_url,
        config_path=relative_path(root, config_path),
        config_dir=relative_path(root, config_path.parent),
    )


def list_projects(registry: ProjectRegistry, memory: Memory) -> list[ProjectSummary]:
    summaries: list[ProjectSummary] = []
    for project_id in registry.list_project_ids():
        try:
            config_path = resolve_registered_config_path(registry, project_id)
            config = load_config(config_path)
            summaries.append(_summary_from_paths(registry, memory, project_id, config_path, config))
        except (OSError, ValidationError, json.JSONDecodeError, ValueError):
            row = memory.get_project(project_id)
            summaries.append(
                ProjectSummary(
                    id=project_id,
                    name=row["name"] if row else project_id,
                    base_url=row["base_url"] if row else project_id,
                    config_path=registry.config_path(project_id),
                    config_dir=str(Path(registry.config_path(project_id)).parent),
                )
            )
    return summaries


def get_project(registry: ProjectRegistry, memory: Memory, project_id: str) -> ProjectDetail:
    if project_id not in registry.list_project_ids():
        raise ProjectNotFoundError(f"unknown project_id: {project_id}")
    config_path = resolve_registered_config_path(registry, project_id)
    config = load_config(config_path)
    summary = _summary_from_paths(registry, memory, project_id, config_path, config)
    root = project_root(registry)
    return ProjectDetail(
        **summary.model_dump(),
        config=config,
        provider_credentials_configured=_provider_credentials_status(config, root),
    )


def create_project(
    registry: ProjectRegistry,
    memory: Memory,
    req: CreateProjectRequest,
) -> ProjectSummary:
    _validate_project_id(req.project_id)
    if req.project_id in registry.list_project_ids():
        raise ProjectAlreadyExistsError(f"project_id '{req.project_id}' is already registered")

    directory = resolve_under_root(registry, req.config_dir)
    directory.mkdir(parents=True, exist_ok=True)
    config_path = config_file_in_dir(directory)

    config = req.config.model_copy(update={"project_id": req.project_id})
    config_path.write_text(json.dumps(config.model_dump(mode="json"), indent=2) + "\n")

    _persist_provider_credentials(registry, config, req.provider_credentials)

    registry.register(req.project_id, config_path)
    memory.ensure_project(req.project_id, req.name, config.base_url)
    return _summary_from_paths(registry, memory, req.project_id, config_path, config)


def update_project(
    registry: ProjectRegistry,
    memory: Memory,
    project_id: str,
    req: UpdateProjectRequest,
) -> ProjectSummary:
    if project_id not in registry.list_project_ids():
        raise ProjectNotFoundError(f"unknown project_id: {project_id}")

    config_path = resolve_registered_config_path(registry, project_id)
    config = req.config.model_copy(update={"project_id": project_id})
    config_path.write_text(json.dumps(config.model_dump(mode="json"), indent=2) + "\n")

    _persist_provider_credentials(registry, config, req.provider_credentials)

    if req.name is not None:
        if memory.get_project(project_id):
            memory.update_project(project_id, name=req.name, base_url=config.base_url)
        else:
            memory.ensure_project(project_id, req.name, config.base_url)
    elif memory.get_project(project_id):
        memory.update_project(project_id, base_url=config.base_url)

    return _summary_from_paths(registry, memory, project_id, config_path, config)


def delete_project(registry: ProjectRegistry, memory: Memory, project_id: str) -> dict:
    if project_id not in registry.list_project_ids():
        raise ProjectNotFoundError(f"unknown project_id: {project_id}")

    try:
        session_ids = memory.delete_project(project_id)
    except ValueError as e:
        raise ProjectDeleteBlockedError(str(e)) from e

    try:
        from suth.storage import delete_session_storage

        delete_session_storage(session_ids)
    except (KeyError, RuntimeError):
        # Storage is optional outside `specific dev`; DB/registry cleanup still applies.
        pass

    registry.unregister(project_id)
    return {"id": project_id, "deleted_sessions": len(session_ids)}


def inspect_config_dir(registry: ProjectRegistry, rel_dir: str) -> dict:
    preview = config_at(registry, rel_dir)
    if preview["config"] is not None:
        try:
            config = SuthConfig.model_validate(preview["config"])
            preview["config"] = config.model_dump(mode="json")
            preview["provider_credentials_configured"] = _provider_credentials_status(
                config, project_root(registry)
            )
        except ValidationError as e:
            raise InvalidProjectRequestError(f"invalid suth_config.json: {e}") from e
    return preview
