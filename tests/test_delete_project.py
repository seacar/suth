import json

import pytest

from suth.mcp_server.registry import ProjectRegistry, UnregisteredProjectError
from suth.projects.service import (
    CreateProjectRequest,
    ProjectDeleteBlockedError,
    ProjectNotFoundError,
    create_project,
    default_config,
    delete_project,
)


class FakeMemory:
    def __init__(self):
        self.projects: dict[str, dict] = {}
        self.running_projects: set[str] = set()
        self.deleted: list[str] = []

    def ensure_project(self, project_id: str, name: str, base_url: str) -> None:
        self.projects[project_id] = {"id": project_id, "name": name, "base_url": base_url}

    def get_project(self, project_id: str) -> dict | None:
        return self.projects.get(project_id)

    def update_project(self, project_id: str, *, name: str | None = None, base_url: str | None = None) -> None:
        row = self.projects.setdefault(project_id, {"id": project_id, "name": project_id, "base_url": ""})
        if name is not None:
            row["name"] = name
        if base_url is not None:
            row["base_url"] = base_url

    def delete_project(self, project_id: str) -> list[str]:
        if project_id in self.running_projects:
            raise ValueError(f"project '{project_id}' has a running session")
        self.deleted.append(project_id)
        self.projects.pop(project_id, None)
        return ["session-1", "session-2"]


@pytest.fixture
def registry(tmp_path):
    registry_path = tmp_path / "mcp_projects.json"
    registry_path.write_text("{}\n")
    return ProjectRegistry(registry_path)


def test_delete_project_unregisters_and_clears_db(registry, tmp_path):
    memory = FakeMemory()
    target_dir = tmp_path / "demo-app"
    target_dir.mkdir()
    config_path = target_dir / "suth_config.json"
    config_path.write_text("{}\n")

    req = CreateProjectRequest(
        project_id="demo-app",
        name="Demo App",
        config_dir="./demo-app",
        config=default_config("demo-app", "http://localhost:3000"),
    )
    create_project(registry, memory, req)

    result = delete_project(registry, memory, "demo-app")

    assert result == {"id": "demo-app", "deleted_sessions": 2}
    assert memory.deleted == ["demo-app"]
    assert "demo-app" not in registry.list_project_ids()
    assert config_path.is_file()


def test_delete_project_unknown(registry):
    memory = FakeMemory()
    with pytest.raises(ProjectNotFoundError):
        delete_project(registry, memory, "missing")


def test_delete_project_blocks_running_session(registry, tmp_path):
    memory = FakeMemory()
    target_dir = tmp_path / "demo-app"
    target_dir.mkdir()
    (target_dir / "suth_config.json").write_text("{}\n")

    req = CreateProjectRequest(
        project_id="demo-app",
        name="Demo App",
        config_dir="./demo-app",
        config=default_config("demo-app", "http://localhost:3000"),
    )
    create_project(registry, memory, req)
    memory.running_projects.add("demo-app")

    with pytest.raises(ProjectDeleteBlockedError, match="running session"):
        delete_project(registry, memory, "demo-app")

    assert "demo-app" in registry.list_project_ids()


def test_registry_unregister(registry, tmp_path):
    registry_path = registry.path
    registry._entries = {"demo-app": "./demo-app/suth_config.json"}
    registry_path.write_text(json.dumps(registry._entries) + "\n")

    registry.unregister("demo-app")

    assert registry.list_project_ids() == []
    with pytest.raises(UnregisteredProjectError):
        registry.config_path("demo-app")
