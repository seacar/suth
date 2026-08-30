import threading
import time

from suth.watch import watch_and_rerun


def test_watch_reruns_on_change_and_stops_on_interrupt(tmp_path):
    watched = tmp_path / "build-output.txt"
    watched.write_text("v1")

    calls = []

    def rebuild_after_delay():
        time.sleep(0.05)
        watched.write_text("v2")  # simulates an external rebuild, not a side effect of run_once

    threading.Thread(target=rebuild_after_delay, daemon=True).start()

    def run_once():
        calls.append(len(calls))
        if len(calls) == 2:
            raise KeyboardInterrupt  # simulate the dev hitting Ctrl+C

    watch_and_rerun(str(watched), run_once, poll_interval=0.01)

    assert len(calls) == 2  # initial run, then one re-run after the external change
