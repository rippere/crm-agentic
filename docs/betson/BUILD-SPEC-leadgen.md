# NovaCRM — Lead-Generation / Marketing Module — Build Spec

**Status:** Ready-to-build architecture spec. **Owner:** lead architect. **Date:** 2026-08-13.
**Repo:** `crm-agentic` (`/mnt/external/Projects/crm-agentic`).

## 0. Purpose & framing (ground truth)

From the 2026-08-12 Mike Betti meeting: **build for Zach** (entry-level test client, returns
Sept 1, runs the photo-booth division "on an island", pro-CRM, AI-forward). The client's
definition of the product in his own words: **"10,000 leads → a database → a funnel of
engagement."** Bar: **demonstrable in September, solid in October** so Zach is never tempted to
reach for Salesforce or an off-the-shelf CRM. **Model on Zoho/HubSpot, NOT Salesforce.**

This module is the funnel engine: **leads → segmentation → campaigns → email/SMS sequences →
scheduler → bot-outreach draft that a human approves before send → engagement scoring** that
feeds lead stage transitions. It reuses the existing `contacts`/`deals` conventions verbatim
(workspace scoping, per-endpoint auth, ORM-first + supabase_rest fallback, Celery
trigger/poll, `ActivityEvent` audit rows). The bot→human handoff copies the proven HITL pattern
already shipped in `workers/followup_sequences.py` (draft via Claude → post for human approval →
resolve). Nothing here invents a new architectural layer.

Design non-goals for this phase: deep analytics/reporting widgets (Phase 12–13), the AVOS/Voss
rep-share ingest (separate interface, tracked elsewhere).

---

## 1. DATA MODEL

Seven new tables. All follow the house shape exactly: `id UUID PK DEFAULT gen_random_uuid()`;
`workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE`; enums as
`TEXT ... CHECK (...)`; JSON as `JSONB NOT NULL DEFAULT '...'`; `created_at`/`updated_at`
`TIMESTAMPTZ NOT NULL DEFAULT NOW()`; tenant-scoped uniqueness; RLS policy keyed on
`users.supabase_uid = auth.uid()`. Cross-row FKs use `ON DELETE SET NULL` except owned children
(`sequence_steps`, `lead_segment_members`, `sequence_enrollments`) which `CASCADE`.

### Migration files to add

- **`apps/api/migrations/023_outbound_engagement.sql`** — the seven `CREATE TABLE` blocks +
  indexes + `ENABLE RLS` + `DROP/CREATE POLICY`. FK ordering inside the file:
  `leads` → `lead_segments` → `lead_segment_members` → `sequences` → `sequence_steps` →
  `campaigns` → `sequence_enrollments` → `engagement_events` (last; it references leads,
  campaigns, sequence_steps).
- **Mirror the same `CREATE TABLE`/`CREATE INDEX` (NO RLS/policy lines) into
  `apps/api/migrations/init_docker.sql`**, appended after the `commitments` block. Without this
  the Docker path silently lacks the tables (`init_docker.sql` has no migration runner and has
  already drifted).
- 023 is the next free number (022 is the last; 020/021 are gaps, don't reuse; 002 is a known
  duplicate — leave it).

### Tables

#### `leads`
The funnel row. A lead may optionally link to a `contacts` row once qualified (bot→human close
promotes a lead to a contact/deal); keep both so import volume (10k) never pollutes the curated
contacts table.

| column | type | notes |
|---|---|---|
| id | UUID PK | `gen_random_uuid()` |
| workspace_id | UUID NOT NULL | FK workspaces CASCADE |
| contact_id | UUID NULL | FK contacts SET NULL — set when promoted |
| name | TEXT NULL | |
| email | TEXT NULL | |
| phone | TEXT NULL | for SMS |
| company | TEXT NULL | |
| title | TEXT NULL | |
| source | TEXT NOT NULL DEFAULT 'import' | CHECK in ('import','manual','web','api','referral','event') |
| stage | TEXT NOT NULL DEFAULT 'new' | CHECK in ('new','contacted','engaged','qualified','converted','lost') |
| score | INTEGER NOT NULL DEFAULT 0 | engagement score 0-100 (denormalized latest) |
| score_detail | JSONB NOT NULL DEFAULT '{}' | `{value,label,signals:[]}` mirrors contact.ml_score shape |
| owner_id | UUID NULL | FK users SET NULL — human who owns close |
| custom_fields | JSONB NOT NULL DEFAULT '{}' | import passthrough columns |
| external_id | TEXT NULL | dedup key for imports |
| last_engaged_at | TIMESTAMPTZ NULL | |
| created_at / updated_at | TIMESTAMPTZ NOT NULL DEFAULT NOW() | updated_at onupdate |

Constraints/indexes: `UNIQUE (workspace_id, email)` (partial `WHERE email IS NOT NULL`),
`UNIQUE (workspace_id, external_id)` (partial `WHERE external_id IS NOT NULL`),
`idx_leads_ws_stage (workspace_id, stage)`, `idx_leads_ws_score (workspace_id, score DESC)`,
`idx_leads_ws_created (workspace_id, created_at DESC)`.

#### `lead_segments`
A saved audience. Either static (explicit membership) or dynamic (a stored filter JSON evaluated
at campaign-launch time).

