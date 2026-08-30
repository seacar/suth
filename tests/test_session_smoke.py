import os
import uuid
from datetime import datetime, timezone

import pytest

from suth.db import Memory, get_engine

requires_db = pytest.mark.skipif(
    "DATABASE_URL" not in os.environ,
    reason="needs a live Postgres — run via `specific exec cli -- .venv/bin/python -m pytest`",
)


@requires_db
def test_session_round_trips_through_postgres():
    memory = Memory(get_engine())
    project_id = f"smoke-test-{uuid.uuid4().hex[:8]}"
    session_id = str(uuid.uuid4())

    memory.ensure_project(project_id, "Smoke Test Project", "http://localhost:8765")
    memory.create_session(
        session_id=session_id,
        project_id=project_id,
        persona_id="impatient-mobile-shopper-v2",
        objective="find a cheap listing",
        environment="dev",
        model_used="OllamaBrain",
    )

    for i in range(1, 4):
        memory.log_step(
            session_id=session_id,
            step_index=i,
            thought=f"thinking at step {i}",
            emotion="neutral",
            frustration_delta=1,
            action={"type": "click", "target": f"e{i}"},
            dom_snapshot_ref="http://localhost:8765/",
            screenshot_ref=f"sessions/{session_id}/step-{i:04d}.png",
        )

    memory.finish_session(session_id, status="completed", verdict="stalled", friction_score=3.0)

    session_row = memory.get_session(session_id)
    assert session_row is not None
    assert session_row["status"] == "completed"
    assert session_row["verdict"] == "stalled"

    steps = memory.get_steps(session_id)
    assert [s["step_index"] for s in steps] == [1, 2, 3]
    assert steps[0]["thought"] == "thinking at step 1"


@requires_db
def test_set_video_persists_ref_and_start_time():
    memory = Memory(get_engine())
    project_id = f"video-smoke-{uuid.uuid4().hex[:8]}"
    session_id = str(uuid.uuid4())

    memory.ensure_project(project_id, "Video Smoke Test", "http://localhost:8765")
    memory.create_session(
        session_id=session_id,
        project_id=project_id,
        persona_id="power-user-v1",
        objective="find a cheap listing",
        environment="dev",
        model_used="OllamaBrain",
    )

    started_at = datetime.now(timezone.utc)
    memory.set_video(session_id, f"sessions/{session_id}/replay.webm", started_at, 18.5)

    session_row = memory.get_session(session_id)
    assert session_row["video_ref"] == f"sessions/{session_id}/replay.webm"
    assert session_row["video_started_at"] is not None
    assert session_row["video_duration_seconds"] == 18.5
