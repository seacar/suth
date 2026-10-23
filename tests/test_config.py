import pytest
from pydantic import ValidationError

from suth.config import DEFAULT_MAX_STEPS, DEFAULT_TIMEOUT_SECONDS, SuthConfig


def _config(**overlay) -> SuthConfig:
    return SuthConfig.model_validate(
        {
            "project_id": "demo",
            "base_url": "http://localhost:9999",
            "environments": {"dev": {"model": "local", **overlay}},
            "llm_providers": {"local": {"provider": "ollama", "model": "gemma4"}},
        }
    )


def test_unset_limits_fall_back_to_defaults():
    resolved = _config().resolve("dev")
    assert resolved.max_steps == DEFAULT_MAX_STEPS
    assert resolved.timeout_seconds == DEFAULT_TIMEOUT_SECONDS
    assert resolved.token_cap is None


def test_explicit_limits_and_token_cap_pass_through():
    resolved = _config(max_steps=3, timeout_seconds=30, token_cap=5000).resolve("dev")
    assert (resolved.max_steps, resolved.timeout_seconds, resolved.token_cap) == (3, 30, 5000)


@pytest.mark.parametrize("field", ["max_steps", "timeout_seconds", "token_cap"])
def test_zero_limits_are_rejected_not_silently_defaulted(field):
    with pytest.raises(ValidationError):
        _config(**{field: 0})
