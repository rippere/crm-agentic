-- ─── 023_outbound_engagement.sql ─────────────────────────────────────────────
-- Outbound engine: leads, lead_segments, lead_segment_members, sequences,
-- sequence_steps, campaigns, sequence_enrollments, engagement_events.
--
-- The funnel engine for the lead-gen / marketing module: leads → segmentation →
-- campaigns → email/SMS sequences → scheduler → bot-outreach HITL draft → engagement
-- scoring that feeds lead stage transitions. Follows the house shape exactly:
-- `id UUID PK DEFAULT gen_random_uuid()`; `workspace_id UUID NOT NULL REFERENCES
-- workspaces(id) ON DELETE CASCADE`; enums as TEXT ... CHECK (...); JSONB NOT NULL
-- DEFAULT '{}'; created_at/updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(); RLS keyed
-- on users.supabase_uid = auth.uid().
--
-- FK ordering is load-bearing (create order below is FK-safe, no forward refs):
--   leads → lead_segments → lead_segment_members → sequences → sequence_steps →
--   campaigns → sequence_enrollments → engagement_events (last; references leads,
--   campaigns, sequence_enrollments, sequence_steps).
--
-- Owned children (lead_segment_members, sequence_steps, sequence_enrollments)
-- CASCADE; an enrollment is owned by its campaign AND its sequence/lead, so its
-- campaign_id, sequence_id and lead_id are all NOT NULL + ON DELETE CASCADE.
-- Nullable cross-row FKs (contact_id, owner_id, segment_id, campaigns.sequence_id,
-- engagement_events' campaign_id/enrollment_id/step_id) use ON DELETE SET NULL.
--
-- Fully idempotent / re-runnable (IF NOT EXISTS + DROP POLICY IF EXISTS).
--
-- NOTE: USER-applied to prod — this migration is written here but is NOT executed
-- automatically; apply it manually against the production database. The same DDL
-- (minus the RLS / policy lines) is mirrored into init_docker.sql for the Docker
-- path, which has no migration runner.

-- ─── leads ───────────────────────────────────────────────────────────────────
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

ALTER TABLE leads ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "leads_policy" ON leads;
CREATE POLICY "leads_policy" ON leads
  USING (workspace_id = (SELECT workspace_id FROM users WHERE supabase_uid = auth.uid()));

-- ─── lead_segments ───────────────────────────────────────────────────────────
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

ALTER TABLE lead_segments ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "lead_segments_policy" ON lead_segments;
CREATE POLICY "lead_segments_policy" ON lead_segments
  USING (workspace_id = (SELECT workspace_id FROM users WHERE supabase_uid = auth.uid()));

-- ─── lead_segment_members ────────────────────────────────────────────────────
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

ALTER TABLE lead_segment_members ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "lead_segment_members_policy" ON lead_segment_members;
CREATE POLICY "lead_segment_members_policy" ON lead_segment_members
  USING (workspace_id = (SELECT workspace_id FROM users WHERE supabase_uid = auth.uid()));

-- ─── sequences ───────────────────────────────────────────────────────────────
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

ALTER TABLE sequences ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "sequences_policy" ON sequences;
CREATE POLICY "sequences_policy" ON sequences
  USING (workspace_id = (SELECT workspace_id FROM users WHERE supabase_uid = auth.uid()));

-- ─── sequence_steps ──────────────────────────────────────────────────────────
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

ALTER TABLE sequence_steps ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "sequence_steps_policy" ON sequence_steps;
CREATE POLICY "sequence_steps_policy" ON sequence_steps
  USING (workspace_id = (SELECT workspace_id FROM users WHERE supabase_uid = auth.uid()));

-- ─── campaigns ───────────────────────────────────────────────────────────────
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

ALTER TABLE campaigns ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "campaigns_policy" ON campaigns;
CREATE POLICY "campaigns_policy" ON campaigns
  USING (workspace_id = (SELECT workspace_id FROM users WHERE supabase_uid = auth.uid()));

-- ─── sequence_enrollments ────────────────────────────────────────────────────
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

ALTER TABLE sequence_enrollments ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "sequence_enrollments_policy" ON sequence_enrollments;
CREATE POLICY "sequence_enrollments_policy" ON sequence_enrollments
  USING (workspace_id = (SELECT workspace_id FROM users WHERE supabase_uid = auth.uid()));

-- ─── engagement_events ───────────────────────────────────────────────────────
-- Append-only fact table. Declared last (references leads, campaigns,
-- sequence_enrollments, sequence_steps). Feeds the scoring worker.
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

ALTER TABLE engagement_events ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "engagement_events_policy" ON engagement_events;
CREATE POLICY "engagement_events_policy" ON engagement_events
  USING (workspace_id = (SELECT workspace_id FROM users WHERE supabase_uid = auth.uid()));
