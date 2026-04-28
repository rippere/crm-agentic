-- ─── 003_deal_health.sql ─────────────────────────────────────────────────────
-- Adds deal health scoring: health_score (0-100) + stage_changed_at

ALTER TABLE deals
  ADD COLUMN IF NOT EXISTS health_score      INT NOT NULL DEFAULT 100
                                             CHECK (health_score BETWEEN 0 AND 100),
  ADD COLUMN IF NOT EXISTS stage_changed_at  TIMESTAMPTZ NOT NULL DEFAULT NOW();

CREATE INDEX IF NOT EXISTS idx_deals_workspace_health
  ON deals (workspace_id, health_score);
