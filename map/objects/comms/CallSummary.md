---
type: object
cluster: comms
universe: live
status: verified
entity: apps/api/app/models/call_summary.py
---

# CallSummary

A transcribed/summarized phone call (product word "call summary"; class `CallSummary`, table `call_summaries`).

## Why this shape

It holds the output of the Whisper transcription pipeline: a row is created at upload with empty transcript/summary, then filled asynchronously by the transcribe worker. `transcript`/`summary` default to "" (not null) so the row is valid before the worker runs; `action_items` is JSONB for LLM-extracted to-dos surfaced on the contact timeline.

## Shape

- PK `id` (UUID); `title` (default "Untitled Call"); `duration_seconds` nullable
- `transcript` Text (default ""), `summary` Text (default ""), `action_items` JSONB (default list)
- `participants` (String), `call_date` (server_default now), `model_used` (default "whisper-base")
- FKs: `workspace_id` → workspaces (CASCADE, NOT NULL), `contact_id` → contacts (SET NULL)

Citations: `apps/api/app/models/call_summary.py:12`, `:15`, `:16`, `:19-24`

## Connected to

- **owns:** nothing (no child relationships defined)
- **owned-by:** Workspace, Contact (FK columns; no ORM back-populates declared)
- **joins:** queried by `contact_id` in contact context
- **looks-like-but-is-not:** not a Message — separate voice channel; no connector link

## If you change this

- **Hits:** writer — `routers/calls.py:83` (create on upload), `workers/transcribe.py:99` (fills transcript/summary); readers — `routers/calls.py:116/149/184`, `routers/contacts.py:1144/1700`, `services/contact_context.py:75`
- **Does not hit:** connectors, webhook_logs, engagement_events, messages

## Surfaces

| Surface | Role |
|---|---|
| routers/calls.py (upload), workers/transcribe.py | writes |
| routers/calls.py, contacts.py; services/contact_context.py | reads |

## See

- Source: `apps/api/app/models/call_summary.py`
