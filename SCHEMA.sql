-- ============================================================
-- NovaCRM Agentic — Supabase Schema
-- Paste this entire file into Supabase → SQL Editor → Run
-- ============================================================

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ─── Contacts ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS contacts (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name          TEXT NOT NULL,
  email         TEXT UNIQUE NOT NULL,
  company       TEXT NOT NULL,
  role          TEXT NOT NULL DEFAULT '',
  avatar        TEXT NOT NULL DEFAULT '',       -- initials e.g. "SC"
  status        TEXT NOT NULL DEFAULT 'lead'
                  CHECK (status IN ('lead','prospect','customer','churned')),
  ml_score      JSONB NOT NULL DEFAULT '{"value":50,"label":"warm","trend":"stable","signals":[]}',
  semantic_tags JSONB NOT NULL DEFAULT '[]',
  last_activity TEXT NOT NULL DEFAULT 'Never',
  revenue       NUMERIC NOT NULL DEFAULT 0,
  deal_count    INTEGER NOT NULL DEFAULT 0,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─── Deals ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS deals (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  title               TEXT NOT NULL,
  company             TEXT NOT NULL DEFAULT '',
  contact_name        TEXT NOT NULL DEFAULT '',
  contact_id          UUID REFERENCES contacts(id) ON DELETE SET NULL,
  value               NUMERIC NOT NULL DEFAULT 0,
  stage               TEXT NOT NULL DEFAULT 'discovery'
                        CHECK (stage IN ('discovery','qualified','proposal','negotiation','closed_won','closed_lost')),
  ml_win_probability  INTEGER NOT NULL DEFAULT 50 CHECK (ml_win_probability BETWEEN 0 AND 100),
  expected_close      TEXT NOT NULL DEFAULT '',
  assigned_agent      TEXT NOT NULL DEFAULT '',
  notes               TEXT NOT NULL DEFAULT '',
  created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─── Agents ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS agents (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name        TEXT NOT NULL,
  type        TEXT NOT NULL UNIQUE,
  status      TEXT NOT NULL DEFAULT 'idle'
                CHECK (status IN ('active','processing','idle','error')),
  description TEXT NOT NULL DEFAULT '',
  model       TEXT NOT NULL DEFAULT '',
  accuracy    NUMERIC NOT NULL DEFAULT 0,
  tasks_today INTEGER NOT NULL DEFAULT 0,
  last_run    TEXT NOT NULL DEFAULT 'Never',
  workflow    JSONB NOT NULL DEFAULT '[]',
  metrics     JSONB NOT NULL DEFAULT '[]',
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─── Activity Events ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS activity_events (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  type        TEXT NOT NULL,
  agent_name  TEXT NOT NULL,
  description TEXT NOT NULL,
  meta        TEXT NOT NULL DEFAULT '',
  severity    TEXT NOT NULL DEFAULT 'info'
                CHECK (severity IN ('info','success','warning')),
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─── Auto-update updated_at ──────────────────────────────────
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER contacts_updated_at
  BEFORE UPDATE ON contacts
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE OR REPLACE TRIGGER deals_updated_at
  BEFORE UPDATE ON deals
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE OR REPLACE TRIGGER agents_updated_at
  BEFORE UPDATE ON agents
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ─── Indexes ─────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_contacts_status    ON contacts(status);
CREATE INDEX IF NOT EXISTS idx_contacts_email     ON contacts(email);
CREATE INDEX IF NOT EXISTS idx_deals_stage        ON deals(stage);
CREATE INDEX IF NOT EXISTS idx_deals_contact_id   ON deals(contact_id);
CREATE INDEX IF NOT EXISTS idx_activity_created   ON activity_events(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_agents_status      ON agents(status);
