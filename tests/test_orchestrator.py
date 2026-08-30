import threading
import time
from concurrent.futures import Future
from types import SimpleNamespace

import pytest

from suth.orchestrator.service import BudgetExceededError, ConcurrencyLimitError, Orchestrator, _Handle
from suth.session import SessionResult


def fake_result(session_id: str) -> SessionResult:
    return SessionResult(
        session_id=session_id, persona_id="p", verdict="objective_met",
        step_count=1, final_frustration=0, friction_score=0.0,
    )


def make_orchestrator(**kwargs) -> Orchestrator:
    return Orchestrator(memory=None, max_concurrency=4, **kwargs)


def seed_running_handle(orchestrator: Orchestrator, project_id: str, caller: str | None = None) -> None:
    """A never-completing Future stands in for an in-flight session, so cap
    checks can be tested without ever touching a real Driver/Brain. state=
    "running" (not the "queued" default) since _active_count only counts
    sessions actually running, not ones still waiting for a slot."""
    handle = _Handle(session_id="fake", future=Future(), project_id=project_id, caller=caller, state="running")
    orchestrator._handles[handle.session_id] = handle


class ExplodingConfig:
    project_id = "proj"

    def __getattr__(self, name):
        raise AssertionError("start_session should have rejected before touching config")


def test_rejects_when_project_concurrency_cap_reached():
    orchestrator = make_orchestrator(max_per_project=1)
    seed_running_handle(orchestrator, project_id="proj")

    with pytest.raises(ConcurrencyLimitError, match="proj"):
        orchestrator.start_session(
            config=ExplodingConfig(), persona=None, objective="x", brain=None
        )


def test_rejects_when_caller_concurrency_cap_reached():
    orchestrator = make_orchestrator(max_per_caller=1)
    seed_running_handle(orchestrator, project_id="other-proj", caller="agent-1")

    class Config:
        project_id = "proj"

    with pytest.raises(ConcurrencyLimitError, match="agent-1"):
        orchestrator.start_session(
            config=Config(), persona=None, objective="x", brain=None, caller="agent-1"
        )


def test_project_cap_is_scoped_per_project():
    orchestrator = make_orchestrator(max_per_project=1)
    seed_running_handle(orchestrator, project_id="proj-a")

    # A different project shouldn't be blocked by proj-a being at capacity.
    # (Will actually attempt to submit — check only that it's not rejected
    # by the concurrency gate itself.)
    count_before = orchestrator._active_count(project_id="proj-b")
    assert count_before == 0


def test_no_memory_means_no_budget_check():
    orchestrator = make_orchestrator()
    # Should not raise even with no budget configured, since there's no
    # Memory to check against.
    orchestrator._check_budget("proj", "caller")


def test_budget_exceeded_error_message_mentions_project_and_caller():
    class FakeMemory:
        def get_budget(self, project_id, caller, period="all-time"):
            return {"token_cap": 100, "spend_to_date": 150}

    orchestrator = Orchestrator(memory=FakeMemory())
    with pytest.raises(BudgetExceededError, match="proj.*caller-x"):
        orchestrator._check_budget("proj", "caller-x")


# --- queue_if_full / batch fan-out ---------------------------------------
# These monkeypatch suth.orchestrator.service.run_session with a fast fake,
# so the real queuing/threading logic is exercised without a live Driver/Brain.


def test_queued_sessions_all_complete_without_deadlocking(monkeypatch):
    """Regression: an earlier draft counted queued-but-not-yet-running
    sessions toward their own cap check, so N queued sessions each waited
    for a slot that included themselves — none ever started. This submits
    more sessions than max_per_project and asserts they all finish."""

    def fake_run_session(**kwargs):
        time.sleep(0.02)
        return fake_result(kwargs["session_id"])

    monkeypatch.setattr("suth.orchestrator.service.run_session", fake_run_session)
    orchestrator = Orchestrator(memory=None, max_concurrency=6, max_per_project=2)
    config = SimpleNamespace(project_id="proj")

    session_ids = [
        orchestrator.start_session(
            config=config, persona=None, objective="x", brain=None,
            queue_if_full=True, session_id=f"s{i}",
        )
        for i in range(5)
    ]

    results = [orchestrator.get_report(sid) for sid in session_ids]
    assert len(results) == 5
    assert {r.session_id for r in results} == set(session_ids)


