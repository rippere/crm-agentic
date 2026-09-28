-- ─── 026_connectors_outlook.sql ─────────────────────────────────────────────
-- Allow 'outlook' as a connectors.service value (Outlook / Microsoft 365
-- mailbox connector, app/routers/outlook.py).
--
-- 001_unified_schema.sql created `service TEXT NOT NULL CHECK (service IN
-- ('gmail', 'slack', 'teams'))`; Postgres auto-named that constraint
-- `connectors_service_check` (verified against prod). Until this runs, the
-- Outlook OAuth callback's INSERT fails the CHECK and the connect flow 500s.
--
-- Widening only: every existing row ('gmail' / 'slack') still satisfies the new
-- constraint, so currently-deployed code is unaffected. Re-runnable (DROP IF
-- EXISTS then ADD). connectors is a small table, so the brief ACCESS EXCLUSIVE
-- lock while ADD CONSTRAINT validates existing rows is negligible.
--
-- NOTE: USER-applied to prod — this migration is written here but is NOT executed
-- automatically; apply it manually against the production database BEFORE the
-- Outlook connector is used. The same CHECK is mirrored into init_docker.sql for
-- the Docker path, which has no migration runner.

BEGIN;

ALTER TABLE connectors DROP CONSTRAINT IF EXISTS connectors_service_check;
ALTER TABLE connectors
  ADD CONSTRAINT connectors_service_check
  CHECK (service IN ('gmail', 'outlook', 'slack', 'teams'));

COMMIT;
