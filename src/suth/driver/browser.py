import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from playwright.sync_api import Browser, Page, Playwright, sync_playwright
from pydantic import BaseModel

from suth.driver.actions import ActionResult, InteractionModeError, OriginGuardrailError
from suth.objective import ObjectiveCheck

if TYPE_CHECKING:
    # Deferred to break the driver<->brain import cycle — see brain/interface.py.
    from suth.brain.schema import Action

# Interactive elements the Driver knows how to enumerate and act on. Kept as a
# single selector so a `ref` can be re-resolved later via `nth()` against the
# same query, without needing to persist live Locator handles across steps.
INTERACTIVE_SELECTOR = (
    "a, button, input, select, textarea, summary, [role='button'], "
    "[role='link'], [role='checkbox'], [role='radio'], [role='tab'], "
    "[role='switch'], [role='menuitem'], [tabindex]"
)


class DomElement(BaseModel):
    ref: str
    role: str
    name: str
    tag: str


class DomState(BaseModel):
    url: str
    elements: list[DomElement]


def _accessible_name(el) -> str:
    for attr in ("aria-label", "alt", "placeholder", "value", "title"):
        value = el.get_attribute(attr)
        if value:
            return value.strip()
    text = el.inner_text(timeout=1000).strip()
    if text:
        return text
    return ""


def same_origin(url: str, origin: str) -> bool:
    """Pure helper behind the origin guardrail — unit-testable without a live page."""
    netloc = urlparse(url).netloc
    return not netloc or netloc == origin


def _role(el, tag: str) -> str:
    role = el.get_attribute("role")
    if role:
        return role
    return {
        "a": "link",
        "button": "button",
        "input": "textbox",
        "select": "combobox",
        "textarea": "textbox",
        "summary": "button",
    }.get(tag, tag)


