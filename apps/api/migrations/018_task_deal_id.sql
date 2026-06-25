-- Migration 018: Add deal_id FK to tasks
-- Lets a task (including cc: follow-ups captured by /log) be scoped to the deal it
-- concerns, completing the contact_id link added in the by-external upsert. Nullable
-- FK with ON DELETE SET NULL -> deleting a deal orphans its tasks rather than cascading.
-- No backfill, no lock; safe on the live table. Idempotent.

ALTER TABLE tasks
  ADD COLUMN IF NOT EXISTS deal_id UUID REFERENCES deals(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_tasks_deal_id
  ON tasks (workspace_id, deal_id)
  WHERE deal_id IS NOT NULL;
