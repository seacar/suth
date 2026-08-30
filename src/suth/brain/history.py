from pydantic import BaseModel


class StepRecord(BaseModel):
    step_index: int
    thought: str
    action_type: str
    target: str | None
    dom_changed: bool
    url: str = ""
    emotion: str = ""
    frustration_delta: int = 0
    screenshot_ref: str | None = None


class HistoryWindow:
    """Bounded history: last `window_size` steps verbatim, older steps condensed
    to a one-line synopsis so context doesn't grow unbounded across a long session.
    """

    def __init__(self, window_size: int = 6):
        self.window_size = window_size
        self._records: list[StepRecord] = []

    def add(self, record: StepRecord) -> None:
        self._records.append(record)

    @property
    def records(self) -> list[StepRecord]:
        return list(self._records)

    def render(self) -> str:
        if not self._records:
            return ""
        cutoff = max(0, len(self._records) - self.window_size)
        older, recent = self._records[:cutoff], self._records[cutoff:]

        lines = []
        if older:
            summary = "; ".join(
                f"step {r.step_index}: {r.action_type}"
                f"{f' on {r.target}' if r.target else ''}"
                f" ({'changed' if r.dom_changed else 'no change'})"
                for r in older
            )
            lines.append(f"(earlier steps, condensed) {summary}")
        for r in recent:
            lines.append(
                f'step {r.step_index}: thought="{r.thought}" -> {r.action_type}'
                f"{f' on {r.target}' if r.target else ''}"
                f" ({'DOM changed' if r.dom_changed else 'no DOM change'})"
            )
        return "\n".join(lines)
