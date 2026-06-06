-- ─── 002_webhook_logs.sql ────────────────────────────────────────────────────
-- Webhook delivery log: persists every Gmail Pub/Sub push and Slack Events API
-- call so operators can audit delivery, replay errors, and track Celery job IDs.

CREATE TABLE IF NOT EXISTS webhook_logs (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  -- workspace_id is nullable: a push may arrive before the connector is resolved
  workspace_id     UUID REFERENCES workspaces(id) ON DELETE CASCADE,
  source           TEXT NOT NULL CHECK (source IN ('gmail', 'slack')),
  event_type       TEXT NOT NULL,
  status           TEXT NOT NULL DEFAULT 'received'
                     CHECK (status IN ('received', 'queued', 'error')),
  payload_summary  TEXT,
  job_id           TEXT,
  error_detail     TEXT,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS webhook_logs_workspace_created_idx
  ON webhook_logs (workspace_id, created_at DESC);

CREATE INDEX IF NOT EXISTS webhook_logs_created_idx
  ON webhook_logs (created_at DESC);

ALTER TABLE webhook_logs ENABLE ROW LEVEL SECURITY;

CREATE POLICY workspace_isolation ON webhook_logs
  USING (
    workspace_id IS NULL OR
    workspace_id IN (
      SELECT workspace_id FROM users WHERE supabase_uid = auth.uid()
    )
  );
