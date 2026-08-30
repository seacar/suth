from suth.driver.browser import same_origin


def test_same_origin_matches():
    assert same_origin("http://localhost:8765/foo", "localhost:8765")


def test_same_origin_rejects_different_host():
    assert not same_origin("https://evil.example.com/", "localhost:8765")


def test_same_origin_rejects_different_port():
    assert not same_origin("http://localhost:9999/", "localhost:8765")


def test_same_origin_allows_empty_netloc():
    # about:blank and similar have no netloc — treated as harmless, not a violation.
    assert same_origin("about:blank", "localhost:8765")
