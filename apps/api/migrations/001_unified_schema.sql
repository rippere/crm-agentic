-- ─── 001_unified_schema.sql ──────────────────────────────────────────────────
-- Unified 11-table schema for CRM-Agentic
-- Tables created first, RLS enabled, all policies added at the end.

-- ─── TABLES ──────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS workspaces (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name        TEXT NOT NULL,
  slug        TEXT NOT NULL UNIQUE,
  mode        TEXT NOT NULL DEFAULT 'sales' CHECK (mode IN ('sales', 'pm', 'both')),
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS users (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  supabase_uid  UUID NOT NULL UNIQUE,
  workspace_id  UUID REFERENCES workspaces(id) ON DELETE CASCADE,
  email         TEXT,
  role          TEXT NOT NULL DEFAULT 'member' CHECK (role IN ('admin', 'member')),
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS contacts (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id   UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  name           TEXT,
  email          TEXT,
  company        TEXT,
  role           TEXT,
  avatar         TEXT,
  status         TEXT NOT NULL DEFAULT 'lead' CHECK (status IN ('lead', 'prospect', 'customer', 'churned')),
  ml_score       JSONB NOT NULL DEFAULT '{"value":50,"label":"warm","trend":"stable","signals":[]}',
  semantic_tags  JSONB NOT NULL DEFAULT '[]',
  last_activity  TEXT NOT NULL DEFAULT 'Never',
  revenue        NUMERIC NOT NULL DEFAULT 0,
  deal_count     INT NOT NULL DEFAULT 0,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (workspace_id, email)
);

CREATE TABLE IF NOT EXISTS deals (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id        UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  title               TEXT,
  company             TEXT,
  contact_name        TEXT,
  contact_id          UUID REFERENCES contacts(id) ON DELETE SET NULL,
  value               NUMERIC NOT NULL DEFAULT 0,
  stage               TEXT NOT NULL DEFAULT 'discovery' CHECK (stage IN ('discovery', 'qualified', 'proposal', 'negotiation', 'closed_won', 'closed_lost')),
  ml_win_probability  INT NOT NULL DEFAULT 50 CHECK (ml_win_probability BETWEEN 0 AND 100),
  expected_close      TEXT,
  assigned_agent      TEXT,
  notes               TEXT,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS agents (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  name         TEXT,
  type         TEXT,
  description  TEXT,
  model        TEXT,
  status       TEXT NOT NULL DEFAULT 'idle' CHECK (status IN ('active', 'processing', 'idle', 'error')),
  accuracy     NUMERIC NOT NULL DEFAULT 0,
  tasks_today  INT NOT NULL DEFAULT 0,
  last_run     TEXT NOT NULL DEFAULT 'Never',
  workflow     JSONB NOT NULL DEFAULT '[]',
  metrics      JSONB NOT NULL DEFAULT '[]',
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS activity_events (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  type         TEXT,
  agent_name   TEXT,
  description  TEXT,
  meta         TEXT,
  severity     TEXT NOT NULL DEFAULT 'info' CHECK (severity IN ('info', 'success', 'warning')),
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS connectors (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id    UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  service         TEXT NOT NULL CHECK (service IN ('gmail', 'slack', 'teams')),
  encrypted_token TEXT NOT NULL,
  refresh_token   TEXT,
  token_expiry    TIMESTAMPTZ,
  external_email  TEXT,
  message_count   INT NOT NULL DEFAULT 0,
  task_count      INT NOT NULL DEFAULT 0,
  last_sync       TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (workspace_id, service, external_email)
);

CREATE TABLE IF NOT EXISTS messages (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id   UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  connector_id   UUID REFERENCES connectors(id) ON DELETE SET NULL,
  external_id    TEXT NOT NULL,
  subject        TEXT,
  body_plain     TEXT NOT NULL,
  sender_email   TEXT,
  received_at    TIMESTAMPTZ,
  contact_id     UUID REFERENCES contacts(id) ON DELETE SET NULL,
  processed      BOOLEAN NOT NULL DEFAULT FALSE,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (workspace_id, external_id)
);

CREATE TABLE IF NOT EXISTS tasks (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  message_id   UUID REFERENCES messages(id) ON DELETE SET NULL,
  contact_id   UUID REFERENCES contacts(id) ON DELETE SET NULL,
  title        TEXT NOT NULL,
  description  TEXT NOT NULL DEFAULT '',
  status       TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'in_progress', 'done', 'cancelled')),
  due_date     DATE,
  assignee_id  UUID REFERENCES users(id) ON DELETE SET NULL,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS metric_templates (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  name         TEXT,
  description  TEXT,
  data_type    TEXT CHECK (data_type IN ('text', 'number', 'boolean', 'date')),
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS clarity_scores (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  message_id   UUID UNIQUE REFERENCES messages(id) ON DELETE CASCADE,
  score        INT CHECK (score BETWEEN 0 AND 100),
  rationale    TEXT,
  model_used   TEXT NOT NULL DEFAULT 'claude-sonnet-4-6',
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─── INDEXES ─────────────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_messages_workspace_processed ON messages(workspace_id, processed);
CREATE INDEX IF NOT EXISTS idx_messages_contact ON messages(contact_id);
CREATE INDEX IF NOT EXISTS idx_tasks_workspace_status ON tasks(workspace_id, status);
CREATE INDEX IF NOT EXISTS idx_connectors_workspace_service ON connectors(workspace_id, service);

-- ─── RLS ─────────────────────────────────────────────────────────────────────

ALTER TABLE workspaces ENABLE ROW LEVEL SECURITY;
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE contacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE deals ENABLE ROW LEVEL SECURITY;
ALTER TABLE agents ENABLE ROW LEVEL SECURITY;
ALTER TABLE activity_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE connectors ENABLE ROW LEVEL SECURITY;
ALTER TABLE messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE metric_templates ENABLE ROW LEVEL SECURITY;
ALTER TABLE clarity_scores ENABLE ROW LEVEL SECURITY;

-- ─── POLICIES ────────────────────────────────────────────────────────────────

-- workspaces: insert (any authed user can create one), select (own workspace only)
CREATE POLICY "workspaces_insert" ON workspaces
  FOR INSERT TO authenticated WITH CHECK (true);
CREATE POLICY "workspaces_select" ON workspaces
  FOR SELECT TO authenticated
  USING (id = (SELECT workspace_id FROM users WHERE supabase_uid = auth.uid()));

-- users: insert own row, select own row
CREATE POLICY "users_insert" ON users
  FOR INSERT TO authenticated WITH CHECK (supabase_uid = auth.uid());
CREATE POLICY "users_select" ON users
  FOR SELECT TO authenticated USING (supabase_uid = auth.uid());

-- all other tables: workspace isolation
CREATE POLICY "contacts_policy" ON contacts
  USING (workspace_id = (SELECT workspace_id FROM users WHERE supabase_uid = auth.uid()));
CREATE POLICY "deals_policy" ON deals
  USING (workspace_id = (SELECT workspace_id FROM users WHERE supabase_uid = auth.uid()));
CREATE POLICY "agents_policy" ON agents
  USING (workspace_id = (SELECT workspace_id FROM users WHERE supabase_uid = auth.uid()));
CREATE POLICY "activity_events_policy" ON activity_events
  USING (workspace_id = (SELECT workspace_id FROM users WHERE supabase_uid = auth.uid()));
CREATE POLICY "connectors_policy" ON connectors
  USING (workspace_id = (SELECT workspace_id FROM users WHERE supabase_uid = auth.uid()));
CREATE POLICY "messages_policy" ON messages
  USING (workspace_id = (SELECT workspace_id FROM users WHERE supabase_uid = auth.uid()));
CREATE POLICY "tasks_policy" ON tasks
  USING (workspace_id = (SELECT workspace_id FROM users WHERE supabase_uid = auth.uid()));
CREATE POLICY "metric_templates_policy" ON metric_templates
  USING (workspace_id = (SELECT workspace_id FROM users WHERE supabase_uid = auth.uid()));
CREATE POLICY "clarity_scores_policy" ON clarity_scores
  USING (workspace_id = (SELECT workspace_id FROM users WHERE supabase_uid = auth.uid()));
