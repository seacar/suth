-- Phase 2: record which persona version a session actually ran, so bumping a
-- persona's YAML later doesn't silently reinterpret old session records.
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS persona_version INTEGER NOT NULL DEFAULT 1;
