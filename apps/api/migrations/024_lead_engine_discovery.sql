-- ─── 024_lead_engine_discovery.sql ───────────────────────────────────────────
-- Autonomous Lead Engine, Increment 1 (Discovery). Adds discovery_runs and
-- widens leads.source to admit 'discovery'. Idempotent (IF NOT EXISTS + DROP ...
-- IF EXISTS). NOT executed automatically — apply by hand to Supabase prod. The
-- same DDL minus RLS is mirrored into init_docker.sql.
--
-- Follows the 023 house shape verbatim: `id UUID PK gen_random_uuid()`;
-- `workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE` first;
-- TEXT + inline-CHECK enums; JSONB NOT NULL DEFAULT '{}'; created_at/updated_at
-- TIMESTAMPTZ NOT NULL DEFAULT NOW(); workspace-first idx_<table>_ws_* indexes
-- with IF NOT EXISTS; RLS ENABLE-only keyed on users.supabase_uid = auth.uid().
--
-- FK ordering: discovery_runs references only workspaces (pre-023) and the leads
-- CHECK edit touches the shipped 023 leads table — both pre-exist in prod.

-- widen the shipped leads.source CHECK (023 names it leads_source_check implicitly)
ALTER TABLE leads DROP CONSTRAINT IF EXISTS leads_source_check;
ALTER TABLE leads ADD CONSTRAINT leads_source_check
  CHECK (source IN ('import','manual','web','api','referral','event','discovery'));

CREATE TABLE IF NOT EXISTS discovery_runs (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id  UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  locality      TEXT NOT NULL,                          -- "Burlington, VT"
  provider      TEXT,                                   -- places provider(s) used
  status        TEXT NOT NULL DEFAULT 'queued'
                  CHECK (status IN ('queued','running','succeeded','partial','failed')),
  params        JSONB NOT NULL DEFAULT '{}',            -- categories, radius_m, max_venues, requested provider
  rubric        JSONB NOT NULL DEFAULT '{}',            -- snapshot of DEFAULT_RUBRIC (or per-run override) used
  stats         JSONB NOT NULL DEFAULT '{}',            -- {found, scored, inserted, skipped, errors}
  job_id        TEXT,                                   -- Celery task id (mirrors agents.py marker)
  error         TEXT,
  started_at    TIMESTAMPTZ,
  completed_at  TIMESTAMPTZ,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_discovery_runs_ws_status  ON discovery_runs (workspace_id, status);
CREATE INDEX IF NOT EXISTS idx_discovery_runs_ws_created ON discovery_runs (workspace_id, created_at DESC);

ALTER TABLE discovery_runs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "discovery_runs_policy" ON discovery_runs;
CREATE POLICY "discovery_runs_policy" ON discovery_runs
  USING (workspace_id = (SELECT workspace_id FROM users WHERE supabase_uid = auth.uid()));
