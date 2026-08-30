from typing import Literal

from pydantic import BaseModel, Field

ActionType = Literal[
    "click",
    "type",
    "scroll",
    "hover",
    "go_back",
    "zoom",
    "declare_confusion",
    "abandon",
]


class Action(BaseModel):
    type: ActionType
    target: str | None = None
    text: str | None = None
    direction: Literal["up", "down"] | None = None


class StepDecision(BaseModel):
    """The LLM's structured decision for one state-machine step — plan §4 step 3."""

    thought: str
    emotion: str
    frustration_delta: int = Field(ge=-5, le=5)
    action: Action
