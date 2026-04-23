-- ─── 001_unified_schema.sql ──────────────────────────────────────────────────
-- Unified 11-table schema for CRM-Agentic (replaces 000_original_schema.sql)
-- Includes workspace isolation, RLS, and performance indexes.

-- ─── 1. workspaces ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS workspaces (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name        TEXT NOT NULL,
  slug        TEXT NOT NULL UNIQUE,
  mode        TEXT NOT NULL CHECK (mode IN ('sales', 'pm', 'both')) DEFAULT 'sales',
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE workspaces ENABLE ROW LEVEL SECURITY;
-- workspaces has no workspace_id FK; row access is managed at the users level.
-- Users can read their own workspace only.
CREATE POLICY "workspace_isolation" ON workspaces
  USING (id = (SELECT workspace_id FROM users WHERE supabase_uid = auth.uid()));

-- ─── 2. users ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  supabase_uid  UUID NOT NULL UNIQUE,
  workspace_id  UUID REFERENCES workspaces(id) ON DELETE CASCADE,
  email         TEXT,
  role          TEXT NOT NULL CHECK (role IN ('admin', 'member')) DEFAULT 'member',
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE users ENABLE ROW LEVEL SECURITY;
CREATE POLICY "workspace_isolation" ON users
  USING (workspace_id = (SELECT workspace_id FROM users WHERE supabase_uid = auth.uid()));

-- ─── 3. contacts ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS contacts (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id   UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  name           TEXT,
  email          TEXT,
  company        TEXT,
  role           TEXT,
  avatar         TEXT,
  status         TEXT NOT NULL CHECK (status IN ('lead', 'prospect', 'customer', 'churned')) DEFAULT 'lead',
  ml_score       JSONB NOT NULL DEFAULT '{"value":50,"label":"warm","trend":"stable","signals":[]}',
  semantic_tags  JSONB NOT NULL DEFAULT '[]',
  last_activity  TEXT NOT NULL DEFAULT 'Never',
  revenue        NUMERIC NOT NULL DEFAULT 0,
  deal_count     INT NOT NULL DEFAULT 0,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (workspace_id, email)
);

ALTER TABLE contacts ENABLE ROW LEVEL SECURITY;
CREATE POLICY "workspace_isolation" ON contacts
  USING (workspace_id = (SELECT workspace_id FROM users WHERE supabase_uid = auth.uid()));

-- ─── 4. deals ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS deals (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id        UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  title               TEXT,
  company             TEXT,
  contact_name        TEXT,
  contact_id          UUID REFERENCES contacts(id) ON DELETE SET NULL,
  value               NUMERIC NOT NULL DEFAULT 0,
  stage               TEXT NOT NULL CHECK (stage IN ('discovery', 'qualified', 'proposal', 'negotiation', 'closed_won', 'closed_lost')) DEFAULT 'discovery',
  ml_win_probability  INT NOT NULL CHECK (ml_win_probability BETWEEN 0 AND 100) DEFAULT 50,
  expected_close      TEXT,
  assigned_agent      TEXT,
  notes               TEXT,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE deals ENABLE ROW LEVEL SECURITY;
CREATE POLICY "workspace_isolation" ON deals
  USING (workspace_id = (SELECT workspace_id FROM users WHERE supabase_uid = auth.uid()));

-- ─── 5. agents ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS agents (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  name         TEXT,
  type         TEXT,
  description  TEXT,
  model        TEXT,
  status       TEXT NOT NULL CHECK (status IN ('active', 'processing', 'idle', 'error')) DEFAULT 'idle',
  accuracy     NUMERIC NOT NULL DEFAULT 0,
  tasks_today  INT NOT NULL DEFAULT 0,
  last_run     TEXT NOT NULL DEFAULT 'Never',
  workflow     JSONB NOT NULL DEFAULT '[]',
  metrics      JSONB NOT NULL DEFAULT '[]',
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE agents ENABLE ROW LEVEL SECURITY;
CREATE POLICY "workspace_isolation" ON agents
  USING (workspace_id = (SELECT workspace_id FROM users WHERE supabase_uid = auth.uid()));

-- ─── 6. activity_events ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS activity_events (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  type         TEXT,
  agent_name   TEXT,
  description  TEXT,
  meta         TEXT,
  severity     TEXT NOT NULL CHECK (severity IN ('info', 'success', 'warning')) DEFAULT 'info',
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE activity_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY "workspace_isolation" ON activity_events
  USING (workspace_id = (SELECT workspace_id FROM users WHERE supabase_uid = auth.uid()));

-- ─── 7. connectors ───────────────────────────────────────────────────────────
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

ALTER TABLE connectors ENABLE ROW LEVEL SECURITY;
CREATE POLICY "workspace_isolation" ON connectors
  USING (workspace_id = (SELECT workspace_id FROM users WHERE supabase_uid = auth.uid()));

-- ─── 8. messages ─────────────────────────────────────────────────────────────
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

ALTER TABLE messages ENABLE ROW LEVEL SECURITY;
CREATE POLICY "workspace_isolation" ON messages
  USING (workspace_id = (SELECT workspace_id FROM users WHERE supabase_uid = auth.uid()));

-- ─── 9. tasks ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tasks (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  message_id   UUID REFERENCES messages(id) ON DELETE SET NULL,
  contact_id   UUID REFERENCES contacts(id) ON DELETE SET NULL,
  title        TEXT NOT NULL,
  description  TEXT NOT NULL DEFAULT '',
  status       TEXT NOT NULL CHECK (status IN ('open', 'in_progress', 'done', 'cancelled')) DEFAULT 'open',
  due_date     DATE,
  assignee_id  UUID REFERENCES users(id) ON DELETE SET NULL,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE tasks ENABLE ROW LEVEL SECURITY;
CREATE POLICY "workspace_isolation" ON tasks
  USING (workspace_id = (SELECT workspace_id FROM users WHERE supabase_uid = auth.uid()));

-- ─── 10. metric_templates ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS metric_templates (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  name         TEXT,
  description  TEXT,
  data_type    TEXT CHECK (data_type IN ('text', 'number', 'boolean', 'date')),
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE metric_templates ENABLE ROW LEVEL SECURITY;
CREATE POLICY "workspace_isolation" ON metric_templates
  USING (workspace_id = (SELECT workspace_id FROM users WHERE supabase_uid = auth.uid()));

-- ─── 11. clarity_scores ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS clarity_scores (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  message_id   UUID UNIQUE REFERENCES messages(id) ON DELETE CASCADE,
  score        INT CHECK (score BETWEEN 0 AND 100),
  rationale    TEXT,
  model_used   TEXT NOT NULL DEFAULT 'claude-sonnet-4-6',
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE clarity_scores ENABLE ROW LEVEL SECURITY;
CREATE POLICY "workspace_isolation" ON clarity_scores
  USING (workspace_id = (SELECT workspace_id FROM users WHERE supabase_uid = auth.uid()));

-- ─── Indexes ─────────────────────────────────────────────────────────────────
CREATE INDEX idx_messages_workspace_processed ON messages(workspace_id, processed);
CREATE INDEX idx_messages_contact ON messages(contact_id);
CREATE INDEX idx_tasks_workspace_status ON tasks(workspace_id, status);
CREATE INDEX idx_connectors_workspace_service ON connectors(workspace_id, service);
