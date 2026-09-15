---
type: object
cluster: comms
universe: live
status: verified
entity: apps/api/app/models/engagement_event.py
---

# EngagementEvent

An append-only engagement fact (open/click/reply/send) feeding lead scoring (class `EngagementEvent`, table `engagement_events`).

## Why this shape

An append-only fact table (per its own docstring) that the engagement scoring worker aggregates into a lead score, and the sequence sender reads to gate/advance steps. `weight` lets each event type contribute differently; `metadata_` maps to SQL column `metadata` (Python attr renamed to dodge SQLAlchemy's reserved name). It fans across the outreach graph — lead, campaign, enrollment, step.

## Shape

- PK `id` (UUID); `type` NOT NULL; `channel` nullable; `weight` Integer (default 0); `metadata_` → column `metadata` JSONB (default dict); `occurred_at` + `created_at` server_default now
- FKs: `workspace_id` → workspaces (CASCADE, NOT NULL), `lead_id` → leads (CASCADE, NOT NULL), `campaign_id` → campaigns (SET NULL), `enrollment_id` → sequence_enrollments (SET NULL), `step_id` → sequence_steps (SET NULL)

Citations: `apps/api/app/models/engagement_event.py:14`, `:17-31`, `:32-35`

## Connected to

- **owns:** nothing (pure fact/leaf)
- **owned-by:** Workspace, Lead, Campaign, SequenceEnrollment, SequenceStep (FK columns; no ORM relationships declared)
- **joins:** aggregated by `type` per campaign (`routers/campaigns.py:472`)
- **looks-like-but-is-not:** not a Message — no body/subject; a scoring signal, not comms content. `metadata_` attr ≠ column name `metadata`. Also not ActivityEvent (the human-readable feed).

## If you change this

- **Hits:** writers — `routers/outreach.py:401/460/543`, `routers/leads.py:467`, `workers/sequence_sender.py:362/388`; readers — `workers/engagement_score.py:226` (scoring aggregation), `workers/sequence_sender.py:301` (dedupe/gate), `routers/campaigns.py:472` (per-campaign counts)
- **Does not hit:** messages, connectors, call_summaries, webhook_logs

## Surfaces

| Surface | Role |
|---|---|
| routers/outreach.py, leads.py; workers/sequence_sender.py | writes |
| workers/engagement_score.py, sequence_sender.py; routers/campaigns.py | reads |

## See

- Source: `apps/api/app/models/engagement_event.py`
