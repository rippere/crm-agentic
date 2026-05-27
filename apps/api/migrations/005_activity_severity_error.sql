-- ─── 005_activity_severity_error.sql ─────────────────────────────────────────
-- Adds 'error' to the activity_events.severity CHECK constraint.
--
-- The application code (slack_interactions.py) already writes severity='error'
-- for HITL failures.  The original CHECK only allowed ('info', 'success',
-- 'warning'), causing a constraint violation on every HITL error path.
--
-- Strategy: drop the old constraint, add the corrected one.
-- Safe to run repeatedly — DROP IF EXISTS prevents errors on re-run.

ALTER TABLE activity_events
  DROP CONSTRAINT IF EXISTS activity_events_severity_check;

ALTER TABLE activity_events
  ADD CONSTRAINT activity_events_severity_check
  CHECK (severity IN ('info', 'success', 'warning', 'error'));
