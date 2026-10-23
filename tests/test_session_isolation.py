from pathlib import Path

from suth.brain.interface import ProviderProfile
from suth.brain.schema import Action, StepDecision
from suth.config import ResolvedRunConfig
from suth.personas.loader import load_persona
from suth.session import run_session


class ClickThenAbandon:
    def __init__(self):
        self.calls = 0

    def generate_step(self, persona, objective, history_text, dom_state):
        self.calls += 1
        if self.calls == 1:
            target = dom_state.elements[0].ref
            return StepDecision(thought="t", emotion="calm", frustration_delta=0, action=Action(type="click", target=target))
        return StepDecision(thought="done", emotion="bored", frustration_delta=0, action=Action(type="abandon"))


def _config(base_url: str) -> ResolvedRunConfig:
    return ResolvedRunConfig(
        project_id="isolation-test",
        base_url=base_url,
        headed=False,
        provider_profile=ProviderProfile(provider="ollama", model="none"),
        max_steps=5,
        timeout_seconds=60,
        record_video=False,
    )


def test_concurrent_sessions_get_their_own_screenshot_dirs(tmp_path, monkeypatch):
    # Two sessions writing step-0001.png into one shared folder used to
    # overwrite each other inside a batch.
    html = tmp_path / "page.html"
    html.write_text("<html><body><button>go</button></body></html>")
    monkeypatch.chdir(tmp_path)

    for sid in ("session-a", "session-b"):
        run_session(
            _config(html.as_uri()),
            load_persona("power-user-v1"),
            "press go",
            ClickThenAbandon(),
            memory=None,
            upload_screenshots=False,
            session_id=sid,
        )

    assert (Path("screenshots") / "session-a" / "step-0001.png").is_file()
    assert (Path("screenshots") / "session-b" / "step-0001.png").is_file()
    assert not list(Path("screenshots").glob("*.png"))
