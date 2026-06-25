# Refutation attempt — Nightly Celery beat TypeError cascade (NovaCRM)

VERDICT: UPHELD (finding survives refutation). Severity: high — confirmed.

## What was checked and how

Source tree: /tmp/crm-signup-fix/apps/api
Runtime: /mnt/external/Projects/crm-agentic/apps/api/.venv/bin/python (cpython-3.11), celery 5.4.0
Probe used a bogus DATABASE_URL (asyncpg://invalid@127.0.0.1:1) and broker=memory://; never touched real infra.

## 1. beat_schedule hard-codes args=[]  (app/workers/celery_app.py:27-48)
  nightly-pipeline-optimize -> app.workers.pipeline.optimize_pipeline   args=[]   crontab(2,0)
  nightly-deal-health       -> app.workers.deal_health_worker.compute_deal_health args=[] crontab(2,15)
  daily-hitl-followup       -> app.workers.followup_sequences.check_stale_deals_hitl args=[] crontab(9,0)
  pm-health-check           -> app.workers.pm_agent.run_health_check    args=[]   (pm_agent not in include list -> not registered)

## 2. Registered task run() signatures (introspected from live celery_app)
  optimize_pipeline:        run(workspace_id: 'str')          bind=True (pipeline.py:103)
  compute_deal_health:      run(workspace_id: 'str')          bind=True (deal_health_worker.py:111)
  check_stale_deals_hitl:   run()                             bind=True (followup_sequences.py:193)

## 3. Faithful dispatch via Celery (task.apply(args=[]), eager+propagate) — mirrors worker executing a beat message
  nightly-pipeline-optimize: RAISED TypeError: optimize_pipeline() missing 1 required positional argument: 'workspace_id'
       raised at Celery trace.py: `R = retval = fun(*args, **kwargs)` (call-binding, before any DB/event-loop code)
  nightly-deal-health:       RAISED TypeError: compute_deal_health() missing 1 required positional argument: 'workspace_id'
       raised at the same call-binding line
  daily-hitl-followup:       RAISED ValidationError (Settings: SUPABASE_SERVICE_ROLE_KEY/SUPABASE_JWT_SECRET/SECRET_KEY missing)
       => NOT the args bug; signature is () so binding succeeds, fails later only on test-env config. Matches the claim.
  (bind=True => Celery injects `self`; empty scheduled args leave workspace_id unbound -> TypeError every fire.)

## 4. Cascade — verified by file:line and DB schema
  - Deal.health_score default=100, nullable=False  (models/deal.py:26)
  - DB schema enforces same default+CHECK: init_docker.sql:60 and migrations/003_deal_health.sql:5
      health_score INT NOT NULL DEFAULT 100 CHECK (health_score BETWEEN 0 AND 100)
  - ONLY writer of Deal.health_score (assignment): deal_health_worker.py:87 (`deal.health_score = score`)
      grep of entire app/: all other refs read/filter only (mcp_server, deals router, ai router).
      No raw-SQL/migration/trigger writes health_score (only test fakes). Only DB trigger is update_updated_at() (touches updated_at).
  - Follow-up sweep filter: followup_sequences.py:95  `Deal.health_score <= 40`
  - Proactive critical-alert path: deal_health_worker.py:92  `if score <= 25`

  => Nightly compute_deal_health crashes at binding -> deals never re-scored -> stay at 100
     -> daily HITL sweep `<=40` selects zero deals -> no follow-up drafts / no Slack HITL cards
     -> `<=25` deal_alert path also never fires.

## 5. Refutation checks that FAILED to refute (i.e., no mitigation exists)
  - No signal hooks that could inject workspace_id into beat args:
      grep for on_after_configure / setup_periodic_tasks / add_periodic_task / task_prerun /
      before_task_publish / custom Scheduler -> NONE found.
  - Only callers that pass workspace_id are admin-only HTTP routes, NOT the cron:
      deals.py:109  compute_deal_health.delay(str(workspace_id))   under @router.post(".../deals/health"), Depends(require_admin)
      deals.py:260  optimize_pipeline.delay(str(workspace_id))     under Depends(require_admin)
    These prove the signature requires workspace_id (manual triggers work) while the beat entry hard-codes args=[] (cron breaks).
  - pm-health-check references app.workers.pm_agent.run_health_check, which is absent from the include= list in
    celery_app.py:17 -> task not registered -> separate latent issue, out of scope for this finding.

## Conclusion
Every load-bearing element reproduces. The TypeError is guaranteed on every nightly fire of the two per-workspace
tasks, fires at Python call-binding before any side effects, and the health-score cascade is real (single writer,
DB default 100, no server-side recompute). Finding is UPHELD.