| column | type | notes |
|---|---|---|
| id | UUID PK | |
| workspace_id | UUID NOT NULL | FK workspaces CASCADE |
| name | TEXT NOT NULL | |
| description | TEXT NULL | |
| kind | TEXT NOT NULL DEFAULT 'static' | CHECK in ('static','dynamic') |
| filter | JSONB NOT NULL DEFAULT '{}' | dynamic: `{stage,source,min_score,tags,...}` |
| member_count | INTEGER NOT NULL DEFAULT 0 | denormalized cache |
| created_at / updated_at | TIMESTAMPTZ | |

`UNIQUE (workspace_id, name)`, `idx_lead_segments_ws (workspace_id)`.

#### `lead_segment_members`
Static-segment join table (owned child of both segment and lead → CASCADE both FKs).

| column | type | notes |
|---|---|---|
| id | UUID PK | |
| workspace_id | UUID NOT NULL | FK workspaces CASCADE |
| segment_id | UUID NOT NULL | FK lead_segments CASCADE |
| lead_id | UUID NOT NULL | FK leads CASCADE |
| added_at | TIMESTAMPTZ NOT NULL DEFAULT NOW() | |

`UNIQUE (segment_id, lead_id)`, `idx_lsm_segment (segment_id)`, `idx_lsm_lead (lead_id)`.

#### `sequences`
An ordered multi-step outreach recipe (the "drip"). Independent of a campaign so it can be
reused; a campaign points at one sequence.

| column | type | notes |
|---|---|---|
| id | UUID PK | |
| workspace_id | UUID NOT NULL | FK workspaces CASCADE |
| name | TEXT NOT NULL | |
| description | TEXT NULL | |
| channel | TEXT NOT NULL DEFAULT 'email' | CHECK in ('email','sms','mixed') |
| status | TEXT NOT NULL DEFAULT 'draft' | CHECK in ('draft','active','archived') |
| step_count | INTEGER NOT NULL DEFAULT 0 | denormalized |
| settings | JSONB NOT NULL DEFAULT '{}' | `{stop_on_reply:true,quiet_hours:[...]}` |
| created_at / updated_at | TIMESTAMPTZ | |

`UNIQUE (workspace_id, name)`, `idx_sequences_ws_status (workspace_id, status)`.

#### `sequence_steps`
Owned child of `sequences` (CASCADE). One message/wait node.

| column | type | notes |
|---|---|---|
| id | UUID PK | |
| workspace_id | UUID NOT NULL | FK workspaces CASCADE |
| sequence_id | UUID NOT NULL | FK sequences CASCADE |
| step_order | INTEGER NOT NULL | 0-based position |
| channel | TEXT NOT NULL DEFAULT 'email' | CHECK in ('email','sms') |
| delay_hours | INTEGER NOT NULL DEFAULT 0 | wait since previous step |
| subject | TEXT NULL | email only |
| body_template | TEXT NOT NULL DEFAULT '' | supports `{{name}}`,`{{company}}` tokens |
| requires_approval | BOOLEAN NOT NULL DEFAULT TRUE | HITL gate (bot→human) |
| ai_generate | BOOLEAN NOT NULL DEFAULT FALSE | draft via Claude at send time |
| created_at / updated_at | TIMESTAMPTZ | |

`UNIQUE (sequence_id, step_order)`, `idx_seqsteps_sequence (sequence_id, step_order)`.

#### `campaigns`
Binds a segment + a sequence + a schedule. This is the launch unit.

| column | type | notes |
|---|---|---|
| id | UUID PK | |
| workspace_id | UUID NOT NULL | FK workspaces CASCADE |
| segment_id | UUID NULL | FK lead_segments SET NULL |
| sequence_id | UUID NULL | FK sequences SET NULL |
| name | TEXT NOT NULL | |
| status | TEXT NOT NULL DEFAULT 'draft' | CHECK in ('draft','scheduled','active','paused','completed','archived') |
| channel | TEXT NOT NULL DEFAULT 'email' | CHECK in ('email','sms','mixed') |
| scheduled_at | TIMESTAMPTZ NULL | when the scheduler activates it |
| started_at / completed_at | TIMESTAMPTZ NULL | |
| stats | JSONB NOT NULL DEFAULT '{}' | `{enrolled,sent,opened,clicked,replied,converted}` denormalized |
| settings | JSONB NOT NULL DEFAULT '{}' | throttle, daily cap, sender identity |
| created_at / updated_at | TIMESTAMPTZ | |

`UNIQUE (workspace_id, name)`, `idx_campaigns_ws_status (workspace_id, status)`,
`idx_campaigns_scheduled (status, scheduled_at)` (scheduler scan).

#### `sequence_enrollments`
One lead's live position in a campaign's sequence (owned child, CASCADE on campaign & lead).
This is the row the scheduler/sender advances.

| column | type | notes |
|---|---|---|
| id | UUID PK | |
| workspace_id | UUID NOT NULL | FK workspaces CASCADE |
| campaign_id | UUID NOT NULL | FK campaigns CASCADE |
| sequence_id | UUID NOT NULL | FK sequences SET NULL |
| lead_id | UUID NOT NULL | FK leads CASCADE |
| current_step | INTEGER NOT NULL DEFAULT 0 | next step_order to send |
| status | TEXT NOT NULL DEFAULT 'active' | CHECK in ('active','waiting','paused','completed','stopped','bounced') |
| next_run_at | TIMESTAMPTZ NULL | when the next step is due |
| last_sent_at | TIMESTAMPTZ NULL | |
| created_at / updated_at | TIMESTAMPTZ | |

