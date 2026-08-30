import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from suth.abandonment import AbandonmentEvaluator
from suth.brain.history import HistoryWindow, StepRecord
from suth.brain.interface import Brain
from suth.config import ResolvedRunConfig
from suth.db import Memory
from suth.driver.browser import Driver
from suth.objective import ObjectiveCheck
from suth.personas.schema import Persona
from suth.scoring import friction_score as compute_friction_score
from suth.taxonomy import FailureHit, classify_session


@dataclass
class SessionResult:
    session_id: str
    persona_id: str
    verdict: str
    step_count: int
    final_frustration: int
    friction_score: float
    failures: list[FailureHit] = field(default_factory=list)


def run_session(
    config: ResolvedRunConfig,
    persona: Persona,
    objective: str,
    brain: Brain,
    memory: Memory | None = None,
    upload_screenshots: bool = True,
    objective_check: ObjectiveCheck | None = None,
    environment: str = "dev",
    caller: str | None = None,
    on_step: Callable[[int, StepRecord], None] | None = None,
    session_id: str | None = None,
    batch_id: str | None = None,
) -> SessionResult:
    """The 6-step loop from plan §4: capture -> infer -> validate -> execute ->
    evaluate -> log -> loop, up to config.max_steps. `on_step` is an optional
    hook (used by `--step` mode) invoked after each step is logged. `session_id`
    lets a caller (the Orchestrator) know the id before the run completes.
    `batch_id` links this session to a multi-persona batch run, if any.
    """
    session_id = session_id or str(uuid.uuid4())
    history = HistoryWindow()
    evaluator = AbandonmentEvaluator(persona)
    caller = caller or "cli"

    if memory:
        memory.ensure_project(config.project_id, config.project_id, config.base_url)
        memory.create_session(
            session_id=session_id,
            project_id=config.project_id,
            persona_id=persona.id,
            persona_version=persona.version,
            objective=objective,
            environment=environment,
            model_used=brain.__class__.__name__,
            caller=caller,
            batch_id=batch_id,
        )

    stop_reason = "timeout"
    step_index = 0
    deadline = time.monotonic() + config.timeout_seconds

    try:
        with Driver(
            base_url=config.base_url,
            headed=config.headed,
            storage_state_path=config.auth.path if config.auth else None,
            interaction_mode=persona.interaction_mode,
            record_video=config.record_video,
        ) as driver:
            while step_index < config.max_steps:
                if time.monotonic() >= deadline:
                    # Wall-clock budget exhausted — same bucket as running out
                    # of max_steps (classify_session treats "timeout" as "we
                    # stopped because we ran out of allotted budget", not an
                    # evaluator-detected failure pattern).
                    stop_reason = "timeout"
                    break
                step_index += 1

                # 1. capture
                dom_state = driver.snapshot()

                # 2. infer
                decision = brain.generate_step(
                    persona=persona,
                    objective=objective,
                    history_text=history.render(),
                    dom_state=dom_state,
                )

                # 3. validate output: a target must reference a real element
                valid_refs = {el.ref for el in dom_state.elements}
                action = decision.action
                if action.target is not None and action.target not in valid_refs:
                    action = action.model_copy(update={"target": None})
                    decision = decision.model_copy(update={"action": action})

                # 4. execute
                action_result = None
                if action.type not in ("declare_confusion", "abandon"):
                    action_result = driver.execute(action)

                # 5. evaluate
                objective_met = bool(objective_check) and driver.check_objective(objective_check)
                fired = None if objective_met else evaluator.observe(decision, action_result)

                # 6. log
                screenshot_ref = action_result.screenshot_path if action_result else None
                if memory:
                    if upload_screenshots and screenshot_ref:
                        from suth.storage import upload_screenshot

                        screenshot_ref = upload_screenshot(screenshot_ref, session_id)
                    memory.log_step(
                        session_id=session_id,
                        step_index=step_index,
                        thought=decision.thought,
                        emotion=decision.emotion,
                        frustration_delta=decision.frustration_delta,
                        action=action.model_dump(),
                        dom_snapshot_ref=dom_state.url,
                        screenshot_ref=screenshot_ref,
                    )

                record = StepRecord(
                    step_index=step_index,
                    thought=decision.thought,
                    action_type=action.type,
                    target=action.target,
                    dom_changed=bool(action_result and action_result.dom_changed),
                    url=dom_state.url,
                    emotion=decision.emotion,
                    frustration_delta=decision.frustration_delta,
                    screenshot_ref=screenshot_ref,
                )
                history.add(record)
                if on_step:
                    on_step(step_index, record)

                if objective_met:
                    stop_reason = "objective_met"
                    break
                if fired:
                    stop_reason = fired
                    break

        verdict, hits = classify_session(
            history.records, stop_reason, objective_check_configured=bool(objective_check)
        )
        score = compute_friction_score(evaluator.frustration_score, verdict, hits)
    except Exception:
        # Whatever else went wrong (a hung driver call past its own timeout,
        # an LLM provider error, a DB write failure), the session must still
        # reach a terminal state — otherwise it's stuck at status="running"
        # forever with no ended_at, which is exactly the "hangs forever" the
        # GUI (and list_recently_finished's polling) can never resolve.
        if memory:
            memory.finish_session(session_id=session_id, status="failed", verdict="error")
        raise

    if memory:
        memory.log_failures(session_id, hits)
        memory.finish_session(
            session_id=session_id, status="completed", verdict=verdict, friction_score=score
        )
        if upload_screenshots and driver.video_path and driver.video_started_at:
            from suth.storage import upload_video
            from suth.video import duration_from_session_times, read_webm_duration_seconds

            video_ref = upload_video(driver.video_path, session_id)
            duration = read_webm_duration_seconds(driver.video_path)
            if duration is None:
                row = memory.get_session(session_id)
                duration = duration_from_session_times(
                    row.get("ended_at") if row else None, driver.video_started_at
                )
            memory.set_video(session_id, video_ref, driver.video_started_at, duration)

    return SessionResult(
        session_id=session_id,
        persona_id=persona.id,
        verdict=verdict,
        step_count=step_index,
        final_frustration=evaluator.frustration_score,
        friction_score=score,
        failures=hits,
    )
