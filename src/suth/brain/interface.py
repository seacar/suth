from typing import TYPE_CHECKING, Protocol

from pydantic import BaseModel

from suth.brain.schema import StepDecision
from suth.credentials import resolve_credential as _resolve_credential
from suth.personas.schema import Persona

if TYPE_CHECKING:
    # Deferred to break the driver<->brain import cycle (driver.browser needs
    # brain.schema.Action; brain.interface needs driver.browser.DomState) —
    # this is a type-only reference, never a runtime one.
    from suth.driver.browser import DomState


class ProviderProfile(BaseModel):
    """One named entry from `suth_config.json`'s `llm_providers` block — plan §5.5."""

    provider: str
    model: str
    base_url: str | None = None
    credential: str | None = None


def resolve_credential(ref: str) -> str:
    """Resolve a credential reference like `env:ANTHROPIC_API_KEY`.

    Raises a clear error at startup rather than failing confusingly mid-session,
    per plan §5.5.
    """
    return _resolve_credential(ref)


class Brain(Protocol):
    """Provider-agnostic interface the state machine talks to — plan §2/§5.5.

    Concrete backends (Ollama now; Anthropic/OpenAI in Phase 6) are pure adapters
    behind this interface — adding one never touches the state machine, taxonomy,
    or scoring.
    """

    def generate_step(
        self, persona: Persona, objective: str, history_text: str, dom_state: "DomState"
    ) -> StepDecision: ...


def get_brain(profile: ProviderProfile) -> Brain:
    if profile.credential:
        resolve_credential(profile.credential)  # fail fast if missing

    if profile.provider == "ollama":
        from suth.brain.providers.ollama import OllamaBrain

        return OllamaBrain(profile)

    # Seam for Phase 6: adding a provider means writing one adapter here, not
    # touching the state machine, taxonomy, or scoring.
    raise NotImplementedError(
        f"provider '{profile.provider}' has no adapter yet — only 'ollama' is "
        "implemented (Phase 1); add suth.brain.providers.{profile.provider} in Phase 6"
    )
