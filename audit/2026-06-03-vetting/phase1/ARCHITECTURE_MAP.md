# NovaCRM — Architecture Map (Phase 1 Synthesis)

**Worktree:** `/tmp/crm-signup-fix` · **Branch:** `fix/signup-confirm-redirect` · **HEAD:** `429da2f`
**Caveat (load-bearing):** This is NOT `master`. It is the signup-confirm-redirect fix branch. The synthesizer confirmed prod (`https://www.riphere.com`) is reachable and serves this code's routes (`/`, `/dashboard`, `/contacts`, `/login` all 200), but a diff vs `master` was not taken. Treat findings as "deployed-branch reality," and re-confirm against `master` before remediation.

**Product naming is itself unresolved:** FastAPI title/package = `CRM-Agentic`; README/UI/MCP = `NovaCRM`; config example brand + auth-callback comment + live domain = `riphere(.com)`. Three names, one product.

---

## 1. Subsystem Inventory

| # | Subsystem | Tech | Role | Health (1-line) |
|---|-----------|------|------|-----------------|
| 1 | **Web shell / auth** | Next.js 16 App Router, `@supabase/ssr` | Marketing landing + Supabase-auth'd app shell; sole server-side guard in `(app)/layout.tsx` | Guard works; edge session-refresh **dead** (proxy.ts) |
| 2 | **Web data layer** | api-client + supabase + hooks | "Supabase for auth, FastAPI for data" — but 3 competing access styles | Inconsistent; 2 dead hooks, 1 dead SSE route |
| 3 | **API core / auth** | FastAPI, PyJWT (JWKS ES256), SQLAlchemy | JWT verify + auto-provision User+Workspace + per-handler tenancy | Auth works; tenancy = hand-rolled guard only |
| 4 | **API domain routers** | FastAPI async, pgvector | CRUD for contacts/deals/tasks/projects/messages/events/search | Functional; pagination & several correctness bugs |
| 5 | **API AI subsystem** | Anthropic Claude, Whisper, MiniLM | "Nova" Q&A, MCP server, call transcription, scoring services | Real but thin; `/agents/{id}/run` is a **stub** |
| 6 | **Celery workers** | Celery 5.4 + Redis | Ingest, enrichment, scoring, HITL, health monitor | **2 of 4 beat jobs crash every fire** |
| 7 | **Connectors / OAuth** | Gmail + Slack, Fernet, HMAC state | Per-workspace ingest + outbound email + HITL approve | Gmail token-death silent; Slack Events **dead** |
| 8 | **DB schema / migrations / RLS** | 12 hand-run SQL files + init_docker | Multi-tenant Postgres + pgvector + RLS policies | **RLS inert at runtime**; schema drift |
| 9 | **Docs / marketing** | README, DEPLOY, DEMO_SCRIPT, page.tsx | Promise-of-record | Materially oversells AI/ML + compliance |

---

## 2. Service Topology (Railway 4 services + Supabase + Redis)

```
                         ┌─────────────────────────────────────────────┐
                         │                SUPABASE                      │
                         │  Auth (ES256 JWT + JWKS)  ·  Postgres 16 +    │
                         │  pgvector  ·  Realtime  ·  Admin API · REST   │
                         └───────▲───────────▲──────────────▲───────────┘
   anon key (browser)           │           │ owner/pooler  │ service_role
   + RLS (intended)             │           │ role (asyncpg)│ key (REST)
                                │           │ RLS BYPASSED  │ RLS BYPASSED
┌───────────────┐   Bearer JWT  │           │               │
│ Railway: WEB  │───────────────┼──► ┌──────┴───────────────┴─────┐
│ Next.js       │  REST (95%)        │ Railway: API (FastAPI)     │
│ (standalone)  │◄───────────────────┤  uvicorn · slowapi(IP) ·   │
│ DEMO_MODE flag│  .delay() jobs     │  per-handler ws guard      │
└───────────────┘                    └───┬──────────────┬─────────┘
   ▲   │ direct Supabase                 │ enqueue       │ inline LLM/Gmail
   │   │ (Pattern B): workspaces,         ▼ (Redis)       ▼
   │   │ agents(no ws filter),       ┌─────────┐    Anthropic / Gmail
   │   │ Realtime activity_events    │ REDIS   │    (in request path)
   │   └────────────────────────────►│ broker+ │
   │                                 │ backend │
   │  ┌──────────────────────────┐   └────┬────┘
   │  │ Railway: WORKER          │◄───────┤ single default queue, concurrency=2
   │  │ (prefork c=2, no routing)│        │ NO retry/acks_late/DLQ/time_limit
   │  └──────────────────────────┘        │
   │  ┌──────────────────────────┐        │
   │  │ Railway: BEAT (scheduler)│────────┘ 4 cron tasks (2 crash)
   │  └──────────────────────────┘
   │  ┌──────────────────────────┐
   │  │ Railway: FLOWER (monitor)│
   │  └──────────────────────────┘
   └── Google/Slack OAuth + Pub/Sub push + Slack Events/Interactions (webhooks → API)
```