`UNIQUE (campaign_id, lead_id)`, `idx_enroll_due (status, next_run_at)` (sender scan),
`idx_enroll_ws_campaign (workspace_id, campaign_id)`.

#### `engagement_events`
Append-only fact table: every outbound send and every inbound signal. Feeds the scoring worker.
Declared last (references leads/campaigns/sequence_steps).

| column | type | notes |
|---|---|---|
| id | UUID PK | |
| workspace_id | UUID NOT NULL | FK workspaces CASCADE |
| lead_id | UUID NOT NULL | FK leads CASCADE |
| campaign_id | UUID NULL | FK campaigns SET NULL |
| enrollment_id | UUID NULL | FK sequence_enrollments SET NULL |
| step_id | UUID NULL | FK sequence_steps SET NULL |
| type | TEXT NOT NULL | CHECK in ('queued','sent','delivered','opened','clicked','replied','bounced','unsubscribed','converted','approved','rejected') |
| channel | TEXT NULL | CHECK in ('email','sms') |
| weight | INTEGER NOT NULL DEFAULT 0 | scoring contribution (open=+5,click=+15,reply=+30,bounce=-20,...) |
| metadata | JSONB NOT NULL DEFAULT '{}' | provider payload, subject, url, message_id |
| occurred_at | TIMESTAMPTZ NOT NULL DEFAULT NOW() | |
| created_at | TIMESTAMPTZ NOT NULL DEFAULT NOW() | |

`idx_engevents_lead (workspace_id, lead_id, occurred_at DESC)`,
`idx_engevents_campaign (campaign_id)`, `idx_engevents_type (workspace_id, type)`.

### Exact CREATE TABLE (in-convention sample — `leads` + `campaigns`)

```sql
-- ─── 023_outbound_engagement.sql ─────────────────────────────────────────────
-- Outbound engine: leads, lead_segments, lead_segment_members, sequences,
-- sequence_steps, campaigns, sequence_enrollments, engagement_events.
-- Idempotent (IF NOT EXISTS + DROP POLICY IF EXISTS).
-- NOT executed automatically — apply by hand to Supabase prod. Same DDL (minus
-- RLS) is mirrored into init_docker.sql for the Docker path.

CREATE TABLE IF NOT EXISTS leads (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id  UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  contact_id    UUID REFERENCES contacts(id) ON DELETE SET NULL,
  name          TEXT,
  email         TEXT,
  phone         TEXT,
  company       TEXT,
  title         TEXT,
  source        TEXT NOT NULL DEFAULT 'import'
                  CHECK (source IN ('import','manual','web','api','referral','event')),
  stage         TEXT NOT NULL DEFAULT 'new'
                  CHECK (stage IN ('new','contacted','engaged','qualified','converted','lost')),
  score         INTEGER NOT NULL DEFAULT 0,
  score_detail  JSONB NOT NULL DEFAULT '{}',
  owner_id      UUID REFERENCES users(id) ON DELETE SET NULL,
  custom_fields JSONB NOT NULL DEFAULT '{}',
  external_id   TEXT,
  last_engaged_at TIMESTAMPTZ,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_leads_ws_email
  ON leads (workspace_id, email) WHERE email IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_leads_ws_extid
  ON leads (workspace_id, external_id) WHERE external_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_leads_ws_stage ON leads (workspace_id, stage);
CREATE INDEX IF NOT EXISTS idx_leads_ws_score ON leads (workspace_id, score DESC);

ALTER TABLE leads ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "leads_policy" ON leads;
CREATE POLICY "leads_policy" ON leads
  USING (workspace_id = (SELECT workspace_id FROM users WHERE supabase_uid = auth.uid()));

-- … lead_segments, lead_segment_members, sequences, sequence_steps here …

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
```

(Repeat the table+index+RLS block for every remaining table. In `init_docker.sql`, paste the
`CREATE TABLE`/`CREATE INDEX` only — drop the `ALTER TABLE ... ENABLE ROW LEVEL SECURITY` and
`DROP/CREATE POLICY` lines.)

---

## 2. SQLALCHEMY MODELS + `packages/types`

One file per table under `apps/api/app/models/`, mirroring `contact.py`/`deal_note.py`
(2.0 `Mapped[...]`/`mapped_column`, `UUID(as_uuid=True)`, `JSONB` with callable defaults,
`server_default=func.now()`).

- `apps/api/app/models/lead.py` → `Lead`
- `apps/api/app/models/lead_segment.py` → `LeadSegment`
- `apps/api/app/models/lead_segment_member.py` → `LeadSegmentMember`
- `apps/api/app/models/sequence.py` → `Sequence`
- `apps/api/app/models/sequence_step.py` → `SequenceStep`
- `apps/api/app/models/campaign.py` → `Campaign`
- `apps/api/app/models/sequence_enrollment.py` → `SequenceEnrollment`
- `apps/api/app/models/engagement_event.py` → `EngagementEvent`

**Register ALL eight** in `apps/api/app/models/__init__.py` (both the `from app.models.x import X`
imports and the `__all__` entries) — matching how `DealNote`/`ContactNote` are wired. Metadata
won't resolve relationships otherwise.

