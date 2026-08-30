from typing import Literal

from pydantic import BaseModel, Field

AbandonmentTrigger = Literal[
    "no_dom_change_after_click",
    "repeated_step_loop",
    "frustration_score_exceeds",
]


class AbandonmentRule(BaseModel):
    trigger: AbandonmentTrigger
    threshold: int = Field(gt=0)


class Persona(BaseModel):
    """A versioned persona definition — see plan §3.1.

    The four pillars (objective, digital literacy, forbidden assumptions,
    abandonment rules) are hard constraints fed to the Brain's prompt, not
    suggestions the LLM can talk itself out of.
    """

    id: str
    name: str | None = None
    version: int = 1
    digital_literacy: Literal["low", "medium", "high"]
    device: Literal["mobile", "desktop"]
    # "keyboard" is enforced by the Driver (not just prompted): click actions
    # become focus+Enter and mouse-only actions like hover are rejected —
    # plan Phase 2 "screen-reader-only" persona.
    interaction_mode: Literal["pointer", "keyboard"] = "pointer"
    forbidden_assumptions: list[str] = Field(default_factory=list)
    abandonment_rules: list[AbandonmentRule] = Field(default_factory=list)
    objective_template: str = "{{objective}}"

    def render_objective(self, objective: str) -> str:
        return self.objective_template.replace("{{objective}}", objective)

    def rule(self, trigger: AbandonmentTrigger) -> AbandonmentRule | None:
        return next((r for r in self.abandonment_rules if r.trigger == trigger), None)
