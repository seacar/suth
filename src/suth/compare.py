from collections import Counter
from dataclasses import dataclass

from suth.db import Memory


@dataclass
class ComparisonResult:
    baseline_session_id: str
    candidate_session_id: str
    baseline_friction_score: float
    candidate_friction_score: float
    friction_delta: float
    baseline_taxonomy_counts: dict[str, int]
    candidate_taxonomy_counts: dict[str, int]
    regressed: bool


def _taxonomy_counts(memory: Memory, session_id: str) -> dict[str, int]:
    hits = memory.get_failures(session_id)
    return dict(Counter(h["taxonomy_label"] for h in hits))


def compare_runs(
    memory: Memory,
    baseline_session_id: str,
    candidate_session_id: str,
    regression_threshold: float = 0.0,
) -> ComparisonResult:
    """Diff two sessions' friction scores + taxonomy hits — plan §5.2/§8.
    `regressed` is true when the candidate's friction score exceeds the
    baseline's by more than `regression_threshold` (CI's gate).
    """
    baseline = memory.get_session(baseline_session_id)
    candidate = memory.get_session(candidate_session_id)
    if baseline is None:
        raise KeyError(f"unknown baseline session_id: {baseline_session_id}")
    if candidate is None:
        raise KeyError(f"unknown candidate session_id: {candidate_session_id}")

    baseline_score = baseline["friction_score"] or 0.0
    candidate_score = candidate["friction_score"] or 0.0
    delta = candidate_score - baseline_score

    return ComparisonResult(
        baseline_session_id=baseline_session_id,
        candidate_session_id=candidate_session_id,
        baseline_friction_score=baseline_score,
        candidate_friction_score=candidate_score,
        friction_delta=delta,
        baseline_taxonomy_counts=_taxonomy_counts(memory, baseline_session_id),
        candidate_taxonomy_counts=_taxonomy_counts(memory, candidate_session_id),
        regressed=delta > regression_threshold,
    )
