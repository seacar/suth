from pathlib import Path

import pytest

from suth.mcp_server.registry import ProjectRegistry
from suth.projects.service import CreateProjectRequest, create_project, get_project
from tests.test_projects import FakeMemory


@pytest.fixture
def registry(tmp_path):
    registry_path = tmp_path / "mcp_projects.json"
    registry_path.write_text("{}\n")
    return ProjectRegistry(registry_path)


def test_create_project_persists_provider_credentials(registry, tmp_path):
    memory = FakeMemory()
    request = CreateProjectRequest.model_validate(
        {
            "project_id": "remote-app",
            "name": "Remote App",
            "config_dir": "./remote-app",
            "config": {
                "project_id": "remote-app",
                "base_url": "http://localhost:3000",
                "environments": {"dev": {"model": "default", "headed": True, "max_steps": 20}},
                "llm_providers": {
                    "default": {
                        "provider": "anthropic",
                        "model": "claude-sonnet-4-20250514",
                        "credential": "env:ANTHROPIC_API_KEY",
                    }
                },
            },
            "provider_credentials": {"env:ANTHROPIC_API_KEY": "sk-test"},
        }
    )

    create_project(registry, memory, request)

    config_path = tmp_path / "remote-app" / "suth_config.json"
    assert config_path.is_file()
    credentials_path = tmp_path / ".suth" / "credentials.json"
    assert credentials_path.is_file()

    detail = get_project(registry, memory, "remote-app")
    assert detail.provider_credentials_configured["env:ANTHROPIC_API_KEY"] is True
