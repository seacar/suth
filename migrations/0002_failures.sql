-- Phase 2: taxonomy classifier output — plan §6.
CREATE TABLE IF NOT EXISTS failures (
    id             SERIAL PRIMARY KEY,
    session_id     TEXT NOT NULL REFERENCES sessions(id),
    taxonomy_label TEXT NOT NULL,
    step_index     INTEGER NOT NULL,
    detail         TEXT
);
