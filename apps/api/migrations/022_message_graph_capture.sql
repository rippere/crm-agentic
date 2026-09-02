-- ─── 022_message_graph_capture.sql ──────────────────────────────────────────
-- Make relationship edges and outreach outcomes RECORDABLE.
--
-- Until now `messages` stored only `sender_email`, so the database could not
-- answer "who else was on this thread?" or "did that email ever get a reply?".
-- Gmail already returns To/Cc/Message-ID/threadId on every message fetch and the
-- ingest worker parsed them into a dict and dropped them on the floor.
--
-- All additions are additive and nullable-or-defaulted, so existing rows and
-- currently-deployed code keep working unchanged:
--   to_emails / cc_emails  — JSONB arrays of bare lowercased addresses (edges)
--   thread_id              — Gmail threadId; reply derivation joins on this
--   rfc_message_id         — RFC 5322 Message-ID header. NOT a foreign key —
--                            see the note in models/message.py
--   in_reply_to            — RFC 5322 In-Reply-To header (threading without Gmail)
--   direction              — 'inbound' | 'outbound'
--   graph_only             — TRUE = metadata-only row (no body); hidden from
--                            every message-facing read path, kept for the graph
--
-- Fully idempotent / re-runnable (IF NOT EXISTS).
--
-- NOTE: USER-applied to prod — this migration is written here but is NOT
-- executed automatically; apply it manually against the production database.
--
-- ORDERING IS LOAD-BEARING: apply this migration BEFORE deploying the code that
-- maps these columns. SQLAlchemy enumerates every mapped column on
-- select(Message), so a model deployed ahead of its migration 500s every
-- message/contact/deal read path at once — exactly the 020_deal_mentions
-- incident (merged 2026-07-10, migration unapplied, all deal endpoints down
-- until 2026-07-15). Applying this migration early is safe; deploying early is not.

ALTER TABLE messages ADD COLUMN IF NOT EXISTS to_emails      JSONB   NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS cc_emails      JSONB   NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS thread_id      TEXT;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS rfc_message_id TEXT;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS in_reply_to    TEXT;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS direction      TEXT;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS graph_only     BOOLEAN NOT NULL DEFAULT FALSE;

-- Reply derivation: given an outbound message, find a later inbound message in
-- the same thread. This index is the one that makes that join cheap.
CREATE INDEX IF NOT EXISTS idx_messages_thread
    ON messages (workspace_id, thread_id, received_at)
    WHERE thread_id IS NOT NULL;

-- Every message-facing read path now filters graph_only rows out; keep that
-- predicate cheap as metadata-only rows come to outnumber deal-relevant ones.
CREATE INDEX IF NOT EXISTS idx_messages_visible
    ON messages (workspace_id, contact_id)
    WHERE graph_only = FALSE;
