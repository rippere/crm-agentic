# NovaCRM — Lead-Gen Increment: Criteria → Auto-Cascade — Build Spec

**Status:** Ready-to-build increment spec (config values pending Zach). **Owner:** lead architect.
**Date:** 2026-08-31. **Repo:** `crm-agentic` (`/mnt/external/Projects/crm-agentic`).
**Builds on:** `BUILD-SPEC-leadgen.md` (shipped module — migration `023`, PR #73).
**Direction source:** `decisions/leadgen-direction-zach-2026-08-31.md` (Pillars A & B).

## 0. Purpose & framing (ground truth)

Turn the shipped leadgen module from a **manual campaign tool** ("pick a segment, click Launch")
into a **target-acquisition engine**: when a lead **matches a target criteria**, it is
**automatically enrolled** into the bound outreach sequence — the "cascading workflow" Zach
described — with a **human-in-the-loop delegation gate** that can escalate or de-escalate per rule.

The design is **reuse-first**. Three facts make this a thin increment, not a new subsystem:

1. **A dynamic `lead_segment` already IS "populated criteria over leads."** Its `filter` JSONB
   (`{stage, source, min_score, tags}`) is evaluated live by
   `workers/campaign_enroll._dynamic_filter_conditions()` / `_resolve_segment_lead_ids()` and
   `routers/segments._apply_lead_filter()`. **We reuse the segment as the criteria/ICP** — no new
   criteria table.
2. **Enrollment, sending, HITL send-approval, and stats already exist** — `sequence_enrollments`,
   `workers/sequence_sender`, `routers/outreach` (pending → approve/reject), and `campaign.stats`.
3. **`sequence_enrollments.campaign_id` is `NOT NULL`.** So each cascade rule **provisions a
   backing campaign** (an always-on `status='active'` campaign) as the enrollment container. This
   makes the entire existing sender/outreach/scoring pipeline work for auto-enrolled leads with
   **zero changes** to those workers/routers.

So the ONLY genuinely new logic is: **an evaluator that periodically (and on lead events) finds
leads newly matching an active rule's criteria and enrolls them — auto, or held for approval —
recording provenance so nothing double-enrolls.**

**Reframing:** a *manual campaign* = "enroll this segment **once**, on launch." A *cascade rule* =
"an **always-on** campaign that **keeps enrolling** new matches." Same substrate.

### Design non-goals for this increment
- **Trust-based auto-adjustment of the delegation level** (the full "delegative graph" that moves
  the HITL boundary automatically as trust is earned). This increment ships the *levels* and
  *manual* escalation/de-escalation; auto-adjust is a later phase.
- **Pillar C (whisper / real-time deal adaptation)** and **Pillar D (install analytics)** —
  separate modules, out of scope (see the direction doc).

### PENDING ZACH (config, not schema — the schema below is answer-agnostic)
- **Q1 criteria fields:** the concrete signals of a good photobooth lead (venue type, event
  volume, geography, budget band). These extend the segment `filter` vocabulary — **additively**,
  so unknown keys are ignored today (`_dynamic_filter_conditions` already skips unknown keys).
- **Q2 delegation defaults:** which rules start `auto` vs `approve_enroll`. Ships as a per-rule
  enum with a **safe default of `approve_enroll`** (nothing auto-sends without a human until Zach
  opts a rule up to `auto`).

---

## 1. DATA MODEL

Two new tables in **`apps/api/app/migrations/024_criteria_cascade.sql`** (024 is the next free
number; 023 is the last leadgen migration). Same house shape as `023`: `id UUID PK`,
`workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE`, enums as `TEXT CHECK`,
JSONB `NOT NULL DEFAULT`, `created_at`/`updated_at`, tenant-scoped uniqueness, RLS keyed on
`users.supabase_uid = auth.uid()`. **Mirror the no-RLS DDL into `init_docker.sql`** after the
`023` block (same rule as the base spec — `init_docker.sql` has no migration runner).

FK order inside the file: `cascade_rules` (references `lead_segments`, `sequences`, `campaigns`)
→ `cascade_matches` (references `cascade_rules`, `leads`, `sequence_enrollments`).

### `cascade_rules`
Binds a **criteria** (a segment) → a **sequence**, through a **backing campaign**, with a
**delegation level**. The always-on analogue of a manual campaign.

| column | type | notes |
|---|---|---|
| id | UUID PK | `gen_random_uuid()` |
| workspace_id | UUID NOT NULL | FK workspaces CASCADE |
| name | TEXT NOT NULL | |
| segment_id | UUID NOT NULL | FK lead_segments **ON DELETE CASCADE** — the criteria; rule is meaningless without it |
| sequence_id | UUID NOT NULL | FK sequences ON DELETE CASCADE — the outreach recipe to enroll into |
| campaign_id | UUID NOT NULL | FK campaigns ON DELETE CASCADE — the **backing** always-on campaign the rule provisions & owns |
| status | TEXT NOT NULL DEFAULT 'paused' | CHECK in ('paused','active','archived') — `paused` = evaluated-but-does-nothing (observe breadth before turning on) |
| delegation | TEXT NOT NULL DEFAULT 'approve_enroll' | CHECK in ('auto','approve_enroll','observe') — the HITL gate (see §1.1) |
| trigger_on | JSONB NOT NULL DEFAULT '["create","import","score","stage"]' | which lead events fire targeted evaluation (superset always also caught by the beat sweep) |
| daily_cap | INTEGER NOT NULL DEFAULT 0 | max auto-enrollments/day, 0 = uncapped (throttle; Zach's "prove narrow" needs a governor) |
| stats | JSONB NOT NULL DEFAULT '{}' | `{matched,enrolled,pending,rejected,suppressed}` denormalized |
| last_evaluated_at | TIMESTAMPTZ NULL | |
| created_at / updated_at | TIMESTAMPTZ NOT NULL DEFAULT NOW() | updated_at onupdate |

`UNIQUE (workspace_id, name)`, `UNIQUE (campaign_id)` (one rule per backing campaign),
`idx_cascade_rules_ws_status (workspace_id, status)`,
`idx_cascade_rules_active (status, last_evaluated_at)` (sweeper scan).

### `cascade_matches`
Append-only provenance + **idempotency ledger**: one row per (rule, lead) the evaluator has ever
seen. This is what stops double-enrollment and gives Zach the "why did this lead get contacted?"
audit. Owned child of `cascade_rules` (CASCADE).

| column | type | notes |
|---|---|---|
| id | UUID PK | |
| workspace_id | UUID NOT NULL | FK workspaces CASCADE |
| rule_id | UUID NOT NULL | FK cascade_rules CASCADE |
| lead_id | UUID NOT NULL | FK leads CASCADE |
| enrollment_id | UUID NULL | FK sequence_enrollments ON DELETE SET NULL — set once enrolled |
| status | TEXT NOT NULL DEFAULT 'pending' | CHECK in ('pending','enrolled','rejected','suppressed') |
| matched_filter | JSONB NOT NULL DEFAULT '{}' | snapshot of the criteria filter at match time (provenance) |
| decided_by | UUID NULL | FK users ON DELETE SET NULL — human who approved/rejected (null when auto) |
| matched_at | TIMESTAMPTZ NOT NULL DEFAULT NOW() | |
| decided_at | TIMESTAMPTZ NULL | |
| created_at | TIMESTAMPTZ NOT NULL DEFAULT NOW() | |

`UNIQUE (rule_id, lead_id)` — **the idempotency key**; the evaluator inserts
`ON CONFLICT (rule_id, lead_id) DO NOTHING`, so a lead is matched to a rule exactly once ever.
`idx_cascade_matches_rule_status (rule_id, status)`,
`idx_cascade_matches_ws_pending (workspace_id, status)` (approval queue scan).

### 1.1 Delegation levels — the (initial) delegative HITL graph

| level | on match | who approves the ENROLLMENT | sends still gated by |
|---|---|---|---|
| `observe` | record `cascade_match(status='suppressed')`, **no enrollment** | — (measures breadth/provenance only) | n/a |
| `approve_enroll` (default) | record `cascade_match(status='pending')`, **no enrollment yet** | a human, via `POST /cascades/{id}/matches/{mid}/approve` → creates the enrollment | per-step `sequence_step.requires_approval` (existing `/outreach`) |
| `auto` | create enrollment immediately, `cascade_match(status='enrolled')` | nobody (enrollment auto) | per-step `sequence_step.requires_approval` (existing `/outreach`) |

**Escalation/de-escalation = changing a rule's `delegation` (PATCH).** Manual in this increment.
Two independent gates compose: enrollment-gate (this table) and send-gate (existing `/outreach`).
A fully-hands-off rule is `delegation='auto'` **and** its sequence steps `requires_approval=false`.

---

## 2. SQLALCHEMY MODELS + `packages/types`

Two model files under `apps/api/app/models/`, mirroring `campaign.py`/`sequence_enrollment.py`
(2.0 `Mapped[...]`/`mapped_column`, `UUID(as_uuid=True)`, `JSONB` callable defaults,
`server_default=func.now()`):

- `apps/api/app/models/cascade_rule.py` → `CascadeRule`
- `apps/api/app/models/cascade_match.py` → `CascadeMatch`

**Register BOTH** in `apps/api/app/models/__init__.py` (imports + `__all__`). FK columns only; add
no `relationship()` back-populates onto the hot `Lead`/`Campaign`/`Sequence` models.

**`packages/types/crm.ts`** — add `CascadeStatus`, `CascadeDelegation`, `CascadeRule`;
`CascadeMatchStatus`, `CascadeMatch` (timestamps `string`, ids `string`, JSONB
`Record<string, unknown>`), mirroring the `Campaign`/`SequenceEnrollment` interfaces.

---

## 3. API SURFACE

One new router `apps/api/app/routers/cascades.py`. Same conventions as the base spec: module-level
`router = APIRouter()`, full `/workspaces/{workspace_id}/...` paths, per-endpoint
`if current_user.workspace_id != workspace_id: raise HTTPException(403)`, every query
`.where(Model.workspace_id == workspace_id)`, inline Pydantic schemas, literal-set validation →
422, `ActivityEvent` on writes, ORM-first + `supabase_rest` fallback before 404. **Static
sub-paths before `/{id}`.** Register in `main.py`.

| method | path | purpose |
|---|---|---|
| GET | `/workspaces/{ws}/cascades` | list rules (query `status`) incl. `stats` |
| POST | `/workspaces/{ws}/cascades` | create a rule → **provisions the backing campaign** (see §3.1) → 201 |
| POST | `/workspaces/{ws}/cascades/preview` | **dry-run** `{segment_id}` → `{match_count}` (reuse `_resolve_segment_lead_ids`) — "how many leads match now" before activating (static path) |
| GET | `/workspaces/{ws}/cascades/pending` | enrollment-approval queue: `cascade_matches` where `status='pending'`, joined lead + rule (static path) |
| GET | `/workspaces/{ws}/cascades/{id}` | detail incl. stats + recent matches |
| PATCH | `/workspaces/{ws}/cascades/{id}` | edit name / **delegation** (escalate/de-escalate) / `daily_cap` / `trigger_on` |
| POST | `/workspaces/{ws}/cascades/{id}/activate` | status→active (starts matching) |
| POST | `/workspaces/{ws}/cascades/{id}/pause` | status→paused (stops matching; existing enrollments run on) |
| POST | `/workspaces/{ws}/cascades/{id}/evaluate` | manual evaluate-now → 202 (enqueue `evaluate_cascade`) |
| GET | `/workspaces/{ws}/cascades/{id}/matches` | provenance ledger (query `status`) |
| POST | `/workspaces/{ws}/cascades/{id}/matches/{mid}/approve` | approve a `pending` match → create enrollment (reuse enroll path), set match `enrolled`+`enrollment_id`+`decided_by`, `engagement_event(type='approved')` → 202 |
| POST | `/workspaces/{ws}/cascades/{id}/matches/{mid}/reject` | reject → match `rejected`+`decided_by` |
| DELETE | `/workspaces/{ws}/cascades/{id}` | archive rule + backing campaign (status→archived) |

### 3.1 Backing-campaign provisioning (create)
On `POST /cascades`, in one transaction: create a `campaign` (`name = "⚡ " + rule.name`,
`status='active'`, `segment_id`, `sequence_id`, `channel = sequence.channel`,
`settings={'cascade': true}`) then the `cascade_rule` pointing at it. Rule `status` starts
`paused` (nothing matches until explicitly activated — safe default, matches Zach's observe-first
posture). Deleting/archiving the rule archives the backing campaign.

---

## 4. WORKERS (Celery)

One new worker `apps/api/app/workers/cascade_evaluator.py` (copy `campaign_enroll.py`/
`engagement_score.py` structure: sync `@celery_app.task(name=..., bind=True)` → `asyncio.run`,
own `_get_async_session()`, write results + `ActivityEvent`; `_all` beat dispatcher). **Add the
module to `celery_app.py include=[...]` and a beat entry.**

### Tasks
- `evaluate_cascades_all()` — **beat dispatcher** (crontab every 10 min), enumerate workspace ids,
  `evaluate_workspace_cascades.delay(ws)` each.
- `evaluate_workspace_cascades(workspace_id)` — for each `cascade_rule` with `status='active'`:
  1. **Resolve current matches:** reuse `campaign_enroll._resolve_segment_lead_ids(db, ws,
     segment)` on the rule's segment — the criteria eval already exists; do not reimplement it.
  2. **Diff against the ledger:** `INSERT INTO cascade_matches (rule_id, lead_id, ...) ... ON
     CONFLICT (rule_id, lead_id) DO NOTHING` for each resolved lead. Only genuinely new rows
     proceed (idempotent — a lead matches a rule once, ever).
  3. **Apply delegation** per new match, honoring `daily_cap`:
     - `observe` → set match `suppressed`.
     - `approve_enroll` → leave match `pending` (surfaces in `/cascades/pending`). No enrollment.
     - `auto` → create a `sequence_enrollment` on the **backing campaign** (reuse the
       `campaign_enroll` insert idiom: `ON CONFLICT (campaign_id, lead_id) DO NOTHING`,
       `current_step=0`, `next_run_at=NOW()`), set match `enrolled` + `enrollment_id`,
       `engagement_event(type='queued')`. The existing `sequence_sender` beat picks it up.
  4. Update `rule.stats` + `last_evaluated_at`.
- `evaluate_cascade(workspace_id, rule_id)` — single-rule form; enqueued by
  `POST /cascades/{id}/evaluate` and by lead-event hooks (below).

### Lead-event hooks (targeted, low-latency — complement the 10-min sweep)
Where the base module already writes lead changes, enqueue a **targeted** evaluation so a hot lead
cascades in seconds, not up to 10 minutes:
- `workers/import_leads.py` — after a bulk import commits, enqueue `evaluate_workspace_cascades`.
- `workers/engagement_score.py` — after `score_lead_engagement` advances a lead's stage/score,
  enqueue `evaluate_workspace_cascades` (score-threshold crossings are the highest-value trigger —
  a lead going hot should cascade immediately).
Guard each with `rule.trigger_on` membership. The beat sweep is the backstop; hooks are the
fast path. **No new poll endpoints** — reuse `GET /jobs/{job_id}` for any job returns.

### Beat / include additions (`celery_app.py`)
```python
"evaluate-cascades": {"task": "app.workers.cascade_evaluator.evaluate_cascades_all", "schedule": crontab(minute="*/10"), "args": []},
```
`include=[...]` gains `app.workers.cascade_evaluator`.

---

## 5. WEB UI

Next.js App Router, `"use client"`, 4-layer stack (route → hook → api-client → demo-data), dark
zinc/indigo, `Card`/`Button`/`Badge` primitives. **Every api-client method needs an `if
(isDemoMode)` branch + a demo fixture.**

### New pages
1. `src/app/(app)/cascades/page.tsx` — rules list (contacts-table pattern): name, criteria
   (segment) chip, sequence chip, **delegation badge** (auto / approve / observe), live
   `match_count`, status, `stats`. `NewCascadeModal` = pick a **criteria segment** + a **sequence**
   + delegation level + daily cap; on open, call `previewCascade(segment_id)` to show the live
   match count before commit. Row actions: Activate / Pause, Evaluate now.
2. `src/app/(app)/cascades/[id]/page.tsx` — rule detail: stats tiles
   (matched/enrolled/pending/rejected), the **matches provenance table** (lead, status, matched_at,
   which enrollment), delegation escalate/de-escalate control (PATCH), and a link to the backing
   campaign.
3. **Cascade approval queue** — either `src/app/(app)/cascades/pending/page.tsx` or a tab on the
   existing `/outreach` page. Editable-free approve/reject cards over `/cascades/pending`
   (distinct from `/outreach`, which gates **sends**; this gates **enrollments**). Copies the
   `/outreach` card + optimistic-remove pattern.

### Hooks / data layer
- `src/hooks/useCascades.ts` — mirror `useCampaigns.ts` (`create`, `activate`, `pause`,
  `evaluate`, `preview`, `updateDelegation`; matches list; approve/reject). **In demo mode do NOT
  refetch after an optimistic mutation** — the base module's `campaigns` bug (a demo `refetch`
  re-seeds static fixtures and drops the optimistic insert; fixed in PR #73) applies identically
  here. Guard `refetch` with `!isDemoMode`.
- `src/lib/api-client.ts` — `listCascades/createCascade/getCascade/updateCascade/activateCascade/
  pauseCascade/evaluateCascade/previewCascade/listCascadeMatches/listPendingCascades/
  approveCascadeMatch/rejectCascadeMatch`, each with a demo branch.
- `src/lib/types.ts` / `supabase.ts` — camelCase `Cascade`, `CascadeMatch` + snake_case
  `CascadeRow`, `CascadeMatchRow`.
- `src/lib/utils.ts` — `cascadeDelegationConfig` (colors/labels for auto/approve/observe),
  `cascadeStatusConfig`.
- `src/lib/demo-data.ts` — `demoCascades` (~3 rules across delegation levels, bound to existing
  `demoSegments`/`demoSequences`), `demoCascadeMatches` (mix of enrolled/pending/suppressed).
- `src/components/layout/Sidebar.tsx` — add `{ href: "/cascades", label: "Cascades", icon: Zap,
  hideModes: ["pm"] }` to the workspace nav group (sales-only, like Leads/Campaigns).

---

## 6. BUILD ORDER (dependency-layered units)

Strict layering: schema → models/types → API → workers → UI → tests. Units within a layer number
can parallelize; a later layer waits on its predecessor's acceptance.

**C1 — Schema.** `024_criteria_cascade.sql` (2 tables, FK order, indexes, RLS) + no-RLS mirror in
`init_docker.sql`. *Accept:* applies clean twice (idempotent) on a scratch DB;
`grep -c "CREATE TABLE" init_docker.sql` +2; FK order verified.

**C2 — Models + registry.** `cascade_rule.py`, `cascade_match.py` + register in
`models/__init__.py`. *Accept:* `import app.models` and `from app.main import app` boot with no
mapper error.

**C3 — TS types.** Add unions/interfaces to `packages/types/crm.ts`. *Accept:*
`pnpm exec tsc --noEmit` passes.

**C4 — Router: cascades** (`routers/cascades.py` incl. preview/pending/matches/approve/reject +
backing-campaign provisioning) + register in `main.py`. Depends C2/C3. *Accept:*
`tests/test_cascades.py` green (create provisions a campaign; preview returns a count;
approve creates an enrollment + flips match to `enrolled`; 403/404/422; delegation PATCH).

**C5 — Worker: cascade_evaluator** + beat + include + lead-event hooks in `import_leads` /
`engagement_score`. Depends C2 + base `campaign_enroll` (reuses `_resolve_segment_lead_ids`).
*Accept:* `tests/test_cascade_evaluator.py`: an `active` `auto` rule enrolls only NEW matches
(ON CONFLICT no-dup across two runs), `approve_enroll` leaves `pending` with no enrollment,
`observe` records `suppressed`, `daily_cap` throttles; dispatcher enumerates workspaces.

**C6 — Web data layer** (`types.ts`, `supabase.ts`, `utils.ts`, `api-client.ts` demo branches,
`demo-data.ts`, `useCascades.ts` with the demo-no-refetch guard). Depends C3. *Accept:*
`pnpm exec tsc --noEmit`; demo fixtures typed.

**C7 — Web pages** (`/cascades`, `/cascades/[id]`, approval queue) + Sidebar. Depends C6.
*Accept:* demo build renders the list, the rule builder shows a live preview count, the detail
provenance table renders, the approval queue approve/reject works in demo. `pnpm build` succeeds.

**C8 — E2E** (`e2e/cascade.spec.ts`, role/text locators, demo mode) covering: create a rule (with
preview count) → activate → approval queue shows a pending match → approve → match flips to
enrolled. *Accept:* `pnpm test:e2e` green in demo env.

**C9 — Regression + review.** Full API pytest, web tsc+build, e2e; `ecc:fastapi-reviewer` +
`ecc:react-reviewer` + `ecc:database-reviewer` on the diff. *Accept:* all green; migration `024`
applied by hand to Supabase prod + folded into `init_docker.sql`.

---

## 7. VERIFICATION PLAN (exact commands)

Repo root: `/mnt/external/Projects/crm-agentic`.

```bash
# Schema idempotency (throwaway Postgres — second run a no-op)
psql "$SCRATCH_DB_URL" -f apps/api/migrations/024_criteria_cascade.sql
psql "$SCRATCH_DB_URL" -f apps/api/migrations/024_criteria_cascade.sql
grep -c "CREATE TABLE" apps/api/migrations/init_docker.sql   # +2 vs baseline

# Models import / app boots
cd apps/api && .venv/bin/python -c "import app.models; from app.main import app; print('ok', len(app.routes))"

# API tests
cd apps/api && .venv/bin/python -m pytest tests/test_cascades.py tests/test_cascade_evaluator.py -q

# Celery wiring smoke
cd apps/api && .venv/bin/python -c "from app.workers.celery_app import celery_app; print([t for t in celery_app.tasks if 'cascade' in t])"

# Web type-check + build (demo env)
cd apps/web && pnpm exec tsc --noEmit
cd apps/web && NEXT_PUBLIC_DEMO_MODE=true NEXT_PUBLIC_SUPABASE_URL=https://placeholder.supabase.co NEXT_PUBLIC_SUPABASE_ANON_KEY=placeholder-anon-key NEXT_PUBLIC_FASTAPI_URL=http://localhost:8000 pnpm build

# E2E (demo)
cd apps/web && pnpm test:e2e cascade.spec.ts
```

**Manual demo walk-through (the story for Zach):** demo build → `/cascades` → New Cascade → pick a
criteria segment (live preview: "matches 14 leads now") + a 3-step sequence + delegation
`approve_enroll` → Activate → a lead is imported/scored into range → `/cascades/pending` shows it
as a pending match → Approve → it becomes an active enrollment on the backing campaign → the
existing `/outreach` queue shows its first-step draft. **This is the "identify → cascade →
human-gated engage" loop end to end.**

---

## 8. Reuse ledger (what this increment does NOT rebuild)

| Reused, unchanged | From |
|---|---|
| Criteria evaluation (`{stage,source,min_score,tags}` → SQL) | `campaign_enroll._dynamic_filter_conditions` / `_resolve_segment_lead_ids` |
| Enrollment creation (ON CONFLICT, current_step, next_run_at) | `campaign_enroll._run_enroll` idiom |
| Sending + quiet-hours + stop_on_reply | `sequence_sender` (beat) |
| Send-time HITL (draft → approve/reject) | `routers/outreach` + `/outreach` UI |
| Engagement scoring + stage auto-advance | `engagement_score` |
| Campaign stats rollup | `campaigns.stats` + `engagement_events` |
| Job trigger/poll | `_mark_job_dispatched` + `GET /jobs/{id}` |

New surface is only: 2 tables, 1 router, 1 evaluator worker, 2 lead-event hook calls, 3 pages.
Everything downstream of "a lead is enrolled" is the shipped module.
