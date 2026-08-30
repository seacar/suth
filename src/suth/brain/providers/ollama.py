import json

import httpx

from suth.brain.interface import ProviderProfile
from suth.brain.prompt import system_prompt, user_prompt
from suth.brain.schema import StepDecision
from suth.driver.browser import DomState
from suth.personas.schema import Persona

DEFAULT_BASE_URL = "http://localhost:11434"


class OllamaBrain:
    """MVP default backend — local, no credential required (plan §5.5)."""

    def __init__(self, profile: ProviderProfile):
        self.model = profile.model
        self.base_url = profile.base_url or DEFAULT_BASE_URL
        self._client = httpx.Client(base_url=self.base_url, timeout=120)
        self._total_tokens = 0

    def token_usage(self) -> int:
        """Cumulative prompt+completion tokens across this instance's calls —
        read by the Orchestrator to record spend against a budget (plan §9)."""
        return self._total_tokens

    def generate_step(
        self, persona: Persona, objective: str, history_text: str, dom_state: DomState
    ) -> StepDecision:
        messages = [
            {"role": "system", "content": system_prompt(persona, objective)},
            {"role": "user", "content": user_prompt(history_text, dom_state)},
        ]
        raw = self._chat(messages)
        try:
            return StepDecision.model_validate(json.loads(raw))
        except (json.JSONDecodeError, ValueError) as e:
            # One nudge-and-retry: models occasionally wrap JSON in prose despite
            # format="json"; ask once more before giving up loudly.
            messages.append({"role": "assistant", "content": raw})
            messages.append(
                {
                    "role": "user",
                    "content": "That was not a single valid JSON object matching the "
                    "contract. Respond again with ONLY the JSON object.",
                }
            )
            raw2 = self._chat(messages)
            try:
                return StepDecision.model_validate(json.loads(raw2))
            except (json.JSONDecodeError, ValueError) as e2:
                raise RuntimeError(
                    f"ollama returned invalid StepDecision JSON twice: {raw2!r}"
                ) from e2

    def _chat(self, messages: list[dict]) -> str:
        resp = self._client.post(
            "/api/chat",
            json={
                "model": self.model,
                "messages": messages,
                "format": "json",
                "stream": False,
            },
        )
        resp.raise_for_status()
        body = resp.json()
        self._total_tokens += body.get("prompt_eval_count", 0) + body.get("eval_count", 0)
        return body["message"]["content"]
