# NovaCRM Phase 2 — Webhook Fail-Open + GET /jobs/{id} IDOR

Date: 2026-06-03
Target API (prod): https://api-production-c080.up.railway.app
Frontend: https://www.riphere.com
Code under review: /tmp/crm-signup-fix/apps/api/app/routers/{gmail.py,slack.py,agents.py}
Authorization: product owner's own infra; read-only DB + single PoC probes only.

================================================================================
## (A) WEBHOOK FAIL-OPEN
================================================================================

### A1. Gmail Pub/Sub webhook — FAIL-OPEN, LIVE-EXPLOITABLE IN PROD (PROVEN)

Code — apps/api/app/routers/gmail.py:372-383
    def _verify_pubsub_secret(request_secret: str | None) -> bool:
        if not settings.GMAIL_WEBHOOK_SECRET:
            return True  # no secret configured — accept all (dev/test only)
        if not request_secret:
            return False
        return hmac.compare_digest(settings.GMAIL_WEBHOOK_SECRET, request_secret)

Used by the unauthenticated webhook — gmail.py:405-431
    @router.post("/webhooks/gmail/push", status_code=204)
    async def gmail_push_webhook(... secret: str | None = Query(default=None) ...):
        if not _verify_pubsub_secret(secret):
            raise HTTPException(403, "Invalid webhook secret")
        ... background_tasks.add_task(_trigger_ingest_for_email, email_address, db)
There is NO get_current_user dependency on this route — it is public by design (Pub/Sub push).

Config default — apps/api/app/config.py:32
    GMAIL_WEBHOOK_SECRET: str = ""   # shared secret appended to webhook URL
=> when the env var is unset, settings.GMAIL_WEBHOOK_SECRET == "" => _verify_pubsub_secret returns True for ANY request.

Prod secret state — railway variables --service api --json:
    $ railway variables --service api --json | python3 -c "...":
    GMAIL_WEBHOOK_SECRET present as key: False
    GMAIL_WEBHOOK_SECRET repr: None
    (key is entirely absent => falls back to "" default => fail-open is ACTIVE in prod)
    For contrast, real secrets ARE present: GOOGLE_CLIENT_SECRET(35), SECRET_KEY(64),
    SLACK_CLIENT_SECRET(32), SLACK_SIGNING_SECRET(32), SUPABASE_JWT_SECRET(88).

No startup guard — grep of apps/api/app/main.py for GMAIL_WEBHOOK_SECRET / webhooks/gmail:
    -> NONE found (the lifespan() startup check only warns about SLACK_SIGNING_SECRET
       for /slack/interactions; nothing warns about or enforces the gmail webhook secret).

LIVE PROOF — single authorized probe, no ?secret= param, valid Pub/Sub-shaped body
(base64 data decodes to {"emailAddress":"notareal-audit-probe@example.com","historyId":"1"}):
    $ curl -s -w "HTTP_STATUS=%{http_code}\n" -X POST \
        "$API/webhooks/gmail/push" -H 'Content-Type: application/json' \
        -d '{"message":{"data":"eyJlbWFpbEFkZHJlc3MiOiJub3RhcmVhbC1hdWRpdC1wcm9iZUBleGFtcGxlLmNvbSIsImhpc3RvcnlJZCI6IjEifQ==","messageId":"audit-probe","publishTime":"2026-06-03T00:00:00Z"},"subscription":"projects/x/subscriptions/y"}'
    HTTP_STATUS=204
    body: (empty)

Interpretation: 204 == request ACCEPTED (not 403). The secret check passed with no
secret supplied. An unauthenticated attacker who knows/guesses a connected mailbox's
email can POST a forged push and cause the server to enqueue a Celery process_gmail_sync
for that workspace's Gmail connector (gmail.py:385-402, _trigger_ingest_for_email looks
up the connector by external_email and calls process_gmail_sync.delay). Email addresses
are low-entropy / discoverable => forced-sync / ingest-trigger abuse and resource
amplification with zero credentials. VERDICT: PROVEN (live).

--------------------------------------------------------------------------------

### A2. Slack Events webhook — FAIL-OPEN IN CODE, but REFUTED IN PROD (secret IS set)

Code — apps/api/app/routers/slack.py:193-220
    def _verify_slack_signature(body, timestamp, signature, signing_secret) -> bool:
        if not signing_secret:
            return True  # dev mode — accept all
        ...
Used by — slack.py:243-268  POST /webhooks/slack/events (no get_current_user; public)
    if not _verify_slack_signature(raw_body, ts, sig, settings.SLACK_SIGNING_SECRET):
        raise HTTPException(401, "Invalid Slack signature")
Config default — config.py:28  SLACK_SIGNING_SECRET: str = ""  => same fail-open shape.

Prod secret state:
    SLACK_SIGNING_SECRET present as key: True
    SLACK_SIGNING_SECRET set=True len=32   (a real 32-char signing secret IS configured)

