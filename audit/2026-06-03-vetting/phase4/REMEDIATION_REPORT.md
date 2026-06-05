# NovaCRM — Phase 4 Synthesis: Consolidated Remediation Report

**Program:** Authorized internal hardening of NovaCRM (crm-agentic), owner's own SaaS.
**Date:** 2026-06-03
**Inputs:** Phase 1 (architecture map + claims register + real pytest runs), Phase 2 (adversarial
validation, 8/9 findings reached command-level verdicts), Phase 3 (market / competitive / compliance research).
**Audience:** product owner + the `crm-pm` maintenance agent.
**Language:** neutral, defensive. This is a fix-our-own-product plan, not an attack narrative.

---

## 1. Executive summary

A structured review of NovaCRM's API, data layer, worker fleet, and public claims surfaced
**seven confirmed defects** and a separate **claims-integrity** workstream. The defects cluster
into three themes, in priority order:

1. **Tenant isolation is single-layered.** The database provides no enforced backstop (RLS is
   inert at runtime), so isolation rests entirely on application-layer `WHERE workspace_id`
   filters. Two confirmed gaps in that layer (a self-service workspace rebind via client-writable
   metadata, and an unscoped job-result read) mean the single layer is also porous. This is the
   highest-impact theme: a single missing filter is a cross-tenant exposure with no second line of
   defense.

2. **One unauthenticated surface fails open.** The Gmail Pub/Sub push webhook accepts any request
   when its shared secret is unconfigured — and the secret is currently absent in production. This
   is the only zero-credential, live-reachable defect, which is why it is P0.

3. **The "always-on agent" scheduled work does not run.** The nightly Celery beat jobs crash on a
   signature/args mismatch, so deal-health scoring and the downstream follow-up sweep are inert.
   The product looks healthy (every deal pinned at the default score) while the headline automation
   is effectively a stub on its schedule.

Supporting these, a cost/DoS exposure (rate limiter degrades to one global bucket; no per-tenant
spend cap on a shared model key) and a data-hygiene defect (contact deletion orphans rather than
erases linked PII) round out the register.

