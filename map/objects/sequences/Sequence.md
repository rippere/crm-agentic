---
type: object
cluster: sequences
universe: live
status: verified
entity: apps/api/app/models/sequence.py
---

# Sequence

The outreach playbook template (class `Sequence`, table `sequences`) — a named, multi-step cadence a campaign runs against leads.

## Why this shape

A sequence is the reusable *template* (name, channel, status, settings) while its steps live in a separate `sequence_steps` table — so a campaign references one definition and many leads enroll against the same steps without duplicating step content. `step_count` is a denormalized counter kept in sync by the router. `status` gates whether it can run (draft → active → archived); delete is soft (`status='archived'`).

## Shape

- `id` uuid PK; `workspace_id` FK→workspaces CASCADE (not null)
- `name` not null; `description` Text nullable
- `channel` not null default "email"; `status` not null default "draft"
- `step_count` int not null default 0 (denormalized); `settings` JSONB not null default {}
- `created_at`/`updated_at` timestamptz; `steps` relationship → SequenceStep (viewonly, ordered by step_order)

Citations: `apps/api/app/models/sequence.py:11-38`

## Connected to

- **owns:** SequenceStep (1→N, viewonly, `sequence.py:32-38`); SequenceEnrollment references it via `sequence_id`
- **owned-by:** Workspace (CASCADE)
- **joins:** Campaign points at a sequence via `campaign.sequence_id` (`workers/campaign_enroll.py:161`)
- **looks-like-but-is-not:** not the runtime state of a send — that is SequenceEnrollment; not the message content — that is SequenceStep.body_template

## If you change this

- **Hits:** `routers/sequences.py` (CRUD + SequenceResponse/DetailResponse, e.g. :153, :175, :262, :395, :460); `workers/sequence_sender.py:248-256` (`_load_sequence`); `workers/campaign_enroll.py:161`
- **Does not hit:** `workers/followup_sequences.py` (misnamed — it is stale-deal HITL over Deal/Contact/Message, touches no sequence model); `services/outreach_stats.py` (no sequence refs)

## Surfaces

| Surface | Role |
|---|---|
| routers/sequences.py | reads / writes (CRUD, soft-archive, step_count) |
| workers/sequence_sender.py | reads (active sequence per enrollment) |
| workers/campaign_enroll.py | reads (via campaign.sequence_id) |

## See

- Source: `apps/api/app/models/sequence.py`
