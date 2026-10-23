import json

import pytest

from suth.mcp_server.registry import ProjectRegistry
from suth.projects.filesystem import PathNotAllowedError, browse, config_at
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


def test_browse_lists_directories(registry, tmp_path, monkeypatch):
    monkeypatch.setenv("SUTH_BROWSE_ROOTS", str(tmp_path.parent))
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


def test_browse_rejects_paths_outside_allowed_roots(registry, tmp_path, monkeypatch):
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    monkeypatch.setenv("SUTH_BROWSE_ROOTS", str(tmp_path / "nowhere"))

    with pytest.raises(PathNotAllowedError):
        browse(registry, str(outside))
    with pytest.raises(PathNotAllowedError):
        browse(registry, "../" + outside.name)  # `..` is resolved before the check
    with pytest.raises(PathNotAllowedError):
        config_at(registry, "/etc")


def test_browse_hides_parent_outside_allowed_roots(registry, tmp_path, monkeypatch):
    monkeypatch.setenv("SUTH_BROWSE_ROOTS", str(tmp_path / "nowhere"))

    assert browse(registry, ".")["parent"] is None


def test_create_project_rejects_dir_outside_allowed_roots(registry, tmp_path, monkeypatch):
    monkeypatch.setenv("SUTH_BROWSE_ROOTS", str(tmp_path / "nowhere"))
    target = tmp_path.parent / f"{tmp_path.name}-escape"
    req = CreateProjectRequest(
        project_id="escape",
        name="Escape",
        config_dir=str(target),
        config=default_config("escape", "http://localhost:9999"),
    )

    with pytest.raises(PathNotAllowedError):
        create_project(registry, FakeMemory(), req)
    assert not target.exists()


def test_registry_resolves_relative_config_against_registry_dir(registry, tmp_path, monkeypatch):
    config_dir = tmp_path / "apps" / "demo-app"
    config_dir.mkdir(parents=True)
    (config_dir / "suth_config.json").write_text("{}")
    registry.register("demo-app", config_dir / "suth_config.json")
    monkeypatch.chdir(tmp_path / "apps")  # cwd must not matter

    assert registry.resolved_config_path("demo-app") == (config_dir / "suth_config.json").resolve()


def test_registry_sees_projects_registered_by_another_process(registry, tmp_path):
    other = ProjectRegistry(registry.path)
    config = tmp_path / "suth_config.json"
    config.write_text("{}")
    other.register("late-app", config)

    assert "late-app" in registry.list_project_ids()
