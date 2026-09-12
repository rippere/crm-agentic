-- ─── 025_escalation_controls.sql ─────────────────────────────────────────────
-- Autonomous Lead Engine, Increment 2 (Escalation graph + reply-sentiment).
-- Replaces the binary sequence_steps.requires_approval gate with a two-layer
-- control primitive: PROPOSE an action from signals, then CLAMP it by a
-- per-workspace × per-stage operator cap (auto|ask|off), fail-closed behind a
-- workspace-level autonomy master switch. Adds three tables:
--   stage_controls        — per-stage cap the authority resolver reads (R11/R12)
--   workspace_autonomy     — the master switch, defaults FALSE (R12)
--   escalation_decisions   — append-only audit + the future model-governed seam
-- Idempotent (IF NOT EXISTS + DROP POLICY IF EXISTS). NOT executed automatically
-- — apply by hand to Supabase prod. The same DDL minus RLS is mirrored into
-- init_docker.sql.
--
-- Follows the 023 house shape verbatim: `id UUID PK gen_random_uuid()`;
-- `workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE` first;
-- TEXT + inline-CHECK enums; JSONB NOT NULL DEFAULT '{}'; created_at/updated_at
-- TIMESTAMPTZ NOT NULL DEFAULT NOW(); workspace-first idx_<table>_ws_* indexes
-- with IF NOT EXISTS; RLS ENABLE-only keyed on users.supabase_uid = auth.uid().
--
-- The legacy sequence_steps.requires_approval column is RETAINED (this migration
-- is additive); the sender simply stops reading it once the _run_tick rewrite
-- lands. FK ordering: all three tables reference only pre-existing tables
-- (workspaces/users pre-023; leads/sequence_enrollments from 023).

-- ── stage_controls — per-workspace × per-stage cap (the resolver reads this) ──
CREATE TABLE IF NOT EXISTS stage_controls (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id  UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  stage         TEXT NOT NULL
                  CHECK (stage IN ('new','contacted','engaged','qualified','converted','lost')),
  mode          TEXT NOT NULL DEFAULT 'ask'
                  CHECK (mode IN ('auto','ask','off')),          -- R12 fail-closed default
  config        JSONB NOT NULL DEFAULT '{}',                     -- {"thresholds":{"book_score":70,"send_floor":0}}
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (workspace_id, stage)
);
CREATE INDEX IF NOT EXISTS idx_stage_controls_ws ON stage_controls (workspace_id, stage);

ALTER TABLE stage_controls ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "stage_controls_policy" ON stage_controls;
CREATE POLICY "stage_controls_policy" ON stage_controls
  USING (workspace_id = (SELECT workspace_id FROM users WHERE supabase_uid = auth.uid()));

-- ── workspace_autonomy — the workspace-level master switch (R12) ──────────────
CREATE TABLE IF NOT EXISTS workspace_autonomy (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id      UUID NOT NULL UNIQUE REFERENCES workspaces(id) ON DELETE CASCADE,
  autonomy_enabled  BOOLEAN NOT NULL DEFAULT FALSE,               -- R12: off until explicit opt-in
  settings          JSONB NOT NULL DEFAULT '{}',
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_workspace_autonomy_ws ON workspace_autonomy (workspace_id);

ALTER TABLE workspace_autonomy ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "workspace_autonomy_policy" ON workspace_autonomy;
CREATE POLICY "workspace_autonomy_policy" ON workspace_autonomy
  USING (workspace_id = (SELECT workspace_id FROM users WHERE supabase_uid = auth.uid()));

-- ── escalation_decisions — append-only audit (mirrors engagement_events) ──────
-- occurred_at + created_at, NO updated_at (append-only, like engagement_events).
CREATE TABLE IF NOT EXISTS escalation_decisions (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id    UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  lead_id         UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
  enrollment_id   UUID REFERENCES sequence_enrollments(id) ON DELETE SET NULL,
  stage           TEXT NOT NULL
                    CHECK (stage IN ('new','contacted','engaged','qualified','converted','lost')),
  proposed_action TEXT NOT NULL
                    CHECK (proposed_action IN ('send','escalate','stop','hold')),
  final_action    TEXT NOT NULL
                    CHECK (final_action IN ('send','park','escalate','stop','hold')),
  mode            TEXT NOT NULL
                    CHECK (mode IN ('auto','ask','off')),
  score           INTEGER,
  sentiment       TEXT
                    CHECK (sentiment IN ('positive','neutral','negative','objection','booking','unsubscribe')),
  reason          TEXT,
  decided_by      TEXT NOT NULL DEFAULT 'threshold'
                    CHECK (decided_by IN ('threshold','model','human')),   -- future-model seam
  metadata        JSONB NOT NULL DEFAULT '{}',
  occurred_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_escalation_decisions_lead ON escalation_decisions (workspace_id, lead_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_escalation_decisions_enr  ON escalation_decisions (workspace_id, enrollment_id);
CREATE INDEX IF NOT EXISTS idx_escalation_decisions_final ON escalation_decisions (workspace_id, final_action);

ALTER TABLE escalation_decisions ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "escalation_decisions_policy" ON escalation_decisions;
CREATE POLICY "escalation_decisions_policy" ON escalation_decisions
  USING (workspace_id = (SELECT workspace_id FROM users WHERE supabase_uid = auth.uid()));
