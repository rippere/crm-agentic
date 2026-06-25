-- Migration 017: Add next_action + next_action_date to deals
-- Makes follow-up cadence HONEST — an explicit next step and when it's due, instead
-- of inferring urgency from stage_changed_at. Nullable, no default -> no backfill and
-- no table-rewrite lock; safe to run on the live table. Idempotent.

ALTER TABLE deals
  ADD COLUMN IF NOT EXISTS next_action TEXT,
  ADD COLUMN IF NOT EXISTS next_action_date DATE;

CREATE INDEX IF NOT EXISTS idx_deals_next_action_date
  ON deals (workspace_id, next_action_date)
  WHERE next_action_date IS NOT NULL;
