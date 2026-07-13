-- Migration 021: deal health score history table
-- Stores daily snapshots of each deal's health_score for trend charting.
-- A Celery beat task (or manual call) should INSERT one row per deal per day.

CREATE TABLE IF NOT EXISTS deal_health_score_history (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id  UUID NOT NULL REFERENCES workspaces(id)  ON DELETE CASCADE,
    deal_id       UUID NOT NULL REFERENCES deals(id)        ON DELETE CASCADE,
    score         INT  NOT NULL CHECK (score >= 0 AND score <= 100),
    recorded_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_dhsh_deal_recorded
    ON deal_health_score_history(deal_id, recorded_at DESC);

CREATE INDEX IF NOT EXISTS idx_dhsh_workspace
    ON deal_health_score_history(workspace_id);

ALTER TABLE deal_health_score_history ENABLE ROW LEVEL SECURITY;

CREATE POLICY workspace_isolation ON deal_health_score_history
    USING (workspace_id = current_setting('app.current_workspace_id')::uuid);