**Railway services (per DEPLOY.md / railway*.toml):** `web` (Next standalone), `api` (FastAPI), `worker` (Celery prefork c=2), `beat` (scheduler), `flower` (monitor). DEPLOY.md repeatedly recommends `NEXT_PUBLIC_DEMO_MODE=true` on the **web** service during bring-up — a live-config landmine (see §6).

---

## 3. The Data-Flow Split (web → Supabase vs web → FastAPI)

This is the single most important architectural fact. There are **three** competing data-access styles in the web tier, and the intended contract ("Supabase = auth only, FastAPI = all data") is **not** uniformly applied.

| Pattern | Sites | Mechanism | Tenant guard | Verdict |
|---------|-------|-----------|--------------|---------|
| **A (intended, ~95%)** | nearly all hooks/pages | `getSession()` → token + `user_metadata.workspace_id` → `apiClient.* → fetch ${FASTAPI}/workspaces/{id}/...` w/ Bearer | FastAPI per-handler `ws_id` 403 | Dominant; correct shape |
| **B (direct Supabase)** | `layout.tsx`, `useWorkspace`, `Sidebar` (agents), `dashboard` (Realtime) | browser/server anon-key client → `from('workspaces'/'agents')` / Realtime `activity_events` | **RLS only** (and RLS is inert!) | Tenancy hole if RLS missing |
| **C (raw fetch)** | `useRole` (`/me`), `useJobPoller` (`/jobs/:id`), `agents/page.tsx` (`/agents`) | bare `fetch(${FASTAPI}/...)`, bypassing apiClient | FastAPI handler | Bypasses typed client |

