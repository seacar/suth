import threading
import uuid
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field

from suth.brain.history import StepRecord
from suth.brain.interface import Brain
from suth.config import ResolvedRunConfig
from suth.db import Memory
from suth.objective import ObjectiveCheck
from suth.personas.schema import Persona
from suth.session import SessionResult, run_session


class ConcurrencyLimitError(Exception):
    """A per-project or per-caller concurrency cap was already at its limit."""


class BudgetExceededError(Exception):
    """A caller/project's declared token budget for this period is used up."""


@dataclass
class _Handle:
    session_id: str
    future: Future
    project_id: str
    caller: str | None
    persona_id: str = ""
    state: str = "queued"  # "queued" -> "running" -> (future.done())


@dataclass
class _BatchHandle:
    batch_id: str
    session_ids: list[str] = field(default_factory=list)


@dataclass
class BatchMemberResult:
    """One persona's outcome within a batch — `result` is set on success,
    `error` on failure. Never both None: a batch member always resolves to
    exactly one." A single member's exception (e.g. a transient LLM-provider
    error) must not hide the other members' results, so get_batch_report
    catches per-member rather than letting the first failure abort the rest.
    """

    session_id: str
    persona_id: str
    result: SessionResult | None = None
    error: str | None = None


class Orchestrator:
    """Owns the run queue and enforces concurrency/budget limits before a
    session starts — plan §2/§8. The CLI, MCP server, and Local Control API
    are all clients of this one implementation; none of them re-runs session
    logic themselves.

    Backed by a simple in-process thread pool, not yet Specific
    Workflows/Temporal — explicitly acceptable per the plan.
    """

    def __init__(
        self,
        memory: Memory | None = None,
        max_concurrency: int = 4,
        max_per_project: int = 2,
        max_per_caller: int = 1,
    ):
        self.memory = memory
        self.max_per_project = max_per_project
        self.max_per_caller = max_per_caller
        self._executor = ThreadPoolExecutor(max_workers=max_concurrency)
        # A single RLock backs both direct locking and the condition variable,
        # so queued waiters and the accounting they wait on never deadlock or
        # drift out of sync with each other.
        self._lock = threading.RLock()
        self._cv = threading.Condition(self._lock)
        self._handles: dict[str, _Handle] = {}
        self._batches: dict[str, _BatchHandle] = {}

    def _active_count(self, *, project_id: str | None = None, caller: str | None = None) -> int:
        """Counts sessions actually *running* — not merely submitted and
        still queued behind another project slot. This distinction matters:
        if a queued-but-not-yet-running session counted toward its own cap
        check, N sessions queued at once would each wait for a slot that
        includes themselves, and none would ever start (a real deadlock this
        caught during testing, not a hypothetical)."""
        with self._lock:
            return sum(
                1
                for h in self._handles.values()
                if h.state == "running"
                and not h.future.done()
                and (project_id is None or h.project_id == project_id)
                and (caller is None or h.caller == caller)
            )

    def _check_budget(self, project_id: str, caller: str | None) -> None:
        if not self.memory:
            return
        budget = self.memory.get_budget(project_id, caller or "")
        if budget and budget["spend_to_date"] >= budget["token_cap"]:
            raise BudgetExceededError(
                f"budget exceeded for project={project_id!r} caller={caller!r}: "
                f"{budget['spend_to_date']}/{budget['token_cap']} tokens"
            )

    def start_session(
        self,
        config: ResolvedRunConfig,
        persona: Persona,
        objective: str,
        brain: Brain,
        *,
        environment: str = "dev",
        caller: str | None = None,
        objective_check: ObjectiveCheck | None = None,
        upload_screenshots: bool = True,
        on_step: Callable[[int, StepRecord], None] | None = None,
        session_id: str | None = None,
        batch_id: str | None = None,
        queue_if_full: bool = False,
    ) -> str:
        """Budget is always checked synchronously and rejected immediately —
        that's a cost decision, not a scheduling one. Concurrency is
        different: by default (`queue_if_full=False`, unchanged from before)
        a single ad hoc run still rejects fast if the project/caller is at
        its cap, so a human gets an immediate, explainable error rather than
        an open-ended wait. `queue_if_full=True` (used by `start_batch` — one
        coherent multi-persona request, not independent spam) instead blocks
        the *worker thread* until a project slot frees, so the caller still
        gets a session_id back immediately and can watch it sit `state=
        "queued"` via get_status. The per-caller cap is intentionally not
        applied when queuing — all of a batch's sessions come from the same
        originating request, not N independent ones.
        """
        if not queue_if_full:
            if self._active_count(project_id=config.project_id) >= self.max_per_project:
                raise ConcurrencyLimitError(
                    f"project {config.project_id!r} already at its concurrency cap "
                    f"({self.max_per_project})"
                )
            if caller and self._active_count(caller=caller) >= self.max_per_caller:
                raise ConcurrencyLimitError(
                    f"caller {caller!r} already at its concurrency cap ({self.max_per_caller})"
                )
        self._check_budget(config.project_id, caller)

        session_id = session_id or str(uuid.uuid4())
        handle = _Handle(
            session_id=session_id, future=None, project_id=config.project_id,  # type: ignore[arg-type]
            caller=caller, persona_id=getattr(persona, "id", ""),
        )

        def run() -> SessionResult:
            # A submitted task can start executing on a worker thread before
            # the main thread below finishes assigning handle.future — both
            # branches acquire the same lock first, which blocks them until
            # that assignment (still inside the `with self._lock` below) has
            # completed, so handle.future is never read while still None.
            if queue_if_full:
                with self._cv:
                    while self._active_count(project_id=config.project_id) >= self.max_per_project:
                        self._cv.wait()
                    handle.state = "running"
            else:
                with self._lock:
                    handle.state = "running"
            return run_session(
                config=config,
                persona=persona,
                objective=objective,
                brain=brain,
                memory=self.memory,
                upload_screenshots=upload_screenshots,
                objective_check=objective_check,
                environment=environment,
                caller=caller,
                on_step=on_step,
                session_id=session_id,
                batch_id=batch_id,
            )

        with self._lock:
            self._handles[session_id] = handle
            future = self._executor.submit(run)
            handle.future = future

        def _on_done(_f):
            with self._cv:
                self._cv.notify_all()  # wake any project-slot waiters
            if self.memory:
                self._record_spend(config.project_id, caller, brain)

        future.add_done_callback(_on_done)
        return session_id

    def _record_spend(self, project_id: str, caller: str | None, brain: Brain) -> None:
        tokens = getattr(brain, "token_usage", lambda: 0)()
        if self.memory and tokens:
            self.memory.record_spend(project_id, caller or "", tokens)

    def start_batch(
        self,
        config: ResolvedRunConfig,
        personas: list[Persona],
        objective: str,
        brain_factory: Callable[[], Brain],
        *,
        environment: str = "dev",
        caller: str | None = None,
        objective_check: ObjectiveCheck | None = None,
        upload_screenshots: bool = True,
        on_step_factory: Callable[[str], Callable[[int, StepRecord], None]] | None = None,
    ) -> str:
        """Fan out `objective` across every persona in `personas`, in
        parallel up to `max_per_project` at a time — the rest queue rather
        than reject (see `start_session`). One fresh Brain instance per
        persona (never shared across threads: cheap, and avoids any need to
        make a provider adapter thread-safe). Returns a batch_id immediately;
        member sessions are visible via get_batch_report.

        `on_step_factory`, if given, is called once per member with that
        member's *pre-generated* session_id and must return an on_step
        callback for it — this is how a caller (e.g. the API) wires up
        per-session live-step streaming for each persona in the batch,
        keyed by a session_id it couldn't otherwise know before the batch
        actually started.
        """
        batch_id = str(uuid.uuid4())
        if self.memory:
            self.memory.ensure_project(config.project_id, config.project_id, config.base_url)
            self.memory.create_batch(batch_id, config.project_id, objective, environment, caller)

        session_ids = []
        for persona in personas:
            session_id = str(uuid.uuid4())
            self.start_session(
                config=config,
                persona=persona,
                objective=objective,
                brain=brain_factory(),
                environment=environment,
                caller=caller,
                objective_check=objective_check,
                upload_screenshots=upload_screenshots,
                batch_id=batch_id,
                queue_if_full=True,
                session_id=session_id,
                on_step=on_step_factory(session_id) if on_step_factory else None,
            )
            session_ids.append(session_id)

        with self._lock:
            self._batches[batch_id] = _BatchHandle(batch_id=batch_id, session_ids=session_ids)
        return batch_id

    def get_batch_session_ids(self, batch_id: str) -> list[str]:
        handle = self._batches.get(batch_id)
        if handle is None:
            raise KeyError(f"unknown batch_id: {batch_id}")
        return list(handle.session_ids)

    def get_batch_report(self, batch_id: str) -> list[BatchMemberResult]:
        """Blocks until every member session finishes. One persona's
        exception (a transient provider error, say) is captured per-member,
        not allowed to abort the whole list and hide everyone else's
        results — this is exactly what live testing against a real,
        occasionally-flaky LLM backend caught: an ollama connection blip on
        one persona used to take the entire batch report down with it."""
        out = []
        for sid in self.get_batch_session_ids(batch_id):
            handle = self._handles.get(sid)
            persona_id = handle.persona_id if handle else ""
            try:
                out.append(BatchMemberResult(session_id=sid, persona_id=persona_id, result=self.get_report(sid)))
            except Exception as e:
                out.append(BatchMemberResult(session_id=sid, persona_id=persona_id, error=str(e)))
        return out

    def get_status(self, session_id: str) -> str:
        handle = self._handles.get(session_id)
        if handle is None:
            if self.memory:
                row = self.memory.get_session(session_id)
                if row:
                    return row["status"]
            raise KeyError(f"unknown session_id: {session_id}")
        if not handle.future.done():
            return handle.state
        return "failed" if handle.future.exception() else "completed"

    def get_report(self, session_id: str) -> SessionResult:
        """Blocks until the session finishes, then returns its result (or
        re-raises whatever exception it failed with)."""
        handle = self._handles.get(session_id)
        if handle is None:
            raise KeyError(f"unknown session_id: {session_id}")
        return handle.future.result()

    def add_completion_callback(self, session_id: str, callback: Callable[[Future], None]) -> None:
        """Register `callback(future)` to run when `session_id` finishes —
        used by the Local Control API to push a WebSocket completion event
        without the Orchestrator knowing anything about it."""
        handle = self._handles.get(session_id)
        if handle is None:
            raise KeyError(f"unknown session_id: {session_id}")
        handle.future.add_done_callback(callback)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=True)
