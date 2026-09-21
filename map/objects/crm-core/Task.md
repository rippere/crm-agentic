---
type: object
cluster: crm-core
universe: live
status: verified
entity: apps/api/app/models/task.py
---

# Task

An actionable to-do (UI "Tasks"); class `Task`, table `tasks`.

## Why this shape

It is the polymorphic work item — nullable FKs to message/contact/deal/project let one task attach to whichever entity spawned it, and `external_id` makes vault→NovaCRM sync idempotent (the `/tasks/by-external` upsert path).

## Shape

- PK `id`; `workspace_id` FK → workspaces (CASCADE); nullable FKs `message_id`→messages, `contact_id`→contacts, `deal_id`→deals, `project_id`→projects (all SET NULL); `assignee_id`→users; `external_id` for sync; `status` default "open"; `due_date` Date.

Citations: `apps/api/app/models/task.py:15`, `:17`, `:18`, `:19`, `:20`, `:21`, `:26`

## Connected to

- **owns:** nothing (leaf).
- **owned-by:** Workspace; and optionally Message / Contact / Deal / Project / User via the five nullable FKs.
- **joins:** none — it is itself the junction between a message/contact/deal/project and an assignee.
- **looks-like-but-is-not:** `Commitment` (commitment.py) — the accountability/kept-broken record harvested from session logs, not a user-assignable to-do.

## If you change this

- **Hits:** routers/tasks.py, routers/deals.py, routers/contacts.py, routers/search.py, routers/ai.py; workers/ingest.py (creates tasks from inbound mail), workers/pm_agent.py (counts per project).
- **Does not hit:** Commitment path (commitments.py) — sibling, not this table.

## Surfaces

| Surface | Role |
|---|---|
| routers/tasks.py | reads / writes |
| routers/deals.py, contacts.py, search.py, ai.py | reads |
| workers/ingest.py | writes (creates/deletes by message_id) |
| workers/pm_agent.py | reads (task count per project) |

## See

- Source: `apps/api/app/models/task.py`
