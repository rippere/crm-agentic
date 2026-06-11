-- Migration 016: Add win_loss_reason column to deals
-- Tracks why a deal was won or lost for analytics

ALTER TABLE deals
  ADD COLUMN IF NOT EXISTS win_loss_reason TEXT
    CHECK (win_loss_reason IN ('price','competition','timing','fit','champion_left','other'));

CREATE INDEX IF NOT EXISTS idx_deals_win_loss_reason
  ON deals (workspace_id, stage, win_loss_reason)
  WHERE win_loss_reason IS NOT NULL;
