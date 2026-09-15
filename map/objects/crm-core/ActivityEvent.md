---
type: object
cluster: crm-core
universe: live
status: verified
entity: apps/api/app/models/activity_event.py
---

# ActivityEvent

The system audit/activity-feed row (UI "Activity" feed); class `ActivityEvent`, table `activity_events`.

## Why this shape

It is a write-mostly append-only audit log — loose, mostly-nullable string columns (`type`, `agent_name`, `description`, `meta`, `severity`) with NO entity FKs; `meta` is a free-form string that callers query with LIKE (e.g. embedding a `hitl_id` or `agent_id`), so almost every worker can drop a row without a schema change.

## Shape

- PK `id`; `workspace_id` FK → workspaces (CASCADE) — the only FK; `type`, `agent_name`, `description`, `meta` all nullable String; `severity` default "info"; `created_at` only.

Citations: `apps/api/app/models/activity_event.py:15`, `:16`, `:17`, `:19`, `:20`, `:21`

## Connected to

- **owns:** nothing.
- **owned-by:** Workspace via `workspace_id` only — no contact/deal/task linkage (associations live encoded as strings inside `meta`).
- **joins:** none.
- **looks-like-but-is-not:** `EngagementEvent` (engagement_event.py) / `webhook_log.py` — per-contact engagement signals and raw webhook records, not the human-readable activity feed.

## If you change this

- **Hits:** routers/events.py (feed + SSE stream + create), routers/slack_interactions.py, routers/outreach.py, routers/campaigns.py; services/discovery.py; workers pipeline.py, pm_agent.py, slack_ingest.py, engagement_score.py, deal_health_worker.py, discovery.py, import_leads.py, campaign_enroll.py, sequence_sender.py.
- **Does not hit:** EngagementEvent / webhook_log ingestion paths.

## Surfaces

| Surface | Role |
|---|---|
| routers/events.py | reads / writes (feed + SSE) |
| routers/slack_interactions.py, outreach.py, campaigns.py | writes (audit) |
| services/discovery.py | writes |
| workers/* (pipeline, pm_agent, slack_ingest, engagement_score, deal_health_worker, discovery, import_leads, campaign_enroll, sequence_sender) | writes (audit rows) |

## See

- Source: `apps/api/app/models/activity_event.py`
