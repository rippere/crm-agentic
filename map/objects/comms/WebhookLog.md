---
type: object
cluster: comms
universe: live
status: verified
entity: apps/api/app/models/webhook_log.py
---

# WebhookLog

An audit row for one inbound webhook delivery (class `WebhookLog`, table `webhook_logs`).

## Why this shape

A lightweight append-only receipt for provider push notifications (Slack events, Gmail push) so the team can see what arrived and whether it was processed. `workspace_id` is nullable because a webhook can land before the workspace is resolved; `status`/`job_id`/`error_detail` track the async handoff; `payload_summary` keeps a trimmed string, not the full body.

## Shape

- PK `id` (UUID); `workspace_id` → workspaces (CASCADE, **nullable**); `source` NOT NULL; `event_type` NOT NULL
- `status` (default "received"); `payload_summary`, `job_id`, `error_detail` nullable; `created_at` server_default now

Citations: `apps/api/app/models/webhook_log.py:12`, `:16-24`

## Connected to

- **owns:** nothing
- **owned-by:** Workspace (nullable FK column only; no ORM relationship declared)
- **joins:** none
- **looks-like-but-is-not:** not the message payload store — only a summary/receipt; the Message row is the real content

## If you change this

- **Hits:** writers — `routers/slack.py:244/258/308` (Slack event webhooks), `routers/gmail.py:408/422` (Gmail push); reader — `routers/webhook_logs.py:37` (list, filterable by source :44 / status :46)
- **Does not hit:** messages, connectors, call_summaries, engagement_events; no worker touches it

## Surfaces

| Surface | Role |
|---|---|
| routers/slack.py, gmail.py | writes |
| routers/webhook_logs.py | reads |

## See

- Source: `apps/api/app/models/webhook_log.py`
