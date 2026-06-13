# NovaCRM — Phase 4 Remediation Roadmap (30 / 60 / 90)

**Date:** 2026-06-03 · Sequenced plan to close the seven findings + claims integrity, and to install
the durable posture from `REMEDIATION_REPORT.md` §4 (derive tenancy only from server-controlled
state; enforce at two layers; fail closed when unconfigured).

Each item lists the **fix**, the **observed-working exit test** (how we'll know it's actually done,
not just asserted), and **status**. "DEPLOYED" = live on Railway; "VERIFIED" = re-tested in prod.

---

## Now → 30 days (Sev-1 + start Sev-2)

### 1. F1 — Gmail webhook fail closed *(P0, first)*
- **Fix.** In `gmail.py:_verify_pubsub_secret`, remove the `if not secret: return True` branch — fail
  closed (reject) when `GMAIL_WEBHOOK_SECRET` is unconfigured. Add a `lifespan()` startup check that
  warns/refuses if the secret is unset, mirroring the existing Slack-interactions HITL guard. **Set
  `GMAIL_WEBHOOK_SECRET` in the api service env** (currently absent). Extend the same startup guard
  to the Slack-events secret as defense-in-depth.
- **Exit test.** Re-run the authorized probe: a no-`?secret=` POST to `/webhooks/gmail/push` returns
  **403**, not 204; a correctly-signed push still returns 204. Confirm the env var is present in
  prod. Confirm startup logs the guard.
