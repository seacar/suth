import asyncio
import queue
import threading

DONE = object()  # sentinel
POLL_TIMEOUT = 0.5  # seconds — bounds each blocking queue.get() call (see _drain)


class SessionEventBus:
    """Bridges the Orchestrator's synchronous worker threads (where
    `run_session`'s `on_step` hook fires) to the API's async WebSocket
    handlers. Per-session step queues; a separate global queue carries
    session-lifecycle events for the "notify on any completion" GUI feature.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._queues: dict[str, queue.Queue] = {}
        self._gates: dict[str, threading.Event] = {}
        self._global_subscribers: list[queue.Queue] = []

    def _queue_for(self, session_id: str) -> queue.Queue:
        with self._lock:
            return self._queues.setdefault(session_id, queue.Queue())

    def publish(self, session_id: str, event: dict) -> None:
        self._queue_for(session_id).put(event)

    def close(self, session_id: str) -> None:
        self._queue_for(session_id).put(DONE)

    def gate_for(self, session_id: str) -> threading.Event:
        """A per-step pause gate for `--step`-equivalent mode: `on_step`
        clears it and blocks on `.wait()`; the API's /continue endpoint
        `.set()`s it in response to a client message."""
        with self._lock:
            return self._gates.setdefault(session_id, threading.Event())

    def publish_global(self, event: dict) -> None:
        """Fan out to every currently-connected /events subscriber. Each
        subscriber has its own queue (not one shared queue), so a listener
        that connects late only ever sees events published after it
        subscribed — no stale backlog, and N listeners each see everything."""
        with self._lock:
            subscribers = list(self._global_subscribers)
        for q in subscribers:
            q.put(event)

    @staticmethod
    async def _drain(q: queue.Queue):
        """Yield items from a thread-safe queue.Queue without ever blocking a
        thread-pool worker indefinitely: each blocking get() is bounded to
        POLL_TIMEOUT, so if the consumer stops iterating (WebSocket closed,
        generator GC'd/cancelled), no worker thread stays wedged forever —
        it just returns on its next timeout and the pool slot frees up.
        """
        loop = asyncio.get_event_loop()
        while True:
            try:
                yield await loop.run_in_executor(None, q.get, True, POLL_TIMEOUT)
            except queue.Empty:
                continue

    async def subscribe(self, session_id: str):
        q = self._queue_for(session_id)
        async for event in self._drain(q):
            if event is DONE:
                return
            yield event

    async def subscribe_global(self):
        q: queue.Queue = queue.Queue()
        with self._lock:
            self._global_subscribers.append(q)
        try:
            async for event in self._drain(q):
                yield event
        finally:
            with self._lock:
                self._global_subscribers.remove(q)


bus = SessionEventBus()
