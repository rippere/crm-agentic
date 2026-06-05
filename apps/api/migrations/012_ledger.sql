-- 012: ledger — life-KPI snapshots + commitments (the accountability layer).
-- A local collector pushes daily KPI snapshots and "commitments" (promises
-- harvested from work-session records) into a personal workspace. Mirrors the
-- existing external_id idempotency pattern (messages/tasks/projects) so a
-- re-harvest of the same source upserts instead of duplicating. updated_at is
-- maintained app-side via SQLAlchemy onupdate (no triggers), matching tasks /
-- projects. Idempotent — all statements guarded with IF NOT EXISTS.

CREATE TABLE IF NOT EXISTS kpi_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    domain TEXT NOT NULL,            -- 'engineering' | 'knowledge' | 'product' | 'life'
    metric TEXT NOT NULL,            -- e.g. 'git_commits', 'sessions', 'records.main', 'crm_users'
    value NUMERIC NOT NULL,
    meta JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (workspace_id, date, metric)
);
CREATE INDEX IF NOT EXISTS idx_kpi_ws_date ON kpi_snapshots(workspace_id, date);
CREATE INDEX IF NOT EXISTS idx_kpi_ws_metric_date ON kpi_snapshots(workspace_id, metric, date);

CREATE TABLE IF NOT EXISTS commitments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    external_id TEXT,
    title TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'auto',        -- 'auto' | 'explicit'
    source TEXT,                               -- vault rel_path of originating session record
    declared_at TIMESTAMPTZ NOT NULL,
    due_date DATE,
    status TEXT NOT NULL DEFAULT 'open',       -- 'open' | 'kept' | 'broken' | 'dropped'
    evidence TEXT,                             -- how kept/broken was verified (git sha, record path)
    scored_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (workspace_id, external_id)
);
CREATE INDEX IF NOT EXISTS idx_commitments_ws_status ON commitments(workspace_id, status);
