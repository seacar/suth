import os
import uuid

import pytest

from suth.compare import compare_runs
from suth.db import Memory, get_engine

requires_db = pytest.mark.skipif(
    "DATABASE_URL" not in os.environ,
    reason="needs a live Postgres — run via `specific exec cli -- .venv/bin/python -m pytest`",
)


def make_session(memory: Memory, project_id: str, friction_score: float, taxonomy_label: str) -> str:
    session_id = str(uuid.uuid4())
    memory.ensure_project(project_id, project_id, "http://localhost:8765")
    memory.create_session(
        session_id=session_id,
        project_id=project_id,
        persona_id="impatient-mobile-shopper-v2",
        objective="obj",
        environment="ci",
        model_used="OllamaBrain",
    )
    memory.finish_session(session_id, status="completed", verdict=taxonomy_label, friction_score=friction_score)
    return session_id


@requires_db
def test_budget_blocks_once_spend_reaches_cap():
    memory = Memory(get_engine())
    project_id = f"budget-test-{uuid.uuid4().hex[:8]}"
    memory.ensure_project(project_id, project_id, "http://localhost:8765")
    memory.set_budget(project_id, "ci-runner", token_cap=1000)

    assert memory.get_budget(project_id, "ci-runner")["spend_to_date"] == 0

    memory.record_spend(project_id, "ci-runner", 400)
    budget = memory.get_budget(project_id, "ci-runner")
    assert budget["spend_to_date"] == 400
    assert budget["spend_to_date"] < budget["token_cap"]

    memory.record_spend(project_id, "ci-runner", 700)
    budget = memory.get_budget(project_id, "ci-runner")
    assert budget["spend_to_date"] == 1100
    assert budget["spend_to_date"] >= budget["token_cap"]


@requires_db
def test_record_spend_is_noop_without_a_declared_budget():
    memory = Memory(get_engine())
    project_id = f"budget-test-{uuid.uuid4().hex[:8]}"
    memory.ensure_project(project_id, project_id, "http://localhost:8765")
    memory.record_spend(project_id, "nobody", 500)  # no budget row exists
    assert memory.get_budget(project_id, "nobody") is None


@requires_db
def test_compare_runs_flags_regression_past_threshold():
    memory = Memory(get_engine())
    project_id = f"compare-test-{uuid.uuid4().hex[:8]}"
    baseline = make_session(memory, project_id, friction_score=5.0, taxonomy_label="objective_met")
    candidate = make_session(memory, project_id, friction_score=20.0, taxonomy_label="dead_click")

    comparison = compare_runs(memory, baseline, candidate, regression_threshold=2.0)

    assert comparison.friction_delta == 15.0
    assert comparison.regressed is True


@requires_db
def test_compare_runs_within_threshold_is_not_a_regression():
    memory = Memory(get_engine())
    project_id = f"compare-test-{uuid.uuid4().hex[:8]}"
    baseline = make_session(memory, project_id, friction_score=5.0, taxonomy_label="objective_met")
    candidate = make_session(memory, project_id, friction_score=6.0, taxonomy_label="objective_met")

    comparison = compare_runs(memory, baseline, candidate, regression_threshold=2.0)

    assert comparison.regressed is False
