---
type: object
cluster: intelligence
universe: ghost
status: verified
entity: apps/api/app/models/metric_template.py
---

# MetricTemplate

A workspace-scoped definition of a custom metric (class `MetricTemplate`, table `metric_templates`). **GHOST — fully unwired, registry-only.**

## Why this shape

A lightweight, all-nullable descriptor (`name`, `description`, `data_type`) — presumably a planned admin feature for defining custom metric types to feed KPI snapshots — but no service, router, or worker was ever built against it.

## Shape

- `id` UUID PK; `workspace_id` FK→workspaces CASCADE (not null); `name`/`description`/`data_type` nullable; `created_at` tz server_default now(). No relationships.

Citations: `apps/api/app/models/metric_template.py:11-19`

## Connected to

- **owns:** nothing.
- **owned-by:** Workspace (by FK only).
- **joins:** none.
- **looks-like-but-is-not:** looks like the schema behind `KpiSnapshot.metric`, but nothing links them; `kpi_snapshots.metric` is a free-form string, not an FK to this table.

## If you change this

- **Hits:** nothing functional — only the model registry `models/__init__.py:10,38` imports/exports it.
- **Does not hit:** any router, service, worker, or query.

## Surfaces

| Surface | Role |
|---|---|
| models/__init__.py | import/export only |
| (none) | no reads, no writes |

**Ghost justification:** grep for `MetricTemplate`/`metric_templates` across `app/` hits only `models/__init__.py` and the model file itself — no CRUD, no endpoint, no worker. A Phase-2 scaffold (commit `672235b`) with **no documented purpose in any spec** — it never grew a feature. Do not implement against it; safe to drop in a dead-code sweep (or leave a one-line "reserved, unused" note). Low priority either way. *[a2a review 2026-09-15]*

## See

- Source: `apps/api/app/models/metric_template.py`