Relationships: keep them minimal to avoid mapper-config churn — define FK columns only; add
`relationship()` back-populates lazily only where a router needs eager traversal (e.g.
`Sequence.steps`). Do NOT add relationships onto the large existing `Contact`/`User` models
beyond `Lead.contact_id`/`owner_id` FK columns (avoids touching hot models).

**`packages/types/crm.ts`** — add string-literal union types + interfaces (mirroring
`Deal`/`Contact`): `LeadStage`, `LeadSource`, `Lead`; `SegmentKind`, `LeadSegment`;
`SequenceStatus`, `SequenceChannel`, `Sequence`, `SequenceStep`; `CampaignStatus`, `Campaign`;
`EnrollmentStatus`, `SequenceEnrollment`; `EngagementEventType`, `EngagementEvent`. Timestamps as
`string`, ids as `string`, JSONB as `Record<string, unknown>`. `index.ts` already re-exports —
no change there.

---

## 3. API SURFACE

Five new router files. Each: module-level `router = APIRouter()` (no prefix/tags), full paths
incl. `/workspaces/{workspace_id}/...`, per-endpoint `if current_user.workspace_id !=
workspace_id: raise HTTPException(403)` as first line, every query `.where(Model.workspace_id ==
workspace_id)`, inline Pydantic schemas (`<Thing>Response` w/ `from_attributes`,
`Create<Thing>Request`, `Update<Thing>Request`), enum-ish validation against literal sets → 422,
`ActivityEvent` audit rows on writes, ORM-first + `supabase_rest.get_row` fallback before 404.
**Declare static sub-paths BEFORE `/{id}` routes.** Register each in `main.py` (import line +
`include_router(..., tags=[...])`); `routers/__init__.py` stays empty.

### `routers/leads.py`  (register BEFORE any generic `/{id}`-shadowing router)

| method | path | purpose | body → response |
|---|---|---|---|
| GET | `/workspaces/{ws}/leads` | list w/ filters | query: `stage,source,min_score,segment_id,q,limit,offset,sort` → `LeadResponse[]` |
| GET | `/workspaces/{ws}/leads/funnel` | funnel counts per stage | → `{stage,count,value}[]` (static path, declare first) |
| POST | `/workspaces/{ws}/leads/import` | **bulk CSV import up to 10k** | `ImportLeadsRequest{rows:[...], mapping:{}, dedupe_on:'email'}` → 202 `{status:'queued',job_id}` (enqueues worker; see §4) |
| GET | `/workspaces/{ws}/leads/import/{job_id}` | import progress | → poll shim; prefer shared `GET /jobs/{id}` |
| POST | `/workspaces/{ws}/leads/export` | CSV export of filtered set | filters → `text/csv` stream (static path, declare before `/{id}`) |
| POST | `/workspaces/{ws}/leads` | create one | `CreateLeadRequest` → 201 `LeadResponse` |
| GET | `/workspaces/{ws}/leads/{lead_id}` | detail | → `LeadResponse` |
| PATCH | `/workspaces/{ws}/leads/{lead_id}` | update fields | `UpdateLeadRequest` → `LeadResponse` |
| POST | `/workspaces/{ws}/leads/{lead_id}/stage` | **funnel stage transition** | `{stage}` validated vs literal set (422 on bad) → `LeadResponse`; writes `ActivityEvent` + `engagement_event(type='converted')` when stage→converted |
| POST | `/workspaces/{ws}/leads/{lead_id}/promote` | **bot→human close handoff**: create/link a `contacts` row (+ optional `deals`), set `lead.contact_id`, stage→qualified/converted | `{create_deal:bool, owner_id?}` → `{lead, contact_id, deal_id?}` |
| POST | `/workspaces/{ws}/leads/{lead_id}/score` | trigger engagement recompute | → 202 `{status:'queued',job_id}` (enqueue `score_lead_engagement`) |
| DELETE | `/workspaces/{ws}/leads/{lead_id}` | delete | → 204 |

### `routers/segments.py`

| method | path | purpose |
|---|---|---|
| GET | `/workspaces/{ws}/segments` | list segments (+ member_count) |
| POST | `/workspaces/{ws}/segments` | create (static or dynamic w/ `filter`) → 201 |
| GET | `/workspaces/{ws}/segments/{id}` | detail |
| PATCH | `/workspaces/{ws}/segments/{id}` | rename/edit filter |
| DELETE | `/workspaces/{ws}/segments/{id}` | delete |
| GET | `/workspaces/{ws}/segments/{id}/members` | list resolved leads (dynamic: evaluate `filter`; static: join table) |
| POST | `/workspaces/{ws}/segments/{id}/members` | add leads to static segment `{lead_ids:[]}` → recompute member_count |
| DELETE | `/workspaces/{ws}/segments/{id}/members/{lead_id}` | remove |

### `routers/campaigns.py`  (static sub-paths declared before `/{id}`)

