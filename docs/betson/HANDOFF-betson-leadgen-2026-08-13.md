# NovaCRM — Betson Lead-Gen Module + CRM Task Coverage — HANDOFF

**Date:** 2026-08-13 · **Branch:** `feat/betson-leadgen-module` · **Repo:** `crm-agentic`
**Grounding:** the 2026-08-12 Ben ↔ Mike Betti meeting distillations
([[NovaCRM — Betson Meeting Distillation 2026-08-12]], [[Betson Engagement — Fleet Vision & Continuity 2026-08-12]]).

This document is the single point of context for the NovaCRM work done to cover the newer
Betson-usage CRM tasks. It is written to be picked up cold by any maintainer.

---

## 1. What this session covered

Five NovaCRM (`crm-agentic`) tasks from the 2026-08-12 meeting all now have real coverage — one
built as a full feature, four resolved as grounded decision/scoping docs.

| CRM task (external_id) | Kind | Status | Deliverable |
|---|---|---|---|
| `mtg20260812-crm-leadgen-module` | **Build** | **Built, verified** | Full lead-gen/marketing module (this branch) |
| `mtg20260812-crm-avos-data-interface` | Decide | Documented | `docs/betson/decisions/avos-data-interface.md` |
| `mtg20260812-crm-salesforce-coexist` | Decide | **Decided** | `docs/betson/decisions/salesforce-coexistence.md` |
| `mtg20260812-crm-double-dip` | Structure | Documented | `docs/betson/decisions/double-dip-structure.md` |
| `mtg20260812-crm-demo-mike-then-zach` | Sequence | Planned | `docs/betson/decisions/demo-sequencing.md` |

---

## 2. The lead-gen / marketing module (the flagship)

Delivers Zach's stated core need: **"10,000 leads → a database → a funnel of engagement."**
Modeled on Zoho/HubSpot patterns, **not** Salesforce. Reuses the app's existing conventions
verbatim (workspace scoping, per-endpoint auth, ORM-first + supabase_rest fallback, Celery
trigger/poll, `ActivityEvent` audit) and copies the proven human-in-the-loop (HITL) pattern
already shipped in `workers/followup_sequences.py`.

Full architecture spec: **`docs/betson/BUILD-SPEC-leadgen.md`** (data model, API surface, workers,
UI, build order, verification plan).

### 2.1 Data model — 8 new tables (migration `023_outbound_engagement.sql`)
`leads`, `lead_segments`, `lead_segment_members`, `sequences`, `sequence_steps`, `campaigns`,
`sequence_enrollments`, `engagement_events`. All workspace-scoped with RLS keyed on
`users.supabase_uid = auth.uid()`. `leads` is separate from the curated `contacts` table so a
10k import never pollutes contacts; a lead is *promoted* to a contact/deal on close.

### 2.2 API — 5 routers, ~44 endpoints (`routers/{leads,segments,sequences,campaigns,outreach}.py`)
- **leads** — list/filter, `/funnel` counts, **CSV bulk import up to 10k** (staged file → worker),
  CSV export, stage transitions, **promote → contact/deal**, score recompute.
- **segments** — static + dynamic (stored-filter) audiences, member resolution.
- **sequences** — the drip recipe; ordered step builder (`PUT /steps`).
- **campaigns** — bind segment + sequence + schedule; launch/pause/resume; live stats.
- **outreach** — the **bot→human HITL queue**: a step with `requires_approval` produces a pending
  draft a human approves before send; inbound provider webhook (HMAC-verified) records
  open/click/reply/bounce/unsub.

### 2.3 Workers — 4 Celery tasks + 2 beat schedules
- `import_leads` — chunked 10k import, dedupe via `ON CONFLICT DO NOTHING`.
- `campaign_enroll` — one enrollment per segment lead on launch.
- `engagement_score` — weighted event scoring (open+5/click+15/reply+30/converted+40/bounce−20/
  unsub−30), clamp 0–100, cold/warm/hot label, **auto-advances lead stage** on thresholds.
  Beat: hourly.
- `sequence_sender` — the scheduler/sender; HITL gate before delivery; honors `stop_on_reply` +
  quiet hours. Beat: every 5 min. **SMS is a stub** (logs + event) until a Twilio connector is
  wired; email reuses the Gmail path.

### 2.4 Web UI — 7 pages + full data layer
`/leads` (table ⇄ funnel board, bulk CSV import, detail w/ score gauge + engagement timeline +
promote), `/campaigns` (+ detail w/ stats + conversion chart), `/sequences` (+ step builder),
`/outreach` (approval queue). New hooks (`useLeads/useSegments/useCampaigns/useSequences/
useOutreach`), `apiClient` methods with demo branches, ~40 photo-booth-flavored demo leads, and
4 new sidebar nav items (sales-mode only).

