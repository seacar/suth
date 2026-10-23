import pytest

from suth.compare import compare_runs


class FakeMemory:
    def __init__(self, sessions: dict, failures: dict):
        self.sessions, self.failures = sessions, failures

    def get_session(self, session_id):
        return self.sessions.get(session_id)

    def get_failures(self, session_id):
        return self.failures.get(session_id, [])


def test_flags_regression_above_threshold():
    memory = FakeMemory(
        {"a": {"friction_score": 2.0}, "b": {"friction_score": 3.5}},
        {"b": [{"taxonomy_label": "dead_click"}, {"taxonomy_label": "dead_click"}]},
    )

    result = compare_runs(memory, "a", "b", regression_threshold=1.0)

    assert result.friction_delta == pytest.approx(1.5)
    assert result.regressed
    assert result.candidate_taxonomy_counts == {"dead_click": 2}
    assert not compare_runs(memory, "a", "b", regression_threshold=2.0).regressed


def test_missing_scores_count_as_zero_and_unknown_ids_raise():
    memory = FakeMemory({"a": {"friction_score": None}, "b": {"friction_score": 0.0}}, {})
    assert not compare_runs(memory, "a", "b").regressed
    with pytest.raises(KeyError, match="baseline"):
        compare_runs(memory, "nope", "b")
