"""Replay-video helpers — duration from a Playwright .webm, with a wall-clock fallback."""

from __future__ import annotations

import struct
from datetime import datetime
from pathlib import Path

_DURATION_ID = b"\x44\x89"
_TIMECODE_SCALE_ID = b"\x2a\xd7\xb1"
_DEFAULT_TIMECODE_SCALE = 1_000_000
_HEAD_BYTES = 128 * 1024


def read_webm_duration_seconds(path: str | Path) -> float | None:
    """Best-effort Duration from a WebM Info element. Playwright records WebM;
    the value lives near the start of the file so we only read a prefix."""
    try:
        with Path(path).open("rb") as handle:
            head = handle.read(_HEAD_BYTES)
    except OSError:
        return None
    return duration_from_webm_bytes(head)


def duration_from_webm_bytes(data: bytes) -> float | None:
    scale = _read_uint_element(data, _TIMECODE_SCALE_ID) or _DEFAULT_TIMECODE_SCALE
    raw = _read_float_element(data, _DURATION_ID)
    if raw is None or raw < 0:
        return None
    seconds = raw * scale / 1_000_000_000
    if not (0 < seconds < 24 * 60 * 60):
        return None
    return seconds


def duration_from_session_times(
    ended_at: datetime | None, video_started_at: datetime | None
) -> float | None:
    """Fallback when the container has no Duration — recording wall-clock."""
    if ended_at is None or video_started_at is None:
        return None
    seconds = (ended_at - video_started_at).total_seconds()
    if seconds < 0:
        return None
    return seconds


def _read_vint(data: bytes, offset: int) -> tuple[int, int] | None:
    if offset >= len(data):
        return None
    first = data[offset]
    if first == 0:
        return None
    length = 1
    mask = 0x80
    while first & mask == 0:
        length += 1
        mask >>= 1
        if length > 8:
            return None
    if offset + length > len(data):
        return None
    value = first & (mask - 1)
    for byte in data[offset + 1 : offset + length]:
        value = (value << 8) | byte
    return value, offset + length


def _payload_after(data: bytes, element_id: bytes) -> bytes | None:
    start = 0
    while True:
        index = data.find(element_id, start)
        if index < 0:
            return None
        parsed = _read_vint(data, index + len(element_id))
        if parsed is None:
            start = index + 1
            continue
        size, payload_at = parsed
        if size <= 0 or payload_at + size > len(data):
            start = index + 1
            continue
        return data[payload_at : payload_at + size]


def _read_float_element(data: bytes, element_id: bytes) -> float | None:
    payload = _payload_after(data, element_id)
    if payload is None:
        return None
    if len(payload) == 4:
        return struct.unpack(">f", payload)[0]
    if len(payload) == 8:
        return struct.unpack(">d", payload)[0]
    return None


def _read_uint_element(data: bytes, element_id: bytes) -> int | None:
    payload = _payload_after(data, element_id)
    if not payload:
        return None
    return int.from_bytes(payload, "big")
