# NovaCRM — Claims Register (Phase 1 Synthesis)

**Worktree:** `/tmp/crm-signup-fix` @ `429da2f` (branch `fix/signup-confirm-redirect`, **not master**).

**Status taxonomy**
- **VERIFIED** — confirmed true by reading source / running it (this session or by a reader with cited line evidence).
- **PLAUSIBLE** — code supports it but the runtime/prod condition was not observed (env-dependent).
- **UNVERIFIED** — cannot be determined from the repo; needs a live check (Supabase policy, Railway env, Anthropic API, prod DB).
- **FALSE** — contradicted by source / requirements / build artifacts.

**"Severity of being wrong"** = blast radius **if the claim is believed and it is actually false** (legal, security, data-loss, or just-embarrassing).

---

## A. Landing-page / marketing claims — HIGHEST SCRUTINY (B2B false-advertising exposure)

These are customer- and investor-facing and asserted as fact. None are backed by code. For a B2B SaaS, **advertising SOC 2 Type II / GDPR / uptime SLAs without the underlying controls is a concrete legal and contractual risk** (misrepresentation, breach-of-warranty, and — for SOC 2 — implying a certification that does not exist).

| # | Claim | Source | Status | Evidence | Severity if wrong |
|---|-------|--------|--------|----------|-------------------|
| A1 | **"SOC 2 Type II"** certified (hero + footer badge) | `page.tsx:179,462` | **FALSE** | No controls, no audit artifact in repo; DEPLOY.md:204-214 itself says "No Sentry / No alerting / no uptime monitoring." Asserting SOC 2 without a report is misrepresentation. | **CRITICAL (legal)** — implies an attestation that does not exist; enterprise procurement and regulators treat this as material. |
| A2 | **"GDPR Compliant"** (footer badge) | `page.tsx:462` | **UNVERIFIED→likely FALSE** | No DPA, data-subject, deletion, or retention machinery found; `delete_contact` SET NULLs rather than cascades; no records-of-processing. | **HIGH (legal)** — EU customers rely on this contractually. |
| A3 | **"99.9% uptime"** (badges) / **"99.99% SLA"** (Enterprise) | `page.tsx:179,386,462` | **FALSE** | No monitoring/alerting/SLA instrumentation (DEPLOY.md:204-214); PROGRESS.md:49 "no live deployment URL configured." An SLA you don't measure isn't one. | **HIGH (contractual)** — an unbacked SLA is an enforceable promise. |
| A4 | **"94.7% Accuracy"** hero + dashboard tile; **"F1: 0.947"**; live log "f1:0.947→0.951" | `page.tsx:143,194,247,349` | **FALSE** | No model is trained/evaluated anywhere; `agent.accuracy` is a seeded literal never computed; lead/deal scoring are heuristics. The "model_retrain" log line is hardcoded static. | **HIGH (legal/repute)** — fabricated performance metric. |
| A5 | **Lead Scoring = "XGBoost v2" + "Feature Store"** | `page.tsx:246-247`, `seed.ts:175` | **FALSE** | `score_contact.py` is `base 50 ± status/revenue/deal`; `requirements.txt` has **no xgboost**; no feature store exists. | **HIGH** — names a model class the product does not run. |
| A6 | **Email Composer = "GPT-4o Fine-tuned"**, "48% Open / 22% Reply" | `page.tsx:260-261` | **FALSE** | `contacts.py:310` uses `claude-haiku-4-5`; `requirements.txt` has **no openai**; open/reply rates are not tracked anywhere. | **HIGH** — wrong vendor model + invented funnel metrics. |
| A7 | **Pipeline = "RL Policy" + "LightGBM"** | `page.tsx:254` | **FALSE** | `pipeline.py` is a heuristic win-prob nudge; no RL, no lightgbm dep. | **HIGH** |
| A8 | **Churn = "RoBERTa Fine-tuned"**; first-class "Churn Prediction" feature/agent | `page.tsx:272-275` | **FALSE** | No churn agent in seed list, no churn model, no transformers dep; only per-message Claude-Haiku sentiment exists. | **HIGH** — sells a capability that doesn't exist. |
| A9 | **Call Summarization = "Whisper Large v3" + "Claude 3.5", "in 23 seconds"** | `page.tsx:267-268` | **FALSE** | `transcribe.py` uses Whisper **base** (env default) + `claude-sonnet-4-6`; "23s" latency unmeasured; and the worker likely can't read the audio file at all in prod (cross-container path). | **MEDIUM-HIGH** — wrong model size + unverifiable latency on a possibly-broken feature. |
| A10 | **Pricing tiers** ($49 Starter/3 agents, $149 Pro/unlimited, Enterprise SSO+SCIM/on-prem) | `page.tsx:370-388` | **FALSE (unenforced)** | No billing/Stripe/entitlement code anywhere; agent caps & SSO/SCIM not gated. | **MEDIUM** — revenue leak + promise of features (SSO/SCIM) that don't exist. |
| A11 | **"Live · streaming" agent activity log** on landing | `page.tsx:343-361` | **FALSE** | Rows are hardcoded literals; "Live" label is decorative. | **LOW (repute)** |
| A12 | **Semantic Contact Sorting = all-MiniLM-L6-v2 + cosine** | `page.tsx:239-240` | **VERIFIED** | `embedding.py:13` (MiniLM, 384-d) + `search.py` pgvector `<=>`. **The one true ML claim on the page.** | n/a (true) |

