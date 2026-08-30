from pydantic import BaseModel


class OriginGuardrailError(Exception):
    """Raised when an action would navigate the page off the configured origin."""


class InteractionModeError(Exception):
    """Raised when an action isn't available under the persona's interaction_mode
    (e.g. `hover` for a keyboard-only/screen-reader persona)."""


class ActionResult(BaseModel):
    ok: bool
    error: str | None = None
    dom_changed: bool = False
    screenshot_path: str | None = None
