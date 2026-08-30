import struct
from datetime import datetime, timedelta, timezone
from pathlib import Path

from suth.video import duration_from_session_times, duration_from_webm_bytes, read_webm_duration_seconds


def _vint(n: int) -> bytes:
    assert 0 <= n < 127
    return bytes([0x80 | n])


def test_duration_from_webm_bytes_uses_default_timecode_scale():
    # Duration 18500.0 at the default 1_000_000 scale → 18.5s
    payload = struct.pack(">d", 18500.0)
    blob = b"pad" + b"\x44\x89" + _vint(8) + payload
    assert duration_from_webm_bytes(blob) == 18.5


def test_duration_from_webm_bytes_honors_timecode_scale():
    scale = (1_000_000_000).to_bytes(4, "big")
    duration = struct.pack(">f", 12.0)
    blob = b"\x2a\xd7\xb1" + _vint(4) + scale + b"\x44\x89" + _vint(4) + duration
    assert duration_from_webm_bytes(blob) == 12.0


def test_duration_from_webm_bytes_rejects_garbage():
    assert duration_from_webm_bytes(b"not a webm") is None


def test_read_webm_duration_seconds_missing_file(tmp_path: Path):
    assert read_webm_duration_seconds(tmp_path / "missing.webm") is None


def test_duration_from_session_times():
    started = datetime(2026, 8, 29, 20, 2, 30, tzinfo=timezone.utc)
    ended = started + timedelta(seconds=18.25)
    assert duration_from_session_times(ended, started) == 18.25
    assert duration_from_session_times(None, started) is None
    assert duration_from_session_times(started, ended) is None