> **DEMO_SCRIPT.md disagrees with the page on every headline number** (revenue $485K vs $2.4M; accuracy 91% vs 94.7%; "beta with 3 teams"; $49/$149 framed per-user vs per-month). All are mock values presented as real → if shown to investors, the inconsistency itself is a credibility/diligence risk (A13, **MEDIUM**, UNVERIFIED for the "3 teams/ACV" traction claims).

---

## B. Security & multi-tenancy claims

| # | Claim | Source | Status | Evidence | Severity if wrong |
|---|-------|--------|--------|----------|-------------------|
| B1 | "11-table schema ships with RLS providing workspace isolation" (defense-in-depth) | DEPLOY.md:105; `001:160-205` | **FALSE (at runtime)** | API connects as Supabase owner/pooler role (`database.py`) + service_role REST → **RLS bypassed**; `auth.uid()` NULL (GUC never set); **no FORCE RLS**; app returns rows + 324 tests pass ⇒ bypass. | **CRITICAL** — operators believe a DB backstop exists; it does not. Single missing guard = silent cross-tenant leak. |
| B2 | `/auth/verify` reassigns `user.workspace_id` from JWT `user_metadata` **with no authz** | `auth.py:102-105` (verified this session) | **VERIFIED (the code path)**; exploitability **UNVERIFIED** | `user.workspace_id = new_ws_id` from `meta_ws_id_str`, no ownership check; `get_current_user` then trusts it. | **CRITICAL iff** Supabase allows client `updateUser({data:{workspace_id}})` → self-service takeover into any victim workspace as admin. **Gating open question.** |
| B3 | `workspace_id` comes from user-writable `user_metadata`; Pattern-B web reads + provisioner trust it | onboarding `updateUser`, `layout.tsx`, `useWorkspace`, `Sidebar` | **VERIFIED** | Onboarding writes it; consumers `.eq()` on it. | **HIGH** — amplifies B2; cross-tenant reads if RLS/anon path misconfigured. |
| B4 | `Sidebar` agents query has **no** `workspace_id` filter (RLS-only) | `Sidebar.tsx:131-137` | **VERIFIED** | `from('agents').select('name,status').limit(4)` — no `.eq('workspace_id')`. | **HIGH** — relies entirely on anon-key RLS being correct (unconfirmed). |
| B5 | Gmail push webhook **fails OPEN** when `GMAIL_WEBHOOK_SECRET` empty | `gmail.py:378-379` (verified) | **VERIFIED** | `if not settings.GMAIL_WEBHOOK_SECRET: return True`. Secret also passed in URL query (logged). No Google OIDC verify. | **HIGH** — unauthenticated forced-sync/DoS against any known connector email **iff** secret unset in prod (UNVERIFIED). |
| B6 | Slack **Events** webhook **fails OPEN** when secret empty | `slack.py:207` (verified) | **VERIFIED** | `return True` on empty secret; only Slack is startup-warned. | **HIGH (if unset)** — but see B12, Events ingest is dead anyway. |
| B7 | Slack **interactions** (HITL) **fails CLOSED** | `slack_interactions.py:44-45` (verified) | **VERIFIED** | `if not SLACK_SIGNING_SECRET: return False`. **Correct**, and *contradicts* DEPLOY.md:55 which says it's "skipped when unset." | **MEDIUM (doc risk)** — operators have a wrong mental model and might "fix" it the wrong way. |
| B8 | HITL approve has **no tenant authz on the actor** | `slack_interactions.py:240-256,92` | **VERIFIED (latent)** | Global `hitl_pending` lookup by `hitl_id` (no ws filter); email then sent via the tenant named in trusted server-minted meta. uuid4 unguessability is the only mitigation. | **HIGH (if Slack app is single multi-tenant distribution)** — UNVERIFIED whether one signing secret is shared across customers. |
| B9 | Gmail token-refresh failure surfaces connector "error" status | `gmail_client.py` + `gmail.py:42-87` | **FALSE** | Refresh 400 raises raw; worker `except→break` then **bumps `last_sync`**; no `connector_auth_error` event (unlike Slack). Dead Gmail connector shows active/stale, ingests nothing. | **HIGH (silent data-staleness)** — customer sees "connected," gets no email sync, no signal. |
| B10 | RLS uses ES256 user JWT to open the DB connection | implied by DEPLOY "defense-in-depth" | **FALSE** | User JWT never opens a DB connection (`dependencies.py:40`). | **HIGH** — reinforces B1. |
| B11 | "init_docker.sql has no RLS; prod uses RLS" | init_docker:2; DEPLOY.md:112 | **PLAUSIBLE but moot** | True as written, but prod RLS is inert (B1), so both envs = "no RLS for the API." | **MEDIUM** — false sense of dev/prod difference. |
| B12 | Slack Events real-time ingest works | commit 74a589b; `slack.py:223-240` | **FALSE** | Lookup `external_email == bare team_id`; callback never stores a bare team_id (only real email or `{team}:{user}`). Every event → `slack_push_no_connector`. | **MEDIUM** — shipped feature that has never fired. |
| B13 | OAuth state is "signed, expiring, with anti-forgery nonce" | `oauth_state.py:5,48` | **FALSE (nonce part)** | Signed+expiring = true; nonce minted but **never persisted/checked** → replayable within 600s. Anti-forgery claim overstated. | **LOW** — callbacks idempotent; impact low. |
| B14 | Connector OAuth tokens encrypted at rest (Fernet from SECRET_KEY) | `crypto.py:9-25` | **VERIFIED** | Fernet key = base64url(SHA256(SECRET_KEY)). Single static key, no rotation/versioning. | n/a (true; rotation gap noted) |
| B15 | Rate limiter uses authed user_id else IP | `limiter.py:6-10` | **FALSE** | `request.state.user` **never set** (0 assignments) → always IP; behind Railway = proxy IP (no X-Forwarded-For handling); in-memory per-process (unshared across replicas). | **MEDIUM** — limits either collapse all tenants into one bucket or are evadable; effectively absent on most write/AI/export endpoints. |
| B16 | `require_admin` is a real privilege boundary | `dependencies.py:88-93`; `deals.py:101,254` | **FALSE (vacuous)** | All provisioning hardcodes `role='admin'` (`dependencies.py:76`, `auth.py:88`, `workspaces.py:92`); model default 'member' is unreachable. Admin-only endpoints gate nothing. | **MEDIUM** — privileged actions (optimize, recompute, real-email invite) open to all. |
| B17 | JWT verify is ES256-only | implied | **FALSE (broader)** | `algorithms=['ES256','RS256']`, `verify_aud=False` (`auth.py:47-49`). Not exploitable via JWKS today, but wider than stated. | **LOW** |
| B18 | `SUPABASE_JWT_SECRET` is required "backend auth" | README:110, DEPLOY.md:46, config.py:14 | **FALSE (unused)** | Verifier never reads it (`auth.py:6-8`); verification is JWKS public-key. Required env var that does nothing. | **LOW (ops confusion)** |
| B19 | Historical secret leak in HANDOFF.md (Supabase anon key + test password) | commit 893a7ba | **VERIFIED (leak happened)**; rotation **UNVERIFIED** | Scrub commit exists; values still recoverable from git history; DEPLOY.md says "rotate if shared" but doesn't confirm. | **HIGH (if not rotated)** — live creds in history. |
| B20 | Live `.env` with real secrets on disk | testReality env_gaps | **VERIFIED** | `/mnt/external/Projects/crm-agentic/apps/api/.env` holds service-role key, JWT secret, Anthropic key, Google/Slack secrets. | **HIGH (local exposure)** |

