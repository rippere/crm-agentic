---
type: object
cluster: lead-engine
universe: live
status: verified
entity: apps/api/app/models/discovery_run.py
---

# DiscoveryRun

Run-bookkeeping for one long-running market-discovery job (table `discovery_runs`); the Autonomous Lead Engine Increment 1. **Newest noun on the active `feat/lead-engine-discovery` branch.**

## Why this shape

Tracks only the JOB, not its output — discovered venues land in the existing `leads` table (source='discovery'), so this table is pure lifecycle state. `status` walks queued→running→succeeded/partial/failed. Docstring pins shape to migration `024_lead_engine_discovery.sql`. Row is committed status='queued' BEFORE the Celery task dispatches (closes dispatch-before-commit race), then driven by the worker. `params`/`rubric`/`stats` JSONB snapshot inputs and progress; `job_id` holds the Celery task id.

## Shape

- `id` uuid PK; `workspace_id` FK→workspaces CASCADE (not null)
- `locality` Text not null; `provider` Text nullable
- `status` not null default "queued"; `params`/`rubric`/`stats` JSONB default {}
- `job_id` Text (celery id); `error` Text; `started_at`/`completed_at` nullable; created/updated

Citations: `apps/api/app/models/discovery_run.py:11`, `:32`, `:34`, `:35-38`

## Connected to

- **owns:** nothing by FK — produces Lead rows as a side-effect (source='discovery'), not an ownership edge
- **owned-by:** Workspace (CASCADE)
- **joins:** none (no FK to Lead — decoupled by design; docstring model:19-21)
- **looks-like-but-is-not:** a lead-import job — import_leads has no run table (polls generic GET /jobs); DiscoveryRun is first-class because runs are long and rubric-scored.

## If you change this

- **Hits:** `routers/discovery.py:35` (DiscoveryRunResponse, POST + list/get-run), `services/discovery.py:90` (create + commit-before-dispatch), `workers/discovery.py:177,191,306` (status transitions + stats)
- **Does not hit:** the `leads` table schema (only appends rows), LeadSegment/Campaign

## Surfaces

| Surface | Role |
|---|---|
| routers/discovery.py | reads / writes (dispatch, poll) |
| services/discovery.py | writes (create queued row) |
| workers/discovery.py | writes (run lifecycle + stats) |

## See

- Source: `apps/api/app/models/discovery_run.py`
