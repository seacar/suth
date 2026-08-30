import os
from datetime import datetime, timezone

from sqlalchemy import (
    Engine,
    MetaData,
    Table,
    create_engine,
    delete,
    insert,
    select,
    update,
)

metadata = MetaData()


def _reflect(engine: Engine) -> dict[str, Table]:
    """Mirrors migrations/0001_init.sql — reflected as SQLAlchemy Core Tables
    (not ORM classes) since the .sql file, not Python, is the schema's source
    of truth."""
    metadata.reflect(
        bind=engine,
        only=["projects", "personas", "sessions", "steps", "failures", "budgets", "batches"],
    )
    return {t.name: t for t in metadata.tables.values()}


def get_engine() -> Engine:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL is not set — run via `specific exec cli -- ...` (or `specific dev`)"
        )
    return create_engine(database_url.replace("postgres://", "postgresql+psycopg://", 1))


class Memory:
    """Postgres-backed session/step log — plan §6. Writes are per-step and
    committed immediately (write-through), so a crash mid-session doesn't lose
    the transcript captured so far.
    """

    def __init__(self, engine: Engine):
        self.engine = engine
        self.tables = _reflect(engine)

    def ensure_project(self, project_id: str, name: str, base_url: str) -> None:
        t = self.tables["projects"]
        with self.engine.begin() as conn:
            exists = conn.execute(select(t.c.id).where(t.c.id == project_id)).first()
            if not exists:
                conn.execute(insert(t).values(id=project_id, name=name, base_url=base_url))

    def get_project(self, project_id: str) -> dict | None:
        t = self.tables["projects"]
        with self.engine.connect() as conn:
            row = conn.execute(select(t).where(t.c.id == project_id)).mappings().first()
            return dict(row) if row else None

    def update_project(
        self,
        project_id: str,
        *,
        name: str | None = None,
        base_url: str | None = None,
    ) -> None:
        t = self.tables["projects"]
        values: dict[str, str] = {}
        if name is not None:
            values["name"] = name
        if base_url is not None:
            values["base_url"] = base_url
        if not values:
            return
        with self.engine.begin() as conn:
            conn.execute(update(t).where(t.c.id == project_id).values(**values))

    def create_session(
        self,
        session_id: str,
        project_id: str,
        persona_id: str,
        objective: str,
        environment: str,
        model_used: str,
        caller: str | None = None,
        persona_version: int = 1,
        batch_id: str | None = None,
    ) -> None:
        t = self.tables["sessions"]
        with self.engine.begin() as conn:
            conn.execute(
                insert(t).values(
                    id=session_id,
                    project_id=project_id,
                    persona_id=persona_id,
                    persona_version=persona_version,
                    objective=objective,
                    environment=environment,
                    model_used=model_used,
                    status="running",
                    caller=caller,
                    batch_id=batch_id,
                )
            )

    def create_batch(
        self, batch_id: str, project_id: str, objective: str, environment: str, caller: str | None = None
    ) -> None:
        t = self.tables["batches"]
        with self.engine.begin() as conn:
            conn.execute(
                insert(t).values(
                    id=batch_id, project_id=project_id, objective=objective,
                    environment=environment, caller=caller,
                )
            )

    def get_batch(self, batch_id: str) -> dict | None:
        t = self.tables["batches"]
        with self.engine.connect() as conn:
            row = conn.execute(select(t).where(t.c.id == batch_id)).mappings().first()
            return dict(row) if row else None

    def get_batch_sessions(self, batch_id: str) -> list[dict]:
        t = self.tables["sessions"]
        with self.engine.connect() as conn:
            rows = conn.execute(
                select(t).where(t.c.batch_id == batch_id).order_by(t.c.started_at)
            ).mappings()
            return [dict(r) for r in rows]

    def log_step(
        self,
        session_id: str,
        step_index: int,
        thought: str,
        emotion: str,
        frustration_delta: int,
        action: dict,
        dom_snapshot_ref: str | None = None,
        screenshot_ref: str | None = None,
    ) -> None:
        t = self.tables["steps"]
        with self.engine.begin() as conn:
            conn.execute(
                insert(t).values(
                    session_id=session_id,
                    step_index=step_index,
                    thought=thought,
                    emotion=emotion,
                    frustration_delta=frustration_delta,
                    action_jsonb=action,
                    dom_snapshot_ref=dom_snapshot_ref,
                    screenshot_ref=screenshot_ref,
                )
            )

    def finish_session(
        self,
        session_id: str,
        status: str,
        verdict: str,
        friction_score: float | None = None,
    ) -> None:
        t = self.tables["sessions"]
        with self.engine.begin() as conn:
            conn.execute(
                update(t)
                .where(t.c.id == session_id)
                .values(
                    status=status,
                    verdict=verdict,
                    friction_score=friction_score,
                    ended_at=datetime.now(timezone.utc),
                )
            )

    def set_video(
        self,
        session_id: str,
        video_ref: str,
        video_started_at: datetime,
        video_duration_seconds: float | None = None,
    ) -> None:
        """Attach the finalized replay video's storage ref, the moment
        Playwright began recording it (so steps' `created_at` can be offset
        for GUI seek), and the container duration when we have it."""
        t = self.tables["sessions"]
        values = {"video_ref": video_ref, "video_started_at": video_started_at}
        if video_duration_seconds is not None:
            values["video_duration_seconds"] = video_duration_seconds
        with self.engine.begin() as conn:
            conn.execute(update(t).where(t.c.id == session_id).values(**values))

    def get_session(self, session_id: str) -> dict | None:
        t = self.tables["sessions"]
        with self.engine.connect() as conn:
            row = conn.execute(select(t).where(t.c.id == session_id)).mappings().first()
            return dict(row) if row else None

    def list_recent_sessions(self, project_id: str | None = None, limit: int = 20) -> list[dict]:
        t = self.tables["sessions"]
        stmt = select(t).order_by(t.c.started_at.desc()).limit(limit)
        if project_id:
            stmt = stmt.where(t.c.project_id == project_id)
        with self.engine.connect() as conn:
            return [dict(r) for r in conn.execute(stmt).mappings()]

    def list_recently_finished(self, since) -> list[dict]:
        """Sessions that ended after `since` (a datetime) — used by the Local
        Control API's cross-process completion watcher (plan Phase 5): the
        only state every surface (CLI/MCP/API) shares is Postgres itself."""
        t = self.tables["sessions"]
        with self.engine.connect() as conn:
            rows = conn.execute(
                select(t).where(t.c.ended_at.isnot(None)).where(t.c.ended_at > since)
            ).mappings()
            return [dict(r) for r in rows]

    def get_steps(self, session_id: str) -> list[dict]:
        t = self.tables["steps"]
        with self.engine.connect() as conn:
            rows = conn.execute(
                select(t).where(t.c.session_id == session_id).order_by(t.c.step_index)
            ).mappings()
            return [dict(r) for r in rows]

    def log_failures(self, session_id: str, hits: list) -> None:
        if not hits:
            return
        t = self.tables["failures"]
        with self.engine.begin() as conn:
            conn.execute(
                insert(t),
                [
                    {
                        "session_id": session_id,
                        "taxonomy_label": h.taxonomy_label,
                        "step_index": h.step_index,
                        "detail": h.detail,
                    }
                    for h in hits
                ],
            )

    def get_failures(self, session_id: str) -> list[dict]:
        t = self.tables["failures"]
        with self.engine.connect() as conn:
            rows = conn.execute(
                select(t).where(t.c.session_id == session_id).order_by(t.c.step_index)
            ).mappings()
            return [dict(r) for r in rows]

    def set_budget(
        self, project_id: str, caller: str, token_cap: int, period: str = "all-time"
    ) -> None:
        """Declare/replace a spend cap. A (project_id, caller, period) with no
        row here is uncapped — enforcement only kicks in once declared."""
        t = self.tables["budgets"]
        with self.engine.begin() as conn:
            conn.execute(
                t.delete().where(
                    (t.c.project_id == project_id)
                    & (t.c.caller == caller)
                    & (t.c.period == period)
                )
            )
            conn.execute(
                insert(t).values(
                    project_id=project_id, caller=caller, period=period, token_cap=token_cap
                )
            )

    def get_budget(self, project_id: str, caller: str, period: str = "all-time") -> dict | None:
        t = self.tables["budgets"]
        with self.engine.connect() as conn:
            row = (
                conn.execute(
                    select(t).where(
                        (t.c.project_id == project_id)
                        & (t.c.caller == caller)
                        & (t.c.period == period)
                    )
                )
                .mappings()
                .first()
            )
            return dict(row) if row else None

    def record_spend(
        self, project_id: str, caller: str, tokens: int, period: str = "all-time"
    ) -> None:
        """No-op if no budget row exists for this key — spend is only tracked
        against a cap someone actually declared."""
        if tokens <= 0:
            return
        t = self.tables["budgets"]
        with self.engine.begin() as conn:
            conn.execute(
                update(t)
                .where(
                    (t.c.project_id == project_id)
                    & (t.c.caller == caller)
                    & (t.c.period == period)
                )
                .values(spend_to_date=t.c.spend_to_date + tokens)
            )

    def delete_project(self, project_id: str) -> list[str]:
        """Delete a project and all database rows tied to it.

        Returns session ids so callers can purge object storage artifacts.
        """
        sessions_t = self.tables["sessions"]
        with self.engine.begin() as conn:
            running = conn.execute(
                select(sessions_t.c.id).where(
                    (sessions_t.c.project_id == project_id) & (sessions_t.c.status == "running")
                )
            ).first()
            if running:
                raise ValueError(f"project '{project_id}' has a running session")

            session_ids = [
                row[0]
                for row in conn.execute(
                    select(sessions_t.c.id).where(sessions_t.c.project_id == project_id)
                )
            ]

            if session_ids:
                failures_t = self.tables["failures"]
                conn.execute(delete(failures_t).where(failures_t.c.session_id.in_(session_ids)))

                steps_t = self.tables["steps"]
                conn.execute(delete(steps_t).where(steps_t.c.session_id.in_(session_ids)))

            conn.execute(delete(sessions_t).where(sessions_t.c.project_id == project_id))

            batches_t = self.tables["batches"]
            conn.execute(delete(batches_t).where(batches_t.c.project_id == project_id))

            budgets_t = self.tables["budgets"]
            conn.execute(delete(budgets_t).where(budgets_t.c.project_id == project_id))

            projects_t = self.tables["projects"]
            conn.execute(delete(projects_t).where(projects_t.c.id == project_id))

        return session_ids
