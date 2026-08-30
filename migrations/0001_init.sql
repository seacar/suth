-- Initial schema — plan §6. `failures` and `budgets` are deferred to Phase 2/3.
CREATE TABLE IF NOT EXISTS projects (
    id             TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    base_url       TEXT NOT NULL,
    staging_config JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS personas (
    id               TEXT NOT NULL,
    project_id       TEXT REFERENCES projects(id),
    name             TEXT NOT NULL,
    version          INTEGER NOT NULL DEFAULT 1,
    definition_jsonb JSONB NOT NULL,
    PRIMARY KEY (id, version)
);

CREATE TABLE IF NOT EXISTS sessions (
    id             TEXT PRIMARY KEY,
    project_id     TEXT NOT NULL REFERENCES projects(id),
    persona_id     TEXT NOT NULL,
    objective      TEXT NOT NULL,
    environment    TEXT NOT NULL,
    model_used     TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'running',
    verdict        TEXT,
    friction_score DOUBLE PRECISION,
    started_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at       TIMESTAMPTZ,
    caller         TEXT
);

CREATE TABLE IF NOT EXISTS steps (
    id                SERIAL PRIMARY KEY,
    session_id        TEXT NOT NULL REFERENCES sessions(id),
    step_index        INTEGER NOT NULL,
    dom_snapshot_ref  TEXT,
    thought           TEXT NOT NULL,
    emotion           TEXT NOT NULL,
    frustration_delta INTEGER NOT NULL,
    action_jsonb      JSONB NOT NULL,
    screenshot_ref    TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (session_id, step_index)
);
