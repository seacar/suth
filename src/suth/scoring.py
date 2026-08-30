from suth.taxonomy import FailureHit

# Fixed starter weights (plan Phase 2: "start with simple fixed weights, tune
# later"). objective_met carries no penalty since it isn't a failure.
TAXONOMY_PENALTIES: dict[str, float] = {
    "dead_click": 2.0,
    "label_ambiguity": 1.5,
    "navigation_loop": 3.0,
    "timeout_abandonment": 4.0,
    "rage_quit": 5.0,
    "silent_failure": 6.0,
    "objective_met": 0.0,
}


def friction_score(frustration_total: int, verdict: str, hits: list[FailureHit]) -> float:
    """Weighted sum of frustration deltas + a penalty per taxonomy hit,
    including the session's terminal verdict itself."""
    penalty = sum(TAXONOMY_PENALTIES.get(h.taxonomy_label, 0.0) for h in hits)
    penalty += TAXONOMY_PENALTIES.get(verdict, 0.0)
    return float(frustration_total) + penalty
