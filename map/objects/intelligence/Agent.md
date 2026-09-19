---
type: object
cluster: intelligence
universe: live
status: verified
entity: apps/api/app/models/agent.py
---

# Agent

The AI-agent record — one row per configured automation agent in a workspace (class `Agent`, table `agents`).

## Why this shape

Denormalized dashboard row: alongside config (`name`, `type`, `model`, `description`) it caches display/runtime state (`status`, `accuracy`, `tasks_today`, `last_run`) and JSONB `workflow`/`metrics` bags, so the agents dashboard renders from one row without joins. String `last_run` default "Never" and JSONB lists are UI-shaped rather than normalized.

## Shape

- `id` UUID PK; `workspace_id` FK→workspaces CASCADE (not null); `name`/`type`/`description`/`model` nullable; `status` not null default "idle"; `accuracy` Numeric not null default 0; `tasks_today` int not null default 0; `last_run` not null default "Never"; `workflow` JSONB list; `metrics` JSONB list; created/updated tz
- relationship `workspace` back_populates `Workspace.agents`

Citations: `apps/api/app/models/agent.py:11-30`

## Connected to

- **owns:** nothing directly (agents dispatch jobs via `_mark_job_dispatched`, not FK-owned rows).
- **owned-by:** Workspace (back_populates `agents`).
- **joins:** Workspace.
- **looks-like-but-is-not:** the DB *record* of an agent, not the runtime — actual execution lives in Celery workers (`workers/pm_agent.py`, etc.); this row is config + cached status only.

## If you change this

- **Hits:** `routers/agents.py` (list :137, run :146, patch :219, run-stats :287); default-agent seeding in `routers/auth.py:25,148`, `routers/workspaces.py:84-98`, `dependencies.py:52-88`; `workers/pm_agent.py:41-55` (resets stuck `Agent.status == "processing"`). Many routers import `_mark_job_dispatched` from `routers/agents.py`.
- **Does not hit:** clarity, KPI, deal-health, metric-template tables.

## Surfaces

| Surface | Role |
|---|---|
| routers/agents.py | reads + writes (list/run/patch/stats) |
| routers/auth.py, workspaces.py, dependencies.py | writes (seed default agents) |
| workers/pm_agent.py | reads + writes (stuck-agent watchdog) |

## See

- Source: `apps/api/app/models/agent.py`