**Critical nuance:** `workspace_id` is read from `user_metadata`, which **onboarding writes via `updateUser({data:{workspace_id}})`** — i.e., user-mutable. Pattern-B reads trust it directly for `.eq()` filters. Pattern-A trusts FastAPI to re-verify. **`Sidebar.tsx` queries `agents` with NO `workspace_id` filter at all** — pure RLS reliance. Since RLS is inert (§4), the only thing preventing cross-tenant agent reads in the sidebar is... nothing at the DB layer; it depends entirely on whether RLS policies are actually enforced (they are not, for the API role — but the **browser anon key** path *is* subject to RLS, so the sidebar's safety hinges on anon-key RLS being correctly configured, which was not verifiable from the repo).

`activity_events` is read **four** ways: REST seed (`listActivity`), Realtime `postgres_changes`, Header REST, **plus an orphaned SSE proxy** (`api/events/route.ts`, token-in-URL, zero consumers).

---

## 4. Tenancy & RLS — the load-bearing security story (and why it's hollow)

```
JWT (ES256) ──verify(JWKS)──► supabase_uid ──► User.workspace_id ──► handler: if cu.ws != path.ws → 403
                                                                              └► .where(workspace_id == ...)
                                                                              
DB connection = Supabase pooler "postgres" OWNER role  ──►  auth.uid() is NULL  ──►  RLS matches 0 rows
                                                                              └►  but owner BYPASSES RLS anyway
                                                                              └►  no FORCE ROW LEVEL SECURITY
                                                                              └►  request.jwt.claims GUC never set
```

**RLS is present in DDL but inert at the API tier.** Confirmed by convergent evidence: app returns rows + 324 tests pass *while* policies key on `auth.uid()` that is always NULL → the only way both are true is RLS bypass (owner role). `supabase_rest.py` uses the **service_role key** = also RLS-bypassing. So tenant isolation rests **entirely** on a copy-pasted per-handler guard repeated 50+ times. `dependencies.get_workspace_id` exists to centralize this but is **used by zero routers** (dead). `agents.py` uses a *different* scoping idiom (no path param). One omitted `.where` on any future endpoint = silent cross-tenant leak with no DB backstop. `call_summaries` has **no RLS policy at all** even on paper.

---

## 5. Background Job Schedule (Celery Beat) — and the silent failures

Confirmed in `celery_app.py:27-46`:

| Task | Schedule (UTC) | Signature | Status |
|------|----------------|-----------|--------|
| `pipeline.optimize_pipeline` | 02:00 | `(self, workspace_id)` | **CRASHES** — beat passes `args:[]` → `TypeError: missing workspace_id`. Never ran from scheduler. |
| `deal_health_worker.compute_deal_health` | 02:15 | `(self, workspace_id)` | **CRASHES** — same. Never ran from scheduler. |
| `followup_sequences.check_stale_deals_hitl` | 09:00 | no-arg, fans out internally | Runs OK |
| `pm_agent.run_health_check` | every 30 min | no-arg, fans out internally | Runs OK (but spams `activity_events`: ≥48 heartbeats/ws/day, no dedupe) |

**Cascade failure (the nastiest emergent bug):** Deals default `health_score=100`; only `compute_deal_health` lowers it; that job is the crashing one. So in prod **nothing ever drops to the ≤40 threshold** unless an admin manually clicks recompute → the *working* daily HITL follow-up sweep (`health_score<=40`) **finds nothing to do**. The dead nightly job silently neuters the live daily job. The dashboard "Deal Health" agent shows green while doing nothing. `pm_agent` (the "catches silent failures" monitor) **cannot** detect these crashes — they fail before writing any row, leaving no stuck-Agent/event to find.

**On-demand jobs** (router `.delay()`): score/enrich/health/optimize/embed/reprocess/transcribe. **`POST /agents/{id}/run` is a stub** — returns a random `job_id`, enqueues nothing; UI shows "processing" forever; `pm_agent` flips it to `error` at 30 min → a **false error alert on every manual run**.

**Cross-container break:** `transcribe_call` gets a local tempfile path written by the **web/API** process but runs in a **separate** Railway worker container with no shared volume → `FileNotFoundError`, empty transcript forever, no retry. (Open Q: do web+worker share a volume? If not, all call transcription is broken in prod.)

---

## 6. Demo Mode — the deploy-posture landmine

A single env var `NEXT_PUBLIC_DEMO_MODE=true`:
- Bypasses **all** auth in `(app)/layout.tsx:10-16` (no `getUser`).
- Makes `useRole` return `admin` everywhere.
- Short-circuits every `apiClient` method to inline fixtures.
- Skips Supabase refresh in `proxy.ts` (moot — proxy is dead anyway).

If shipped `true` on the production web service, **the entire app is public, unauthenticated, all-data-fake, every user "admin."** DEPLOY.md *recommends enabling it* on the web service during backend setup. **MUST confirm the live Railway value.** (The e2e smoke + `pnpm build` were both run *with* demo mode on, so "green build" does not exercise the real auth path.)

---

## 7. Notable Implementation Truths (verified this session)

- **`proxy.ts` is DEAD.** Verified decisively: `.next/server/middleware-manifest.json` = `{"middleware":{}, "sortedMiddleware":[], "functions":{}}`; built `middleware.js` is a 219-byte generic stub with **none** of the proxy logic (0 matches for the matcher regex / `getUser` / `NEXT_PUBLIC_DEMO_MODE`). Root cause: file is `proxy.ts` exporting `proxy()`, not `middleware.ts` exporting `middleware()`. Next 16 registered nothing. **This contradicts the `read-web-data` reader's "build artifacts prove it's wired" claim — that grep-hit was a false positive (module tree-shaken into a generic chunk, never registered).** Consequence: no edge session refresh; server-layout cookie set/remove are no-ops citing a middleware that does not exist → the exact "auth params fall back to Site URL" bug class this branch is patching.
- **Workspace takeover surface** confirmed `auth.py:102-105`: `user.workspace_id = new_ws_id` from JWT `user_metadata` with **no ownership check**. Severity = CRITICAL **iff** the Supabase project allows client `updateUser({data:{workspace_id}})` (a common default). This single open question gates the whole tenancy verdict.
- **Webhook posture split** confirmed: Gmail push (`gmail.py:378-379`) and Slack Events (`slack.py:207`) **fail OPEN** (`return True` on empty secret); Slack interactions (`slack_interactions.py:44-45`) **fails CLOSED**. Only Slack is warned at startup; Gmail is silent. DEPLOY.md *incorrectly* documents Slack as "skipped when unset" — doc says fail-open, code fails-closed.
- **Slack Events real-time ingest is DEAD:** lookup is `Connector.external_email == bare team_id`, but callbacks only ever store a real email or `{team_id}:{user_id}`, never a bare team_id. Every event logs `slack_push_no_connector`. A shipped feature that cannot fire.
- **The "6 AI agents / ML stack" is theater:** real stack = Claude Haiku 4.5 + Sonnet 4.6 + local Whisper-base + local MiniLM + Python heuristics. `requirements.txt` has **no** xgboost/lightgbm/openai/torch/transformers. Deal "health"/lead "score"/win-"probability" are rules engines / static columns. `accuracy` is a seeded literal never computed.

---

## 8. Frank Assessment of Architectural Coherence

**Verdict: a working spine wrapped in three layers of drift — pattern drift, doc/marketing drift, and a security model that is real on paper and absent at runtime.**

**What's coherent:**
- The core request path (Next client → Bearer JWT → FastAPI → async SQLAlchemy → Postgres) is sound and conventional.
- Auth verification (ES256 via JWKS, cached) is correct.
- The Claude-backed services that *do* exist (clarity/sentiment/extraction/transcription/Nova/MCP) are real and tenant-scoped.
- Slack interactions HITL fail-closed and OAuth-state HMAC signing are done right.
- 324 API unit tests genuinely pass (verified twice) — but against **mocks** (no real DB/Redis); it oversells coverage if read as "system is tested."

**What's incoherent / fragile (ranked):**
1. **Security-model mismatch.** The schema advertises RLS multi-tenancy; the runtime enforces tenancy via 50+ copy-pasted Python guards while RLS is inert. The two stories don't match, and the docs reassure operators about protection that isn't active. Defense-in-depth is a façade — it's defense-in-one-line.
2. **Self-service tenant takeover** via user-writable `user_metadata.workspace_id` (CRITICAL pending one Supabase-policy check). The same user-mutable value is trusted by Pattern-B web reads, the auto-provisioner, *and* `/auth/verify`.
3. **Scheduler half-broken silently.** 2/4 nightly jobs have never run; one of them neuters a working job via the health-score cascade; the "health monitor" is blind to it. No retry/DLQ/time-limit anywhere; one heavy tenant starves all others on a 2-slot shared queue.
4. **Three data-access patterns + four ways to read `activity_events` + dead SSE route + 2 dead hooks** — the web data layer has no single source of truth, and direct-Supabase reads (esp. the unfiltered `agents` sidebar query) lean on RLS that may not be configured for the anon path.
5. **Pervasive copy-paste instead of shared abstractions:** ~10 worker DB-session factories (divergent), ~30 repeats of the getSession→token/ws block, 6+ hand-rolled LLM-JSON parsers (different robustness — extraction silently drops fenced JSON), 3 `OAuth2PasswordBearer` instances, 3 provisioning copies (divergent agent seeding), 2 Slack-signature verifiers with opposite postures. Every one is a place for the next bug to diverge.
6. **Cross-process local-path coupling** (transcribe) and **request-session reuse in BackgroundTasks** (HITL email, Gmail push) — both work intermittently and fail under teardown/cross-container conditions.
7. **Material claim/reality gap** in marketing (SOC 2, GDPR, 99.9%, XGBoost/GPT-4o/RoBERTa, 94.7%/F1:0.947) — not just inconsistency but **legal/compliance exposure** for a B2B product (see CLAIMS_REGISTER.md).

**Bottom line:** NovaCRM is a competent vertical slice that *demos* well (which is exactly what the demo-mode + mock-metrics + fake-ML-labels optimize for) but is **not yet a trustworthy multi-tenant system**: tenancy has no DB backstop, a takeover path likely exists, half the autonomous "agents" don't run, and the public claims outrun the code. The highest-leverage homogenizations (one auth/session hook, one tenancy dependency, one worker-session factory, one LLM-JSON parser, kill demo-mode-in-prod, rename proxy→middleware) would each collapse a whole class of these defects.
