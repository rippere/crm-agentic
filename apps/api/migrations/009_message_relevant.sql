-- ─── 009_message_relevant.sql ────────────────────────────────────────────────
-- Adds a nullable 'relevant' flag to messages.
--
-- Set by the ingest pipeline and by the reprocess_workspace_messages task using
-- the existing _is_automated_sender + _is_deal_relevant heuristics. NULL means
-- "not yet evaluated"; the inbox UI defaults to showing All so nothing is hidden.
--
-- Non-destructive and idempotent — safe to re-run.

ALTER TABLE messages ADD COLUMN IF NOT EXISTS relevant BOOLEAN;
