-- Migration 024: Add disposition to activity_events
-- A call-type activity now requires a mandatory next-step disposition
-- (follow_up_1mo | follow_up_6mo | dead), enforced server-side in create_activity.
-- This column persists it. Nullable with no default: non-call activities and every
-- existing row stay NULL, so there is no backfill and no table-rewrite lock — safe on
-- the live table (same profile as 017_deal_next_action.sql). The live DB is Postgres 17,
-- so an inline ADD COLUMN with a NULL-permissive CHECK is metadata-only / lock-safe
-- (no NOT VALID / VALIDATE CONSTRAINT dance needed). Idempotent via ADD COLUMN IF NOT
-- EXISTS: re-running skips the column and its inline CHECK, so no duplicate constraint.
-- NO RLS lines: activity_events already carries its policy via 013_force_rls; a
-- column-only change touches no policy.

ALTER TABLE activity_events
  ADD COLUMN IF NOT EXISTS disposition TEXT
    CHECK (disposition IS NULL OR disposition IN ('follow_up_1mo', 'follow_up_6mo', 'dead'));
