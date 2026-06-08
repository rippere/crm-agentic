-- ─── 014_deal_notes.sql ──────────────────────────────────────────────────────
-- Append-only notes thread for deals (Phase 11c / WS-L).
-- Each note is an immutable row; the deal-detail page renders them chronologically.
-- Fully idempotent / re-runnable (IF NOT EXISTS + DROP POLICY IF EXISTS).
--
-- NOTE: USER-applied to prod — this migration is written here but is NOT executed
-- automatically; apply it manually against the production database.

CREATE TABLE IF NOT EXISTS deal_notes (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id  UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  deal_id       UUID NOT NULL REFERENCES deals(id) ON DELETE CASCADE,
  body          TEXT NOT NULL DEFAULT '',
  author        TEXT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_deal_notes_workspace ON deal_notes (workspace_id);
CREATE INDEX IF NOT EXISTS idx_deal_notes_deal      ON deal_notes (deal_id, created_at);

-- ─── RLS (matches the auth.uid() pattern from 008_rls_indexes.sql) ───────────────

ALTER TABLE deal_notes ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "deal_notes_policy" ON deal_notes;
CREATE POLICY "deal_notes_policy" ON deal_notes
  USING (workspace_id = (SELECT workspace_id FROM users WHERE supabase_uid = auth.uid()));
