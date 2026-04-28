-- ─── 004_call_summaries.sql ──────────────────────────────────────────────────
-- Stores transcribed + AI-summarised call recordings

CREATE TABLE IF NOT EXISTS call_summaries (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id     UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  contact_id       UUID REFERENCES contacts(id) ON DELETE SET NULL,
  title            TEXT NOT NULL DEFAULT 'Untitled Call',
  duration_seconds INT,
  transcript       TEXT NOT NULL DEFAULT '',
  summary          TEXT NOT NULL DEFAULT '',
  action_items     JSONB NOT NULL DEFAULT '[]',
  participants     TEXT,
  call_date        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  model_used       TEXT NOT NULL DEFAULT 'whisper-base',
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_call_summaries_workspace
  ON call_summaries (workspace_id, call_date DESC);

CREATE INDEX IF NOT EXISTS idx_call_summaries_contact
  ON call_summaries (contact_id);
