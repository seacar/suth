import asyncio

import pytest

from suth.api.events import DONE, SessionEventBus


def test_per_session_publish_and_subscribe():
    bus = SessionEventBus()
    bus.publish("s1", {"a": 1})
    bus.publish("s1", {"a": 2})
    bus.close("s1")

    async def collect():
        return [e async for e in bus.subscribe("s1")]

    assert asyncio.run(collect()) == [{"a": 1}, {"a": 2}]


def test_late_global_subscriber_does_not_see_backlog():
    """Regression: the first cut used one shared queue.Queue for /events, so
    a listener that connected late got old events instead of only live ones —
    caught via a real cross-process test against the running API, reproduced
    here as a fast unit test."""
    bus = SessionEventBus()
    bus.publish_global({"stale": True})  # published before anyone subscribed

    async def peek_with_timeout():
        # > POLL_TIMEOUT (0.5s) so at least one real empty-queue poll cycle
        # completes — proving absence, not just "didn't get to check yet".
        gen = bus.subscribe_global()
        try:
            return await asyncio.wait_for(gen.__anext__(), timeout=0.7)
        except asyncio.TimeoutError:
            return None
        finally:
            await gen.aclose()

    assert asyncio.run(peek_with_timeout()) is None


def test_multiple_global_subscribers_each_get_every_event():
    bus = SessionEventBus()

    async def scenario():
        gen_a = bus.subscribe_global()
        gen_b = bus.subscribe_global()
        # Async generators are lazy — nothing runs (including registering in
        # _global_subscribers) until __anext__() is first awaited. Start both
        # as tasks so they actually reach that point before we publish.
        task_a = asyncio.ensure_future(gen_a.__anext__())
        task_b = asyncio.ensure_future(gen_b.__anext__())
        await asyncio.sleep(0.05)
        bus.publish_global({"live": True})
        a = await asyncio.wait_for(task_a, timeout=1)
        b = await asyncio.wait_for(task_b, timeout=1)
        await gen_a.aclose()
        await gen_b.aclose()
        return a, b

    a, b = asyncio.run(scenario())
    assert a == {"live": True}
    assert b == {"live": True}


def test_step_through_gate_blocks_until_set():
    import threading
    import time

    bus = SessionEventBus()
    gate = bus.gate_for("s1")
    gate.clear()
    order = []

    def worker():
        order.append("before-wait")
        gate.wait(timeout=2)
        order.append("after-wait")

    t = threading.Thread(target=worker)
    t.start()
    time.sleep(0.1)
    assert order == ["before-wait"]  # still blocked
    gate.set()
    t.join(timeout=2)
    assert order == ["before-wait", "after-wait"]
