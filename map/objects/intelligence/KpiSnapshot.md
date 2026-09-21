---
type: object
cluster: intelligence
universe: live
status: verified
entity: apps/api/app/models/kpi_snapshot.py
---

# KpiSnapshot

A dated workspace metric value (class `KpiSnapshot`, table `kpi_snapshots`).

## Why this shape

A generic long/narrow time-series row — (`date`, `domain`, `metric`, `value`) plus a `meta` JSONB bag — rather than a wide per-metric table, so arbitrary KPIs across domains can be recorded and upserted without schema changes. Upsert keyed on (workspace_id, date, metric); `Numeric` value preserves exact decimals.

## Shape

- `id` UUID PK; `workspace_id` FK→workspaces CASCADE (not null); `date` Date not null; `domain` not null; `metric` not null; `value` Numeric not null; `meta` JSONB not null default {}; `created_at` + `updated_at` (onupdate now()) tz
- relationship `workspace` (no back_populates)

Citations: `apps/api/app/models/kpi_snapshot.py:12-25`

## Connected to

- **owns:** nothing.
- **owned-by:** Workspace.
- **joins:** none (standalone time series).
- **looks-like-but-is-not:** not per-deal/per-message; a workspace-level aggregate metric store. Distinct from clarity/health scores. See MetricTemplate — it looks related but nothing links them.

## If you change this

- **Hits:** `routers/kpi.py` end to end — `KpiSnapshotIn/Batch/Response` (:17-42), `upsert_kpi_snapshots` POST (:55, upsert :74-82), `list_kpi_snapshots` GET (:101-123). Also exposed via the `novacrm` MCP `kpi_snapshots` tool.
- **Does not hit:** clarity, deal health, agents, metric templates.

## Surfaces

| Surface | Role |
|---|---|
| routers/kpi.py | reads + writes (batch upsert + filtered list) |

## See

- Source: `apps/api/app/models/kpi_snapshot.py`