Separately, the public landing page asserts compliance and performance claims (SOC 2 Type II,
99.9%/99.99% uptime, GDPR, "94.7% accuracy," a named ML model lineup) that the codebase does not
substantiate. Phase 3 research establishes these as the product's **highest-liability surface** and
the cheapest to remediate (edit copy, don't build features). They are tracked as their own
workstream, not as security debt.

**One correction carried forward from validation:** the AM PM-brief ranked "Slack signing secret
unset" as the #1 critical. Validation **refuted** this — the Slack signing secret *is* set in
production, so that webhook correctly rejects unsigned requests (HTTP 401). The genuinely
live-exploitable webhook is **Gmail**, whose secret is absent. Three other findings (CORS
reflection, browser anon-read, Slack-events exploitability) were likewise refuted in prod and are
recorded so they are not re-chased.

**Current remediation state (entering Phase 4):**
- 3 signup/auth fixes already on `origin/master` (production build, confirmation-email redirect,
  auth-param rescue) — these predate this register and are unrelated to the seven findings.
- `fix/ws-b` — workspace-id scoping fix **staged** (needs `app_metadata` backfill + coordinated cutover).
- `fix/ws-d-agent-execution` — Celery beat fix **in progress**.
- 5 of 7 findings have no fix branch yet.

---

## 2. Confirmed findings — consolidated

Severity: 🔴 critical · 🟠 high. "Reachability" states how an external party would actually arrive
at the defect, with the caveat from validation. Full command-level evidence is in `../phase2/`.

### F1 — Gmail Pub/Sub webhook fails open 🔴 P0
- **What.** `_verify_pubsub_secret` (`apps/api/app/routers/gmail.py:372-383`) returns `True` when
  `GMAIL_WEBHOOK_SECRET` is empty. The env var is **absent in production**
  (`config.py:32` default `""`), so the unauthenticated `POST /webhooks/gmail/push` accepts any
  request. There is no startup guard for this secret (unlike the Slack-interactions HITL path).
- **Observed.** A single authorized probe with no `?secret=` returned **HTTP 204 (accepted)**, not
  403. A forged push enqueues a `process_gmail_sync` Celery task for a connector matched by email
  address — low-entropy and discoverable — yielding forced-sync / ingest-trigger amplification with
  zero credentials.
- **Why P0.** Only finding that is both unauthenticated and live-reachable today.
- **Evidence.** `../phase2/evidence-webhook-idor.md` §A1.
- **Status.** OPEN — no fix branch. *(This is the next item after Phase 4.)*

### F2 — Cross-tenant workspace rebind via client-writable metadata 🔴
- **What.** `POST /auth/verify` reconcile branch (`auth.py:100-109`) writes `user.workspace_id` from
  the JWT's `user_metadata.workspace_id` with no membership check. `user_metadata` is writable by
  the end user through the standard GoTrue `PUT /auth/v1/user` path. The same untrusted-metadata
  read exists in the `dependencies.py` auto-provision path (44-77).
- **Observed.** End-to-end reproduction (two test users, since cleaned up): user A self-asserted
  user B's `workspace_id`, re-verified, and then **read and wrote** B's contacts and deals as
  `role=admin` (HTTP 200/201). A negative control against a never-asserted workspace correctly
  returned 403 — so the per-request guard works; only the metadata rebind defeats it.
- **Evidence.** `../phase2/evidence-takeover.md`, `../branch-worktree/EVIDENCE_workspace_takeover_metadata.md`.
- **Status.** FIX-STAGED — `fix/ws-b` (5252714): bind via server-only `app_metadata`; needs a
  membership backfill + coordinated code/deploy cutover as one step.

### F3 — Database RLS is inert at runtime 🔴
- **What.** The API connects as the shared `postgres` role (`rolbypassrls = t`, table owner). RLS is
  enabled but **not forced** (`relforcerowsecurity = f`) on every tenant table, and
  `request.jwt.claims` is empty at the DB layer so `auth.uid()` is NULL. `call_summaries` has **zero
  policies**. Net: the DB enforces no tenant isolation; the existing policies never run.
- **Observed.** A single unfiltered `SELECT` as the exact API role returned rows spanning **two
  distinct real workspaces** for both `contacts` (7 rows / 2 ws) and `deals` (8 rows / 2 ws).
- **Why it matters.** It is the missing second layer behind F2/F4 — any missing app-layer filter,
  injection sink, or service-key exposure becomes a full cross-tenant exposure with no backstop.
- **Evidence.** `../phase2/evidence-rls.md`.
- **Status.** OPEN.

### F4 — `GET /jobs/{id}` missing tenant scoping (cross-tenant job-result read) 🟠
- **What.** `get_job_status` (`agents.py:115-134`) authenticates the caller but never compares the
  job to `current_user.workspace_id`; it returns `celery_app.AsyncResult(job_id).result` for any
  id. The three sibling endpoints in the same file all scope correctly on
  `Agent.workspace_id == current_user.workspace_id` — this one is the outlier.
- **Observed.** A PoC reproducing the verbatim handler body against the live `crm-redis` backend
  returned a Workspace-A job result (private contact signals) to a Workspace-B caller. Auth gate is
  proven live (401 without a valid JWT). End-to-end cross-tenant across two real prod workspaces was
  not independently demonstrated because job_ids are server-minted UUIDv4 (not enumerable) — so this
  is a **code-proven authenticated IDOR**, gated by login and by knowledge/leakage of a foreign job_id.
- **Evidence.** `../phase2/evidence-missing-where.md` (FINDING 1), `../poc_jobs_idom.py`.
- **Status.** OPEN. *(A second, LOW/latent gap — `/slack/interactions` event+contact lookups
  missing a workspace filter — is recorded in the same file as FINDING 2; it is gated behind
  fail-closed HMAC and is defense-in-depth only.)*

### F5 — Cost / DoS: rate limiter degrades to one global bucket; no per-tenant spend cap 🟠
- **What.** `_rate_key` (`limiter.py`) reads `request.state.user`, which is **never set** anywhere in
  the app, so it always falls back to `get_remote_address`. Behind Railway's proxy without
  `--proxy-headers`, that is one fixed edge-proxy IP — i.e. a **single global bucket for all
  tenants**. There is no per-workspace token/cost budget on the single shared `ANTHROPIC_API_KEY`,
  and the heaviest amplifier (`POST /messages/reprocess`, ~4 model calls per message) has no rate
  limit at all. Workers run hard-pinned at `--concurrency=2` with no queue isolation.
- **Observed.** Running the verbatim `limiter.py` against the project's pinned slowapi showed two
  tenants collapsing to one key and the per-user branch being dead. (No live load/spend test was run
  — per authorization; magnitudes are from static call-count + concurrency analysis.)
- **Effect.** One tenant can throttle a route for everyone (the limiter's global bucket) and drive
  unbounded spend / starve the 2-slot pool.
- **Evidence.** `../phase2/evidence-cost-dos.md`, `../branch-worktree/REFUTATION_EVIDENCE_ratelimiter.md`.
- **Status.** OPEN.

### F6 — Celery beat scheduled jobs crash (scheduled agents inert) 🟠
- **What.** `beat_schedule` (`celery_app.py:27-48`) fires `optimize_pipeline` and
  `compute_deal_health` with `args: []`, but both task bodies require a `workspace_id` positional.
  Each fire raises `TypeError: missing 1 required positional argument: 'workspace_id'` at the call
  boundary, before any DB work. Cascade: `compute_deal_health` never persists scores → deals stay at
  the default `health_score = 100` → the `daily-hitl-followup` sweep (`health_score <= 40`) matches
  nothing → no proactive follow-ups. Admin-triggered manual runs pass `workspace_id` correctly and
  do work, which is why the failure hides in demos.
- **Observed.** Reproduced locally against the real task bodies: both raise the TypeError; the
  third scheduled task (`check_stale_deals_hitl`, no args) is correctly wired.
- **Evidence.** `../phase2/evidence-beat.md`, `../branch-worktree/EVIDENCE_celery_beat_typeerror.md`.
- **Status.** IN PROGRESS — `fix/ws-d-agent-execution`. Preferred fix: a no-arg **fan-out dispatcher**
  task that enumerates active workspaces and enqueues the per-workspace task for each, keeping the
  existing per-workspace contract the admin endpoints rely on.

### F7 — Contact deletion orphans linked PII (no cascade / no erasure) 🟠
- **What.** `delete_contact` (`contacts.py:435-463`) issues a single `db.delete(contact)`. The ORM
  relationships set no `cascade=`, and every child FK (`deals`, `messages`, `tasks`,
  `call_summaries`) is `ON DELETE SET NULL`. So children survive with `contact_id` NULLed —
  orphaned, not erased. The handler docstring ("Delete a contact and all cascade-linked records") is
  materially incorrect.
- **Observed.** Seed → delete → observe → cleanup reproduction (and an independent verifier pass,
  UPHELD) showed the contact row gone but the deal, message (`sender_email` + `body_plain`), task,
  and call_summary (`transcript` + `summary`) all surviving with PII intact.
- **Compliance link.** Directly undercuts the "GDPR compliant" landing claim — a deletion the system
  reports as successful (204) does not erase the personal data in linked rows.
- **Evidence.** `../phase2/evidence-delete-contact.md`.
- **Status.** OPEN. Recommended fix: application-level erasure (explicitly delete/scrub PII on linked
  rows in the same transaction) rather than relying on SET NULL; correct the docstring.

---

## 3. Refuted in production — closed, do not re-chase

| Item | Why closed |
|------|-----------|
| Slack Events webhook fail-open | `SLACK_SIGNING_SECRET` **is** set in prod; unsigned probe → HTTP 401. Code-level fail-open is real but configuration-mitigated. **Corrects the AM PM-brief's #1 ranking.** Latent risk only if a deploy loses the secret (no startup guard). |
| CORS reflection | Malicious origin is **not** reflected in `Access-Control-Allow-Origin`. |
| Browser direct-read under anon key | Refuted at runtime — client calls are authenticated API calls, not anon table reads. |

**Defensive note (latent, not debt):** because neither the Gmail webhook nor the Slack-events
webhook has a startup guard, a future deploy that drops either secret silently re-opens that
surface. The F1 fix should add a startup check for `GMAIL_WEBHOOK_SECRET`, and the same pattern
should be extended to the Slack-events secret as defense-in-depth.

---

## 4. Cross-cutting root cause

Five of the seven findings share one root cause: **tenancy is derived from, or defended at, a single
client-influenced or single-layer point.**

- F2 derives tenancy from a **client-writable** field (`user_metadata`).
- F3 removes the **database backstop** that would catch any app-layer miss.
- F4 is exactly such an app-layer miss (one handler without the filter every sibling has).
- F5's limiter trusts a principal (`request.state.user`) that is never populated, so it silently
  degrades to a shared key.
- F1 trusts an unconfigured secret to mean "open" rather than "closed."

The durable fix is a posture shift, not seven point patches: **derive tenancy only from
server-controlled state, enforce it at two layers (app filter + forced RLS under a non-bypass role),
and fail closed when a control is unconfigured.** The 30/60/90 plan is sequenced to install that
posture, not just to clear the list.

---

## 5. Claims-integrity workstream (separate from security)

Phase 3 establishes the public landing claims as the single highest-liability and lowest-cost-to-fix
surface. None are backed by code (`../phase1/CLAIMS_REGISTER.md` §A). The remedy is to **substantiate
or soften** — copy edits, not feature builds:

| Claim | Disposition | Note |
|-------|-------------|------|
| "SOC 2 Type II" (implies certified) | **Remove now** | SOC 2 is an attestation with a mandatory multi-month audited window; "certified" is itself incorrect phrasing. Market is actively punishing fake SOC 2 (Delve, Apr 2026). Highest liability. |
| "GDPR Compliant" | **Remove / soften now** | Undercut by F7 (no real erasure) + no DPA/RoPA machinery. EU customers rely on it contractually. |
| "99.9% uptime" / "99.99% SLA" | **Remove / soften now** | A relied-upon uptime promise is an enforceable warranty; no monitoring or status page exists behind it. |
| "94.7% Accuracy" / "F1: 0.947" | **Remove now** | No model is trained/evaluated; figure is a seeded literal. Bare methodology-free accuracy is the exact pattern FTC's Workado order targets (injunctive substantiation risk). |
| Model lineup (XGBoost / RoBERTa / Whisper Large v3 / GPT-4o fine-tuned) | **Correct to actual** | Scoring is heuristic; composer uses Claude Haiku; churn/RoBERTa not present; transcription uses Whisper base + Claude Sonnet. Name only what runs. |
| Pricing tiers / SSO / SCIM | **Gate or soften** | No billing/entitlement code; SSO/SCIM not implemented. |

Legal framing (Phase 3 §3, verifier-corrected): the exposure theory is FTC Act §5 deception — a
material representation likely to mislead, **actionable without proof of breach or intent**;
"lack of substantiation" can suffice. The realistic risk on the accuracy claim is an injunctive
substantiation order, not a multimillion-dollar fine — but the SOC 2 / uptime / GDPR badges are the
genuinely dangerous ones. **This workstream should run in parallel with F1–F2 because it is hours of
copy editing, not engineering.** The `fix/honest-marketing-claims` branch exists but its edits were
never written — start fresh from the table above.

---

## 6. What Phase 4 changes about the plan

Nothing in validation moved a finding off the list, but three things sharpen sequencing:

1. **F1 (Gmail webhook) is the only true P0** — unauthenticated and live. It jumps ahead of the
   staged F2 work for *first* attention even though F2 has a branch.
2. **F3 should land with/just after F4**, not later — F4 is the proof that the F3 backstop is needed,
   and fixing F4 alone still leaves every other handler one typo away from the same class of bug.
3. **Claims integrity is promoted to "do in parallel, this week"** — Phase 3 makes it the
   highest liability-per-hour item on the board, and it does not compete for the same engineering
   focus as the isolation work.

See `RISK_REGISTER.md` for the scored register and `ROADMAP_30_60_90.md` for the sequenced plan.
```