---
type: object
cluster: crm-core
universe: live
status: verified
entity: apps/api/app/models/deal.py
---

# Deal

A pipeline opportunity (UI "Deals"); class `Deal`, table `deals`.

## Why this shape

It is the pipeline unit — `stage`, `value`, `ml_win_probability` and `health_score` are first-class columns so funnel/forecast/health queries filter and sort directly; `stage_changed_at` is tracked separately from `updated_at` to measure stage velocity.

## Shape

- PK `id`; `workspace_id` FK → workspaces (CASCADE); `contact_id` FK → contacts (SET NULL, nullable); `stage` default "discovery"; `value` Numeric; `ml_win_probability` / `health_score` Integer; `competitors`/`mentions` JSONB; `stage_changed_at`. Also denormalized `contact_name`/`company` strings (`:17`,`:18`).

Citations: `apps/api/app/models/deal.py:15`, `:19`, `:21`, `:22`, `:26`, `:32`

## Connected to

- **owns:** DealNote (deal_id), Task (deal_id), DealHealthHistory — point here.
- **owned-by:** Workspace via `workspace_id`; loosely linked to Contact via `contact_id` (SET NULL, so orphanable).
- **joins:** none.
- **looks-like-but-is-not:** `deal_health_history.py` (the time-series of health scores) — the audit trail, not the deal itself.

## If you change this

- **Hits:** routers/deals.py, routers/mcp_server.py, routers/search.py, routers/ai.py; services/contact_context.py; workers/pipeline.py, workers/deal_health_worker.py, workers/followup_sequences.py.
- **Does not hit:** ClarityScore / kpi_snapshot rollups (recomputed downstream, not direct writers).

## Surfaces

| Surface | Role |
|---|---|
| routers/deals.py | reads / writes |
| routers/mcp_server.py, search.py, ai.py | reads |
| services/contact_context.py | reads |
| workers/pipeline.py, deal_health_worker.py | writes (stage/health) |
| workers/followup_sequences.py | reads |

## See

- Source: `apps/api/app/models/deal.py`
