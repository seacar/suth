from dataclasses import dataclass

from suth.brain.history import StepRecord

# The seven labels from plan Phase 2. `objective_met` is the only non-failure
# outcome, so it never produces a `failures` row — see classify_session.
TAXONOMY_LABELS = (
    "dead_click",
    "label_ambiguity",
    "navigation_loop",
    "timeout_abandonment",
    "rage_quit",
    "silent_failure",
    "objective_met",
)


@dataclass
class FailureHit:
    taxonomy_label: str
    step_index: int
    detail: str


def _find_incidents(steps: list[StepRecord]) -> list[FailureHit]:
    hits: list[FailureHit] = []
    for s in steps:
        if s.action_type == "declare_confusion":
            hits.append(FailureHit("label_ambiguity", s.step_index, "persona declared confusion"))
        elif s.action_type == "click" and not s.dom_changed:
            hits.append(FailureHit("dead_click", s.step_index, "click produced no visible DOM change"))

    for i in range(2, len(steps)):
        current, prev, two_ago = steps[i], steps[i - 1], steps[i - 2]
        # A->B->A: only counts if the URL actually moved away and back. On a
        # single-page app whose URL never changes, current.url == two_ago.url
        # is true on almost every step and would false-positive constantly —
        # requiring current.url != prev.url rules that out.
        left_and_returned = current.url and current.url == two_ago.url and current.url != prev.url
        if left_and_returned and current.action_type != "declare_confusion":
            hits.append(
                FailureHit("navigation_loop", current.step_index, f"returned to {current.url}")
            )
    return hits


def classify_session(
    steps: list[StepRecord], stop_reason: str, objective_check_configured: bool
) -> tuple[str, list[FailureHit]]:
    """Post-session classifier — a pure function over the recorded transcript,
    so it's testable against canned golden transcripts with no live LLM call.

    `stop_reason` is whatever ended the loop: an AbandonmentEvaluator verdict
    ("abandoned"/"stalled"/"repeated_action_loop"/"rage_quit"), "objective_met"
    (the Driver-side assertion passed), or "timeout" (max_steps exhausted).
    """
    hits = _find_incidents(steps)

    if stop_reason == "objective_met":
        verdict = "objective_met"
    elif stop_reason == "timeout":
        # Without a configured assertion we can't tell success from silent
        # failure — only claim silent_failure when we know what to check for.
        verdict = "silent_failure" if objective_check_configured else "timeout_abandonment"
    elif stop_reason in ("abandoned", "rage_quit"):
        verdict = "rage_quit"
    elif stop_reason == "stalled":
        verdict = "dead_click"
    elif stop_reason == "repeated_action_loop":
        tail = steps[-3:] if len(steps) >= 3 else steps
        tail_types = {s.action_type for s in tail}
        tail_urls = {s.url for s in tail}
        if tail_types == {"declare_confusion"}:
            verdict = "label_ambiguity"
        elif len(tail_urls) > 1:
            # The repeated action actually moved between distinct URLs.
            verdict = "navigation_loop"
        else:
            # Same action repeated on a page whose URL never changed — e.g.
            # mashing a button on a single-page app. Closer to a dead control
            # than a navigation loop.
            verdict = "dead_click"
    else:
        verdict = stop_reason

    return verdict, hits
