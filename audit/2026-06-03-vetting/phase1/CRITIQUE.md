# NovaCRM — Phase 1 Completeness Critique (for Phase 2 targeting)

**Critic role:** completeness/skeptic. Inputs reviewed: `ARCHITECTURE_MAP.md`, `CLAIMS_REGISTER.md`, all nine `read-*.md` notes, plus the actual file tree at `/tmp/crm-signup-fix`. I re-ran source spot-checks to find what the understanding phase *missed* or *asserted without proof*.

**Headline:** Phase 1 is strong on the API core, tenancy theory, workers, and marketing claims. It is **thin or wrong in four places**: (1) it under-read the web tier — ~13 `(app)` pages each do their own direct-Supabase reads and only 4 were catalogued; (2) it **mischaracterized the test suite's tenancy coverage** — the 403 tests are structurally incapable of catching the very bug Phase 1 ranks #1; (3) it left the two CRITICAL gating questions (workspace-takeover, demo-mode-in-prod) **un-probed even though they are checkable without prod**; (4) several "FALSE/data-loss" claims rest on conflicting evidence between the two synthesis docs (`delete_contact` cascade, MCP auth, CORS) that nobody reconciled.

---

## Part 1 — What's MISSING (subsystems / files nobody read)

### 1.1 The web `(app)` page tier is almost entirely unread (BIGGEST GAP)
The architecture map's "Pattern B" table lists **4** direct-Supabase sites (`layout.tsx`, `useWorkspace`, `Sidebar`, `dashboard`). The reality: **every one of ~13 app pages constructs its own `createBrowserClient()`**:

```
dashboard, pipeline, contacts, contacts/[id], projects, projects/[id],
tasks, settings, connectors, calls, inbox, agents  (+ login, onboarding, page.tsx)
```

The readers covered `dashboard`, `Sidebar`, `Header`, `CommandPalette`, the hooks, and `layout.tsx` — but **never opened** `pipeline/page.tsx` (4 separate Supabase clients on one page, incl. bulk-delete), `inbox`, `calls`, `connectors`, `settings`, `tasks`, `contacts/[id]`, `projects/[id]`, `reports`. The map even calls the web data layer "no single source of truth" but then under-counts the sprawl by ~3×. **For a multi-tenancy audit this is the highest-value unread surface**: each page independently reads `getSession()` then trusts `workspace_id` and either (a) calls FastAPI (re-checked) or (b) hits Supabase directly under inert RLS. Whether any of these 9 unread pages does a *direct table read* (like `Sidebar.from('agents')`) was never determined. **Confirmed in this pass:** most use Supabase only for `getSession()`/`signOut()` — but `pipeline`, `projects`, `projects/[id]`, `tasks`, `contacts/[id]`, `calls`, `inbox` were never line-read to confirm they don't `.from()` a table. This must be swept in Phase 2.

