-- ─── 015_contact_notes.sql ───────────────────────────────────────────────────
-- Append-only notes thread for contacts (Phase 11d).
-- Each note is an immutable row; the contact-detail page renders them chronologically.
-- Fully idempotent / re-runnable (IF NOT EXISTS + DROP POLICY IF EXISTS).
--
-- NOTE: USER-applied to prod — this migration is written here but is NOT executed
-- automatically; apply it manually against the production database.

CREATE TABLE IF NOT EXISTS contact_notes (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id  UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  contact_id    UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
  body          TEXT NOT NULL DEFAULT '',
  author        TEXT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_contact_notes_workspace ON contact_notes (workspace_id);
CREATE INDEX IF NOT EXISTS idx_contact_notes_contact   ON contact_notes (contact_id, created_at);

-- ─── RLS (matches the auth.uid() pattern from 008_rls_indexes.sql) ───────────────

ALTER TABLE contact_notes ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "contact_notes_policy" ON contact_notes;
CREATE POLICY "contact_notes_policy" ON contact_notes
  USING (workspace_id = (SELECT workspace_id FROM users WHERE supabase_uid = auth.uid()));
