from types import SimpleNamespace

import pytest

from suth.brain.schema import Action
from suth.driver.browser import Driver
from suth.objective import ObjectiveCheck

COUNTER_PAGE = """<html><body>
<button id="b" onclick="document.getElementById('n').textContent = String(Number(document.getElementById('n').textContent) + 1)">add</button>
<span id="n">0</span>
</body></html>"""


class FakeLocator:
    def __init__(self, attached=True, click_error=None):
        self.attached = attached
        self.click_error = click_error
        self.clicks = 0

    def wait_for(self, state, timeout):
        if not self.attached:
            raise TimeoutError("not attached")

    def click(self, timeout):
        self.clicks += 1
        if self.click_error:
            raise self.click_error


def _fake_driver(tmp_path, locator: FakeLocator) -> Driver:
    driver = Driver(base_url="http://localhost:9", screenshot_dir=tmp_path, record_video=False)
    driver.page = SimpleNamespace(content=lambda: "<html/>", url="http://localhost:9/")  # type: ignore[assignment]
    driver._resolve = lambda ref: locator  # type: ignore[method-assign]
    return driver


def test_click_that_fails_after_dispatch_is_not_retried(tmp_path):
    # e.g. the click landed but Playwright then timed out waiting on navigation
    locator = FakeLocator(click_error=TimeoutError("navigation timeout"))
    result = _fake_driver(tmp_path, locator).execute(Action(type="click", target="e0"))

    assert locator.clicks == 1
    assert not result.ok and result.error.startswith("action_failed")


def test_missing_target_is_retried_then_reported_without_dispatch(tmp_path):
    locator = FakeLocator(attached=False)
    result = _fake_driver(tmp_path, locator).execute(Action(type="click", target="e0"))

    assert locator.clicks == 0
    assert not result.ok and result.error.startswith("element_not_found")


@pytest.fixture
def live_driver(tmp_path):
    html = tmp_path / "page.html"
    html.write_text(COUNTER_PAGE)
    driver = Driver(base_url=html.as_uri(), headed=False, screenshot_dir=tmp_path / "shots", record_video=False)
    driver.start()
    yield driver
    driver.stop()


def test_real_click_fires_exactly_once(live_driver):
    ref = next(el.ref for el in live_driver.snapshot().elements if el.name == "add" or el.tag == "button")
    result = live_driver.execute(Action(type="click", target=ref))

    assert result.ok and result.dom_changed
    assert live_driver.page.locator("#n").text_content() == "1"


def test_objective_checks(live_driver):
    assert live_driver.check_objective(ObjectiveCheck(type="url_pattern", value=r"page\.html$"))
    assert live_driver.check_objective(ObjectiveCheck(type="dom_text", value="add"))
    assert not live_driver.check_objective(ObjectiveCheck(type="dom_text", value="checkout complete"))
