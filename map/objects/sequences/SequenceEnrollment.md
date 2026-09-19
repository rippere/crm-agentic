---
type: object
cluster: sequences
universe: live
status: verified
entity: apps/api/app/models/sequence_enrollment.py
---

# SequenceEnrollment

The live run-state of one lead moving through one sequence in a campaign (class `SequenceEnrollment`, table `sequence_enrollments`).

## Why this shape

Enrollment is its own row because it is the mutable cursor the sender advances: `current_step` (next step), `status` (active/waiting/completed/stopped), `next_run_at` (scheduler pickup), `last_sent_at` (detect fresh approval). Keeping this off Sequence/Step lets the immutable template fan out to many leads with independent progress. It carries FKs to all four parents so the sender can join to campaign status and load the right step without extra lookups.

## Shape

- `id` uuid PK; `workspace_id` FK→workspaces CASCADE (not null)
- `campaign_id` FK→campaigns CASCADE (not null); `sequence_id` FK→sequences CASCADE (not null); `lead_id` FK→leads CASCADE (not null)
- `current_step` int not null default 0; `status` not null default "active"
- `next_run_at`/`last_sent_at` timestamptz nullable; created/updated
- Enroller upserts `ON CONFLICT (campaign_id, lead_id) DO NOTHING` (`workers/campaign_enroll.py:172`). The backing unique index **is present** in `migrations/023_outbound_engagement.sql:194` + `init_docker.sql:380`, just not mirrored as `__table_args__` on this model — parity gap only, **no runtime risk** (schema is provisioned from migrations, house style). Optional (S): add a `UniqueConstraint` for readability. *[a2a review 2026-09-15]*

Citations: `apps/api/app/models/sequence_enrollment.py:11-36`

## Connected to

- **owns:** EngagementEvent rows keyed by `enrollment_id` (`workers/sequence_sender.py:298-308,362,388`)
- **owned-by:** Campaign, Sequence, Lead, Workspace (four cascade FKs)
- **joins:** Campaign (sender joins on status='active', `sequence_sender.py:235-240`); SequenceStep (matched by current_step == step_order)
- **looks-like-but-is-not:** not the send record itself (EngagementEvent is); not the template (Sequence/SequenceStep); the (campaign_id, lead_id) uniqueness lives in the DB, not the model

## If you change this

- **Hits:** `workers/sequence_sender.py` (`_due_enrollments` :229-243, tick loop :331-416 mutating status/current_step/next_run_at/last_sent_at); `workers/campaign_enroll.py:170-176` (bulk pg_insert on_conflict); `routers/outreach.py` (`_load_enrollment` :175-181, pending-drafts scan status=='waiting' :260-267, draft/approve routes :307+)
- **Does not hit:** `routers/sequences.py` (template CRUD only); `workers/followup_sequences.py`; `services/outreach_stats.py`

## Surfaces

| Surface | Role |
|---|---|
| workers/campaign_enroll.py | writes (bulk enroll) |
| workers/sequence_sender.py | reads / writes (advances the cursor each tick) |
| routers/outreach.py | reads / writes (HITL draft/approve, pending feed) |

## See

- Source: `apps/api/app/models/sequence_enrollment.py`