| method | path | purpose |
|---|---|---|
| GET | `/workspaces/{ws}/campaigns` | list (query: `status`) |
| POST | `/workspaces/{ws}/campaigns` | create draft (bind segment_id + sequence_id) → 201 |
| GET | `/workspaces/{ws}/campaigns/{id}` | detail incl. `stats` |
| PATCH | `/workspaces/{ws}/campaigns/{id}` | edit while draft |
| POST | `/workspaces/{ws}/campaigns/{id}/schedule` | set `scheduled_at`, status→scheduled |
| POST | `/workspaces/{ws}/campaigns/{id}/launch` | status→active, **enroll segment** → 202 (enqueue `enroll_campaign`) |
| POST | `/workspaces/{ws}/campaigns/{id}/pause` | status→paused (halts sender) |
| POST | `/workspaces/{ws}/campaigns/{id}/resume` | status→active |
| GET | `/workspaces/{ws}/campaigns/{id}/enrollments` | list enrollments + status |
| GET | `/workspaces/{ws}/campaigns/{id}/stats` | live rollup from `engagement_events` |
| DELETE | `/workspaces/{ws}/campaigns/{id}` | archive |

### `routers/sequences.py`  (static sub-paths before `/{id}`)

| method | path | purpose |
|---|---|---|
| GET | `/workspaces/{ws}/sequences` | list |
| POST | `/workspaces/{ws}/sequences` | create → 201 |
| GET | `/workspaces/{ws}/sequences/{id}` | detail incl. ordered `steps[]` |
| PATCH | `/workspaces/{ws}/sequences/{id}` | rename/status |
| DELETE | `/workspaces/{ws}/sequences/{id}` | archive |
| PUT | `/workspaces/{ws}/sequences/{id}/steps` | **replace full ordered step list** (builder save) `{steps:[{step_order,channel,delay_hours,subject,body_template,requires_approval,ai_generate}]}` → recompute `step_count` |
| POST | `/workspaces/{ws}/sequences/{id}/steps` | append one step |
| PATCH | `/workspaces/{ws}/sequences/{id}/steps/{step_id}` | edit one |
| DELETE | `/workspaces/{ws}/sequences/{id}/steps/{step_id}` | remove |

### `routers/outreach.py`  (the bot→human HITL handoff surface)

Copies the `followup_sequences.py` HITL idiom (draft → pending → approve/reject → resolve) but
scoped to sequence sends. A step with `requires_approval=TRUE` produces a **pending draft** the
human approves before the sender actually delivers.

| method | path | purpose |
|---|---|---|
| GET | `/workspaces/{ws}/outreach/pending` | queue of drafts awaiting approval (enrollment + rendered/AI subject+body) |
| POST | `/workspaces/{ws}/outreach/{enrollment_id}/draft` | (re)generate the current step's draft via Claude → returns editable `{subject,body}` |
| POST | `/workspaces/{ws}/outreach/{enrollment_id}/approve` | approve (optionally edited) → marks send-ready, writes `engagement_event(type='approved')`, lets sender deliver → 202 |
| POST | `/workspaces/{ws}/outreach/{enrollment_id}/reject` | reject → skip/stop step, `engagement_event(type='rejected')` |
| POST | `/workspaces/{ws}/webhooks/engagement` | inbound provider webhook (open/click/reply/bounce/unsub) → append `engagement_event`, update `enrollment` (stop_on_reply), enqueue `score_lead_engagement`. Rate-limited `@limiter.limit`, no auth (HMAC-verify payload instead — mirror `webhook_logs.py`). |

**Response schema note:** every `<Thing>Response` carries `model_config = {"from_attributes":
True}` and is built with `.model_validate(orm_obj)`. `stage`/`status`/`type`/`source`/`channel`
validated in-handler against the same literal sets as the SQL CHECK constraints → `HTTPException
(422)`.

---

## 4. WORKERS (Celery)

Four new workers under `apps/api/app/workers/`. Copy `score_contact.py` structure: sync
`@celery_app.task(name="app.workers.<mod>.<fn>", bind=True)` wrapper → `asyncio.run(_async(...))`;
own `_get_async_session()` reusing `PGBOUNCER_CONNECT_ARGS`; primitive args (cast to UUID
inside); write results to Postgres + log an `ActivityEvent`; `<task>_all` dispatcher for
beat-scheduled fan-out over workspaces. **Add every module to `celery_app.py include=[...]`**
and add beat entries.

### `workers/import_leads.py` — bulk import processor
`process_lead_import(workspace_id, rows_json_or_path, mapping, dedupe_on)`. Chunked insert
(batch 500) of up to 10k rows: map columns → `Lead`, dedupe on `(workspace_id, email/external_id)`
via `INSERT ... ON CONFLICT DO NOTHING` (or pre-select existing keys), accumulate
`{inserted,skipped,errors}`, write a summary `ActivityEvent`. Triggered from
`POST /leads/import`. Poll via shared `GET /jobs/{job_id}` (call `_mark_job_dispatched` at
enqueue). For a 10k CSV the router should persist the payload to a temp/staging area and pass a
reference, not 10k rows through the JSON serializer.

### `workers/campaign_enroll.py` — enrollment builder
`enroll_campaign(workspace_id, campaign_id)`: resolve the campaign's segment (static join or
dynamic filter eval) → create one `sequence_enrollment` per lead (`ON CONFLICT (campaign_id,
lead_id) DO NOTHING`), set `current_step=0`, `next_run_at=NOW()` (or campaign `scheduled_at`),
bump `campaign.stats.enrolled`. Triggered from `POST /campaigns/{id}/launch`.

### `workers/sequence_sender.py` — the scheduler/sender (beat-driven)
- `tick_sequences_all()` — **beat dispatcher** (crontab every 5 min), enumerates workspace ids,
  calls `tick_sequences.delay(ws_id)` per workspace.