LIVE PROOF — no-signature probe (url_verification challenge), expect rejection if set:
    $ curl -s -w "HTTP_STATUS=%{http_code}\n" -X POST \
        "$API/webhooks/slack/events" -H 'Content-Type: application/json' \
        -d '{"type":"url_verification","challenge":"audit-probe-123"}'
    HTTP_STATUS=401
    body: {"detail":"Invalid Slack signature"}

Interpretation: because SLACK_SIGNING_SECRET is set in prod, the fail-open branch is
NOT reachable; the unsigned request is correctly rejected with 401. The code-level
fail-open bug is real but is currently MITIGATED BY CONFIGURATION in production.
VERDICT for prod exploitability: REFUTED. (Latent risk: any deploy that loses the
secret silently disables Slack-events auth, and unlike /slack/interactions there is
NO startup guard for this route either.)

================================================================================
## (B) GET /jobs/{id} IDOR — authenticated cross-tenant; auth-gated (PARTIAL)
================================================================================

Code — apps/api/app/routers/agents.py:115-134
    @router.get("/jobs/{job_id}", response_model=JobStatusResponse)
    async def get_job_status(
        job_id: str,
        current_user: User = Depends(get_current_user),   # auth required, but...
    ) -> JobStatusResponse:
        from app.workers.celery_app import celery_app
        task = celery_app.AsyncResult(job_id)              # <-- attacker-supplied id
        state = task.state
        result = None; error = None
        if state == "SUCCESS":
            raw = task.result
            result = raw if isinstance(raw, dict) else {"value": str(raw)}
        elif state == "FAILURE":
            error = str(task.result)
        return JobStatusResponse(job_id=job_id, state=state, result=result, error=error)

MISSING CONTROL: the handler never loads a job/workspace record and never compares it
to current_user.workspace_id. Contrast with the SAME file's run_agent / update_agent /
list_agents (agents.py:45, 58, 100) which all scope queries by
`Agent.workspace_id == current_user.workspace_id`. The /jobs/{id} reader has no such
predicate — ANY authenticated user can read ANY Celery job's state/result/error by id,
regardless of which workspace enqueued it. Job results can contain another tenant's
ingest output / error strings (cross-tenant info disclosure).

Route is the agents.py one — main.py:123  app.include_router(agents.router, tags=["agents"])

Auth precondition (characterizing severity) — dependencies.py:18-40 get_current_user
validates a Supabase JWT (verify_supabase_jwt) and loads the User. So this is NOT
unauthenticated: it requires *some* valid login, but signup is open, so any registered
user is a valid attacker against every other workspace's jobs.

LIVE PROOF (negative controls confirm the gate, code confirms the gap):
    $ curl -s -w "HTTP_STATUS=%{http_code}\n" "$API/jobs/00000000-0000-0000-0000-000000000000"
    HTTP_STATUS=401   body: {"detail":"Not authenticated"}          (no token => blocked)
    $ curl -s -H "Authorization: Bearer not-a-real-jwt" -w "HTTP_STATUS=%{http_code}\n" "$API/jobs/deadbeef-job-id"
    HTTP_STATUS=401   body: {"detail":"Could not validate credentials"} (bad token => blocked)
    (sanity: /openapi.json => 200, /agents no-auth => 401 — API is up, route exists.)

WHAT IS NOT YET DEMONSTRATED (honest caveat): I did not provision two test users in two
workspaces, enqueue a real job in workspace A, and read it from workspace B's token,
because that requires creating test users + triggering a real Celery job (out of scope
for a single read-only probe, and Celery job_ids are server-generated v4 UUIDs so they
are unguessable without leakage). The IDOR is PROVEN AT THE CODE LEVEL (no authorization
check on a per-resource read) and the auth gate is PROVEN LIVE; the end-to-end
cross-tenant read across two real workspaces is NOT independently demonstrated here.
VERDICT: PARTIAL (code-proven authz gap; not an unauthenticated/end-to-end live demo).
Note also job_id is unvalidated as a UUID, but AsyncResult(str) is safe (no injection).

================================================================================
## NET
================================================================================
(A) Gmail webhook: PROVEN unauthenticated fail-open, LIVE (HTTP 204 with no secret;
    prod var absent; config default ""; no startup guard).
(A) Slack events webhook: fail-open in code, REFUTED in prod (secret set => HTTP 401).
(B) /jobs/{id}: code-proven missing-workspace-authz IDOR, but auth-gated (401 without a
    valid JWT) and not demonstrated end-to-end cross-tenant => PARTIAL.

REMEDIATION
- gmail.py _verify_pubsub_secret + slack.py _verify_slack_signature: remove the
  `if not <secret>: return True` branch — FAIL CLOSED (return False / raise) when the
  secret is unconfigured. Add a lifespan() startup check for GMAIL_WEBHOOK_SECRET (and
  the slack-events secret) mirroring the existing SLACK_SIGNING_SECRET HITL warning.
- Set GMAIL_WEBHOOK_SECRET in the api service env immediately (it is currently absent).
- agents.py get_job_status: persist a Job row keyed by workspace_id at enqueue time and
  filter `Job.id == job_id AND Job.workspace_id == current_user.workspace_id` (return 404
  on mismatch), the same pattern already used by list_agents/run_agent/update_agent.
