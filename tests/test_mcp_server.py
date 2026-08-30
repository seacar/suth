import os
import uuid

import pytest
from mcp.server.mcpserver.exceptions import ToolError

requires_db = pytest.mark.skipif(
    "DATABASE_URL" not in os.environ,
    reason="needs a live Postgres — run via `specific exec cli -- .venv/bin/python -m pytest`",
)

# Imported lazily inside tests, not at module scope: importing suth.mcp_server.server
# connects to Postgres immediately (constructs a live Memory/Orchestrator), so it
# must not happen at collection time when DATABASE_URL isn't set.


@requires_db
def test_run_audit_rejects_unregistered_project_id():
    from suth.mcp_server.server import run_audit

    with pytest.raises(ToolError, match="not registered"):
        run_audit(
            project_id="../../etc/passwd",
            persona_id="impatient-mobile-shopper-v2",
            objective="x",
            environment="ci",
        )


@requires_db
def test_run_audit_rejects_dev_environment():
    from suth.mcp_server.server import run_audit

    with pytest.raises(ToolError, match="'dev'"):
        run_audit(
            project_id="suth-test-app",
            persona_id="impatient-mobile-shopper-v2",
            objective="x",
            environment="dev",
        )


@requires_db
def test_run_audit_rejects_bad_mode():
    from suth.mcp_server.server import run_audit

    with pytest.raises(ToolError, match="mode"):
        run_audit(
            project_id="suth-test-app",
            persona_id="impatient-mobile-shopper-v2",
            objective="x",
            environment="ci",
            mode="destroy-everything",
        )


@requires_db
def test_run_audit_rejects_when_budget_exhausted():
    from suth.db import Memory, get_engine
    from suth.mcp_server.server import run_audit

    memory = Memory(get_engine())
    memory.ensure_project("suth-test-app", "suth-test-app", "http://localhost:8765")
    caller = f"malicious-caller-{uuid.uuid4().hex[:8]}"
    memory.set_budget("suth-test-app", caller, token_cap=0)

    os.environ["SUTH_MCP_CALLER"] = caller
    try:
        with pytest.raises(ToolError, match="budget exceeded"):
            run_audit(
                project_id="suth-test-app",
                persona_id="impatient-mobile-shopper-v2",
                objective="x",
                environment="ci",
            )
    finally:
        del os.environ["SUTH_MCP_CALLER"]


@requires_db
def test_list_projects_returns_registry_contents():
    from suth.mcp_server.server import list_projects

    assert "suth-test-app" in list_projects()


@requires_db
def test_create_persona_validates_and_versions():
    from suth.mcp_server.server import create_persona

    persona_id = f"mcp-created-{uuid.uuid4().hex[:8]}"
    result = create_persona(
        {
            "id": persona_id,
            "digital_literacy": "medium",
            "device": "desktop",
            "abandonment_rules": [{"trigger": "frustration_score_exceeds", "threshold": 5}],
        }
    )
    assert result["version"] == 1
    assert result["changed"] is True

    # Re-creating with identical content should not bump the version.
    result2 = create_persona(
        {
            "id": persona_id,
            "digital_literacy": "medium",
            "device": "desktop",
            "abandonment_rules": [{"trigger": "frustration_score_exceeds", "threshold": 5}],
        }
    )
    assert result2["version"] == 1
    assert result2["changed"] is False


@requires_db
def test_create_persona_rejects_invalid_definition():
    from suth.mcp_server.server import create_persona

    with pytest.raises(ToolError, match="invalid persona definition"):
        create_persona({"id": "bad", "digital_literacy": "expert", "device": "mobile"})


@requires_db
def test_run_audit_matrix_rejects_dev_environment():
    from suth.mcp_server.server import run_audit_matrix

    with pytest.raises(ToolError, match="'dev'"):
        run_audit_matrix(
            project_id="suth-test-app",
            persona_ids=["power-user-v1", "elderly-low-vision-v1"],
            objective="x",
            environment="dev",
        )


@requires_db
def test_run_audit_matrix_rejects_unregistered_project():
    from suth.mcp_server.server import run_audit_matrix

    with pytest.raises(ToolError, match="not registered"):
        run_audit_matrix(
            project_id="not-a-real-project",
            persona_ids=["power-user-v1"],
            objective="x",
            environment="ci",
        )


@requires_db
def test_run_audit_matrix_rejects_empty_persona_list():
    from suth.mcp_server.server import run_audit_matrix

    with pytest.raises(ToolError, match="non-empty"):
        run_audit_matrix(project_id="suth-test-app", persona_ids=[], objective="x", environment="ci")


@requires_db
def test_run_audit_matrix_rejects_unknown_persona_before_starting_anything():
    from suth.mcp_server.server import run_audit_matrix

    with pytest.raises(ToolError, match="not found in Postgres"):
        run_audit_matrix(
            project_id="suth-test-app",
            persona_ids=["power-user-v1", "definitely-not-a-real-persona"],
            objective="x",
            environment="ci",
        )
