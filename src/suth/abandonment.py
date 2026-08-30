from suth.brain.schema import StepDecision
from suth.driver.actions import ActionResult
from suth.personas.schema import Persona


class AbandonmentEvaluator:
    """Tracks cross-step state and decides when a persona's abandonment
    thresholds (plan §3.1/§4) have been crossed. Pure logic — no Driver/Brain
    dependency — so it's unit-testable against canned decisions.
    """

    def __init__(self, persona: Persona):
        self.persona = persona
        self.frustration_score = 0
        self._no_change_streak = 0
        self._recent_actions: list[tuple[str, str | None]] = []

    def observe(
        self, decision: StepDecision, action_result: ActionResult | None
    ) -> str | None:
        """Update state given one step's outcome. Returns a verdict string
        ("abandoned" | "stalled" | "repeated_action_loop" | "rage_quit") if a rule
        fired this step, else None to keep looping.
        """
        self.frustration_score = max(0, self.frustration_score + decision.frustration_delta)

        if decision.action.type == "abandon":
            return "abandoned"

        if decision.action.type == "click":
            dom_changed = bool(action_result and action_result.dom_changed)
            self._no_change_streak = 0 if dom_changed else self._no_change_streak + 1
            rule = self.persona.rule("no_dom_change_after_click")
            if rule and self._no_change_streak >= rule.threshold:
                return "stalled"

        self._recent_actions.append((decision.action.type, decision.action.target))
        loop_rule = self.persona.rule("repeated_step_loop")
        if loop_rule and len(self._recent_actions) >= loop_rule.threshold:
            window = self._recent_actions[-loop_rule.threshold :]
            if len(set(window)) == 1:
                return "repeated_action_loop"

        frustration_rule = self.persona.rule("frustration_score_exceeds")
        if frustration_rule and self.frustration_score >= frustration_rule.threshold:
            return "rage_quit"

        return None
