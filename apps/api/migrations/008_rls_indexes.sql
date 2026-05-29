-- ─── 008_rls_indexes.sql ─────────────────────────────────────────────────────
-- RLS & index hygiene (WS-K):
--   1. Recreate projects_policy to use the auth.uid() pattern shared by every
--      other workspace-scoped table in 001_unified_schema.sql. The original
--      006_projects_table.sql policy relied on current_setting('app.workspace_id'),
--      a GUC that is never configured at runtime — so the policy never matched.
--   2. Add the missing workspace_id FK indexes that other tables already have
--      (messages/tasks/connectors/deals/call_summaries carry theirs in earlier
--      migrations). Covers clarity_scores, activity_events, agents,
--      metric_templates, contacts, and projects.
-- Fully idempotent / re-runnable (DROP POLICY IF EXISTS + CREATE INDEX IF NOT EXISTS).

-- ─── PROJECTS RLS FIX ──────────────────────────────────────────────────────────

ALTER TABLE projects ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "projects_policy" ON projects;
CREATE POLICY "projects_policy" ON projects
  USING (workspace_id = (SELECT workspace_id FROM users WHERE supabase_uid = auth.uid()));

-- ─── MISSING workspace_id FK INDEXES ────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_clarity_scores_workspace   ON clarity_scores(workspace_id);
CREATE INDEX IF NOT EXISTS idx_activity_events_workspace  ON activity_events(workspace_id);
CREATE INDEX IF NOT EXISTS idx_agents_workspace           ON agents(workspace_id);
CREATE INDEX IF NOT EXISTS idx_metric_templates_workspace ON metric_templates(workspace_id);
CREATE INDEX IF NOT EXISTS idx_contacts_workspace         ON contacts(workspace_id);
CREATE INDEX IF NOT EXISTS idx_projects_workspace         ON projects(workspace_id);
