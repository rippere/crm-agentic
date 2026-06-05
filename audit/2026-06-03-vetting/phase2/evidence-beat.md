# Phase 2 — Target D1/D2: Nightly beat jobs crash + deal-health cascade

**Date:** 2026-06-03
**Auditor:** automated security validation (read-only source review + local reproduction)
**Verdict:** PROVEN (with scope nuances — see §6)
**Source of truth:** `/tmp/crm-signup-fix/apps/api`
**Interpreter:** `/mnt/external/Projects/crm-agentic/apps/api/.venv/bin/python` (CPython 3.11, celery 5.4.0)

---

## 1. The beat schedule (celery_app.py)

`/tmp/crm-signup-fix/apps/api/app/workers/celery_app.py` lines 27-48:

```python
beat_schedule={
    "nightly-pipeline-optimize": {
        "task": "app.workers.pipeline.optimize_pipeline",
        "schedule": crontab(hour=2, minute=0),
        "args": [],                                      # <-- empty
    },
    "nightly-deal-health": {
        "task": "app.workers.deal_health_worker.compute_deal_health",
        "schedule": crontab(hour=2, minute=15),
        "args": [],                                      # <-- empty
    },
    "daily-hitl-followup": {
        "task": "app.workers.followup_sequences.check_stale_deals_hitl",
        "schedule": crontab(hour=9, minute=0),
        "args": [],
    },
    "pm-health-check": {
        "task": "app.workers.pm_agent.run_health_check",
        "schedule": crontab(minute="*/30"),
        "args": [],
    },
}
```

## 2. Task signatures (the user-function bodies the worker invokes via .run())

- `pipeline.py:103-106` — `@celery_app.task(name="...optimize_pipeline", bind=True)` →
  `def optimize_pipeline(self, workspace_id: str)`. **Requires `workspace_id`.**
- `deal_health_worker.py:111-114` — `@celery_app.task(name="...compute_deal_health", bind=True)` →
  `def compute_deal_health(self, workspace_id: str)`. **Requires `workspace_id`.**
- `followup_sequences.py:193-196` — `@celery_app.task(name="...check_stale_deals_hitl", bind=True)` →
  `def check_stale_deals_hitl(self)`. **Takes NO extra args** — `args: []` is correct here.

(`bind=True` means Celery injects `self` automatically; the *scheduled* `args` fill the
remaining positional params. So `args: []` supplies zero positionals → `workspace_id`
is left unbound for the first two tasks.)

## 3. Local reproduction — forcing the error with the beat's exact args

Ran the project venv interpreter against the `/tmp/crm-signup-fix` source tree. Imported
the real `celery_app` + tasks, read the beat schedule back as Celery loaded it, printed the
`run()` signatures, then invoked each task's body with `*args` where `args == []` (exactly
what celery beat passes to the worker on each fire).

Command:
```
cd /tmp/crm-signup-fix/apps/api && \
PYTHONPATH=/tmp/crm-signup-fix/apps/api REDIS_URL="memory://" \
DATABASE_URL="postgresql+asyncpg://invalid/invalid" \
/mnt/external/Projects/crm-agentic/apps/api/.venv/bin/python - <<'PY'
from app.workers.celery_app import celery_app
from app.workers.pipeline import optimize_pipeline
from app.workers.deal_health_worker import compute_deal_health
from app.workers.followup_sequences import check_stale_deals_hitl
import inspect
for name, e in celery_app.conf.beat_schedule.items():
    print(name, e['task'], e.get('args'))
for t in (optimize_pipeline, compute_deal_health, check_stale_deals_hitl):
    print(t.name, inspect.signature(t.run))
for t, args in ((optimize_pipeline, []), (compute_deal_health, []), (check_stale_deals_hitl, [])):
    try: print(t.name, "->", t.run(*args))
    except TypeError as ex: print(t.name, "TypeError:", ex)
PY
```

Observed output (verbatim, trimmed to the load-bearing lines):
```
python: /mnt/external/Projects/crm-agentic/apps/api/.venv/bin/python
source tree: ['/tmp/crm-signup-fix/apps/api']

=== beat_schedule (as loaded) ===
nightly-pipeline-optimize: task=app.workers.pipeline.optimize_pipeline args=[]
nightly-deal-health: task=app.workers.deal_health_worker.compute_deal_health args=[]
daily-hitl-followup: task=app.workers.followup_sequences.check_stale_deals_hitl args=[]
pm-health-check: task=app.workers.pm_agent.run_health_check args=[]

=== task run() signatures ===
app.workers.pipeline.optimize_pipeline: (workspace_id: 'str') -> 'dict[str, Any]'
app.workers.deal_health_worker.compute_deal_health: (workspace_id: 'str') -> 'dict[str, Any]'
app.workers.followup_sequences.check_stale_deals_hitl: () -> 'dict[str, Any]'

--- firing app.workers.pipeline.optimize_pipeline with args=[] (beat 'args:[]') ---
TypeError RAISED: TypeError("optimize_pipeline() missing 1 required positional argument: 'workspace_id'")

--- firing app.workers.deal_health_worker.compute_deal_health with args=[] (beat 'args:[]') ---
TypeError RAISED: TypeError("compute_deal_health() missing 1 required positional argument: 'workspace_id'")

--- firing app.workers.followup_sequences.check_stale_deals_hitl with args=[] (beat 'args:[]') ---
OTHER ValidationError: 5 validation errors for Settings  (SUPABASE_URL ... missing)
   reached frame: __init__ in main.py line 212
```