---

## 3. Verification evidence (observed, not asserted)

| Gate | Result |
|---|---|
| API import + boot | `ok` — **173 routes** (was 129; +44) |
| Full API test suite | **733 passed, 1 failed** — see §5 |
| New router tests | 117 passing (leads/segments/sequences/campaigns/outreach) |
| New worker tests | ~84 passing (import/enroll/score/sender) |
| Celery registry | all 7 new tasks registered; both beat entries present |
| Migration `023` | applied twice idempotently to a throwaway Postgres 16 — zero errors |
| Web type-check | `tsc --noEmit` clean (exit 0) |
| Web demo build | `pnpm build` exit 0 — all 7 new routes compiled |
| Adversarial review | fastapi + react + database reviewers; all blocking + high-value findings fixed & re-verified |

### Review findings fixed this session
- **[blocking]** `sequence_enrollments.sequence_id` `NOT NULL` + `ON DELETE SET NULL` contradiction → `CASCADE` (023 + init_docker + model).
- **[blocking ×3]** demo-mode mutation hooks were silent no-ops → now update local state (create-lead / new-campaign / new-sequence work in the demo click-path).
- **[security]** engagement webhook now verifies payload lead/campaign/enrollment belong to the URL workspace (was a cross-tenant write with a shared global secret).
- **[scale]** 10k import now staged to a file, not shipped inline through the Celery broker.
- **[perf]** `/leads/funnel` + `/campaigns/{id}/stats` now `GROUP BY` aggregates; enrollment/event indexes made workspace-first.

---

## 4. Deploy steps (REQUIRED before this is live)

1. **Apply the migration by hand to Supabase prod** — there is no migration runner on the API
   (a known pre-existing gap; see the open CRM task about `apps/api` migration runner). Run
   `apps/api/migrations/023_outbound_engagement.sql` against prod. The Docker path already has the
   tables via the `init_docker.sql` mirror.
2. Deploy API + web as usual (Railway). No new env vars are required for the demo; a real
   `ENGAGEMENT_WEBHOOK_SECRET` and a Twilio/SMS connector are needed only for live SMS + inbound
   provider webhooks (email works via the existing Gmail path).

---

## 5. Known issues / deliberate follow-ups (NOT blockers for the demo)

- **1 pre-existing test failure**, unrelated to this work: `test_deals.py::test_revenue_cohort_
  groups_by_contact_acquisition_month` is a date-dependent time-bomb (asserts a 2026-05 cohort now
  outside the rolling 3-month window as of 2026-08). It fails on `main` independent of this branch.
  Left untouched (separate deals bug; fixing it is out of scope for this feature).
- **SMS sending is a stub** — logs + records an event but does not deliver until a Twilio connector
  is added. Email is real (Gmail path).
- **3 perf nits left as follow-ups** (fine at September demo scale): `list_pending_outreach` N+1
  on a large simultaneous approval batch; keyset vs OFFSET pagination on `list_leads`. Documented
  in the review; not fixed to keep the diff focused.
- **Migration runner** — applying `023` is manual (see §4). Consider the existing open CRM task to
  add a runner so future migrations auto-apply.

---

## 6. The September demo click-path (the acceptance bar)

In the demo build (`NEXT_PUBLIC_DEMO_MODE=true`), all of this is clickable end to end:
**import a CSV of leads → they land in the table + funnel board → create a segment → build a
3-step sequence → create + launch a campaign over the segment → `/outreach` shows the first-step
draft pending → approve it → the lead advances stage and its engagement score moves.**

This is the exact story to show Zach. Gating + week-by-week sequencing (Mike first, never forward
to Zach until Ben says "ready") is in `docs/betson/decisions/demo-sequencing.md`.

---

## 7. Where everything is

- Spec: `docs/betson/BUILD-SPEC-leadgen.md`
- Decisions: `docs/betson/decisions/{avos-data-interface,salesforce-coexistence,double-dip-structure,demo-sequencing}.md`
- This handoff: `docs/betson/HANDOFF-betson-leadgen-2026-08-13.md`
- Code: `apps/api/{migrations/023_outbound_engagement.sql, app/models, app/routers, app/workers}`,
  `apps/web/src/{app/(app)/{leads,campaigns,sequences,outreach}, hooks, lib}`,
  `packages/types/crm.ts`
