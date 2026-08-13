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

-- Ledger: daily life-KPI snapshots (see migration 012_ledger.sql).
CREATE TABLE IF NOT EXISTS kpi_snapshots (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  date         DATE NOT NULL,
  domain       TEXT NOT NULL,
  metric       TEXT NOT NULL,
  value        NUMERIC NOT NULL,
  meta         JSONB NOT NULL DEFAULT '{}',
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (workspace_id, date, metric)
);

-- Ledger: commitments harvested from session records (see migration 012_ledger.sql).
CREATE TABLE IF NOT EXISTS commitments (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  external_id  TEXT,
  title        TEXT NOT NULL,
  kind         TEXT NOT NULL DEFAULT 'auto',
  source       TEXT,
  declared_at  TIMESTAMPTZ NOT NULL,
  due_date     DATE,
  status       TEXT NOT NULL DEFAULT 'open',
  evidence     TEXT,
  scored_at    TIMESTAMPTZ,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (workspace_id, external_id)
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
CREATE INDEX IF NOT EXISTS idx_kpi_ws_date ON kpi_snapshots(workspace_id, date);
CREATE INDEX IF NOT EXISTS idx_kpi_ws_metric_date ON kpi_snapshots(workspace_id, metric, date);
CREATE INDEX IF NOT EXISTS idx_commitments_ws_status ON commitments(workspace_id, status);

-- ─── SEED DATA ────────────────────────────────────────────────────────────────
-- Default workspace so a fresh deployment has something to show.
-- Skipped if workspace already exists.

DO $$
DECLARE
  ws_id UUID;
BEGIN
  SELECT id INTO ws_id FROM workspaces LIMIT 1;
  IF ws_id IS NULL THEN
    INSERT INTO workspaces (id, name, slug, mode)
    VALUES (gen_random_uuid(), 'NovaCRM Demo', 'novaCRM-demo', 'sales')
    RETURNING id INTO ws_id;

    INSERT INTO agents (workspace_id, name, type, description, model, status, accuracy, tasks_today)
    VALUES
      (ws_id, 'Semantic Sorter',    'semantic_sorter',    'Categorises inbound messages by topic and urgency using embeddings.',    'all-MiniLM-L6-v2',    'active',     94.2, 312),
      (ws_id, 'Lead Scorer',        'lead_scorer',        'Scores contacts 0-100 based on engagement, revenue signals, and stage.',  'heuristic',           'active',     87.1, 148),
      (ws_id, 'Email Composer',     'email_composer',     'Drafts personalised outreach emails using Claude Sonnet.',               'claude-sonnet-4-6',   'idle',       91.8,   0),
      (ws_id, 'Call Summarizer',    'call_summarizer',    'Transcribes calls with Whisper then extracts action items via Claude.',   'whisper-base',        'active',     89.5,  24),
      (ws_id, 'Pipeline Optimizer', 'pipeline_optimizer', 'Detects stale deals and recommends next actions each night.',            'heuristic',           'active',     85.3,  67),
      (ws_id, 'Sentiment Analyzer', 'sentiment_analyzer', 'Runs Claude Haiku over every ingested message for tone signals.',        'claude-haiku-4-5',    'active',     92.0, 203);
  END IF;
END $$;

-- ─── OUTBOUND ENGAGEMENT ENGINE (mirror of 023_outbound_engagement.sql) ───────
-- leads, lead_segments, lead_segment_members, sequences, sequence_steps,
-- campaigns, sequence_enrollments, engagement_events. Docker path has no
-- migration runner, so the same CREATE TABLE / CREATE INDEX DDL is mirrored here
-- (RLS ENABLE / policy lines are intentionally omitted — Docker runs without RLS).
-- FK-safe create order: all referenced tables (workspaces, users, contacts) exist
-- above, and each new table precedes any that references it.

CREATE TABLE IF NOT EXISTS leads (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id    UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  contact_id      UUID REFERENCES contacts(id) ON DELETE SET NULL,
  name            TEXT,
  email           TEXT,
  phone           TEXT,
  company         TEXT,
  title           TEXT,
  source          TEXT NOT NULL DEFAULT 'import'
                    CHECK (source IN ('import','manual','web','api','referral','event')),
  stage           TEXT NOT NULL DEFAULT 'new'
                    CHECK (stage IN ('new','contacted','engaged','qualified','converted','lost')),
  score           INTEGER NOT NULL DEFAULT 0,
  score_detail    JSONB NOT NULL DEFAULT '{}',
  owner_id        UUID REFERENCES users(id) ON DELETE SET NULL,
  custom_fields   JSONB NOT NULL DEFAULT '{}',
  external_id     TEXT,
  last_engaged_at TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_leads_ws_email
  ON leads (workspace_id, email) WHERE email IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_leads_ws_extid
  ON leads (workspace_id, external_id) WHERE external_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_leads_ws_stage ON leads (workspace_id, stage);
CREATE INDEX IF NOT EXISTS idx_leads_ws_score ON leads (workspace_id, score DESC);
CREATE INDEX IF NOT EXISTS idx_leads_ws_created ON leads (workspace_id, created_at DESC);

CREATE TABLE IF NOT EXISTS lead_segments (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id  UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  name          TEXT NOT NULL,
  description   TEXT,
  kind          TEXT NOT NULL DEFAULT 'static'
                  CHECK (kind IN ('static','dynamic')),
  filter        JSONB NOT NULL DEFAULT '{}',
  member_count  INTEGER NOT NULL DEFAULT 0,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (workspace_id, name)
);
CREATE INDEX IF NOT EXISTS idx_lead_segments_ws ON lead_segments (workspace_id);

CREATE TABLE IF NOT EXISTS lead_segment_members (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id  UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  segment_id    UUID NOT NULL REFERENCES lead_segments(id) ON DELETE CASCADE,
  lead_id       UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
  added_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (segment_id, lead_id)
);
CREATE INDEX IF NOT EXISTS idx_lsm_segment ON lead_segment_members (segment_id);
CREATE INDEX IF NOT EXISTS idx_lsm_lead ON lead_segment_members (lead_id);

CREATE TABLE IF NOT EXISTS sequences (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id  UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  name          TEXT NOT NULL,
  description   TEXT,
  channel       TEXT NOT NULL DEFAULT 'email'
                  CHECK (channel IN ('email','sms','mixed')),
  status        TEXT NOT NULL DEFAULT 'draft'
                  CHECK (status IN ('draft','active','archived')),
  step_count    INTEGER NOT NULL DEFAULT 0,
  settings      JSONB NOT NULL DEFAULT '{}',
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (workspace_id, name)
);
CREATE INDEX IF NOT EXISTS idx_sequences_ws_status ON sequences (workspace_id, status);

CREATE TABLE IF NOT EXISTS sequence_steps (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id      UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  sequence_id       UUID NOT NULL REFERENCES sequences(id) ON DELETE CASCADE,
  step_order        INTEGER NOT NULL,
  channel           TEXT NOT NULL DEFAULT 'email'
                      CHECK (channel IN ('email','sms')),
  delay_hours       INTEGER NOT NULL DEFAULT 0,
  subject           TEXT,
  body_template     TEXT NOT NULL DEFAULT '',
  requires_approval BOOLEAN NOT NULL DEFAULT TRUE,
  ai_generate       BOOLEAN NOT NULL DEFAULT FALSE,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (sequence_id, step_order)
);
CREATE INDEX IF NOT EXISTS idx_seqsteps_sequence ON sequence_steps (sequence_id, step_order);

CREATE TABLE IF NOT EXISTS campaigns (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id  UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  segment_id    UUID REFERENCES lead_segments(id) ON DELETE SET NULL,
  sequence_id   UUID REFERENCES sequences(id) ON DELETE SET NULL,
  name          TEXT NOT NULL,
  status        TEXT NOT NULL DEFAULT 'draft'
                  CHECK (status IN ('draft','scheduled','active','paused','completed','archived')),
  channel       TEXT NOT NULL DEFAULT 'email'
                  CHECK (channel IN ('email','sms','mixed')),
  scheduled_at  TIMESTAMPTZ,
  started_at    TIMESTAMPTZ,
  completed_at  TIMESTAMPTZ,
  stats         JSONB NOT NULL DEFAULT '{}',
  settings      JSONB NOT NULL DEFAULT '{}',
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (workspace_id, name)
);
CREATE INDEX IF NOT EXISTS idx_campaigns_ws_status ON campaigns (workspace_id, status);
CREATE INDEX IF NOT EXISTS idx_campaigns_scheduled ON campaigns (status, scheduled_at);

CREATE TABLE IF NOT EXISTS sequence_enrollments (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id  UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  campaign_id   UUID NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
  sequence_id   UUID NOT NULL REFERENCES sequences(id) ON DELETE CASCADE,
  lead_id       UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
  current_step  INTEGER NOT NULL DEFAULT 0,
  status        TEXT NOT NULL DEFAULT 'active'
                  CHECK (status IN ('active','waiting','paused','completed','stopped','bounced')),
  next_run_at   TIMESTAMPTZ,
  last_sent_at  TIMESTAMPTZ,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (campaign_id, lead_id)
);
CREATE INDEX IF NOT EXISTS idx_enroll_due ON sequence_enrollments (workspace_id, status, next_run_at);
CREATE INDEX IF NOT EXISTS idx_enroll_ws_campaign ON sequence_enrollments (workspace_id, campaign_id);

CREATE TABLE IF NOT EXISTS engagement_events (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id  UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  lead_id       UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
  campaign_id   UUID REFERENCES campaigns(id) ON DELETE SET NULL,
  enrollment_id UUID REFERENCES sequence_enrollments(id) ON DELETE SET NULL,
  step_id       UUID REFERENCES sequence_steps(id) ON DELETE SET NULL,
  type          TEXT NOT NULL
                  CHECK (type IN ('queued','sent','delivered','opened','clicked','replied','bounced','unsubscribed','converted','approved','rejected')),
  channel       TEXT
                  CHECK (channel IN ('email','sms')),
  weight        INTEGER NOT NULL DEFAULT 0,
  metadata      JSONB NOT NULL DEFAULT '{}',
  occurred_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_engevents_lead ON engagement_events (workspace_id, lead_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_engevents_campaign ON engagement_events (workspace_id, campaign_id);
CREATE INDEX IF NOT EXISTS idx_engevents_type ON engagement_events (workspace_id, type);
