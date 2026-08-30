import pytest

from suth.abandonment import AbandonmentEvaluator
from suth.brain.schema import Action, StepDecision
from suth.driver.actions import ActionResult
from suth.personas.schema import Persona


def make_persona() -> Persona:
    return Persona(
        id="test-persona",
        digital_literacy="low",
        device="mobile",
        forbidden_assumptions=[],
        abandonment_rules=[
            {"trigger": "no_dom_change_after_click", "threshold": 2},
            {"trigger": "repeated_step_loop", "threshold": 3},
            {"trigger": "frustration_score_exceeds", "threshold": 5},
        ],
    )


def decision(action_type="click", target="e1", frustration_delta=0) -> StepDecision:
    return StepDecision(
        thought="...",
        emotion="neutral",
        frustration_delta=frustration_delta,
        action=Action(type=action_type, target=target),
    )


def test_explicit_abandon_fires_immediately():
    evaluator = AbandonmentEvaluator(make_persona())
    result = evaluator.observe(decision(action_type="abandon", target=None), None)
    assert result == "abandoned"


def test_no_dom_change_after_click_threshold():
    evaluator = AbandonmentEvaluator(make_persona())
    stuck = ActionResult(ok=True, dom_changed=False)
    assert evaluator.observe(decision(target="e1"), stuck) is None  # streak 1
    assert evaluator.observe(decision(target="e1"), stuck) == "stalled"  # streak 2 == threshold


def test_dom_change_resets_streak():
    evaluator = AbandonmentEvaluator(make_persona())
    stuck = ActionResult(ok=True, dom_changed=False)
    moved = ActionResult(ok=True, dom_changed=True)
    # Distinct targets so the repeated_step_loop rule doesn't also fire here —
    # this test is only about the no_dom_change streak counter.
    assert evaluator.observe(decision(target="e1"), stuck) is None
    assert evaluator.observe(decision(target="e2"), moved) is None
    assert evaluator.observe(decision(target="e3"), stuck) is None  # streak restarted at 1


def test_repeated_step_loop_threshold():
    evaluator = AbandonmentEvaluator(make_persona())
    moved = ActionResult(ok=True, dom_changed=True)
    assert evaluator.observe(decision(action_type="hover", target="e2"), moved) is None
    assert evaluator.observe(decision(action_type="hover", target="e2"), moved) is None
    result = evaluator.observe(decision(action_type="hover", target="e2"), moved)
    assert result == "repeated_action_loop"


def test_frustration_score_exceeds_threshold():
    evaluator = AbandonmentEvaluator(make_persona())
    moved = ActionResult(ok=True, dom_changed=True)
    results = [
        evaluator.observe(decision(action_type="hover", target=f"e{i}", frustration_delta=3), moved)
        for i in range(3)
    ]
    assert results[-1] == "rage_quit"


def test_frustration_score_never_goes_negative():
    evaluator = AbandonmentEvaluator(make_persona())
    evaluator.observe(decision(frustration_delta=-3), ActionResult(ok=True, dom_changed=True))
    assert evaluator.frustration_score == 0