---

## C. Auth / session / web claims

| # | Claim | Source | Status | Evidence | Severity if wrong |
|---|-------|--------|--------|----------|-------------------|
| C1 | Supabase session is refreshed at the edge for all non-static routes | `proxy.ts:40-44` | **FALSE** | **Verified this session:** `middleware-manifest.json` = `{"middleware":{}}`; built `middleware.js` (219 B stub) contains none of the proxy logic. File is `proxy.ts`/`export proxy()`, not `middleware.ts`/`middleware()`. **Refutes the `read-web-data` reader's "build artifacts prove it's wired" — that was a tree-shaking false positive.** | **HIGH** — no edge refresh; layout cookie set/remove are no-ops citing a nonexistent middleware → likely the root cause of the "auth params fall back to Site URL" bug this branch patches. |
| C2 | Server components "can't set cookies; handled by middleware" | `supabase.ts:289-294` | **FALSE** | No middleware exists (C1); cookies never rewritten server-side. | **MEDIUM** — comment misleads maintainers; latent session bug. |
| C3 | Signup confirm redirects via `/auth/callback` (PKCE + OTP), open-redirect-safe, origin rebuilt behind Railway | `login:52`, `callback/route.ts:19-21,55-65` | **VERIFIED** | PKCE `exchangeCodeForSession` + OTP `verifyOtp` + `next` sanitized + `x-forwarded-host` rebuild. | n/a (the actual fix on this branch) |
| C4 | In demo mode all auth bypassed + `useRole`→admin | `layout.tsx:10-16`, `useRole.ts:19-23` | **VERIFIED** | Confirmed. | **CRITICAL if demo=true in prod** (see D1) |
| C5 | Confirm-failure shows a success banner | `page.tsx:42-44` | **VERIFIED** | setSession error → `/login?confirmed=1` ("Email confirmed!"). | **LOW** — masks failures, confuses users. |
| C6 | `getSupabase()` "@deprecated, kept for migration" | `supabase.ts:299-303` | **FALSE (justification)** | Zero callers — migration is done; it's just dead code to delete. | **LOW** |
| C7 | Onboarding "Invite" sends a team invite | `onboarding:135-139` | **FALSE** | Only sets `inviteSent=true`; never calls `apiClient.inviteTeammate`. | **LOW** — cosmetic no-op (Settings invite *is* real → divergent behavior). |
| C8 | TS build errors ignored but "runtime behavior is correct" | `next.config.ts:5-9` (verified) | **FALSE (unverifiable half)** | `ignoreBuildErrors:true` confirmed; "runtime correct" is an unprovable assertion in the comment. | **MEDIUM** — auth/tenant-shaped type regressions can't fail the build. |
| C9 | SSE proxy passes token as URL query param | `api/events/route.ts:9` | **VERIFIED (latent)** | Token in `?token=` → leaks to logs/history. Currently **orphaned** (no EventSource consumer). | **MEDIUM if wired**; LOW today. |

