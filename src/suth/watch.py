import time
from collections.abc import Callable
from pathlib import Path


def _signature(path: Path) -> float:
    """Latest mtime under `path` — a file or a directory tree."""
    if path.is_file():
        return path.stat().st_mtime
    if path.is_dir():
        mtimes = [p.stat().st_mtime for p in path.rglob("*") if p.is_file()]
        return max(mtimes) if mtimes else 0.0
    return 0.0


def watch_and_rerun(
    path: str, run_once: Callable[[], None], poll_interval: float = 1.0
) -> None:
    """Re-run `run_once` whenever anything under `path` changes — plan §5.1's
    `--watch` mode. Polling-based (no extra dependency); fine at dev-loop
    cadence. Runs until interrupted (Ctrl+C).
    """
    watched = Path(path)
    run_once()
    last_seen = _signature(watched)
    print(f"\nwatching {watched} for changes (Ctrl+C to stop)...")
    try:
        while True:
            time.sleep(poll_interval)
            current = _signature(watched)
            if current != last_seen:
                last_seen = current
                print(f"\nchange detected under {watched}, re-running...")
                run_once()
    except KeyboardInterrupt:
        print("\nstopped watching")