- `tick_sequences(workspace_id)` — select `sequence_enrollments` where `status IN
  ('active','waiting')` AND `next_run_at <= NOW()` AND parent campaign `status='active'`. For
  each: load the `sequence_step` at `current_step`.
  - If `step.requires_approval` and no approved draft exists → generate/ensure a **pending draft**
    (Claude if `ai_generate`, else render `body_template` tokens), write `engagement_event
    (type='queued')`, set enrollment `status='waiting'`, and surface it to
    `/outreach/pending`. Do NOT send.
  - If approved (or approval not required) → **send** via existing Gmail/SMS connector, write
    `engagement_event(type='sent')`, advance `current_step`, set `next_run_at = NOW() +
    next_step.delay_hours`, `last_sent_at=NOW()`. If no next step → `status='completed'`.
  - Respect `sequences.settings.stop_on_reply` and quiet-hours.
- Send channel: reuse the Gmail path used by `followup_sequences.py`; SMS is a stub connector for
  the Zach demo (log + `engagement_event`) unless a Twilio connector is wired.

### `workers/engagement_score.py` — scoring recompute
- `score_lead_engagement(workspace_id, lead_id)` — sum weighted `engagement_events` over a
  trailing window (open+5, click+15, reply+30, converted+40, bounce-20, unsub-30), clamp 0-100,
  derive `label` (cold/warm/hot), write `lead.score` + `lead.score_detail`, update
  `last_engaged_at`, auto-advance `lead.stage` on thresholds (e.g. reply→engaged, score≥70 &
  replied→qualified), log `ActivityEvent`. Mirrors `score_contact.py` `_compute_score` shape.
- `score_leads_all()` — beat dispatcher (crontab hourly), fans out per workspace →
  `rescore_workspace_leads(workspace_id)` which enqueues per-lead scoring for recently-active
  leads.

### Beat additions (`celery_app.py` `beat_schedule`)
```python
"tick-sequences":      {"task": "app.workers.sequence_sender.tick_sequences_all", "schedule": crontab(minute="*/5"), "args": []},
"hourly-lead-scoring": {"task": "app.workers.engagement_score.score_leads_all",   "schedule": crontab(minute=0),    "args": []},
```
`include=[...]` gains: `app.workers.import_leads`, `app.workers.campaign_enroll`,
`app.workers.sequence_sender`, `app.workers.engagement_score`.

**Trigger/poll:** router enqueues with `.delay(...)`, calls `_mark_job_dispatched(task.id,
str(ws))` (from `routers.agents`), returns `202 {status:'queued',job_id}`. Never build a custom
poll endpoint — reuse `GET /jobs/{job_id}`.

---

## 5. WEB UI

Next.js App Router, `"use client"` pages, 4-layer stack (route → hook → api-client → demo-data).
Dark zinc/indigo theme, `Card`/`Button`/`Badge` primitives, hand-rolled tables & inline board
sub-components (no generic Table/Kanban). **Every api-client method needs an `if (isDemoMode)`
branch** + a demo fixture.

### New pages
1. `src/app/(app)/leads/page.tsx` — **table + funnel-board toggle + bulk CSV import**. Table
   copies `contacts/page.tsx` (stat-tile filter row, `<table>` w/ `LeadRow`, `BulkActionBar`);
   board copies `pipeline/page.tsx` (`FunnelColumn` + `LeadCard` inline over
   `funnelStageOrder.map(...)`). Inline sub-components: `NewLeadModal`, `ImportLeadsModal`
   (file input → CSV parse → column-mapping UI → `apiClient.importLeads` → poll job → toast),
   `LeadDetailPanel` (right drawer).
2. `src/app/(app)/leads/[id]/page.tsx` — lead detail (copy `pipeline/[id]/page.tsx`): overview
   card, engagement-score gauge, `engagement_events` timeline (recharts area for score trend),
   enrollment list, "Promote to contact/deal" button (`apiClient.promoteLead`), stage stepper.
3. `src/app/(app)/campaigns/page.tsx` — campaigns list (contacts table pattern) + `NewCampaignModal`
   (pick segment + sequence + schedule). Status badges; launch/pause/resume actions.
4. `src/app/(app)/campaigns/[id]/page.tsx` — campaign detail: stats tiles (enrolled/sent/opened/
   clicked/replied/converted), enrollment table, funnel conversion chart.
5. `src/app/(app)/sequences/page.tsx` — sequences list + `NewSequenceModal`.
6. `src/app/(app)/sequences/[id]/page.tsx` — **step builder**: ordered list of `StepCard`s
   (channel, delay, subject, body_template w/ token chips, requires_approval toggle, ai_generate
   toggle), add/remove/reorder, "Save" → `apiClient.saveSequenceSteps` (PUT). Preview render.
7. `src/app/(app)/outreach/page.tsx` — **approval queue** (bot→human handoff): list of pending
   drafts, each an editable subject/body card with Approve / Regenerate / Reject. Copies the
   `LogActivityModal`/drawer editing pattern.

