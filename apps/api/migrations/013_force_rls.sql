-- ─── 013_force_rls.sql ───────────────────────────────────────────────────────
-- Harden tenant isolation by FORCING row-level security on every workspace-scoped
-- table, and guarantee each one carries the standard workspace policy in the
-- auth.uid() pattern established by 001_unified_schema.sql / 008_rls_indexes.sql:
--
--     USING (workspace_id = (SELECT workspace_id FROM users WHERE supabase_uid = auth.uid()))
--
-- Background:
--   * 001/008/012 ENABLE row level security and define per-table policies, but
--     ENABLE RLS does NOT apply to the table owner. Postgres exempts the owner
--     (and any superuser / BYPASSRLS role) from RLS unless the table is also set
--     to FORCE ROW LEVEL SECURITY. The CRM API connects with a single role; if
--     that role owns these tables (the common Supabase / single-DSN setup), the
--     ENABLE-only policies never constrain it and cross-workspace reads/writes
--     are possible at the SQL layer.
--   * call_summaries (004) shipped without RLS enabled AND without a policy — it
--     is fixed here (ENABLE + FORCE + policy).
--
-- ⚠️  REQUIRED OPS FOLLOW-UP (NOT performed by this migration) ⚠️
-- ──────────────────────────────────────────────────────────────────────────────
--   FORCE ROW LEVEL SECURITY only actually ENFORCES isolation when the API
--   connects as a Postgres role that is ALL of:
--       • NON-superuser
--       • NON-BYPASSRLS  (no rolbypassrls)
--       • NOT the OWNER of these tables
--   FORCE makes the table owner subject to RLS, but superusers and BYPASSRLS
--   roles still bypass policies entirely, and on Supabase the default
--   `postgres` / service-role connection is privileged. Therefore, to make this
--   migration effective in production, ops MUST:
--       1. Create a dedicated, unprivileged login role, e.g.:
--            CREATE ROLE app_authenticated LOGIN PASSWORD '<secret>'
--              NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
--            GRANT USAGE ON SCHEMA public TO app_authenticated;
--            GRANT SELECT, INSERT, UPDATE, DELETE
--              ON ALL TABLES IN SCHEMA public TO app_authenticated;
--            ALTER DEFAULT PRIVILEGES IN SCHEMA public
--              GRANT SELECT, INSERT, UPDATE, DELETE TO app_authenticated;
--          (app_authenticated must NOT own the tables and must NOT be granted
--           BYPASSRLS or superuser.)
--       2. Ensure auth.uid() resolves for that connection — the request's
--          Supabase JWT `sub` must be propagated per transaction, e.g. via
--          SET LOCAL request.jwt.claim.sub = '<uid>' (or SET ROLE to the
--          Supabase `authenticated` role with the JWT applied). Without a
--          resolvable auth.uid(), the subquery returns NULL and every row is
--          filtered out.
--       3. Repoint the API's DATABASE_URL to connect as that role
--          (USER=app_authenticated). THIS IS AN OPS/ENV CHANGE — this SQL
--          migration cannot and does not change DATABASE_URL.
--   Until step 3 is done, these policies + FORCE are inert for the privileged
--   connection currently in use; nothing breaks, but isolation is not yet
--   enforced at the DB layer.
--
-- This migration must be applied to the production Supabase database by the user
-- (the user applies migrations to prod; this file does not self-apply).
--
-- Idempotent / re-runnable: ENABLE/FORCE RLS are no-ops if already set, and each
-- policy is (re)created with DROP POLICY IF EXISTS + CREATE POLICY. Every table
-- is guarded with to_regclass(...) so the migration is safe even if a given
-- environment is missing one of these tables.
-- ──────────────────────────────────────────────────────────────────────────────

DO $$
DECLARE
  -- Every tenant-scoped table: each has a NOT NULL workspace_id FK to
  -- workspaces(id) and the standard auth.uid() isolation policy.
  tbl  TEXT;
  tbls TEXT[] := ARRAY[
    'contacts',
    'deals',
    'tasks',
    'messages',
    'projects',
    'agents',
    'activity_events',
    'clarity_scores',
    'call_summaries',
    'connectors',
    'metric_templates',
    'kpi_snapshots',
    'commitments'
  ];
BEGIN
  FOREACH tbl IN ARRAY tbls LOOP
    -- Only touch tables that actually exist in this database.
    IF to_regclass(format('public.%I', tbl)) IS NOT NULL THEN
      -- FORCE requires RLS to be ENABLED to have any effect; ENABLE first so
      -- this also repairs call_summaries, which shipped with neither.
      EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY;', tbl);
      EXECUTE format('ALTER TABLE public.%I FORCE  ROW LEVEL SECURITY;', tbl);

      -- (Re)create the workspace isolation policy idempotently. Policy name
      -- matches the existing convention "<table>_policy".
      EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I;', tbl || '_policy', tbl);
      EXECUTE format(
        'CREATE POLICY %I ON public.%I '
        'USING (workspace_id = (SELECT workspace_id FROM users WHERE supabase_uid = auth.uid()));',
        tbl || '_policy', tbl
      );
    END IF;
  END LOOP;
END
$$;
