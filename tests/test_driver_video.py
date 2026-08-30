from pathlib import Path

from suth.brain.schema import Action
from suth.driver.browser import Driver


def test_stop_finalizes_a_video_file(tmp_path):
    html = tmp_path / "page.html"
    html.write_text("<html><body><button>click me</button></body></html>")

    driver = Driver(
        base_url=html.as_uri(),
        headed=False,
        screenshot_dir=tmp_path / "screenshots",
        video_dir=tmp_path / "videos",
    )
    driver.start()
    assert driver.video_started_at is not None
    driver.stop()

    assert driver.video_path is not None
    assert driver.video_path.exists()
    assert driver.video_path.stat().st_size > 0


def test_record_video_false_captures_nothing(tmp_path):
    html = tmp_path / "page.html"
    html.write_text("<html><body>hi</body></html>")

    driver = Driver(
        base_url=html.as_uri(),
        headed=False,
        screenshot_dir=tmp_path / "screenshots",
        video_dir=tmp_path / "videos",
        record_video=False,
    )
    driver.start()
    driver.stop()

    assert driver.video_path is None


def test_go_back_on_fresh_page_recovers_from_blank(tmp_path):
    """A page's implicit pre-goto history entry means go_back() as the very
    first action can strand the driver on about:blank, with zero
    interactive elements for the rest of the run — the Driver must recover
    by returning to base_url instead of leaving the persona stuck."""
    html = tmp_path / "page.html"
    html.write_text("<html><body><button>click me</button></body></html>")

    driver = Driver(
        base_url=html.as_uri(),
        headed=False,
        screenshot_dir=tmp_path / "screenshots",
        record_video=False,
    )
    driver.start()
    try:
        driver.execute(Action(type="go_back"))
        assert driver.page.url != "about:blank"
        assert driver.page.url == html.as_uri()
    finally:
        driver.stop()