### Hooks (`src/hooks/`)
`useLeads.ts` (filter+stage, `importLeads`, `promoteLead`, `updateStage`), `useSegments.ts`,
`useCampaigns.ts` (launch/pause/resume), `useSequences.ts` (+ step CRUD), `useOutreach.ts`
(pending queue, approve/reject/regenerate). Each mirrors `useDeals.ts`: seed from demo when
`isDemoMode`, else Supabase session → `workspace_id` + `access_token` → `apiClient`,
`rowToX()` snake→camel mapper, returns `{items, loading, error, refetch, ...mutations}`.

### `src/lib/api-client.ts`
Add methods inside the `apiClient` object, each with a demo branch, and
`import { demoLeads, demoSegments, demoCampaigns, demoSequences, demoPendingOutreach } from
'./demo-data'`:
`listLeads/getLead/createLead/updateLead/deleteLead/importLeads/promoteLead/updateLeadStage/
getLeadFunnel/getLeadEvents`; `listSegments/createSegment/getSegmentMembers/addSegmentMembers`;
`listCampaigns/getCampaign/createCampaign/launchCampaign/pauseCampaign/resumeCampaign/
getCampaignStats`; `listSequences/getSequence/createSequence/saveSequenceSteps`;
`listPendingOutreach/draftOutreach/approveOutreach/rejectOutreach`. Import-job & score-job poll
via existing `getJob(workspaceId, jobId, token)`.

### Types / config / demo
- `src/lib/types.ts` — `Lead`, `LeadStage`, `Segment`, `Campaign`, `CampaignStatus`, `Sequence`,
  `SequenceStep`, `Enrollment`, `EngagementEvent` (camelCase, mirror `Deal`).
- `src/lib/supabase.ts` — `LeadRow`, `SegmentRow`, `CampaignRow`, `SequenceRow`,
  `SequenceStepRow`, `EnrollmentRow`, `EngagementEventRow` (snake_case DB shape).
- `src/lib/utils.ts` — `funnelStageConfig` + `funnelStageOrder` (colors/labels for the 6 lead
  stages), `campaignStatusConfig`, `engagementScoreConfig` (reuse `leadScoreConfig` idiom).
- `src/lib/demo-data.ts` — `demoLeads` (~40 rows spanning stages/scores), `demoSegments`,
  `demoCampaigns`, `demoSequences` (+ steps), `demoPendingOutreach`, `demoEngagementEvents`.

### Sidebar (`src/components/layout/Sidebar.tsx`)
Add to the `workspace` nav group (import icons from `lucide-react`):
```ts
{ href: "/leads",     label: "Leads",     icon: Filter, hideModes: ["pm"] },
{ href: "/campaigns", label: "Campaigns", icon: Send,   hideModes: ["pm"] },
{ href: "/sequences", label: "Sequences", icon: Workflow, hideModes: ["pm"] },
{ href: "/outreach",  label: "Outreach",  icon: Inbox,  hideModes: ["pm"], badge: pendingCount },
```
`hideModes: ["pm"]` keeps them sales-only (mirrors Pipeline/Reports). Active-state highlight is
automatic (`pathname.startsWith(href + "/")`). Optionally extend `CommandPalette.tsx`
`navigateTo` for `/leads/[id]` deep links.

---

## 6. BUILD ORDER (dependency-layered build units)

Each unit is sized for one agent and carries an acceptance check. Strict layering: schema →
models/types → API → workers → UI → tests. Units within the same layer number can run in
parallel; a later layer must not start until its predecessor's acceptance passes.

**U1 — Schema (migration + docker mirror).** Write `023_outbound_engagement.sql` (8 tables, FK
order, indexes, RLS) and mirror the no-RLS DDL into `init_docker.sql`.
*Accept:* `psql -f 023...` applies clean twice (idempotent) on a scratch DB; `grep -c "CREATE
TABLE" init_docker.sql` increased by 8; FK order verified (no forward-reference errors).

**U2 — SQLAlchemy models + registry.** 8 model files + register in `models/__init__.py`.
*Accept:* `cd apps/api && .venv/bin/python -c "import app.models"` imports with no mapper error;
`.venv/bin/python -c "from app.main import app"` boots (metadata resolves).

**U3 — TypeScript types.** Add interfaces/unions to `packages/types/crm.ts`.
*Accept:* `cd apps/web && pnpm exec tsc --noEmit` passes.

**U4 — Router: leads** (`routers/leads.py` incl. import/export/funnel/stage/promote/score
endpoints + inline schemas) + register in `main.py` (static-before-`/{id}` order).
*Accept:* new `tests/test_leads.py` passes list-empty/create-201/403/404/422 + stage-transition
422; app boots.

**U5 — Router: segments** (`routers/segments.py` + register).
*Accept:* `tests/test_segments.py` green (CRUD + members add/remove + 403).

**U6 — Router: sequences** (`routers/sequences.py` + steps CRUD/PUT + register).
*Accept:* `tests/test_sequences.py` green (create, PUT step list recomputes step_count, 422 on
bad channel).

**U7 — Router: campaigns** (`routers/campaigns.py` + schedule/launch/pause/resume + register).
*Accept:* `tests/test_campaigns.py` green (draft create binds segment+sequence, launch returns
202 + job_id, pause/resume status transitions).

**U8 — Router: outreach/HITL + webhook** (`routers/outreach.py` + register).
*Accept:* `tests/test_outreach.py` green (pending list, approve→202 writes approved event, reject
path, webhook appends engagement_event). U4–U8 can parallelize after U2/U3; they share only
`main.py` (coordinate the include block).