### 1.2 MCP server (`mcp_server.py`, 265 LOC) — barely mentioned, never tenancy-audited
The arch map calls the MCP server "real but thin" and moves on. Nobody verified its **auth + tenancy** path. I checked: it `Depends(get_current_user)`, derives `workspace_id = current_user.workspace_id`, and every handler (`_list_contacts/_list_deals/_stale_deals/_pipeline_summary`) filters `.where(...workspace_id == workspace_id)`. That's the *correct* idiom — **but it's a fifth, separately-maintained copy of tenancy scoping** (router-level, no path param, like `agents.py`), exposing CRM data over a JSON-RPC tool protocol. It belongs in the tenancy blast-radius inventory and the "copy-paste tenancy" count (Phase 1 said "50+ handlers + agents.py different idiom" — it's actually **agents.py AND mcp_server.py** using the no-path-param idiom). An MCP tool surface that returns "name, email, company, role, **ML lead score**" is also a fresh place for the marketing-claim leakage (it advertises "ML lead score" in the tool description — another fabricated-ML touchpoint nobody catalogued).

### 1.3 `main.py` middleware/CORS stack — never read by any subagent
No reader covered `main.py`'s middleware. Two findings the understanding phase missed entirely:
- **CORS is `allow_credentials=True` + operator-supplied `CORS_ORIGIN_REGEX`** (default empty). The inline comment *encourages* operators to set a regex covering "whole domain families … so a domain cutover doesn't need a code change." A sloppy regex (e.g. `.*riphere.*`, or a missing anchor) + credentialed CORS = cross-origin credential theft. Default is safe; the **footgun and the prod value are un-audited**. Not in any claim row.
- **`/health` returns HTTP 200 even when DB/Redis are down** ("degraded" in body). Phase 1's "no alerting" story is worse than stated: the *liveness probe itself* masks outages from Railway, and "a dedicated alerting layer should monitor the body" does not exist (DEPLOY.md: no alerting). This is a concrete availability claim (A3 "99.9%") counter-evidence nobody logged.

### 1.4 `conftest.py` fixture design — read for "it's mocks," not for what it *cannot* test
`read-api-core`/`test-reality` correctly said "324 tests, all mocks." **Nobody analyzed what the fixture structurally forecloses.** See Part 2.1 — this is the single most important correction.

### 1.5 Smaller unread/under-read items
- **`reports/page.tsx`** — never read; it's pure client-side forecast synthesis (`Array.from({length: forecastCount})`), i.e. another "fabricated metric" surface (synthetic forecasts presented as analytics). Not in the claims register.
- **`docker-compose.yml`, `audit.js`, `scripts/railway-deploy.sh`, `start.sh`** — none read. `audit.js` at repo root is unexplained (a prior audit tool? dead?). `start.sh`/compose may answer the **D5 "do web+worker share a volume?"** open question without needing prod.
- **`packages/types/*`** (`pm.ts`, `crm.ts`, `index.ts`) — the shared type contract between web and API was never read; type drift here is where the `next.config.ts ignoreBuildErrors:true` (C8) actually bites.
- **`metric_template.py` / `clarity_score.py` models** — listed but never examined; `metric_template` is unexplained and may relate to the "Feature Store" (A5) fabrication.
- **`.github/workflows/ci.yml`** — read by me, not by the phase. CI is a *claims source* nobody mined (see 2.2).

---

## Part 2 — Claims nobody catalogued / got wrong

### 2.1 CRITICAL CORRECTION: the cross-tenant 403 tests do NOT test tenant isolation
Phase 1's #1 risk is "one omitted `.where` = silent cross-tenant leak with no DB backstop," and it cites "324 tests pass" as caveated-but-reassuring. **The reassurance is misplaced and nobody caught why.** The fixture (`tests/conftest.py`) does:
```python
app.dependency_overrides[get_current_user] = lambda: test_user   # fixed admin, ws = aaaa…
app.dependency_overrides[get_db]          = lambda: mock_db       # AsyncMock; .where() is a no-op
```
The ~20 `*_wrong_workspace_returns_403` tests request a *different* `workspace_id` in the **path** and assert 403. That **only exercises the literal `if current_user.workspace_id != path_ws` line**. It can **never**:
- catch an endpoint that *forgot* the `.where(workspace_id==)` filter (the actual leak mode) — because `mock_db` returns whatever the test hands it, regardless of filter;
- catch the **router-idiom endpoints** (`agents.py`, `mcp_server.py`) that have **no path param at all**, so there's no "wrong workspace" path to even write a test for;
- detect the inert RLS, because no real DB is in the loop.

So the test suite proves "the guard that is present, works" and gives **zero** evidence about "is the guard present everywhere." **Phase 1 should have stated that the 324 tests provide *no* assurance on the headline tenancy risk.** This reframes F1's severity from MEDIUM to **HIGH (false assurance on the #1 risk)**.

### 2.2 CI is a claims source that was never mined — and it's internally stale
`ci.yml` (nobody read it) reveals:
- CI comment says **"295 tests"**; repo actually runs **324**. The project's own CI is out of sync with itself (compounds F4's "stale 29/29" pattern — there are now *three* different test counts: 29, 295, 324).
- CI installs deps via a **hardcoded `pip install fastapi … pgvector …` list, NOT `requirements.txt`.** So green CI does **not** prove `requirements.txt` is installable/correct, and CI's dependency set can silently diverge from prod's. This undercuts any "build is green" assurance and is a supply-chain/repro gap nobody logged.
- **All three CI jobs (web build, e2e, and implicitly the api env) run with `NEXT_PUBLIC_DEMO_MODE: "true"`.** Phase 1 noted the local build used demo mode; it **missed that CI institutionalizes it** — the real auth path is never exercised by *any* automated gate, ever. Strengthens D1/C4/F2.