**Interpretation:**
- `optimize_pipeline([])` and `compute_deal_health([])` raise
  `TypeError: missing 1 required positional argument: 'workspace_id'` — **the claim is PROVEN.**
  The TypeError occurs at the Python call-binding boundary, *before any DB / event-loop code
  runs* (it never reaches the config import that the third task tripped on). So this is purely
  a signature/args mismatch, reproducible with no DB and a dummy broker.
- `check_stale_deals_hitl([])` did **NOT** raise TypeError — its signature is `()`, so the
  empty args list is correct. It failed only later on env/Settings validation, which is a
  test-environment artifact (missing SUPABASE_URL etc.), **not** the beat-args bug. Important
  nuance: the daily HITL sweep is correctly wired w.r.t. args; it is starved by the cascade
  (§4), not by a TypeError.

## 4. The cascade — why the <=40 sweep matches nothing

- `Deal.health_score` default = **100**: `models/deal.py:26`
  `health_score: Mapped[int] = mapped_column(Integer, nullable=False, default=100)`
- The only worker that *recomputes* and persists `health_score` is
  `deal_health_worker.compute_deal_health` (`deal_health_worker.py:87` `deal.health_score = score`).
  Grep confirms **no other code path writes `Deal.health_score`** — all other references
  (`routers/deals.py`, `routers/ai.py`, `routers/mcp_server.py`) only *read/filter* it; the
  `health_score: int = 100` at `routers/deals.py:36` is a Pydantic response-schema default, not a DB writer.
- The daily HITL sweep filters `Deal.health_score <= 40`
  (`followup_sequences.py:95`).

Chain:
1. Nightly `compute_deal_health` **crashes on every fire** (TypeError, §3) → it never persists scores.
2. Therefore deals retain the DB default `health_score = 100` (unless an admin manually triggers — §6).
3. `100 <= 40` is False for every untouched deal → the `daily-hitl-followup` sweep selects
   **zero deals** → no follow-up drafts, no Slack HITL cards, no "proactive" outreach.

Identical secondary impact on the pipeline optimizer: nightly `optimize_pipeline` crashes →
`ml_win_probability` never refreshed by the schedule.

## 5. Do "the agents that never sleep" actually run?

**On their nightly/automated schedule: NO.**
- Pipeline Optimizer (02:00 UTC) → TypeError every night, never executes its body.
- Deal Health Agent (02:15 UTC) → TypeError every night, never scores a deal, never fires the
  `score <= 25` proactive `deal_alert` events (`deal_health_worker.py:92-104`) either.
- Followup/HITL Agent (09:00 UTC) → runs without error but its `health_score <= 40` query is
  empty because of the cascade, so it does nothing visible.

Net: the scheduled "always-on agents" are effectively inert. The system *looks* healthy
(every deal pinned at 100), which masks the failure.

## 6. Scope nuance / honest caveats (what is NOT broken)

- **Manual, admin-triggered runs DO work.** `routers/deals.py:109`
  `compute_deal_health.delay(str(workspace_id))` and `routers/deals.py:260`
  `optimize_pipeline.delay(str(workspace_id))` pass `workspace_id` correctly. These back the
  admin-gated POST endpoints `POST /workspaces/{id}/deals/health` and
  `POST /workspaces/{id}/pipeline/optimize` (both `Depends(require_admin)`). So an admin who
  clicks "recompute" gets correct behavior — which is exactly why this bug can hide in prod:
  on-demand demos work, only the unattended nightly cron is dead.
- The TypeError was reproduced by calling the task **body** (`.run(*args)`), which is what a
  celery worker executes after deserializing a beat message. I did **not** stand up a live
  redis broker + beat + worker in this run (would require prod/redis creds and risks touching
  the live broker, which is out of scope for read-only validation). The signature mismatch is
  deterministic and broker-independent, so a full end-to-end beat run would raise the same
  TypeError in the worker and mark the task FAILURE.
- No DB was mutated. No test data created. The two DATABASE_URL/REDIS_URL values used were
  deliberately invalid/in-memory; the TypeError fires before any connection attempt.

## 7. Remediation

In `celery_app.py`, the two nightly entries cannot use a static `args: []` because the tasks
are per-workspace. Options:
1. Replace each per-workspace task with a **fan-out dispatcher** task (no required args) that
   queries all active workspace_ids and enqueues `optimize_pipeline.delay(ws_id)` /
   `compute_deal_health.delay(ws_id)` per workspace. Point the beat schedule at the dispatcher.
2. Or make `workspace_id` optional and have the task iterate all workspaces when `None`
   (changes the contract the manual endpoints rely on — less clean).

Option 1 is preferred (keeps the per-workspace task contract used by the admin endpoints, and
matches how `check_stale_deals_hitl` already iterates workspaces internally).
