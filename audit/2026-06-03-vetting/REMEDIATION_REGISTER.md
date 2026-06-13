# NovaCRM — Remediation Register (audit 2026-06-03)

Canonical status of the vetting program's **PROVEN** findings and their path to closure.
The `crm-pm` agent reads this each run and re-verifies every open row against `origin/master`
+ Railway, then rewrites the Status column. Full evidence (commands + observed output) for
each row lives in `phase2/`.

**Severity:** 🔴 critical · 🟠 high
**Status flow:** OPEN → FIX-STAGED (branch exists) → MERGED (on origin/master) → DEPLOYED (live on Railway) → VERIFIED (re-tested in prod)

## Source of truth

This register's **Status column is authoritative** and is owned by `crm-pm`, which re-verifies
every row against `origin/master` code + Railway on each run. Treat any other tracker as
secondary to this column.

`project-sync` **must NOT close audit findings.** It infers task completion from commit-message
text, and on **2026-06-13** it over-closed two findings by partial commit-message matching:
- it closed **CLAIM** off `291d230` ("honest marketing claims" wording) even though the
  fabricated ML lineup is still rendered on `page.tsx` — the claim is only *partially* fixed; and
- it closed **F2** (workspace takeover) off `76839ee` ("close cross-tenant IDOR + fail-open
  webhooks"), which actually fixed F1/F4 — F2's code fix landed separately, and its **ops
  residual (app_metadata backfill + cutover) is still outstanding**, so the finding is not closed.

Closing on commit-message keywords is exactly the failure mode this rule prevents: a commit that
*mentions* a topic is not proof the finding's exit test passes. A finding advances only when its
exit test is **observed** passing against `origin/master` + Railway, and only `crm-pm` may move it.

## Status — verified against `origin/master` 2026-06-13

| # | Finding | Sev | Status | Fix branch / commit | Evidence |
|---|---------|-----|--------|--------------------|----------|
| 1 | Gmail Pub/Sub webhook **fail-open** — zero-credential email amplification | 🔴 | **MERGED** — fix on `origin/master`: `routers/gmail.py:_verify_pubsub_secret` returns `False` when `GMAIL_WEBHOOK_SECRET` is unset (fail **closed**). **Residual (ops):** `GMAIL_WEBHOOK_SECRET` + `GMAIL_PUBSUB_TOPIC` still unset in Railway, so the webhook currently rejects **everything** — Gmail push ingest is inert in prod until they are set. | `76839ee` (PR #2) | phase2/evidence-webhook-idor.md §A1 |
| 2 | Cross-tenant **workspace takeover** (read+write) — `workspace_id` lived in user-writable `user_metadata` | 🔴 | **MERGED** — fix on `origin/master`: `dependencies.py` binds workspace only from server-only `app_metadata` via `_read_bound_workspace_id`; user-writable metadata is no longer trusted. **Residual (ops):** `app_metadata` backfill for existing users + cutover confirmation. *(Not closed by `project-sync`'s `76839ee` match — see Source of truth.)* | `fix/ws-b` → merged | phase2/evidence-takeover.md · branch-worktree/EVIDENCE_workspace_takeover_metadata.md |
| 3 | **RLS effectively bypassed** — API connects as one shared `BYPASSRLS` role for all tenants; `call_summaries` has zero enforced policies | 🔴 | **OPEN** — migration `013_force_rls.sql` shipped but **INERT**: the API still connects as a shared `BYPASSRLS` role, so `FORCE ROW LEVEL SECURITY` does not constrain it and `call_summaries` is still effectively policy-free at runtime. Code prep in progress today (lane `rls-dos`), gated behind a flag until the ops role-swap cutover. | `013_force_rls.sql` (inert) | phase2/evidence-rls.md |
| 4 | `GET /jobs/{job_id}` **IDOR** + missing-`WHERE` cross-tenant disclosure | 🟠 | **MERGED** — fix on `origin/master`: `routers/agents.py:get_job_status` reads the owning workspace from the dispatch marker (`_job_owner_workspace`) and returns **404** on mismatch. | `76839ee` (PR #2) | phase2/evidence-missing-where.md · poc_jobs_idom.py |
| 5 | **Cost/DoS** — one tenant can drain spend + starve the 2-slot worker queue; rate limiter degrades to a single global IP bucket | 🟠 | **OPEN** — `limiter.py` keys on IP because `request.state.user` is never set, so it degrades to one global bucket; there is no per-tenant spend cap and `reprocess` is unbounded. Code prep in progress today (lane `rls-dos`). | `fix/rls-dos` (in progress) | phase2/evidence-cost-dos.md · branch-worktree/REFUTATION_EVIDENCE_ratelimiter.md |
| 6 | **Celery beat broken** (`workspace_id` TypeError) — scheduled tasks never executed; Agent-Run was a stub in prod | 🟠 | **MERGED** — fix on `origin/master`: `workers/celery_app.py` `beat_schedule` now points at the no-arg fan-out dispatchers `optimize_pipeline_all` / `compute_deal_health_all`. **Residual:** verify a scheduled cycle runs SUCCESS and recomputes a `health_score` off the default 100 in prod. | `fix/ws-d-agent-execution` → merged | phase2/evidence-beat.md · branch-worktree/EVIDENCE_celery_beat_typeerror.md |
| 7 | **Delete-contact orphans linked PII** — no ORM delete cascade | 🟠 | **OPEN** — `routers/contacts.py:delete_contact` only does `db.delete(contact)` and its docstring **falsely** claims it deletes "all cascade-linked records"; linked PII (`messages`, `call_summaries`) is left orphaned. Fix in progress today (lane `delete-cascade`). | `fix/delete-cascade` (in progress) | phase2/evidence-delete-contact.md |

## Separate workstream — claims integrity

| Item | Sev | Status | Evidence |
|------|-----|--------|----------|
| Landing-page claims — compliance badges (SOC 2 Type II · 99.9% uptime · GDPR Compliant) | 🟠 | **MERGED** — the compliance badges were removed earlier from `page.tsx`. | phase1/CLAIMS_REGISTER.md |
| Landing-page claims — fabricated ML lineup (94.7% accuracy · XGBoost / RoBERTa / GPT-4o / LightGBM · F1 0.947) | 🟠 | **OPEN — PARTIALLY FIXED** — the fabricated ML claims are **still live** on `apps/web/src/app/page.tsx` (94.7% "Accuracy" stat, `XGBoost v2` / `F1: 0.947`, `GPT-4o Fine-tuned`, `RoBERTa Fine-tuned`, `LightGBM`, `f1:0.947→0.951` log line). Fix in progress today (lane `claims`). *(Not closed by `project-sync`'s `291d230` match — see Source of truth.)* | phase1/CLAIMS_REGISTER.md |

Detail on the full claims set (pricing/SSO/SCIM tiers, model-lineup correction targets) is in
`phase1/CLAIMS_REGISTER.md` and `phase4/`. Tiers ($49/$149/Custom) remain to be gated or softened.

## Refuted in prod — NOT debt (recorded so they're not re-chased)

| Finding | Note |
|---------|------|
| CORS reflection | Malicious origin is **not** reflected in `Access-Control-Allow-Origin`. phase2/evidence-cors.md |
| Slack Events webhook fail-open | Signing secret **IS** set in prod → refuted. ⚠️ **Corrects the 2026-06-03 AM PM brief**, which assumed it unset and ranked it #1 critical. Latent risk only if a deploy loses the secret. phase2/evidence-webhook-idor.md §A2 |
| Browser direct-read under anon key | Refuted at runtime for this deployment (client calls are auth, not table reads). phase2/evidence-web-from.md |

## Priority order (remaining open work)

1. **#3 RLS / #5 cost-DoS** — tenant-isolation backstop + abuse limiting; code prep in progress
   (lane `rls-dos`), F3 inert behind a flag until the ops role-swap cutover.
2. **#7 delete cascade** — application-level PII erasure; fix in progress (lane `delete-cascade`).
3. **CLAIM ML lineup** — remove the fabricated 94.7% / XGBoost / RoBERTa / GPT-4o / LightGBM
   lineup from `page.tsx`; fix in progress (lane `claims`).
4. **Ops residuals on the MERGED findings** — set `GMAIL_WEBHOOK_SECRET` + `GMAIL_PUBSUB_TOPIC`
   (#1); run the `app_metadata` backfill + cutover (#2); verify a scheduled beat cycle in prod (#6).
   These advance MERGED → DEPLOYED → VERIFIED and are owned by ops, not code.

---
_Initial population: 2026-06-03, from Phase 2 adversarial evidence. Status reconciled to
`origin/master` ground truth on 2026-06-13: F1/F2/F4/F6 are MERGED (F1/F2/F6 carry ops residuals);
F3/F5/F7 remain OPEN with code prep in flight; the CLAIM workstream is partially fixed (badges
removed, ML lineup still live). Phase 4 (narrative report + risk register + 30/60/90) **is** written
and lives in `phase4/`. The `crm-pm` agent maintains the Status column going forward._
