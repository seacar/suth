-- Multi-persona batch runs: N sessions started together against the same
-- objective/project, grouped for a combined report.
CREATE TABLE IF NOT EXISTS batches (
    id          TEXT PRIMARY KEY,
    project_id  TEXT NOT NULL REFERENCES projects(id),
    objective   TEXT NOT NULL,
    environment TEXT NOT NULL,
    caller      TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE sessions ADD COLUMN IF NOT EXISTS batch_id TEXT REFERENCES batches(id);