### 2.3 `delete_contact` — the two synthesis docs CONFLICT and both are imprecise
- `CLAIMS_REGISTER.md` A2 evidence: "`delete_contact` SET NULLs rather than cascades."
- `read-api-domain`/router docstring: "Delete a contact **and all cascade-linked records**."

Ground truth (I checked models + SQL): SQL FKs are `contact_id … ON DELETE SET NULL` on deals/messages/tasks; but the **SQLAlchemy relationships set no `cascade=` and no `passive_deletes=True`**, and the code path is ORM `await db.delete(contact)`. That means SQLAlchemy may **emit its own UPDATEs to NULL the children in Python** (loading them first), *independent* of the SQL rule — and if a relationship is configured `delete`/`delete-orphan` anywhere (it isn't here, but `clarity_score` is `message`-cascade and `message_id UNIQUE ON DELETE CASCADE`), behavior diverges. **Net: deleting a contact silently detaches its deals/messages/tasks (data becomes orphaned/unattributable), which directly contradicts the GDPR "deletion" claim (A2) — a *contact delete does not delete the contact's data*.** Phase 1 gestured at this but neither doc pinned the mechanism or connected it cleanly to A2. This is a real, checkable data-integrity + compliance finding for Phase 2.

### 2.4 `bulk_deal_action` — asserted nowhere, and it's actually CORRECT (avoid a false positive)
The bulk endpoint is a juicy IDOR target (accepts a list of `deal_ids`). Phase 1 never validated it. I did: it re-queries `select(Deal).where(workspace_id==path_ws, Deal.id.in_(deal_ids))` and operates only on the returned rows — **cross-tenant IDs are silently dropped, not actioned.** This is the *correct* pattern. Worth recording so Phase 2 doesn't burn time "discovering" a non-bug — and as the **positive template** other endpoints should match.

### 2.5 Uncatalogued claim/risk items
- **MCP tool description advertises "ML lead score"** (`mcp_server.py:37`) — another fabricated-ML surface beyond the landing page (extends A4/A5 into the product's agent-facing API).
- **`reports` page emits synthetic forecasts** as analytics — uncatalogued "fabricated metric in-product" (sibling to A11 "Live streaming" decoration, but inside the authed app, shown to paying users).
- **`HUNTER_API_KEY`** appears in `.env.example` and conftest — there's a Hunter.io enrichment dependency nobody traced. `enrich_contact.py` was read but the **external Hunter call + its failure/cost/tenancy behavior** wasn't surfaced as a claim (another unbounded external dependency like the Anthropic key, D8).
- **`SUPABASE_JWT_SECRET` is in BOTH `.env.example` files and conftest as "REQUIRED"** while B18 proves it's unused — the falseness is *more* entrenched than B18 says (it's a required env var in three places that does nothing; operators will provision and guard a secret that has no effect).

---

## Part 3 — Risks dismissed too quickly / scoped wrong

1. **B20 (live `.env` with real secrets) is scoped to the wrong path for THIS audit.** The leak is at `/mnt/external/Projects/crm-agentic/apps/api/.env` — a **different checkout**, not the audited worktree `/tmp/crm-signup-fix` (which has **no** tracked or untracked real `.env` — I verified). Phase 1 presents it inline with the worktree findings. For Phase 2, treat B20 as "developer-workstation exposure of the *other* clone," not "this branch ships secrets." Still HIGH, but don't let it muddy the deployed-branch threat model.

2. **B2 (workspace takeover) and D1/C4 (demo-mode-in-prod) are filed as "UNVERIFIED, needs live check" — but both are checkable NOW without prod.** B2's gate ("does Supabase allow client `updateUser({data:{workspace_id}})`?") is answerable by reading the Supabase project's auth config / a 10-line script against the *staging* anon key, or by inspecting whether the app ever calls it (it does: onboarding `updateUser({data:{workspace_id}})`). The understanding phase treated "UNVERIFIED" as "park it"; the skeptic's move is to **drive the takeover end-to-end in Phase 2** (mint user A, `updateUser` to workspace B's id, hit `/auth/verify`, then read B's contacts). Same for demo-mode: `curl https://www.riphere.com` for the absence of auth redirect / presence of fixture data is a 1-minute live check, not a "park for ops." **These are the two CRITICALs and they were left un-attacked.**

3. **"Inert RLS" is convergent-inference, not observed.** Phase 1 concludes RLS is bypassed because "rows return + tests pass + policies key on NULL `auth.uid()`." That's sound reasoning but it is **not a direct observation** — and the whole #1 risk rests on it. A skeptic must **prove** it: connect to the live/staging DB as the API role and run `SELECT current_user, current_setting('request.jwt.claims', true)` + attempt a cross-tenant `SELECT` to show RLS does not block it. Until then it's PLAUSIBLE, not VERIFIED, and Phase 1 slightly overstates its certainty (it says "Confirmed by convergent evidence" / "CRITICAL" as if observed).

4. **D5 (transcribe cross-container file) dismissed as "UNVERIFIED open question" — but `docker-compose.yml`/railway tomls/`start.sh` (all unread) likely answer it.** Don't carry this as an open question into Phase 2 without first reading the 4 deploy files already in the repo.

5. **proxy.ts "dead middleware" — Phase 1 nailed it, but under-stated the blast radius.** It's filed as "HIGH, root cause of the signup bug." The skeptic angle: a dead middleware means **the `(app)/layout.tsx` server guard is the SOLE auth gate**, and that guard is itself disabled by demo-mode. So auth = one server component check that one env var nullifies. That single-point-of-failure framing (no edge layer, no middleware, one toggle) deserves elevation; it compounds with #2.

6. **Rate limiter (B15) "effectively absent" — correct, but the AI/cost endpoints are the real story.** Phase 1 rates it MEDIUM. Given D8 (unbounded Anthropic spend, shared key, 3+ calls/message) and **no per-tenant quota**, an unauth-evadable IP-only limiter on `/ai/query`, `compose_email`, transcription, and bulk embed is the **cost-DoS** vector. The skeptic should pair B15+D8 and rate the *combination* HIGH (financial), which neither doc does.

---

## Part 4 — Ranked Phase 2 target list (where a skeptical senior eng attacks first)

Ordered by (blast radius × ease of disproof/exploit). Standing priorities — multi-tenancy isolation, auth bypass, worker data-loss, false marketing — are folded in and flagged.

1. **[TENANCY/AUTH-BYPASS — CRITICAL] Prove or kill the workspace-takeover (B2) end-to-end.** Drive it: user A → `supabase.auth.updateUser({data:{workspace_id: <B>}})` → `POST /auth/verify` → `GET /workspaces/<B>/contacts`. If rows return, it's a self-service cross-tenant admin takeover. This is THE gating CRITICAL and was never attacked. Also check whether Supabase project locks `user_metadata` writes (the only mitigation).

2. **[DEPLOY POSTURE — CRITICAL] Observe the live `NEXT_PUBLIC_DEMO_MODE` value on prod web.** `curl -sI`/Playwright `https://www.riphere.com/dashboard` for auth-redirect vs fixture render. One minute; flips the entire app between "secured" and "public, fake, all-admin." Left un-observed in Phase 1.

3. **[TENANCY — CRITICAL] Directly observe RLS is inert** by querying the DB as the API role (`current_user`, `request.jwt.claims`, cross-tenant SELECT). Converts the #1 risk from inferred to proven (or refutes it). Then **sweep every router for a missing `.where(workspace_id==)`** — the test suite cannot, so a human/grep + the `agents.py`/`mcp_server.py` no-path-param idioms must be hand-verified. Add: confirm `call_summaries` (E2) and the MCP tool outputs are not cross-tenant readable.

4. **[WEB TENANCY — HIGH] Sweep the 9 unread `(app)` pages for direct `.from()` table reads** (esp. `pipeline`, `inbox`, `calls`, `connectors`, `tasks`, `contacts/[id]`, `projects/[id]`). Any direct Supabase table read under inert RLS = `Sidebar`-class cross-tenant exposure. Phase 1 only checked 4 of ~13.

5. **[WORKER DATA-LOSS — HIGH] Resolve D5/D6 from the repo's own deploy files first**, then attack: (a) read `docker-compose.yml`+railway tomls+`start.sh` to settle web/worker shared-volume → if none, **all call transcription is silently broken** (data never produced); (b) prove the ingest TOCTOU double-insert (D6) under concurrency=2 + Pub/Sub redelivery (no UNIQUE constraint → duplicate messages). Pair with D7 (no acks_late/DLQ → in-flight task loss on worker death).

6. **[FALSE MARKETING — HIGH/legal] Lock the SOC 2 / GDPR / 99.9% / ML-metric claims as demonstrably false** (A1-A9) with the strongest single artifact each, AND add the two new in-product surfaces: the **MCP "ML lead score"** tool description and the **`reports` synthetic-forecast** page. The GDPR claim (A2) gets a concrete refutation via Part 2.3: *contact deletion orphans rather than deletes the contact's data* — demonstrate it.

7. **[DATA INTEGRITY — HIGH] Demonstrate `delete_contact` orphaning.** Create contact + linked deal/message/task, DELETE the contact, show the children survive with `contact_id = NULL` (SQL rule) or unexpected ORM behavior. Directly refutes the docstring ("all cascade-linked records") and the GDPR claim.

8. **[AUTH-BYPASS surface — HIGH] Webhook fail-open + unauth jobs.** Confirm prod values of `GMAIL_WEBHOOK_SECRET`/`SLACK_SIGNING_SECRET` (B5/B6 → if empty, unauth forced-sync/DoS). Independently, exploit **D4**: any authed user `GET /jobs/{id}` reads any tenant's transcribe/enrich result by ID (verified: zero ws check). Quantify job_id guessability (Celery UUID).

9. **[COST-DoS — HIGH financial] Pair B15 + D8.** Show the IP-only, per-process, X-Forwarded-For-blind limiter does not gate `/ai/query` / `compose_email` / transcription / bulk-embed, and that each call hits the single shared `ANTHROPIC_API_KEY` with no per-tenant quota. One abusive tenant → unbounded spend + 2-slot queue starvation for all others.

10. **[SILENT SCHEDULER FAILURE — HIGH] Reproduce the beat crashes + health cascade (D1/D2).** Run `optimize_pipeline`/`compute_deal_health` via beat's `args:[]` to force the `TypeError`; then show the daily HITL `health_score<=40` sweep finds nothing because nothing lowers the default 100; then show `pm_agent` is blind (crash leaves no row). This is the "agents that never sleep don't run" proof.

11. **[CORS — MEDIUM, easy] Probe prod `CORS_ORIGIN_REGEX`.** With `allow_credentials=True`, test whether an attacker-controlled origin matching a loose regex gets `Access-Control-Allow-Origin` + credentials. Quick `curl -H "Origin: https://evil.riphere.com.attacker.com"`.

12. **[ASSURANCE INTEGRITY — MEDIUM] Document that CI/tests provide false assurance** (2.1 + 2.2): 295-vs-324 drift, hardcoded-pip vs requirements.txt, demo-mode in every gate, and the structurally-untestable tenancy. This isn't a vuln but it's why everything above slipped through — belongs in the Phase 2 report as the root process failure.

---

## Part 5 — Do-NOT-waste-time list (Phase 1 got these right; don't re-litigate)
- `bulk_deal_action` tenancy is **correct** (2.4) — use as the positive template, don't hunt it as a bug.
- SSE `stream_events` (`events.py`) **does** check `workspace_id` (line 108) — the orphaned *web* `api/events/route.ts` token-in-URL (C9) is the only live issue, and it has zero consumers.
- pgvector search SQL-injection-safety, MiniLM semantic search (A12), Fernet token encryption (B14), Slack HITL fail-closed (B7), ES256/JWKS verify, PKCE/OTP signup fix (C3): all VERIFIED-true; no Phase 2 spend.
- `proxy.ts` dead-middleware is **decisively proven** (build manifest empty) — don't re-prove; just act on the blast-radius framing in Part 3 #5.