---

## D. Workers / jobs / AI claims

| # | Claim | Source | Status | Evidence | Severity if wrong |
|---|-------|--------|--------|----------|-------------------|
| D1 | 4 beat jobs run nightly/periodically | DEPLOY.md:184-190; `celery_app.py:27-46` | **FALSE (2 of 4 crash)** | **Verified this session:** `optimize_pipeline` & `compute_deal_health` scheduled `args:[]` but require `workspace_id` → `TypeError` every fire. Never ran from scheduler. | **CRITICAL (silent)** — see D2 cascade. |
| D2 | Deal-health scoring + HITL follow-ups operate in prod | marketing "agents that never sleep" | **FALSE (cascade)** | Deals default `health_score=100`; only the crashing job lowers it; HITL filters `<=40` → finds nothing. Live daily job neutered by dead nightly job. `pm_agent` can't detect it (crash leaves no row). | **HIGH** — a headline feature is inert while UI shows green. |
| D3 | `POST /agents/{id}/run` runs the agent | `agents.py:50-78` | **FALSE (stub)** | Returns random `job_id`, no `.delay()`; UI stuck "processing"; `pm_agent` flips to `error` at 30 min → false error alert every run. | **MEDIUM** — visibly broken core action. |
| D4 | `GET /jobs/{id}` is access-controlled | `agents.py:115-134` | **FALSE** | No workspace/ownership check; any authed user reads any job's result/error by ID (transcribe/enrich carry tenant data). | **HIGH** — cross-tenant data exposure. |
| D5 | `transcribe_call` reads the uploaded audio | `calls.py:80-97` + `transcribe.py` | **PLAUSIBLY FALSE** | Local tempfile written by web/API process; worker is a separate Railway container → `FileNotFoundError`, empty transcript, no retry. **UNVERIFIED:** do web+worker share a volume? | **HIGH if no shared volume** — all call transcription broken. |
| D6 | Ingest dedupes via UNIQUE(workspace_id, external_id) | `ingest.py:8` docstring | **FALSE** | No DB unique constraint in `message.py`; dedupe is app-level SELECT-then-INSERT → TOCTOU double-insert under c=2 + Pub/Sub re-delivery. | **MEDIUM** — duplicate messages. |
| D7 | No retry/acks_late/DLQ/time-limit; single queue c=2 | grep (0 hits) | **VERIFIED** | Worker death loses in-flight tasks, no redelivery; one heavy tenant starves all. | **HIGH (reliability/noisy-neighbor)** |
| D8 | No cost/token/quota controls; one global ANTHROPIC_API_KEY; 3+ Claude calls/message | `config.py:16`; `ingest.py:368,386,409`; grep usage=0 | **VERIFIED** | Unbounded multi-tenant spend on a shared key. | **HIGH (cost/abuse)** |
| D9 | Slack ingest covers public AND private channels | `slack_ingest.py:6` | **FALSE** | Requests `types='im,mpim,public_channel'` — no `private_channel`. | **LOW** — doc/code mismatch. |
| D10 | extraction returns tasks reliably | `extraction.py` | **PARTIAL** | Works for bare JSON, but **silently drops ALL tasks** when Claude fences the array (no ``` stripping, unlike sibling parsers). | **MEDIUM** — silent data loss. |
| D11 | `compose_email` uses Claude Sonnet (docstring) | `contacts.py:265` vs `:310` | **FALSE** | Actually `claude-haiku-4-5`; also a sync client blocking the event loop (`pre_meeting_brief` uses async — inconsistent). | **LOW-MEDIUM** |
| D12 | Model IDs `claude-haiku-4-5` / `claude-sonnet-4-6` (+dated) are valid | grep | **UNVERIFIED** | Needs a live Anthropic call; the entire "real AI" verdict hinges on it. | **HIGH if invalid** — all LLM features dead. |
| D13 | Clarity (Sonnet)/Sentiment (Haiku)/Extraction (Haiku)/Embeddings (MiniLM)/Whisper transcription exist and run | services + workers | **VERIFIED (code)**; runtime pending D12 | Cited line evidence per service. | n/a |

---

## E. Schema / migrations claims

| # | Claim | Source | Status | Severity if wrong |
|---|-------|--------|--------|-------------------|
| E1 | RLS enabled & enforcing (001/006/008) | DEPLOY.md, 001 | **FALSE (inert)** — see B1 | **CRITICAL** |
| E2 | `call_summaries` is RLS-protected | (implied by 001 family) | **FALSE** | 004 has **no** ENABLE/POLICY → transcripts fully exposed the moment they switch to JWT enforcement. | **HIGH** |
| E3 | init_docker.sql is "full schema" | header | **FALSE** | Missing projects table, tasks.project_id, tasks/projects.external_id, messages.relevant, 'error' severity → Docker/CI 500s on the exact paths 009-011 fixed; tests run vs non-prod schema. | **HIGH (test validity)** |
| E4 | 'error' severity violated CHECK on every HITL error path (pre-005) | 005, DEPLOY.md | **VERIFIED** | init_docker still lacks 'error' → Docker reproduces the bug. | **MEDIUM** |
| E5 | tasks.project_id "never existed" (011 comment) | 011 vs 007 | **FALSE (as stated)** | 007 already adds it; true only if 007 never applied → an ops/versioning failure, not a missing migration. No Alembic/version table; 007 & 011 duplicate. | **MEDIUM** — ambiguous prod schema. |
| E6 | Embeddings 384-d MiniLM + HNSW cosine | 002, models, search.py | **VERIFIED** | — | n/a |
| E7 | RLS FOR ALL policies have WITH CHECK | 001:188-205 | **FALSE** | USING only, no WITH CHECK → (if ever enforced) foreign-ws INSERT/UPDATE not blocked. | **MEDIUM (latent)** |
| E8 | Prod migrations 006-011 documented/applied | DEPLOY.md:100-112 | **UNVERIFIED** | Deploy list stops at 005; 006-011 undocumented; true prod schema unknown without inspecting live DB. | **MEDIUM** |

---

## F. Tests / build / process claims

| # | Claim | Source | Status | Evidence | Severity if wrong |
|---|-------|--------|--------|----------|-------------------|
| F1 | "324 tests pass" | PROGRESS.md:40; git log | **VERIFIED (with caveat)** | testReality reproduced **324 passed / 0 failed**, exit 0, twice. **Caveat:** all mock-based unit tests — DB/Redis stubbed (AsyncMock); proves logic-vs-mocks, **not** integration. API-scoped only. | **MEDIUM** — oversells coverage if read as "whole system tested." |
| F2 | `pnpm build` green | testReality | **VERIFIED** | BUILD_EXIT=0, 21 routes — **but built with demo env**, so real auth path not exercised. | **LOW** |
| F3 | e2e smoke passes | testReality | **FALSE (as headline)** | 7/9; 2 failures are brittle-selector bugs in the spec (not product crashes); spec only runs against local demo, can't target prod. | **LOW** |
| F4 | "29/29 endpoints passing / 12 pages" | HANDOFF (commit 0e74552) | **VERIFIED but STALE** | 2026-04-29 snapshot; superseded; never reconciled with the 324 number. | **LOW** |
| F5 | "All 44 api-client methods have demo stubs" | DEPLOY.md:256 | **PLAUSIBLE** | Reader saw ~70 methods each with isDemoMode branch; exact "44" not independently counted. | **LOW** |

---

## Headline verdicts

- **VERIFIED true (notable):** PKCE/OTP signup-confirm fix (C3); ES256/JWKS auth; Fernet token encryption (B14); MiniLM semantic search (A12, E6); messages eager-load no-N+1; pgvector SQL-injection-safe; Slack HITL fail-closed (B7); 324 API unit tests pass (F1, caveated).
- **Most dangerous FALSE claims (act first):**
  1. **B1/E1/E2 — RLS isolation is inert** (CRITICAL; no DB backstop; call_summaries unprotected even on paper).
  2. **B2 — workspace-takeover via user_metadata** (CRITICAL pending one Supabase-policy check).
  3. **A1/A3 — SOC 2 Type II + 99.9% uptime advertised with zero controls** (CRITICAL/HIGH legal).
  4. **C1 — edge auth-refresh middleware is dead** (HIGH; root cause of the bug this branch patches; *and a reader wrongly claimed it was wired*).
  5. **D1/D2 — half the nightly "agents" crash, neutering deal-health + follow-ups** (CRITICAL silent).
  6. **A4-A9 — fabricated ML stack & accuracy metrics** (HIGH legal/repute).
  7. **B5/B9/D4 — Gmail webhook fail-open, silent Gmail token-death, unauthZ /jobs/{id}** (HIGH).
- **Must be resolved by live check (UNVERIFIED, gate severity):** Does Supabase allow client `updateUser({data:{workspace_id}})`? (B2) · Is `NEXT_PUBLIC_DEMO_MODE` true in prod? (D1/C4) · Are GMAIL/SLACK webhook secrets set? (B5/B6) · Is the Slack app one shared multi-tenant distribution? (B8) · Were the leaked HANDOFF creds rotated? (B19) · Do web+worker share a volume? (D5) · Do the Claude model IDs resolve? (D12) · Were migrations 006-011 applied to prod? (E8).