def test_queue_if_full_respects_project_cap(monkeypatch):
    concurrent = 0
    max_seen = 0
    lock = threading.Lock()

    def fake_run_session(**kwargs):
        nonlocal concurrent, max_seen
        with lock:
            concurrent += 1
            max_seen = max(max_seen, concurrent)
        time.sleep(0.05)
        with lock:
            concurrent -= 1
        return fake_result(kwargs["session_id"])

    monkeypatch.setattr("suth.orchestrator.service.run_session", fake_run_session)
    orchestrator = Orchestrator(memory=None, max_concurrency=6, max_per_project=2)
    config = SimpleNamespace(project_id="proj")
    session_ids = [
        orchestrator.start_session(
            config=config, persona=None, objective="x", brain=None,
            queue_if_full=True, session_id=f"s{i}",
        )
        for i in range(6)
    ]
    for sid in session_ids:
        orchestrator.get_report(sid)

    assert max_seen <= 2


def test_queue_if_full_ignores_caller_cap(monkeypatch):
    """Batch members share one caller (the originating request) — they
    shouldn't reject each other under max_per_caller=1."""

    def fake_run_session(**kwargs):
        time.sleep(0.01)
        return fake_result(kwargs["session_id"])

    monkeypatch.setattr("suth.orchestrator.service.run_session", fake_run_session)
    orchestrator = Orchestrator(memory=None, max_concurrency=6, max_per_project=6, max_per_caller=1)
    config = SimpleNamespace(project_id="proj")
    session_ids = [
        orchestrator.start_session(
            config=config, persona=None, objective="x", brain=None,
            queue_if_full=True, caller="batch-caller", session_id=f"s{i}",
        )
        for i in range(3)
    ]
    results = [orchestrator.get_report(sid) for sid in session_ids]

    assert len(results) == 3


def test_start_batch_returns_all_session_ids_and_reports(monkeypatch):
    def fake_run_session(**kwargs):
        return fake_result(kwargs["session_id"])

    monkeypatch.setattr("suth.orchestrator.service.run_session", fake_run_session)
    orchestrator = Orchestrator(memory=None, max_concurrency=6, max_per_project=6)
    config = SimpleNamespace(project_id="proj", base_url="http://x")

    batch_id = orchestrator.start_batch(
        config=config, personas=[None, None, None], objective="x",
        brain_factory=lambda: None,
    )

    session_ids = orchestrator.get_batch_session_ids(batch_id)
    assert len(session_ids) == 3

    members = orchestrator.get_batch_report(batch_id)
    assert len(members) == 3
    assert all(m.error is None for m in members)
    assert all(m.result.verdict == "objective_met" for m in members)


def test_batch_member_failure_does_not_hide_other_members(monkeypatch):
    """Regression: get_batch_report used to call get_report() in a list
    comprehension, so the first member's exception aborted the whole batch
    and hid every other member's (successful) result — caught live, not by
    a pre-existing test, when one persona's Ollama call failed mid-batch."""
    orchestrator = Orchestrator(memory=None, max_concurrency=6, max_per_project=6)
    config = SimpleNamespace(project_id="proj", base_url="http://x")

    good_persona = SimpleNamespace(id="good-persona")
    bad_persona = SimpleNamespace(id="bad-persona")

    # Only known once start_batch generates them, so decide who's "bad" by
    # persona_id rather than by a session_id predicted ahead of time.
    def fake_run_session(**kwargs):
        if kwargs["persona"] is bad_persona:
            raise RuntimeError("simulated provider error")
        return fake_result(kwargs["session_id"])

    monkeypatch.setattr("suth.orchestrator.service.run_session", fake_run_session)

    batch_id = orchestrator.start_batch(
        config=config, personas=[good_persona, bad_persona], objective="x",
        brain_factory=lambda: None,
    )

    members = orchestrator.get_batch_report(batch_id)
    assert len(members) == 2
    by_persona = {m.persona_id: m for m in members}
    assert by_persona["good-persona"].result is not None
    assert by_persona["good-persona"].error is None
    assert by_persona["bad-persona"].result is None
    assert "simulated provider error" in by_persona["bad-persona"].error