class Driver:
    """Drives the target app via Playwright: snapshot, screenshot, execute."""

    def __init__(
        self,
        base_url: str,
        headed: bool = True,
        storage_state_path: str | None = None,
        screenshot_dir: str | Path = "screenshots",
        interaction_mode: str = "pointer",
        record_video: bool = True,
        video_dir: str | Path = "videos",
    ):
        self.base_url = base_url
        self.origin = urlparse(base_url).netloc
        self.headed = headed
        self.storage_state_path = storage_state_path
        self.screenshot_dir = Path(screenshot_dir)
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        self.interaction_mode = interaction_mode
        self.record_video = record_video
        self.video_dir = Path(video_dir)

        self._pw: Playwright | None = None
        self._browser: Browser | None = None
        self._context = None
        self.page: Page | None = None
        self._shot_count = 0
        # Set the instant Playwright starts recording (right before the first
        # navigation) — steps' `created_at` timestamps are offset against this
        # so the web GUI can seek the replay video to any given step.
        self.video_started_at: datetime | None = None
        # Populated by stop() once the context closes and Playwright finalizes
        # the .webm — None if record_video=False or nothing was captured.
        self.video_path: Path | None = None

    def start(self) -> None:
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=not self.headed)
        context_kwargs = {}
        if self.storage_state_path and Path(self.storage_state_path).exists():
            context_kwargs["storage_state"] = self.storage_state_path
        if self.record_video:
            self.video_dir.mkdir(parents=True, exist_ok=True)
            context_kwargs["record_video_dir"] = str(self.video_dir)
            context_kwargs["record_video_size"] = {"width": 1280, "height": 800}
        context = self._browser.new_context(**context_kwargs)
        self._context = context
        self.page = context.new_page()
        self.video_started_at = datetime.now(timezone.utc)
        self.page.goto(self.base_url)

    def stop(self) -> None:
        page, context = self.page, self._context
        if context:
            context.close()  # finalizes the .webm — video.path() is only valid after this
        if page and page.video:
            try:
                self.video_path = Path(page.video.path())
            except Exception:
                self.video_path = None
        if self._browser:
            self._browser.close()
        if self._pw:
            self._pw.stop()

    def __enter__(self) -> "Driver":
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.stop()

    def snapshot(self) -> DomState:
        assert self.page is not None
        locator = self.page.locator(INTERACTIVE_SELECTOR)
        count = locator.count()
        elements: list[DomElement] = []
        for i in range(count):
            el = locator.nth(i)
            if not el.is_visible():
                continue
            tag = el.evaluate("e => e.tagName.toLowerCase()")
            elements.append(
                DomElement(
                    ref=f"e{i}",
                    role=_role(el, tag),
                    name=_accessible_name(el),
                    tag=tag,
                )
            )
        return DomState(url=self.page.url, elements=elements)

    def _resolve(self, ref: str):
        assert self.page is not None
        index = int(ref.removeprefix("e"))
        return self.page.locator(INTERACTIVE_SELECTOR).nth(index)

    def screenshot(self, clip=None) -> str:
        assert self.page is not None
        self._shot_count += 1
        path = self.screenshot_dir / f"step-{self._shot_count:04d}.png"
        self.page.screenshot(path=str(path), clip=clip)
        return str(path)

    def _check_origin(self) -> None:
        assert self.page is not None
        if not same_origin(self.page.url, self.origin):
            current = urlparse(self.page.url).netloc
            self.page.go_back()
            raise OriginGuardrailError(
                f"action navigated off origin ({current} != {self.origin}); reverted"
            )

    def execute(self, action: "Action") -> ActionResult:
        """Execute one action with a single bounded retry on locator resolution."""
        assert self.page is not None
        before_html = self.page.content()

        try:
            self._dispatch(action)
        except (OriginGuardrailError, InteractionModeError) as e:
            return ActionResult(ok=False, error=str(e))
        except Exception:
            time.sleep(0.5)
            try:
                self._dispatch(action)
            except Exception as e:
                return ActionResult(ok=False, error=f"element_not_found: {e}")

        after_html = self.page.content()
        shot = self.screenshot()
        return ActionResult(
            ok=True, dom_changed=before_html != after_html, screenshot_path=shot
        )

    def _dispatch(self, action: "Action") -> None:
        assert self.page is not None
        keyboard_only = self.interaction_mode == "keyboard"

        if action.type == "click":
            target = self._resolve(action.target)
            if keyboard_only:
                # A screen-reader-only persona never uses a mouse — reach the
                # element via focus and activate it the way a keyboard user
                # would, instead of Playwright's synthetic mouse click.
                target.focus(timeout=3000)
                self.page.keyboard.press("Enter")
            else:
                target.click(timeout=3000)
            self._check_origin()
        elif action.type == "type":
            self._resolve(action.target).fill(action.text or "", timeout=3000)
        elif action.type == "scroll":
            direction = 1 if action.direction == "down" else -1
            self.page.mouse.wheel(0, direction * 600)
        elif action.type == "hover":
            if keyboard_only:
                raise InteractionModeError(
                    "hover is a pointer-only action; not available to a keyboard-only persona"
                )
            self._resolve(action.target).hover(timeout=3000)
        elif action.type == "go_back":
            self.page.go_back()
            # A fresh page's session history has an implicit blank entry
            # before its first goto() — go_back() on step 1 (or after
            # anything that replaced history) can land there and strand the
            # persona on a page with zero interactive elements for the rest
            # of the run. Recover by returning to the app instead of letting
            # every subsequent step spiral into declared confusion.
            if self.page.url == "about:blank":
                self.page.goto(self.base_url)
        elif action.type == "zoom":
            box = self._resolve(action.target).bounding_box()
            if box:
                self.screenshot(clip=box)
        elif action.type in ("declare_confusion", "abandon"):
            pass  # no-op at the Driver level; the state machine handles these
        else:
            raise ValueError(f"unknown action type: {action.type}")

    def check_objective(self, check: ObjectiveCheck) -> bool:
        """Driver-side assertion on final app state, independent of the
        persona's self-report — the Silent Failure detector (plan Phase 2)."""
        assert self.page is not None
        if check.type == "url_pattern":
            return bool(re.search(check.value, self.page.url))
        if check.type == "dom_text":
            return self.page.locator(f"text={check.value}").count() > 0
        raise ValueError(f"unknown objective check type: {check.type}")
