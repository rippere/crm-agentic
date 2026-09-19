---
type: object
cluster: comms
universe: live
status: verified
entity: apps/api/app/models/connector.py
---

# Connector

A workspace's OAuth link to an external comms service — Gmail or Slack (class `Connector`, table `connectors`).

## Why this shape

It is the credential vault and sync-state record for outside channels: `encrypted_token`/`refresh_token`/`token_expiry` hold the OAuth secret (encrypted at rest, NOT NULL), and `service` discriminates gmail vs slack. `message_count`/`task_count`/`last_sync` are denormalized counters read by the PM health worker. It parents ingested Messages via `connector_id`.

## Shape

- PK `id` (UUID); `service` (NOT NULL, "gmail"|"slack"); `encrypted_token` NOT NULL; `refresh_token`, `token_expiry` nullable
- `external_email` (account address / Slack team_id); counters `message_count`, `task_count` (default 0); `last_sync` nullable
- FK: `workspace_id` → workspaces (CASCADE, NOT NULL). No `last_error` column (workers log an ActivityEvent instead — `workers/slack_ingest.py:48`)

Citations: `apps/api/app/models/connector.py:12`, `:16-23`, `:15`

## Connected to

- **owns:** messages (`Connector.messages`) — `connector.py:28`
- **owned-by:** Workspace (`Connector.workspace`) — `connector.py:27`
- **joins:** left-joined to Message for service label (`routers/messages.py:174`)
- **looks-like-but-is-not:** `external_email` is repurposed as Slack `team_id` for slack rows (`routers/slack.py:237`), not always an email

## If you change this

- **Hits:** OAuth writers/readers — `routers/gmail.py` (create :190; lookups :181/223/254/280/328/399/494), `routers/slack.py:144` (create; lookups :135/173/235); client wrappers hold the token — `services/gmail_client.py:50`, `services/slack_client.py:43`; sync workers — `workers/ingest.py:279`, `slack_ingest.py:81`, `sequence_sender.py:203` (gmail send), `followup_sequences.py:81/86`, `pm_agent.py:73` (stale-sync >48h); also `routers/slack_interactions.py:97`, `routers/contacts.py:1039`
- **Does not hit:** call_summaries, webhook_logs, engagement_events

## Surfaces

| Surface | Role |
|---|---|
| routers/gmail.py, slack.py | writes (OAuth token store) |
| services/gmail_client.py, slack_client.py | reads (token use) |
| workers/ingest.py, slack_ingest.py, sequence_sender.py, followup_sequences.py, pm_agent.py | reads (sync/send/health) |

## See

- Source: `apps/api/app/models/connector.py`