- **Status.** MERGED (`76839ee`, PR #2) — `_verify_pubsub_secret` now fails closed when the secret is
  unset. **Residual (ops):** `GMAIL_WEBHOOK_SECRET` + `GMAIL_PUBSUB_TOPIC` still unset in Railway, so
  the webhook rejects everything (Gmail push ingest inert in prod until set). MERGED → DEPLOYED pending.

### 2. F2 — Workspace rebind closed *(finish the staged fix)*
- **Fix.** Complete `fix/ws-b`: stop trusting `user_metadata.workspace_id`. Remove the `/auth/verify`
  reconcile write (`auth.py:100-109`) and the `dependencies.py` auto-provision read (44-77) that take
  workspace from client-writable metadata. Source workspace membership from server-controlled state
  (`app_metadata`, admin-only writable, and/or a membership table the user cannot write). **Backfill**
  existing users' `app_metadata` and **cut over code + deploy as one coordinated step** so no window
  exists where a user has neither source.
- **Exit test.** Reproduce the takeover steps from `../phase2/evidence-takeover.md` against a fresh
  pair of test users: after self-writing a foreign `workspace_id`, `/auth/verify` + `/me` must **not**
  rebind, and the cross-tenant `GET /workspaces/{B}/contacts` must return **403**. Tear down test
  users.
- **Status.** MERGED — `dependencies.py` binds workspace only from server-only `app_metadata` via
  `_read_bound_workspace_id`; user-writable metadata is no longer trusted. **Residual (ops):**
  `app_metadata` backfill for existing users + cutover confirmation. MERGED → DEPLOYED pending.

### 3. CLAIM — Substantiate-or-soften the landing page *(parallel, no engineering)*
- **Fix.** From `REMEDIATION_REPORT.md` §5: remove "SOC 2 Type II", "99.9% uptime"/"99.99% SLA",
  "GDPR Compliant", and "94.7% Accuracy"/"F1: 0.947"; correct the model lineup to what actually runs
  (heuristic scoring; Claude Haiku composer; Whisper base + Claude Sonnet transcription; drop
  XGBoost/RoBERTa/GPT-4o-fine-tuned); gate or soften pricing/SSO/SCIM. Start fresh — the
  `fix/honest-marketing-claims` branch was never written.
- **Exit test.** `grep` the rendered `page.tsx` for each removed string → zero hits; every remaining
  performance/model claim maps to a real code path.
- **Status.** PARTIALLY FIXED — the compliance badges (SOC 2 / 99.9% uptime / GDPR) were removed
  earlier, but the fabricated ML lineup (94.7% "Accuracy", `XGBoost v2`, `F1: 0.947`,
  `GPT-4o Fine-tuned`, `RoBERTa Fine-tuned`, `LightGBM`, the `f1:0.947→0.951` log line) is
  **still live** on `apps/web/src/app/page.tsx`. Fix in progress today (lane `claims`). Runs in
  parallel because it is copy, not code.

### 4. F6 — Scheduled agents actually run *(finish in-progress fix)*
- **Fix.** Complete `fix/ws-d-agent-execution`: replace the two `args: []` per-workspace beat entries
  with a **no-arg fan-out dispatcher** task that enumerates active workspaces and enqueues
  `optimize_pipeline.delay(ws)` / `compute_deal_health.delay(ws)` each. Point the beat schedule at the
  dispatcher. Keeps the per-workspace contract the admin endpoints rely on.
- **Exit test.** Trigger the dispatcher (or wait one scheduled cycle) and observe: tasks complete
  without TypeError; at least one deal's `health_score` is recomputed off the default 100; the
  `health_score <= 40` follow-up sweep now selects the intended deals. Check Celery result states are
  SUCCESS, not FAILURE.
- **Status.** MERGED — `workers/celery_app.py` `beat_schedule` now points at the no-arg fan-out
  dispatchers `optimize_pipeline_all` / `compute_deal_health_all`. **Residual:** verify a scheduled
  cycle runs SUCCESS and recomputes a `health_score` off the default 100 in prod. MERGED → VERIFIED
  pending.

---

## 30 → 60 days (close Sev-2)

### 5. F3 + F4 — Tenant isolation: backstop + the proven gap *(land together)*
- **F4 fix.** Persist a `job → workspace_id` mapping at enqueue time (a `jobs` table or a
  workspace-namespaced Redis key) and have `get_job_status` verify the job belongs to
  `current_user.workspace_id`, returning 404 on mismatch — the same pattern the sibling agents.py
  endpoints already use. Do not rely on UUID unguessability.
- **F3 fix.** Stop connecting the API as `postgres`. Create a dedicated **non-superuser,
  non-`BYPASSRLS`, non-owner** login role for the API `DATABASE_URL`. `ALTER TABLE ... FORCE ROW LEVEL
  SECURITY` on all tenant tables. Inject tenant context per request (set `request.jwt.claims` /
  `SET LOCAL`) so `auth.uid()` resolves and policies evaluate. Add a policy to `call_summaries`
  (currently RLS-enabled with zero policies). Keep app-layer filters as defense-in-depth.
- **Why together.** F4 is the concrete proof that the F3 backstop is needed; fixing F4 alone still
  leaves every handler one missing filter from the same class of bug. Also fold in the LOW/latent
  `/slack/interactions` workspace-filter gap (FINDING 2) here.
- **Exit test.** Re-run the decisive unfiltered `SELECT` from `../phase2/evidence-rls.md` as the **new**
  API role → it returns **0 rows / is denied** (RLS now applies), proving the backstop is live. Re-run
  the `../poc_jobs_idom.py`-style check → a Workspace-B caller gets **404**, not Workspace-A's result.
  Confirm the app still functions end-to-end under the new role (existing pytest suite + a smoke pass).
- **Status.** **F4 MERGED** — `routers/agents.py:get_job_status` reads the owning workspace from the
  dispatch marker (`_job_owner_workspace`) and returns 404 on mismatch (`76839ee`, PR #2). **F3 OPEN**
  — `013_force_rls.sql` shipped but **INERT**: the API still connects as a shared `BYPASSRLS` role, so
  FORCE RLS does not constrain it and `call_summaries` is still effectively policy-free at runtime.
  Code prep in progress today (lane `rls-dos`), gated behind a flag until the ops role-swap cutover.

### 6. F7 — Real contact erasure *(also satisfies the GDPR claim's substance)*
- **Fix.** In `delete_contact`, before `db.delete(contact)`, explicitly delete or scrub PII on the
  linked `deals` / `messages` / `tasks` / `call_summaries` for that `contact_id` within the same
  transaction (application-level erasure — do not rely on `SET NULL`). Correct the false docstring.
- **Exit test.** Reproduce `../phase2/evidence-delete-contact.md`: after deleting a contact with linked
  children, the child rows carrying PII (`messages.sender_email`/`body_plain`,
  `call_summaries.transcript`/`summary`) are **gone or scrubbed**, not orphaned with `contact_id` NULL.
- **Status.** OPEN — `delete_contact` still only does `db.delete(contact)` and its docstring falsely
  claims it removes "all cascade-linked records"; linked PII is orphaned. Fix in progress today (lane
  `delete-cascade`).

---

## 60 → 90 days (close Sev-3 + harden)

### 7. F5 — Per-tenant rate limiting + spend cap + queue isolation
- **Fix.** (a) Set `request.state.user` in auth (middleware/dependency) so `_rate_key` keys per-user —
  or make the limiter require an authenticated principal and never silently fall back to a shared IP.
  (b) Run uvicorn with `--proxy-headers --forwarded-allow-ips=<railway CIDR>` (defense-in-depth).
  (c) Add a **per-workspace token/cost budget** (Redis counter or DB ledger) checked before each
  Anthropic call; hard-fail or defer when exceeded. (d) Rate-limit `POST /messages/reprocess` and
  cap/chunk its per-call fan-out. (e) Isolate worker queues (dedicated low-concurrency queue for
  long Whisper/reprocess jobs; separate queue for short enrich/scoring) so one long job can't pin the
  pool.
- **Exit test.** Two test tenants on the same proxy get **independent** rate buckets (one being
  throttled does not throttle the other). A tenant exceeding its budget is blocked before the model
  call. A long reprocess job no longer blocks a second tenant's short jobs.
- **Status.** OPEN — `limiter.py` keys on IP because `request.state.user` is never set, so it degrades
  to one global bucket; no per-tenant spend cap; `reprocess` unbounded. Code prep in progress today
  (lane `rls-dos`).

### 8. Posture hardening (carry-over from the claims/security registers)
- Add a **public status page + real uptime monitoring** before re-introducing any uptime language.
- Stand up the **DPA / records-of-processing / retention** machinery before re-introducing "GDPR
  compliant"; F7 is a prerequisite, not the whole claim.
- If SOC 2 is a goal, start the **multi-month audited window** (realistic ~$25–45K / 6–12 months per
  Phase 3) — there is no shortcut, and the badge must not return to the page before the report exists.
- Address the latent secret-loss exposure: the F1 startup guard should cover **both** the Gmail and
  Slack-events secrets so a future deploy can't silently re-open either webhook.

---

## Tracking

The `crm-pm` agent maintains the Status column in `../REMEDIATION_REGISTER.md` each run
(re-verifying every open row against `origin/master` + Railway). This roadmap is the **plan**; that
register is the **live status of record**. As each exit test above passes in prod, the corresponding
row advances OPEN → FIX-STAGED → MERGED → DEPLOYED → VERIFIED.

**Definition of done for the program:** all seven findings at VERIFIED, the landing page carrying only
substantiated claims, and the decisive RLS `SELECT` returning zero cross-tenant rows under a
non-bypass API role — i.e. tenancy enforced at two layers, failing closed, derived only from
server-controlled state.
```