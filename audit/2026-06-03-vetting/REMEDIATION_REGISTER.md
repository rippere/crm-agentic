# NovaCRM — Remediation Register (audit 2026-06-03)

Canonical status of the vetting program's **PROVEN** findings and their path to closure.
The `crm-pm` agent reads this each run and re-verifies every open row against `origin/master`
+ Railway, then rewrites the Status column. Full evidence (commands + observed output) for
each row lives in `phase2/`.

**Severity:** 🔴 critical · 🟠 high
**Status flow:** OPEN → FIX-STAGED (branch exists) → MERGED (on origin/master) → DEPLOYED (live on Railway) → VERIFIED (re-tested in prod)

## Open — PROVEN

| # | Finding | Sev | Status | Fix branch | Evidence |
|---|---------|-----|--------|-----------|----------|
| 1 | Gmail Pub/Sub webhook **fail-open** — zero-credential email amplification, **live-exploitable in prod** | 🔴 | **VERIFIED** — fails closed since `59a69bb` (merged master, 2026-06-07); `GMAIL_WEBHOOK_SECRET` confirmed set in Railway prod | `59a69bb` (#2) | phase2/evidence-webhook-idor.md §A1 |
| 2 | Cross-tenant **workspace takeover** (read+write) — `workspace_id` lives in user-writable `user_metadata` | 🔴 | **MERGED** — bound via server-only `app_metadata` (`apps/api/app/routers/auth.py`, `dependencies.py`); confirmed already-closed and re-verified in `59a69bb` (#2) | `fix/ws-b` (5252714) → `59a69bb` | phase2/evidence-takeover.md · branch-worktree/EVIDENCE_workspace_takeover_metadata.md |
| 3 | **RLS effectively bypassed** — API connects as one shared `postgres` BYPASSRLS role for all tenants; `call_summaries` has zero policies | 🔴 | OPEN | — | phase2/evidence-rls.md |
| 4 | `GET /jobs/{job_id}` **IDOR** + missing-`WHERE` cross-tenant disclosure | 🟠 | **MERGED** — Redis dispatch marker now carries owning `workspace_id`, 404s foreign callers across all 12 Celery dispatch sites (`59a69bb`, #2) | `59a69bb` (#2) | phase2/evidence-missing-where.md · poc_jobs_idom.py |
| 5 | **Cost/DoS** — one tenant can drain spend + starve the 2-slot worker queue; rate limiter degrades to a single global IP bucket | 🟠 | OPEN | — | phase2/evidence-cost-dos.md · branch-worktree/REFUTATION_EVIDENCE_ratelimiter.md |
| 6 | **Celery beat broken** (`workspace_id` TypeError) — scheduled tasks never execute; Agent-Run is a stub in prod | 🟠 | FIX-STAGED | `fix/ws-d-agent-execution` (in progress) | phase2/evidence-beat.md · branch-worktree/EVIDENCE_celery_beat_typeerror.md |
| 7 | **Delete-contact orphans linked data** — no ORM delete cascade | 🟠 | OPEN | — | phase2/evidence-delete-contact.md |

## Refuted in prod — NOT debt (recorded so they're not re-chased)

| Finding | Note |
|---------|------|
| CORS reflection | Malicious origin is **not** reflected in `Access-Control-Allow-Origin`. phase2/evidence-cors.md |
| Slack Events webhook fail-open | Signing secret **IS** set in prod → refuted. ⚠️ **Corrects the 2026-06-03 AM PM brief**, which assumed it unset and ranked it #1 critical. Latent risk only if a deploy loses the secret. phase2/evidence-webhook-idor.md §A2 |
| Browser direct-read under anon key | Refuted at runtime for this deployment (client calls are auth, not table reads). phase2/evidence-web-from.md |

## Separate workstream — claims integrity

Landing-page claims to substantiate or soften (detail in `phase1/CLAIMS_REGISTER.md`):
SOC 2 Type II · 99.9% uptime · GDPR compliant · "94.7% accuracy" · XGBoost / RoBERTa / Whisper / GPT-4o model lineup · $49/$149/Custom tiers.
The `fix/honest-marketing-claims` branch was created but its edits were never written (session was blocked) — start fresh from this list.

## Priority order

1. ~~**#1 Gmail webhook**~~ — **VERIFIED** closed (`59a69bb`, secret set in prod).
2. ~~**#2 workspace takeover**~~ — **MERGED** (`59a69bb`).
3. **#3 RLS** / ~~**#4 IDOR**~~ — **#4 MERGED** (`59a69bb`); **#3** still open — introduce per-request DB scoping rather than the shared BYPASSRLS role.
4. **#6 beat / Agent-Run** — the headline "agentic" feature is a confirmed stub; `fix/ws-d` in progress.
5. **#5 cost/DoS**, then **#7 delete cascade**, then **claims integrity**.

---
_Initial population: 2026-06-03, from Phase 2 adversarial evidence. The `crm-pm` agent maintains the Status column going forward. Phase 4 (narrative report + risk register + 30/60/90) not yet written._
