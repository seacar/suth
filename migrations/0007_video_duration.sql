-- Persist replay length so History can show and sort by video time.
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS video_duration_seconds DOUBLE PRECISION;

UPDATE sessions
SET video_duration_seconds = EXTRACT(EPOCH FROM (ended_at - video_started_at))
WHERE video_ref IS NOT NULL
  AND video_duration_seconds IS NULL
  AND ended_at IS NOT NULL
  AND video_started_at IS NOT NULL
  AND ended_at >= video_started_at;
