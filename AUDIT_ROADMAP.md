# NovaCRM Architectural Review — Remediation Roadmap (Phase-4 Decision Tree)

Generated from 28 confirmed findings. All findings were verified as accurate; severities below are the **adjusted** verdict severities (not the original finding severities). This roadmap is structured for an orchestrated parallel-worktree fix with independent re-verification.

## Confirmed Findings by Adjusted Severity

| Severity | Count |
|----------|-------|
| Critical | 2 |
| High     | 4 |
| Medium   | 9 |
| Low      | 13 |
| **Total**| **28** |

- **Critical (2):** Slack webhook signature check is skipped when `SLACK_SIGNING_SECRET` is empty (should fail-closed); `POST /agents/{id}/run` is a stub that dispatches no Celery task.
- **High (4):** OAuth callback trusts an unverified client-supplied `state` value (Gmail+Slack); `workspace_id` is read from client-writable JWT metadata (lets a user reference another workspace's records); message→contact linking never happens; beat-scheduled agent tasks have broken signatures.
- **Medium (9):** Slack token-revocation silently swallowed; synchronous enrichment blocking ingest; frontend `.catch(()=>[])` swallowing; Slack callback accepts requests not tied to the initiate flow; ingest silent error swallowing; health check missing Redis/Celery; workers lack logging; agent `last_run`/`accuracy` cosmetic staleness; `useJobPoller` polling a non-existent task.
- **Low (13):** Sentiment dead-code; Slack subject hardcode; `useJobPoller` infinite poll edge case; dashboard partial-failure UX; EventSource session token passed in URL query string; `API_URL` env/docs gap; projects RLS misconfig; missing FK indexes; SSE silent swallow; followup HITL silent swallow; minimal worker logging; `ContactResponse`/`DealResponse` schema nits; pagination gaps.

> Note: several "Low" items collapse into shared workstreams (e.g. all silent-swallow / logging items, all schema nits). They are not 13 independent units of work.

---

## 1. Workstreams (de-duplicated clusters)

### WS-A — OAuth State Integrity (signed/nonce-bound state for Gmail + Slack)
**Findings:** OAuth callback trusts an unverified client-supplied `state` (high); Slack callback not tied to the initiate flow (medium); Gmail callback has no nonce replay protection (medium). These three are **the same root cause** — callbacks trust an unauthenticated, client-supplied `state` and derive `workspace_id` from it. Gmail's `csrf` UUID is cosmetic (never stored/checked); Slack has no nonce at all.
**Fix approach:** HMAC-sign state at the already-authenticated `/auth/*` initiate endpoints using a server secret over `{wid, exp, nonce}` (or a short-lived store). On callback, verify signature + expiry, then derive `workspace_id` from the verified payload — never from raw state. Do NOT add `Depends(get_current_user)` to callbacks (browser redirect carries no Bearer; would 401 every connect). Validate the existing Gmail `csrf` too.
**Files:** `apps/api/app/routers/gmail.py`, `apps/api/app/routers/slack.py` (+ optional small state-helper module). Possibly `apps/web/src/app/auth/{gmail,slack}/callback/page.tsx` (no change needed if same-origin).
**Risk:** Medium — touches live OAuth connect flow; must not break legitimate connects. Requires careful re-test of both connect flows.
**Type:** Deploy (code). No data migration.

### WS-B — Tenant Isolation Boundary (stop trusting client-writable workspace_id)
**Findings:** A user can update their own `workspace_id` in onboarding, and `workspace_id` read from client-writable JWT metadata lets a user reference another workspace's records (high).
**Fix approach:** (1) Delete the `/auth/verify` reconciliation branch that overwrites an existing user's `workspace_id` from JWT (auth.py). (2) Move the binding claim from client-writable `user_metadata` to server-only `app_metadata` in `_sync_workspace_metadata`; read `app_metadata.workspace_id` in `get_current_user` auto-provision and `/auth/verify`. (3) Remove the client-side `supabase.auth.updateUser({data:{workspace_id}})` in onboarding (server already binds in `POST /workspaces`). Backfill existing users' `app_metadata` via admin PATCH.
**Files:** `apps/api/app/routers/auth.py`, `apps/api/app/dependencies.py`, `apps/web/src/app/onboarding/page.tsx`.
**Risk:** HIGH — this is the entire tenant-isolation boundary. A mistake locks every user out or leaves the gap open. Needs independent re-verification (confirm a user cannot reference another workspace's data post-fix). Requires a one-time **app_metadata backfill** for existing users (USER/ops action — see §5).
**Type:** Deploy (code) + one-time data backfill (admin API).

### WS-C — Slack HITL Signature Enforcement (fail-closed)
**Findings:** Slack signature verification is skipped when the secret is unset — **critical, reachable in production** (an unverified `POST /slack/interactions` can trigger an email send through a user's connected Gmail; the `%` LIKE wildcard widens the match).
**Fix approach:** In `_verify_slack_signature`, `return False` (fail-closed) when secret unset; the endpoint already 403s on False. Tighten the `hitl_id` LIKE match (reject `%`/`_`, or match a structured column). Add startup assertion that `SLACK_SIGNING_SECRET` is set when Slack HITL enabled.
**Files:** `apps/api/app/routers/slack_interactions.py`, `apps/api/app/config.py` (optional startup check).
**Risk:** Medium code risk, but **the fix is inert unless `SLACK_SIGNING_SECRET` is actually set in prod** — fail-closed will then block ALL Slack interactions until the secret is configured. Requires USER to set the env var (see §5).
**Type:** Deploy (code) + **USER prod env change** (set `SLACK_SIGNING_SECRET`).

### WS-D — Agent Execution Pipeline (make "Run" real + nightly beat + state)
**Findings:** `POST /agents/{id}/run` stub dispatches no task (critical); beat tasks have broken signatures / never run (high); `useJobPoller` polls non-existent task forever (medium); `last_run` stuck at "Never" (medium); `tasks_today` never increments (low); `accuracy` static seed (medium); `useJobPoller` infinite-poll edge case (low). All centered on the agent-run lifecycle.
**Fix approach (layered):**
1. **Beat fix (high, independent):** add `optimize_pipeline_all()` / `compute_deal_health_all()` no-arg dispatcher tasks that enumerate workspaces and `.delay(ws_id)` each; repoint `beat_schedule`.
2. **Run dispatch (critical):** branch `run_agent` by `agent.type` — dispatch real tasks for `pipeline_optimizer`/`pm_agent`; return 501 for types with no backing task (`email_composer`, `call_summarizer`, `sentiment_analyzer`, `semantic_sorter`); use the real Celery `task.id` as `job_id`; set `last_run`/`tasks_today` and write `agent_run` event only after dispatch.
3. **Poller robustness (medium+low):** add failure-count cap + 401 handling + max-poll cap in `useJobPoller.ts`; have `/jobs/{id}` return non-PENDING for unknown IDs; don't start poller for 501 stub paths.
4. **Cosmetic metrics:** stop presenting fabricated `accuracy` sparkline / `tasks_today` until real outcomes exist (or derive from `ActivityEvent`).
**Files:** `apps/api/app/routers/agents.py`, `apps/api/app/workers/celery_app.py`, new dispatcher tasks in `apps/api/app/workers/`, `apps/web/src/hooks/useJobPoller.ts`, `apps/web/src/app/(app)/agents/page.tsx`, `apps/web/src/app/(app)/dashboard/page.tsx`.
**Risk:** Medium-High — touches the product's headline feature; internal interdependency means it should be ONE workstream, not split across agents.
**Type:** Deploy (code).

### WS-E — Ingest Enrichment Correctness (contact linking + sentiment activation)
**Findings:** message→contact linking never occurs (high); sentiment→`contact.ml_score` never persisted (low — same root cause). Both fixed by populating `message.contact_id`.
**Fix approach:** In `ingest.py`/`slack_ingest.py`, after computing `sender_email`, parse the bare address (`email.utils.parseaddr`, lowercased) and SELECT a workspace-scoped Contact by case-insensitive email; set `message.contact_id` before flush. Link-only, no auto-create. This single change also activates the dead sentiment→`ml_score` path. Backfill the 200 existing NULL rows with the same parse+match.
**Files:** `apps/api/app/workers/ingest.py`, `apps/api/app/workers/slack_ingest.py`.
**Risk:** Low-Medium — additive; must use parsed address (raw RFC2822 won't match). Backfill is data-only and reversible.
**Type:** Deploy (code) + optional data backfill (in-app script).

### WS-F — Ingest Performance (decouple enrichment from critical path)
**Findings:** synchronous sentiment+clarity (and `_is_deal_relevant`, `extract_tasks`) block the ingest worker — up to ~800 sequential Claude calls per 200-msg batch (medium).
**Fix approach:** `_run_sync` does fetch/dedupe/insert only; enqueue per-message (or chord/group) post-ingest enrichment tasks that run sentiment+clarity off the critical path. Interim: switch to `AsyncAnthropic` + `asyncio.gather`.
**Files:** `apps/api/app/workers/ingest.py` (+ new enrichment task module).
**Risk:** Medium — restructures the ingest task; **overlaps WS-E** (both edit `ingest.py`). Must be sequenced with WS-E, not parallel.
**Type:** Deploy (code).

### WS-G — Slack Sync Reliability (surface auth failure, stop blind last_sync bump)
**Findings:** Slack token-revocation silently swallowed + unconditional `last_sync` bump blinds monitoring (medium).
**Fix approach:** Raise distinct `SlackAuthError` on `invalid_auth`/`token_revoked`/etc.; on auth error, do NOT bump `connector.last_sync`; persist failure (ActivityEvent or `last_error` column); fix `connector_status` to stop hardcoding `'active'`.
**Files:** `apps/api/app/services/slack_client.py`, `apps/api/app/workers/slack_ingest.py`, `apps/api/app/routers/gmail.py` (connector_status). Optional `apps/api/app/models/connector.py` (+ migration for `last_error`).
**Risk:** Low-Medium. **Overlaps WS-E (slack_ingest.py)** — sequence or merge with WS-E's slack edits.
**Type:** Deploy (code); optional migration if adding `last_error`.

### WS-H — Backend Observability (logging + silent-swallow removal in workers)
**Findings:** ingest silent error swallowing (medium); no logging in most workers (medium); minimal structured worker logging (low); SSE silent swallow + no rollback (low); followup HITL silent swallow (low); health check missing Redis/Celery (medium).
**Fix approach:** Add `logging.getLogger(__name__)` / `get_task_logger` to all unlogged workers; replace bare `except: pass`/`continue` with logged handlers (key=value, message_id/workspace/exc). SSE: add `await db.rollback()` + log + break-after-N. Health: add Redis PING (+ optional Celery ping on `/health/deep`), keep HTTP 200.
**Files:** `apps/api/app/workers/{ingest,enrich_contact,followup_sequences,slack_ingest,transcribe,deal_health_worker,embed_contacts,pipeline,score_contact}.py`, `apps/api/app/routers/events.py`, `apps/api/app/main.py`.
**Risk:** Low — purely additive observability. **High file overlap with WS-E/F/G in `ingest.py` and `slack_ingest.py`** — those handlers should be folded into whichever WS touches those files first to avoid merge conflicts.
**Type:** Deploy (code).

### WS-I — Frontend Error Surfacing (user-facing error states)
**Findings:** widespread `.catch(()=>[])` swallowing (medium — real offenders: inbox + tasks list loads); dashboard `Promise.all` partial-failure UX (low).
**Fix approach:** Add `error` state + inline retry banner to `inbox/page.tsx` and `tasks/page.tsx` (mirror existing `useDeals` pattern). Add a single `pmError` flag + "some metrics unavailable" notice to dashboard PM block. Leave demo/decorative catches alone.
**Files:** `apps/web/src/app/(app)/inbox/page.tsx`, `apps/web/src/app/(app)/tasks/page.tsx`, `apps/web/src/app/(app)/dashboard/page.tsx`.
**Risk:** Low. Dashboard file overlaps WS-D (poller) — coordinate.
**Type:** Deploy (code).

### WS-J — Credential Handling (move EventSource token out of the URL)
**Findings:** EventSource session token passed in URL query string, where it can appear in browser history and server logs (low, CWE-598).
**Fix approach:** Read Supabase session server-side from cookies in `/api/events/route.ts` (existing `createServerClient` helper); drop `&token=` from the EventSource URL in dashboard (cookies auto-sent same-origin).
**Files:** `apps/web/src/app/api/events/route.ts`, `apps/web/src/app/(app)/dashboard/page.tsx`.
**Risk:** Low. Dashboard file overlaps WS-D/WS-I — coordinate.
**Type:** Deploy (code).

### WS-K — DB Schema & RLS Hygiene (migration-only)
**Findings:** projects RLS uses unconfigured `app.workspace_id` setting (low); missing workspace_id FK indexes (low).
**Fix approach:** New migration: drop/recreate `projects_policy` to the `auth.uid()` pattern used by all other tables; add `idx_clarity_scores_workspace` + `idx_activity_events_workspace` (+ optionally agents/metric_templates with `IF NOT EXISTS`).
**Files:** new `apps/api/migrations/00X_*.sql`.
**Risk:** Low — idempotent, additive. **Migration apply against Supabase is a USER/ops action** (see §5).
**Type:** Migration (must be applied to prod DB).

### WS-L — API Schema & Pagination Correctness
**Findings:** `ContactResponse` omits `updated_at` (low); `DealResponse.created_at` wrongly optional (low); pagination gaps + ingest 200-msg silent cap (low).
**Fix approach:** Add `updated_at` to `ContactResponse`; make `DealResponse.created_at` required. Add `limit`/`offset` Query params to the 5 unbounded list endpoints (keep list shape). For ingest cap, loop until `nextPageToken` exhausted (bounded) or return `truncated: bool` — coordinate with WS-E (ingest.py).
**Files:** `apps/api/app/routers/{contacts,deals,tasks,messages,projects}.py`, `apps/api/app/workers/ingest.py` (cap — overlaps WS-E/F).
**Risk:** Low. Ingest-cap piece overlaps WS-E/F.
**Type:** Deploy (code).

### WS-M — Docs/Config Consistency
**Findings:** missing `API_URL` in docker-compose + stale DEPLOY.md (low).
**Fix approach:** Add `API_URL: ${API_URL:-http://localhost:8000}` to compose anchor; fix DEPLOY.md to mark `API_URL` REQUIRED for API/worker/beat and correct stale "callbacks derive from FRONTEND_URL" text.
**Files:** `docker-compose.yml`, `DEPLOY.md`.
**Risk:** Trivial. **Also requires verifying `API_URL` is set on live Railway services** (USER/ops — see §5).
**Type:** Config/docs only + USER verification of prod env.

---

## 2. Priority Ranking — (Severity × Scope-of-Impact) ÷ Effort

### QUICK WINS (high value, low effort — do first)
| Rank | WS | Why |
|------|----|-----|
| 1 | **WS-C** | Critical, reachable in production (unverified email send), but the code fix is ~2 lines (`return False` + LIKE tightening). Highest value-per-effort. Gated on USER setting the secret. |
| 2 | **WS-B** | High; the entire tenant boundary; small, surgical code change (delete branch + metadata key swap). Large scope of impact, low LOC. |
| 3 | **WS-A** | Two highs+mediums collapse to one signed-state change in 2 files. |

### DEEP WORK (high value, higher effort)
| Rank | WS | Why |
|------|----|-----|
| 4 | **WS-D** | One critical + one high + multiple mediums, but interdependent and touches FE+BE+beat — genuine multi-file effort. |
| 5 | **WS-E** | High; unblocks sentiment/enrichment/deal-health chain; moderate effort, foundation for WS-F. |
| 6 | **WS-F** | Medium; worker-saturation; restructures ingest task (must follow WS-E). |

### MEDIUM-EFFORT / MEDIUM-VALUE
| Rank | WS | Why |
|------|----|-----|
| 7 | **WS-G** | Medium; re-enables monitoring; small but overlaps WS-E files. |
| 8 | **WS-H** | Several mediums+lows; broad but mechanical; overlaps E/F/G files. |
| 9 | **WS-I** | Medium; genuine UX gap in 2-3 FE files. |

### LOW-EFFORT CLEANUP (batch last)
| Rank | WS | Why |
|------|----|-----|
| 10 | **WS-K** | Migration-only hygiene; latent. |
| 11 | **WS-J** | Defense-in-depth credential handling. |
| 12 | **WS-L** | Schema nits + pagination; mostly latent at current scale. |
| 13 | **WS-M** | Docs/config; trivial. |

---

## 3. Dependency Ordering & Parallel-Safety

```
PARALLEL-SAFE BATCH 1 (no file overlap — launch worktree agents simultaneously):
  WS-C  (slack_interactions.py, config.py)
  WS-B  (auth.py, dependencies.py, onboarding/page.tsx)
  WS-A  (gmail.py, slack.py)            ── NOTE: WS-G touches gmail.py connector_status
  WS-K  (new migration file only)
  WS-J  (api/events/route.ts, dashboard/page.tsx)  ── NOTE: dashboard overlaps WS-D/WS-I
  WS-M  (docker-compose.yml, DEPLOY.md)

SEQUENTIAL CHAIN — INGEST FAMILY (shared files: ingest.py, slack_ingest.py):
  WS-E  →  WS-F  →  (WS-G slack edits)  →  (WS-H ingest/slack logging)  →  (WS-L ingest cap)
  These MUST be sequential or merged into one ingest worktree. ingest.py and slack_ingest.py
  are edited by E, F, G, H, and L — do NOT assign to separate parallel agents.

SEQUENTIAL/COORDINATED — AGENT & FRONTEND FAMILY:
  WS-D owns: agents.py, celery_app.py, new worker tasks, useJobPoller.ts,
             agents/page.tsx, dashboard/page.tsx.
  WS-I owns: inbox, tasks, dashboard. WS-J owns: events route + dashboard.
  → dashboard/page.tsx is touched by WS-D, WS-I, WS-J. Assign dashboard edits to ONE agent
    (fold WS-I dashboard banner + WS-J token removal into the WS-D worktree, OR serialize).

HARD ORDER CONSTRAINTS:
  - WS-F after WS-E (F restructures the loop E modifies).
  - WS-A's Gmail edit and WS-G's gmail.py connector_status edit: different functions, low
    conflict risk, but assign to the same worktree or serialize to be safe.
  - WS-B backfill (app_metadata) must be applied BEFORE WS-B code deploy goes live to users,
    or users briefly lose workspace binding. Coordinate code-deploy + backfill as one cutover.
```

**Parallel-safe for independent worktree agents:** WS-C, WS-B, WS-A, WS-K, WS-M (and WS-J/WS-I if dashboard edits are serialized to one owner).
**Must-be-sequential / single-owner:** the INGEST FAMILY (E→F→G→H→L on ingest.py/slack_ingest.py), and the AGENT+DASHBOARD FAMILY (WS-D + dashboard edits of I/J).

---

## 4. Per-Workstream Deploy/Data/Config Classification

| WS | Type | Risk | Needs |
|----|------|------|-------|
| WS-A | Deploy (code) | Med | Re-test both OAuth connects |
| WS-B | Deploy + data backfill | **High** | app_metadata backfill cutover |
| WS-C | Deploy + **prod env** | Med | USER sets `SLACK_SIGNING_SECRET` |
| WS-D | Deploy (code) | Med-High | FE+BE+beat coordination |
| WS-E | Deploy (code) + opt. backfill | Low-Med | 200-row contact-link backfill |
| WS-F | Deploy (code) | Med | After WS-E |
| WS-G | Deploy (+opt. migration) | Low-Med | Overlaps WS-E |
| WS-H | Deploy (code) | Low | Overlaps E/F/G |
| WS-I | Deploy (code) | Low | Dashboard coord |
| WS-J | Deploy (code) | Low | Dashboard coord |
| WS-K | **Migration** | Low | Apply to Supabase |
| WS-L | Deploy (code) | Low | Ingest piece overlaps E/F |
| WS-M | Config/docs | Trivial | Verify prod `API_URL` |

---

## 5. Requires the USER (external gates — cannot be done by fix agents)

1. **WS-C — Set `SLACK_SIGNING_SECRET` in Railway API env.** The fail-closed fix will block ALL Slack HITL interactions until this is set. This is the one item where the code fix without the env change degrades a feature. **Set the secret first, then deploy fail-closed.** (Currently confirmed EMPTY in prod — unverified interactions return `{"ok":true}`.)
2. **WS-B — One-time `app_metadata` backfill for existing Supabase users** via admin PATCH (move `workspace_id` from `user_metadata` → `app_metadata`). Must be coordinated as a cutover with the WS-B code deploy or users transiently lose workspace binding. Touches the Supabase auth admin API.
3. **WS-K — Apply the new RLS/index migration to the production Supabase database.** Migration files can be written by an agent; applying them to prod is a USER/ops action.
4. **WS-M — Verify `API_URL` is actually set on the live Railway API/worker/beat services.** Not inspectable read-only; if unset, OAuth redirect URIs break in prod. Verify and set if missing.
5. **General:** repo is on `master`. Per fix-doctrine, all fix worktrees must **branch first**; do not commit fixes to `master`.

---

## 6. Recommended Phase-4 Execution Plan

**Wave 1 (parallel worktrees, security-critical, low LOC):** WS-C, WS-B, WS-A, WS-K — launch as 4 isolated worktree agents (no file overlap). Gate WS-C/WS-B go-live on the USER env+backfill actions. Independently re-verify each before merge: send an unsigned Slack POST and confirm it is rejected; confirm a user cannot reference another workspace's data; confirm a tampered OAuth state is rejected; query RLS directly to confirm isolation.

**Wave 2 (single-owner ingest worktree, sequential):** WS-E → WS-F, folding WS-G/WS-H/WS-L ingest+slack edits into the same worktree to avoid conflicts on `ingest.py`/`slack_ingest.py`.

**Wave 3 (agent+dashboard worktree):** WS-D, folding WS-I and WS-J dashboard edits into it (single owner of `dashboard/page.tsx`).

**Wave 4 (cleanup, parallel):** remaining WS-H non-ingest (events.py, main.py health), WS-L non-ingest (schema/pagination), WS-J (if not folded), WS-M docs.
