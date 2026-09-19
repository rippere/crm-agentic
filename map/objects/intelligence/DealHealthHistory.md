---
type: object
cluster: intelligence
universe: ghost
status: verified
entity: apps/api/app/models/deal_health_history.py
---

# DealHealthHistory

Intended daily health-score snapshot per deal (class `DealHealthHistory`, table `deal_health_score_history`). **GHOST — read endpoints exist, no writer ever inserts rows.**

## Why this shape

Modeled as an append-only history table (one row per deal per recording, keyed by `deal_id` + `recorded_at`) so a deal's health trend could be charted over time — the live current score lives as `Deal.health_score` on the Deal row, while this table was meant to hold the time series behind it. The write side was never built.

## Shape

- `id` UUID PK; `workspace_id` FK→workspaces CASCADE (not null); `deal_id` FK→deals CASCADE (not null); `score` int not null default 100; `recorded_at` tz server_default now()
- No relationships; no unique constraint on (deal_id, recorded_at)

Citations: `apps/api/app/models/deal_health_history.py:11-26`

## Connected to

- **owns:** nothing.
- **owned-by:** Workspace, Deal.
- **joins:** read-only against Deal in the history endpoint.
- **looks-like-but-is-not:** NOT the source of the live score — that is `Deal.health_score`, written directly by `workers/deal_health_worker.py:104`. This is a separate (empty) time-series store.

## If you change this

- **Hits:** read endpoints only — `routers/deals.py:1672` (`get_deal_health_score_history`) and `routers/ai.py:1992` (trend lookup). Both return `[]` because nothing inserts rows.
- **Does not hit:** the actual health computation (`services/deal_health.py compute_health`) and the worker, which mutate `deal.health_score` and fire ActivityEvent alerts, never this table.

## Surfaces

| Surface | Role |
|---|---|
| routers/deals.py:1649-1677 | reads (history endpoint — always empty) |
| routers/ai.py:1992 | reads (trend — always empty) |
| (none) | writes — NO code path instantiates `DealHealthHistory(...)` |

**Ghost justification:** grep for `DealHealthHistory(` across `app/` returns only the class definition — zero writers. `deal_health_worker.py:104` persists `deal.health_score` and never snapshots here, so the two read endpoints are permanently empty.

**Provenance (why this one matters):** shipped UI-first in Phase 13k (PROGRESS.md #30, merged to master 2026-07-13) — model + both read paths + a live web AreaChart (`apps/web/.../pipeline/[id]/page.tsx:576`). Migration `021_deal_health_score_history.sql` states the intended writer: *"A Celery beat task (or manual call) SHOULD INSERT one row per deal per day."* It was never built, so the chart has rendered its empty state in production for ~2 months (a demo-data stub masks it in demos). Promised-but-unwired, **not** delete-bait.

**To make it live (S effort):** add one `DealHealthHistory(...)` INSERT at the tail of `deal_health_worker.py` (it already loops deals and holds the score + session) + a daily beat entry. Table, indexes, RLS, and both readers already exist. *[a2a review 2026-09-15]*

## See

- Source: `apps/api/app/models/deal_health_history.py`
