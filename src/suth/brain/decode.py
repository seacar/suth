"""Turning a provider's raw reply into a validated StepDecision, shared by
every Brain adapter so each one only owns its own transport."""

import json
from collections.abc import Callable
from typing import Any

from pydantic import ValidationError

from suth.brain.schema import StepDecision

NUDGE = (
    "That was not a single valid JSON object matching the contract. "
    "Respond again with ONLY the JSON object."
)


def parse_step_decision(raw: str) -> StepDecision:
    return StepDecision.model_validate(json.loads(raw))


def decide_with_retry(
    # Any: each provider has its own message TypedDict; this only appends
    # plain role/content turns, which every provider accepts.
    chat: Callable[[list[Any]], str], messages: list[Any], provider: str
) -> StepDecision:
    """One nudge-and-retry: models occasionally wrap JSON in prose or step
    outside the schema's bounds; ask once more before giving up loudly."""
    raw = chat(messages)
    try:
        return parse_step_decision(raw)
    except (json.JSONDecodeError, ValidationError):
        retry = [*messages, {"role": "assistant", "content": raw}, {"role": "user", "content": NUDGE}]
        raw2 = chat(retry)
        try:
            return parse_step_decision(raw2)
        except (json.JSONDecodeError, ValidationError) as e2:
            raise RuntimeError(f"{provider} returned invalid StepDecision JSON twice: {raw2!r}") from e2
