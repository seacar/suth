import anthropic
from anthropic.types.beta import BetaMessageParam

from suth.brain.decode import decide_with_retry
from suth.brain.interface import ProviderProfile, resolve_credential
from suth.brain.prompt import system_prompt, user_prompt
from suth.brain.schema import StepDecision
from suth.driver.browser import DomState
from suth.personas.schema import Persona

# Models that accept server-side refusal fallbacks in their "default" form:
# on a safety-classifier decline the API re-runs the step on a fallback model
# inside the same call, instead of the session dying on one refused step.
FALLBACK_MODELS = frozenset({"claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5"})
FALLBACK_BETA = "server-side-fallback-2026-07-01"

# One step is one short JSON decision — well under this, but leave room for
# adaptive thinking, which these models can't switch off.
MAX_TOKENS = 16000
STEP_SCHEMA = anthropic.transform_schema(StepDecision)


class AnthropicBrain:
    """Claude backend. Structured outputs constrain the reply to the
    StepDecision schema; decode.decide_with_retry still validates the bounds
    the schema can't express (e.g. frustration_delta in -5..5)."""

    def __init__(self, profile: ProviderProfile):
        self.model = profile.model
        api_key = resolve_credential(profile.credential) if profile.credential else None
        self._client = anthropic.Anthropic(
            api_key=api_key,  # None falls back to the SDK's own env/profile resolution
            base_url=profile.base_url,
            timeout=180.0,
        )
        self._total_tokens = 0

    def token_usage(self) -> int:
        """Cumulative tokens processed across this instance's calls (cached
        input included) — read by the Orchestrator to record budget spend."""
        return self._total_tokens

    def generate_step(
        self, persona: Persona, objective: str, history_text: str, dom_state: DomState
    ) -> StepDecision:
        system = system_prompt(persona, objective)
        messages: list[BetaMessageParam] = [{"role": "user", "content": user_prompt(history_text, dom_state)}]
        return decide_with_retry(lambda m: self._chat(system, m), messages, provider="anthropic")

    def _chat(self, system: str, messages: list[BetaMessageParam]) -> str:
        extra: dict = {}
        if self.model in FALLBACK_MODELS:
            extra = {"betas": [FALLBACK_BETA], "fallbacks": "default"}
        response = self._client.beta.messages.create(
            model=self.model,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=messages,
            output_config={
                "effort": "medium",
                "format": {"type": "json_schema", "schema": STEP_SCHEMA},
            },
            **extra,
        )
        usage = response.usage
        self._total_tokens += (
            usage.input_tokens
            + usage.output_tokens
            + (usage.cache_creation_input_tokens or 0)
            + (usage.cache_read_input_tokens or 0)
        )
        if response.stop_reason == "refusal":
            category = response.stop_details.category if response.stop_details else None
            raise RuntimeError(f"anthropic refused the step (category: {category})")
        if response.stop_reason == "max_tokens":
            raise RuntimeError(f"anthropic hit max_tokens ({MAX_TOKENS}) before finishing the step")
        return next((b.text for b in response.content if b.type == "text"), "")
