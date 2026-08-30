import json
from pathlib import Path

from pydantic import BaseModel

from suth.brain.interface import ProviderProfile

DEFAULT_MAX_STEPS = 40
# Wall-clock cap on a single session, independent of max_steps — a step can
# stay within its own per-call bounds (Playwright's ~30s default, the LLM
# provider's own timeout) yet a run can still take unreasonably long once
# enough steps stack up. This is the backstop that guarantees every run
# reaches a verdict instead of running indefinitely. See session.py.
DEFAULT_TIMEOUT_SECONDS = 300


class AuthConfig(BaseModel):
    type: str = "storage_state"
    path: str


class EnvironmentOverlay(BaseModel):
    base_url: str | None = None
    headed: bool | None = None
    headless: bool | None = None
    model: str | None = None
    max_steps: int | None = None
    timeout_seconds: int | None = None
    token_cap: int | None = None
    record_video: bool | None = None


class ResolvedRunConfig(BaseModel):
    project_id: str
    base_url: str
    headed: bool
    provider_profile: ProviderProfile
    max_steps: int
    timeout_seconds: int
    auth: AuthConfig | None = None
    record_video: bool = True


class SuthConfig(BaseModel):
    """Matches plan §5.4's `suth_config.json` shape. Only the `dev` environment
    is required for Phase 1 — `ci`/`agent` overlays can be added without code
    changes once Phase 3 needs them.
    """

    project_id: str
    base_url: str
    auth: AuthConfig | None = None
    default_personas: list[str] = []
    environments: dict[str, EnvironmentOverlay] = {}
    llm_providers: dict[str, ProviderProfile] = {}

    def resolve(self, environment: str = "dev") -> ResolvedRunConfig:
        overlay = self.environments.get(environment)
        if overlay is None:
            raise ValueError(
                f"no '{environment}' entry in environments; have: {list(self.environments)}"
            )
        model_name = overlay.model
        if not model_name:
            raise ValueError(f"environment '{environment}' does not specify a model profile")
        profile = self.llm_providers.get(model_name)
        if profile is None:
            raise ValueError(
                f"environment '{environment}' references unknown llm_providers "
                f"entry '{model_name}'; have: {list(self.llm_providers)}"
            )
        headed = overlay.headed if overlay.headed is not None else not bool(overlay.headless)
        return ResolvedRunConfig(
            project_id=self.project_id,
            base_url=overlay.base_url or self.base_url,
            headed=headed,
            provider_profile=profile,
            max_steps=overlay.max_steps or DEFAULT_MAX_STEPS,
            timeout_seconds=overlay.timeout_seconds or DEFAULT_TIMEOUT_SECONDS,
            auth=self.auth,
            record_video=overlay.record_video if overlay.record_video is not None else True,
        )


def load_config(path: str | Path) -> SuthConfig:
    raw = json.loads(Path(path).read_text())
    return SuthConfig.model_validate(raw)
