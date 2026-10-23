import json
from types import SimpleNamespace

import pytest

from suth.brain.interface import ProviderProfile, get_brain
from suth.brain.providers.anthropic import FALLBACK_BETA, AnthropicBrain
from suth.driver.browser import DomElement, DomState
from suth.personas.loader import load_persona

DOM = DomState(url="http://localhost:8765/", elements=[DomElement(ref="e0", role="button", name="Buy", tag="button")])
VALID = {"thought": "buy it", "emotion": "calm", "frustration_delta": 1, "action": {"type": "click", "target": "e0"}}


def _response(text: str, stop_reason: str = "end_turn", category: str | None = None):
    return SimpleNamespace(
        content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=text)],
        stop_reason=stop_reason,
        stop_details=SimpleNamespace(category=category) if category else None,
        usage=SimpleNamespace(
            input_tokens=100, output_tokens=20, cache_creation_input_tokens=None, cache_read_input_tokens=5
        ),
    )


class FakeMessages:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.replies.pop(0)


def _brain(monkeypatch, replies, model="claude-opus-5-5") -> tuple[AnthropicBrain, FakeMessages]:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    brain = AnthropicBrain(ProviderProfile(provider="anthropic", model=model, credential="env:ANTHROPIC_API_KEY"))
    messages = FakeMessages(replies)
    brain._client = SimpleNamespace(beta=SimpleNamespace(messages=messages))
    return brain, messages


def _step(brain):
    return brain.generate_step(load_persona("power-user-v1"), "buy a car", "", DOM)


def test_get_brain_returns_anthropic_adapter(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    profile = ProviderProfile(provider="anthropic", model="claude-opus-5-5", credential="env:ANTHROPIC_API_KEY")
    assert isinstance(get_brain(profile), AnthropicBrain)


def test_generates_step_with_structured_output_and_fallbacks(monkeypatch):
    brain, messages = _brain(monkeypatch, [_response(json.dumps(VALID))])

    decision = _step(brain)

    assert decision.action.target == "e0"
    call = messages.calls[0]
    assert call["model"] == "claude-opus-5-5"
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert call["fallbacks"] == "default" and call["betas"] == [FALLBACK_BETA]
    assert call["messages"][0]["role"] == "user" and "e0" in call["messages"][0]["content"]
    assert brain.token_usage() == 125


def test_no_fallbacks_for_models_without_support(monkeypatch):
    brain, messages = _brain(monkeypatch, [_response(json.dumps(VALID))], model="claude-haiku-5-5")
    _step(brain)
    assert "fallbacks" not in messages.calls[0]


def test_out_of_bounds_reply_is_nudged_once(monkeypatch):
    bad = {**VALID, "frustration_delta": 9}  # schema can't express -5..5
    brain, messages = _brain(monkeypatch, [_response(json.dumps(bad)), _response(json.dumps(VALID))])

    assert _step(brain).frustration_delta == 1
    retry = messages.calls[1]["messages"]
    assert [m["role"] for m in retry] == ["user", "assistant", "user"]


def test_refusal_raises_with_category(monkeypatch):
    brain, _ = _brain(monkeypatch, [_response("", stop_reason="refusal", category="cyber")])
    with pytest.raises(RuntimeError, match="cyber"):
        _step(brain)
