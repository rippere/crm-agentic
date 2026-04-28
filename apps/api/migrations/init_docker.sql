-- ─── init_docker.sql ──────────────────────────────────────────────────────────
-- Full schema init for self-hosted Postgres (no Supabase RLS).
-- Applied automatically by the `migrate` service in docker-compose.
-- Safe to run repeatedly — all statements use IF NOT EXISTS / IF EXISTS guards.

-- ─── EXTENSIONS ──────────────────────────────────────────────────────────────

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS vector;

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
  embedding      vector(384),
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
  health_score        INT NOT NULL DEFAULT 100 CHECK (health_score BETWEEN 0 AND 100),
  stage_changed_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
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

CREATE TABLE IF NOT EXISTS call_summaries (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id     UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  contact_id       UUID REFERENCES contacts(id) ON DELETE SET NULL,
  title            TEXT NOT NULL DEFAULT 'Untitled Call',
  duration_seconds INT,
  transcript       TEXT NOT NULL DEFAULT '',
  summary          TEXT NOT NULL DEFAULT '',
  action_items     JSONB NOT NULL DEFAULT '[]',
  participants     TEXT,
  call_date        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  model_used       TEXT NOT NULL DEFAULT 'whisper-base',
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─── INDEXES ─────────────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_messages_workspace_processed ON messages(workspace_id, processed);
CREATE INDEX IF NOT EXISTS idx_messages_contact ON messages(contact_id);
CREATE INDEX IF NOT EXISTS idx_tasks_workspace_status ON tasks(workspace_id, status);
CREATE INDEX IF NOT EXISTS idx_connectors_workspace_service ON connectors(workspace_id, service);
CREATE INDEX IF NOT EXISTS idx_contacts_embedding ON contacts USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);
CREATE INDEX IF NOT EXISTS idx_deals_workspace_health ON deals (workspace_id, health_score);
CREATE INDEX IF NOT EXISTS idx_call_summaries_workspace ON call_summaries (workspace_id, call_date DESC);
CREATE INDEX IF NOT EXISTS idx_call_summaries_contact ON call_summaries (contact_id);
