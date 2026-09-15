---
type: object
cluster: crm-core
universe: live
status: verified
entity: apps/api/app/models/project.py
---

# Project

A named workstream grouping tasks (UI "Projects"); class `Project`, table `projects`.

## Why this shape

It is a thin grouping node — just `name`/`status`/optional `contact_id` plus `external_id` for idempotent vault→NovaCRM sync; the real content is the Tasks that FK into it, so Project stays deliberately minimal.

## Shape

- PK `id`; `workspace_id` FK → workspaces (CASCADE); `external_id` for sync; `name` NOT NULL; `status` default "active"; `contact_id` FK → contacts (SET NULL, nullable).

Citations: `apps/api/app/models/project.py:15`, `:17`, `:18`, `:20`, `:21`

## Connected to

- **owns:** Task (project_id → projects) — children.
- **owned-by:** Workspace via `workspace_id`; optionally Contact via `contact_id`.
- **joins:** none.
- **looks-like-but-is-not:** `Campaign` (campaign.py) / `Sequence` — outreach groupings, not task workstreams.

## If you change this

- **Hits:** routers/projects.py, workers/pm_agent.py (iterates projects, counts tasks, emits activity).
- **Does not hit:** Campaign/Sequence enrollment logic — unrelated grouping.

## Surfaces

| Surface | Role |
|---|---|
| routers/projects.py | reads / writes (incl. by-external upsert) |
| workers/pm_agent.py | reads (per-project task tally) |

## See

- Source: `apps/api/app/models/project.py`
