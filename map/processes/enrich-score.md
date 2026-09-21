---
type: process
status: verified
consumes: [Contact, Message, Lead, EngagementEvent, Deal]
produces: [Contact.ml_score, Contact enrichment, Lead.score, Lead.stage, Deal.health_score, ActivityEvent]
---

# enrich-score

Contacts, leads, and deals are scored and enriched by a family of workers, some heuristic and some LLM-backed, writing scores back onto the rows.

## Input → Movement → Output

Four independent workers each read one entity plus its history and write a score or enrichment. `enrich_contact` runs a Hunter.io provider waterfall then Claude Haiku over the last 10 message bodies to fill missing company/role/tags. `score_contact` computes a heuristic 0-100 `ml_score`. `engagement_score` weights a lead's EngagementEvents over a 90-day window and auto-advances lead.stage. `deal_health_worker` decays each active deal's health from stage-staleness + engagement gap and fires a `deal_alert` on critical deals.

## Why this shape

The scorers are split into separate Celery tasks because they have different triggers and cadences — enrichment/lead-score are API-invoked per row, engagement + deal-health run on beat across all workspaces. LLM enrichment reads message bodies with `graph_only.is_(False)` filtered *in SQL before the LIMIT* (`workers/enrich_contact.py:121-133`), else ten recent metadata-only rows would starve enrichment of every real body. The 0-100 for deal health and engagement is pure Python (`services/deal_health.py:27`, `workers/engagement_score.py:102`) so it is testable without LLM determinism.

## Steps

1. enrich_contact: provider waterfall then Claude Haiku, only-null-fields update — `workers/enrich_contact.py:110-169`; providers `services/enrichment.py`.
2. score_contact: heuristic `_compute_score` (base 50 ± status/deals/revenue), write ml_score + ActivityEvent — `workers/score_contact.py:40-119`.
3. engagement_score: window-weighted event sum (open+5…converted+40), write score/score_detail/last_engaged_at, forward-only stage advance — `workers/engagement_score.py:102-274` (`_next_stage` :170).
4. deal_health_worker: newest non-graph_only message + `compute_health`, persist health_score, fire deal_alert ≤25 — `workers/deal_health_worker.py:58-126`; `services/deal_health.py:27`.

## Trigger

- `enrich_contact` — API-invoked, `routers/contacts.py:816`.
- `score_lead` (score_contact) — API-invoked, `routers/contacts.py:580`.
- `engagement_score.score_leads_all` — beat "hourly-lead-scoring" `crontab(minute=0)` (`workers/celery_app.py:59-64`); also enqueued after a send (`sequence_sender.py:421-423`) and from the engagement webhook.
- `deal_health_worker.compute_deal_health_all` — beat "nightly-deal-health" `crontab(hour=2, minute=15)` (`celery_app.py:35-41`). (pipeline win-probability runs 02:00.)

## If you change this

- **Hits:** `services/enrichment.py`, `clarity.py`, `sentiment.py`, `embedding.py`, `deal_health.py`; Contact/Lead/Deal/EngagementEvent/ActivityEvent models; the beat schedule in `celery_app.py`; engagement scoring is coupled to outreach (sends emit the events it weights).
- **Does not hit:** auth, transcribe. Note: **DealHealthHistory is NOT written here** — the worker mutates `Deal.health_score` directly; that table stays a ghost.

## Surfaces

| Surface | Role |
|---|---|
| Celery beat (hourly / nightly) | triggers engagement + deal-health fan-out |
| Contacts/Leads API endpoints | trigger enrich + lead-score on demand |
| Dashboard / deal_alert feed | consume the scores + alerts |

## See

- Objects: [[Contact]], [[Deal]], [[Lead]], [[EngagementEvent]], [[ClarityScore]]
- Source: `apps/api/app/workers/engagement_score.py`, `apps/api/app/workers/deal_health_worker.py`
