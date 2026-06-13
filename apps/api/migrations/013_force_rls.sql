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
--
-- ══════════════════════════════════════════════════════════════════════════════
--  CUTOVER RUNBOOK (ops) — make the backstop ENFORCING and prove it
-- ══════════════════════════════════════════════════════════════════════════════
-- The app-side per-request tenant context is implemented in app/database.py
-- (set_tenant_context) + app/dependencies.py and is GATED behind the config flag
-- DB_RLS_CONTEXT_ENABLED (default False = INERT). Coordinated cutover:
--
--   1. Create a least-privilege login role that is NON-superuser, NON-BYPASSRLS,
--      and NOT the owner of these tables:
--        CREATE ROLE app_authenticated LOGIN PASSWORD '<secret>'
--          NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
--        GRANT USAGE ON SCHEMA public TO app_authenticated;
--        GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public
--          TO app_authenticated;
--        GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_authenticated;
--        ALTER DEFAULT PRIVILEGES IN SCHEMA public
--          GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_authenticated;
--        -- app_authenticated must NOT own the tables and must NOT have BYPASSRLS.
--      The policies read auth.uid() = (request.jwt.claims ->> 'sub'); the app sets
--      request.jwt.claims per transaction (SET LOCAL) so auth.uid() resolves.
--      Ensure the auth schema / auth.uid() helper is visible to the role (Supabase
--      ships it; if absent, define auth.uid() as a SQL function reading the GUC).
--   2. Apply THIS migration (013) to prod.
--   3. Repoint the API DATABASE_URL user to app_authenticated (USER=app_authenticated).
--      ── ENV/OPS change; not performed by this SQL.
--   4. Set DB_RLS_CONTEXT_ENABLED=true in the api service env and redeploy.
--   5. DECISIVE TEST (must return ZERO rows / be denied) — run AS THE NEW ROLE
--      with a tenant context bound, exactly as the app does per request:
--        BEGIN;
--          SET LOCAL request.jwt.claims = '{"sub":"<a real users.supabase_uid>"}';
--          -- unfiltered cross-tenant probe: must now return only that user's ws
--          SELECT count(*) AS visible, count(distinct workspace_id) AS workspaces
--            FROM contacts;          -- expect workspaces = 1 (was 2 in evidence-rls.md)
--          SELECT count(*) FROM call_summaries;  -- now policy-bound (was 0 policies)
--        COMMIT;
--      Pre-cutover (privileged role) the same SELECT returns rows spanning 2
--      workspaces (see ../audit/.../evidence-rls.md §5). Post-cutover it must be
--      scoped to a single workspace, proving the DB-level backstop is live.
--   ROLLBACK: set DB_RLS_CONTEXT_ENABLED=false and/or repoint DATABASE_URL back to
--      the privileged role. FORCE RLS + policies are harmless to a BYPASSRLS role,
--      so leaving 013 applied does not break the privileged connection.
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
