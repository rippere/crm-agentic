---
type: object
cluster: comms
universe: live
status: verified
entity: apps/api/app/models/message.py
---

# Message

The ingested email/Slack message (product word "message"; class `Message`, table `messages`).

## Why this shape

It is the raw comms substrate the whole CRM reads from — reply detection, the relationship graph, contact timelines, and deal-signal scoring all query it. Two naming traps drive the columns: `rfc_message_id` is the RFC 5322 header string (not the FK — `message_id` elsewhere means FK to `messages.id`), and `received_at` doubles as sent-time depending on `direction`.

## Shape

- PK `id` (UUID); `external_id` (provider id, NOT NULL); `body_plain` NOT NULL; `subject`, `sender_email`, `received_at` nullable
- FKs: `workspace_id` → workspaces (CASCADE, NOT NULL), `connector_id` → connectors (SET NULL), `contact_id` → contacts (SET NULL)
- Flags: `processed`, `relevant` (LLM judgment), `graph_only` (metadata-only row, body never stored, hidden from message read paths)
- Header capture (migration 022): `to_emails`/`cc_emails` (JSONB), `thread_id`, `rfc_message_id`, `in_reply_to`, `direction`

Citations: `apps/api/app/models/message.py:27`, `:29`, `:32`, `:43`, `:50`

## Connected to

- **owns:** tasks (`Task.message`), clarity_score (1:1, `ClarityScore.message`) — `message.py:58`, `:59`
- **owned-by:** Workspace, Connector, Contact — `message.py:55-57`
- **joins:** Connector via `connector_id` in the messages list (`routers/messages.py:174`)
- **looks-like-but-is-not:** `rfc_message_id` is a header string, not this row's `id` and not an FK; `graph_only` rows are not hidden by `relevant`

## If you change this

- **Hits:** writers — `workers/ingest.py:442` (Gmail), `workers/slack_ingest.py:202` (Slack), `routers/slack_interactions.py:164`; readers — `routers/messages.py:80/129/173`, `routers/deals.py:1941/2103/2176`, `routers/contacts.py` (:348, :1125, :1509, :1567, :1683, :1798, :1876), `services/contact_context.py:63`, dedupe update `routers/contacts.py:1365`
- **Does not hit:** call_summaries, webhook_logs, engagement_events (no code cross-reference)

## Surfaces

| Surface | Role |
|---|---|
| workers/ingest.py, slack_ingest.py; routers/slack_interactions.py | writes |
| routers/messages.py, deals.py, contacts.py; services/contact_context.py | reads |

## See

- Source: `apps/api/app/models/message.py`
