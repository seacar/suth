from suth.brain.history import StepRecord
from suth.taxonomy import classify_session


def step(i, action_type, target=None, dom_changed=True, url="http://x/", thought="...") -> StepRecord:
    return StepRecord(
        step_index=i, thought=thought, action_type=action_type, target=target,
        dom_changed=dom_changed, url=url,
    )


def test_dead_click_transcript():
    steps = [
        step(1, "click", "e1", dom_changed=False),
        step(2, "click", "e1", dom_changed=False),
    ]
    verdict, hits = classify_session(steps, stop_reason="stalled", objective_check_configured=False)
    assert verdict == "dead_click"
    assert [h.taxonomy_label for h in hits] == ["dead_click", "dead_click"]


def test_label_ambiguity_transcript():
    steps = [
        step(1, "hover", "e1"),
        step(2, "declare_confusion"),
        step(3, "declare_confusion"),
        step(4, "declare_confusion"),
    ]
    verdict, hits = classify_session(
        steps, stop_reason="repeated_action_loop", objective_check_configured=False
    )
    assert verdict == "label_ambiguity"
    assert [h.taxonomy_label for h in hits] == ["label_ambiguity"] * 3


def test_navigation_loop_transcript():
    steps = [
        step(1, "click", "e1", url="http://x/a"),
        step(2, "click", "e2", url="http://x/b"),
        step(3, "click", "e1", url="http://x/a"),  # revisits step 1's URL
        step(4, "click", "e2", url="http://x/b"),  # revisits step 2's URL
    ]
    verdict, hits = classify_session(
        steps, stop_reason="repeated_action_loop", objective_check_configured=False
    )
    assert verdict == "navigation_loop"
    labels = [h.taxonomy_label for h in hits]
    assert labels.count("navigation_loop") == 2


def test_timeout_without_objective_check_is_timeout_abandonment():
    steps = [step(1, "hover", "e1")]
    verdict, _ = classify_session(steps, stop_reason="timeout", objective_check_configured=False)
    assert verdict == "timeout_abandonment"


def test_timeout_with_objective_check_is_silent_failure():
    steps = [step(1, "hover", "e1")]
    verdict, _ = classify_session(steps, stop_reason="timeout", objective_check_configured=True)
    assert verdict == "silent_failure"


def test_explicit_abandon_is_rage_quit():
    steps = [step(1, "hover", "e1")]
    verdict, _ = classify_session(steps, stop_reason="abandoned", objective_check_configured=False)
    assert verdict == "rage_quit"


def test_frustration_ceiling_is_rage_quit():
    steps = [step(1, "hover", "e1")]
    verdict, _ = classify_session(steps, stop_reason="rage_quit", objective_check_configured=True)
    assert verdict == "rage_quit"


def test_constant_url_repeated_click_is_dead_click_not_navigation_loop():
    # Regression: on a single-page app the URL never changes, so a naive
    # "revisited a prior URL" check would false-positive on every step.
    steps = [step(i, "click", "e1", dom_changed=True) for i in range(1, 5)]
    verdict, hits = classify_session(
        steps, stop_reason="repeated_action_loop", objective_check_configured=False
    )
    assert verdict == "dead_click"
    assert not any(h.taxonomy_label == "navigation_loop" for h in hits)


def test_constant_url_produces_no_navigation_loop_incidents():
    steps = [step(i, "hover", f"e{i}") for i in range(1, 6)]
    _, hits = classify_session(steps, stop_reason="timeout", objective_check_configured=False)
    assert not any(h.taxonomy_label == "navigation_loop" for h in hits)


def test_objective_met_transcript_has_no_hits():
    steps = [
        step(1, "click", "e1", url="http://x/a"),
        step(2, "click", "e2", url="http://x/b"),
    ]
    verdict, hits = classify_session(steps, stop_reason="objective_met", objective_check_configured=True)
    assert verdict == "objective_met"
    assert hits == []