**U9 — Worker: import_leads** + celery include.
*Accept:* `tests/test_import_leads_worker.py` (mocked session) inserts N, dedupes on email,
returns summary; `celery_app.py include` lists the module.

**U10 — Worker: campaign_enroll** + include.
*Accept:* unit test enrolls one row per segment lead, ON CONFLICT no-dup, bumps stats.

**U11 — Worker: engagement_score** + beat entry + include.
*Accept:* `_compute_score` unit test: weighted sum clamps 0-100, label derivation, stage
auto-advance on reply; `score_leads_all` dispatcher enumerates workspaces.

**U12 — Worker: sequence_sender** (tick + send + HITL gate) + beat + include. Depends on U8
(pending-draft contract) + U10 (enrollments exist) + U11 (scoring).
*Accept:* unit test: due enrollment with `requires_approval` → pending/waiting, no send; approved
→ send + advance current_step + set next_run_at; last step → completed; stop_on_reply honored.

**U13 — Web data layer** (`types.ts`, `supabase.ts`, `utils.ts` config maps, `api-client.ts`
methods w/ demo branches, `demo-data.ts` fixtures, hooks). Depends on U3.
*Accept:* `pnpm exec tsc --noEmit` passes; demo fixtures typed against `types.ts`.

**U14 — Web pages: /leads (table + board + import + detail)** + Sidebar nav.
*Accept:* demo build renders `/leads`; funnel board + table toggle; import modal opens;
`/leads/[id]` renders score gauge + timeline. `pnpm build` (demo env) succeeds.

**U15 — Web pages: /campaigns + /sequences (builder)** .
*Accept:* demo build renders both; sequence step builder saves via demo stub; campaign detail
shows stats tiles.

**U16 — Web page: /outreach approval queue.**
*Accept:* demo build renders pending drafts with editable body + approve/reject/regenerate.

**U17 — E2E + demo coverage.** Playwright spec `e2e/leadgen.spec.ts` (role/region locators)
covering leads board, campaign create, sequence builder, outreach approve — all in demo mode.
*Accept:* `pnpm build && pnpm test:e2e` green in demo env.

**U18 — Full-suite regression + review.** Run API pytest (all), web tsc + build, e2e; then
`ecc:fastapi-reviewer` + `ecc:react-reviewer` + `ecc:database-reviewer` passes on the diff.
*Accept:* all green; reviewers return no blocking findings; migration applied by hand to Supabase
prod + folded into `init_docker.sql` confirmed.

---

## 7. VERIFICATION PLAN (exact commands)

Repo root: `/mnt/external/Projects/crm-agentic`.

**Schema idempotency (scratch DB):**
```bash
# apply twice against a throwaway Postgres — second run must be a no-op, no errors
psql "$SCRATCH_DB_URL" -f apps/api/migrations/023_outbound_engagement.sql
psql "$SCRATCH_DB_URL" -f apps/api/migrations/023_outbound_engagement.sql
grep -c "CREATE TABLE" apps/api/migrations/init_docker.sql   # +8 vs baseline
```

**Models import / app boots:**
```bash
cd /mnt/external/Projects/crm-agentic/apps/api && .venv/bin/python -c "import app.models; from app.main import app; print('ok', len(app.routes))"
```

**API tests (mocked DB, no creds — conftest injects env):**
```bash
cd /mnt/external/Projects/crm-agentic/apps/api && .venv/bin/python -m pytest -q --tb=short
# targeted:
cd /mnt/external/Projects/crm-agentic/apps/api && .venv/bin/python -m pytest tests/test_leads.py tests/test_campaigns.py tests/test_sequences.py tests/test_segments.py tests/test_outreach.py -q
```
Expect the prior baseline (533) + new tests, all passing.

**Celery wiring smoke:**
```bash
cd /mnt/external/Projects/crm-agentic/apps/api && .venv/bin/python -c "from app.workers.celery_app import celery_app; print([t for t in celery_app.tasks if 'sequence_sender' in t or 'engagement_score' in t or 'import_leads' in t or 'campaign_enroll' in t])"
```

**Web type-check + build (demo env):**
```bash
cd /mnt/external/Projects/crm-agentic/apps/web && pnpm install --frozen-lockfile
cd /mnt/external/Projects/crm-agentic/apps/web && pnpm exec tsc --noEmit
cd /mnt/external/Projects/crm-agentic/apps/web && NEXT_PUBLIC_SUPABASE_URL=https://placeholder.supabase.co NEXT_PUBLIC_SUPABASE_ANON_KEY=placeholder-anon-key NEXT_PUBLIC_FASTAPI_URL=http://localhost:8000 NEXT_PUBLIC_DEMO_MODE=true pnpm build
```

**Demo-clickable E2E:**
```bash
cd /mnt/external/Projects/crm-agentic/apps/web && pnpm exec playwright install chromium --with-deps   # once
cd /mnt/external/Projects/crm-agentic/apps/web && pnpm test:e2e
```

**Manual demo walk-through (the September bar):** demo build → `/leads` shows imported leads in
table + funnel board → create a segment → build a 3-step sequence → create+launch a campaign over
the segment → `/outreach` shows the first-step draft pending → approve → lead advances stage and
engagement score moves. This is the exact click-path Zach is shown; if every step is observable in
the demo build, the module is demonstrable.
```
