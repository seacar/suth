-- Phase 6: per-session video replay, synced to the existing step timeline
-- via video_started_at (the moment Playwright's recording began — steps'
-- existing `created_at` timestamps are offset against this to seek the
-- player, no new per-step column needed).
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS video_ref TEXT;
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS video_started_at TIMESTAMPTZ;
