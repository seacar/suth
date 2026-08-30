from typing import Literal

from pydantic import BaseModel


class ObjectiveCheck(BaseModel):
    """A Driver-side assertion on final app state, independent of the persona's
    self-report — plan Phase 2 "Silent Failure needs a Driver-side objective-check
    hook". Checked after every step; if it never passes before max_steps, the
    session is classified `silent_failure` rather than a plain timeout.
    """

    type: Literal["url_pattern", "dom_text"]
    value: str
