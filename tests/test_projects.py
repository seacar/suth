import json
from pathlib import Path

import pytest

from suth.config import SuthConfig
from suth.mcp_server.registry import ProjectRegistry
from suth.projects.filesystem import browse, config_at
from suth.projects.service import (
    CreateProjectRequest,
    ProjectAlreadyExistsError,
    create_project,
    default_config,
    inspect_config_dir,
)


class FakeMemory:
    def __init__(self):
        self.projects: dict[str, dict] = {}

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


@pytest.fixture
def registry(tmp_path):
    registry_path = tmp_path / "mcp_projects.json"
    registry_path.write_text("{}\n")
    return ProjectRegistry(registry_path)


def test_browse_lists_directories(registry, tmp_path):
    (tmp_path / "suth-test-app").mkdir()
    (tmp_path / "node_modules").mkdir()

    result = browse(registry, ".")

    assert result["path"] == "."
    assert result["abs_path"] == str(tmp_path.resolve())
    assert result["parent"] == str(tmp_path.resolve().parent)
    assert any(entry["name"] == "suth-test-app" for entry in result["entries"])
    assert all(entry["name"] != "node_modules" for entry in result["entries"])


def test_browse_accepts_absolute_path(registry, tmp_path):
    nested = tmp_path / "apps" / "demo"
    nested.mkdir(parents=True)

    result = browse(registry, str(nested))

    assert result["path"] == "./apps/demo"
    assert result["abs_path"] == str(nested.resolve())
    assert result["parent"] == "./apps"


def test_config_at_reports_missing_config(registry, tmp_path):
    (tmp_path / "new-app").mkdir()

    preview = config_at(registry, "./new-app")

    assert preview["exists"] is False
    assert preview["config"] is None
    assert preview["config_path"].endswith("new-app/suth_config.json")


def test_config_at_loads_existing_config(registry, tmp_path):
    app_dir = tmp_path / "existing-app"
    app_dir.mkdir()
    (app_dir / "suth_config.json").write_text(
        json.dumps(
            {
                "project_id": "existing-app",
                "base_url": "http://localhost:4000",
                "environments": {"dev": {"model": "default", "headed": True}},
                "llm_providers": {"default": {"provider": "ollama", "model": "llama3.2:3b"}},
            }
        )
    )

    preview = inspect_config_dir(registry, "./existing-app")

    assert preview["exists"] is True
    assert preview["config"]["base_url"] == "http://localhost:4000"


def test_create_project_writes_config_at_selected_dir(registry, tmp_path):
    memory = FakeMemory()
    target_dir = tmp_path / "apps" / "demo-app"
    config = default_config("demo-app", "http://localhost:3000")
    req = CreateProjectRequest(
        project_id="demo-app",
        name="Demo App",
        config_dir="./apps/demo-app",
        config=config,
    )
    summary = create_project(registry, memory, req)

    config_path = target_dir / "suth_config.json"
    assert config_path.is_file()
    assert summary.config_path == "./apps/demo-app/suth_config.json"
    assert registry.config_path("demo-app") == "./apps/demo-app/suth_config.json"
    assert memory.get_project("demo-app")["name"] == "Demo App"


def test_create_project_rejects_duplicate(registry):
    memory = FakeMemory()
    config = default_config("demo-app", "http://localhost:3000")
    req = CreateProjectRequest(
        project_id="demo-app",
        name="Demo App",
        config_dir="./apps/demo-app",
        config=config,
    )
    create_project(registry, memory, req)
    with pytest.raises(ProjectAlreadyExistsError):
        create_project(registry, memory, req)
