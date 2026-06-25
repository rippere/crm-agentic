# Phase 1 — Web Data-Access Layer (apps/web/src/lib + hooks + components)

Scope repo: `/tmp/crm-signup-fix` — git worktree on branch **`fix/signup-confirm-redirect`** (NOT `master` directly; HEAD = `429da2f fix(auth): rescue auth params that fall back to the Site URL`). The task brief said "production master branch / deployed code" — flag: this worktree is on a signup-fix feature branch, so treat as near-prod but verify against actual master before acting.

Stack: Next.js **16.2.4** (App Router, Turbopack), React 19.2.4, `@supabase/ssr`, FastAPI backend, Celery/Redis jobs (job poller), Supabase Postgres + Supabase Auth + Supabase Realtime.

---

## THE CRITICAL QUESTION: Supabase-direct vs FastAPI — what's the pattern?

**Answer: there are TWO competing data-access patterns, and they are split inconsistently.**

### Pattern A (dominant, ~95% of data): Supabase for AUTH only → FastAPI for DATA
The intended/dominant architecture:
1. Page/hook calls `createBrowserClient()` (from `lib/supabase.ts`) **only** to get the session: `supabase.auth.getSession()` → pulls `session.access_token` and `session.user.user_metadata.workspace_id`.
2. Then it calls `apiClient.*` (from `lib/api-client.ts`) which does `fetch(\`${NEXT_PUBLIC_FASTAPI_URL}${path}\`, { Authorization: Bearer <token> })`.
3. FastAPI is the system of record for contacts, deals, agents, tasks, projects, messages, connectors, calls, activity, workspace CRUD, AI query, CSV import/export, semantic search, etc.

This is the pattern in **every data hook** (`useContacts`, `useDeals`, `useAgents`) and **every (app) page** for mutations and most reads (contacts, calls, connectors, inbox, pipeline, projects, settings, tasks, reports, dashboard PM KPIs).

### Pattern B (the leak, ~4 sites): Page/component talks DIRECTLY to Supabase Postgres, bypassing FastAPI
Exactly four direct `supabase.from(<table>)` / Realtime data paths bypass the backend:

| # | File:line | Call | Table | Notes |
|---|-----------|------|-------|-------|
| B1 | `app/(app)/layout.tsx:33-37` | `.from("workspaces").select("mode").eq("id",wsId).single()` | workspaces | Server component, reads workspace mode for the shell. Uses `createServerClient`. |
| B2 | `hooks/useWorkspace.ts:45-49` | `.from("workspaces").select("*").eq("id",wsId).single()` | workspaces | Duplicates B1's read on the client via a hook. **Same data, two readers, two clients.** |
| B3 | `components/layout/Sidebar.tsx:131-137` | `.from("agents").select("name,status").limit(4)` | agents | "Nexus" live agent widget. **No workspace_id filter** — relies entirely on RLS for tenant scoping. |
| B4 | `app/(app)/dashboard/page.tsx:308-333` | `supabase.channel().on("postgres_changes",{table:"activity_events", filter:workspace_id=eq.<id>}).subscribe()` | activity_events | Supabase **Realtime** subscription for the live activity feed. |

### Pattern C (a third style, redundant with A): raw inline `fetch()` to FastAPI, bypassing apiClient
- `app/(app)/agents/page.tsx:597-608` and `:615-621` — raw `fetch(\`${FASTAPI}/agents\`)` instead of `apiClient.listAgents(token)`. Hand-rolls the exact same call apiClient already wraps. **Duplicated logic.**
- `hooks/useRole.ts:29-32` — raw `fetch(\`${FASTAPI}/me\`)` (no apiClient method for `/me` exists).
- `hooks/useJobPoller.ts:46` — raw `fetch(\`${FASTAPI}/jobs/${jobId}\`)` (no apiClient method for `/jobs/:id`).
- `app/onboarding/page.tsx` — raw fetch + `apiClient.createWorkspace` mix.

So really **three** styles coexist: (A) apiClient→FastAPI, (B) supabase.from→Postgres, (C) raw fetch→FastAPI.

### Activity-events data is read THREE different ways (worst homogenization offender)
The `activity_events` table is surfaced by three different mechanisms:
1. `dashboard/page.tsx:269` — `apiClient.listActivity()` (FastAPI REST seed).
2. `dashboard/page.tsx:308` — Supabase Realtime `postgres_changes` (direct Postgres push).
3. `Header.tsx:51` — `apiClient.listActivity()` again (notifications bell, separate fetch).
Plus there's a **fourth, unused** path: `app/api/events/route.ts` is a Next route handler that proxies an SSE stream from `${FASTAPI}/workspaces/:id/events` — but **nothing in the codebase consumes `/api/events`** (no `EventSource` anywhere; grep found only the comment). Dead/orphaned SSE plumbing that overlaps with the Realtime subscription.

---

## Central files (read in full)

### `lib/api-client.ts` (616 lines) — the FastAPI gateway
- `FASTAPI_URL = process.env.NEXT_PUBLIC_FASTAPI_URL || 'http://localhost:8000'`.
- Module-level `const isDemoMode = process.env.NEXT_PUBLIC_DEMO_MODE === 'true'`.
- `apiFetch(path, options, token?, isFormData?)` — central fetch wrapper. Logs network/CORS failures (TypeError, no status) AND non-2xx (`res.status`), then rethrows `Error("API error <status>")`. Good observability comment at :118-122 about CORS allowlist breakage.
- **Every method has an `if (isDemoMode) return Promise.resolve(<stub>)` branch** before the real `apiFetch`. This is the single biggest source of bloat — the entire demo dataset (briefs, emails, timelines, revenue history, deal-contact map) is hardcoded inline at the top of this file (lines 4-100) instead of in demo-data.ts.
- Covers: agents, connectors (gmail/slack auth+sync+delete), messages (+score-clarity, reprocess), CSV export (contacts/deals — returns Blob), tasks CRUD, contacts CRUD (+compose, score, enrich, status, timeline, brief, send-email, semantic search, embed-all, import CSV), calls (upload/get/delete), deals CRUD (+timeline, bulk action, health, stale, history, probability-trend), pipeline suggestions, workspace CRUD + invite, activity list/create, projects CRUD + tasks, AI query.
- Inconsistency: `getConnectors` is called in `contacts/page.tsx:982` expecting `{provider: string}[]`, but the demo `getConnectorStatus` and `ConnectorRow` use `service` not `provider` (field-name drift — see inconsistencies).
- Inconsistency: uses `require('./demo-data')` (CommonJS) inside `exportContactsCsv`/`exportDealsCsv`/`getStaleDeals` (lines 209/224/409) while importing ESM at the top. Mixed module styles in one file.
- HTTP verb drift: `updateTask` uses `PUT` (:261) while `updateContact`/`updateDeal`/`updateAgent`/`updateWorkspace`/`updateContactStatus` use `PATCH`. Inconsistent REST semantics.

### `lib/supabase.ts` (304 lines) — Supabase client + DB types
- Exports `createBrowserClient()` (singleton, memoized in `_browserClient`), `createServerClient(cookieStore)` (per-request), and **`getSupabase()` marked `@deprecated`** ("kept for backward compat during migration" — migration is incomplete; see below).
- Contains the entire `Database` type + all 11 row types (WorkspaceRow, UserRow, ContactRow, DealRow, AgentRow, ActivityEventRow, ConnectorRow, MessageRow, TaskRow, MetricTemplateRow, ClarityScoreRow). This is the canonical snake_case schema mirror.
- Demo-mode handling: if `!url || !key` AND demo mode → builds a **stub client pointed at `http://localhost:54321` with key `"demo-key"`** (:263). Comment says "Hooks will short-circuit before making any real Supabase calls" — i.e. correctness depends on every caller checking `isDemoMode` first. Sidebar B3 and dashboard Realtime B4 do NOT obviously short-circuit the `.from`/`.channel` calls in demo (Sidebar's `.from("agents")` would fire against the stub localhost:54321 and silently fail — acceptable but sloppy).
- `createServerClient` `set`/`remove` cookie handlers are **no-ops** with comments "handled by middleware". The middleware that's supposed to refresh cookies is `proxy.ts` (see risks — non-standard filename).
- `getSupabase()` deprecated alias: grep shows **zero callers remain** — fully dead, safe to delete.

### `lib/demo-data.ts` (955 lines) — the demo/seed dataset
- Exports `demoWorkspace`, `demoContacts` (10, c-001..c-010), `demoDeals` (8, d-001..d-008), `demoAgents` (6, a-001..a-006), `demoActivity` (15), `demoMessages` (6) + `DemoMessage` type, `demoTasks` (8) + `DemoTask` type, `demoConnectors` (2) + `DemoConnector` type, `demoDashboard` aggregates, `demoKPIs`, `demoRevenueChartData`, `demoAgentAccuracyData`.
- camelCase frontend shape (mlScore, semanticTags, contactName, mlWinProbability, healthScore, createdAt) — i.e. the `types.ts` `Contact`/`Deal`/`Agent` types, NOT the snake_case `*Row` types.
- Internal data inconsistency: `demoActivity` references agents **"Task Extractor"** (ev-011) and uses agent names not present in `demoAgents` (the 6 agents are Semantic Sorter, Lead Scorer, Email Composer, Call Summarizer, Pipeline Optimizer, Sentiment Analyzer — no "Task Extractor"). Cosmetic, demo-only.
- Numeric inconsistency: `demoDashboard.totalRevenue = 485000` and `demoKPIs` "Total Revenue" = "$485,000", but summing `demoContacts[].revenue` = 145k+220k+48k+72k = 485k only if you count churned c-008 (72k) — internally self-consistent but `activeDeals: 6` vs `demoDeals` has 8 entries (2 closed). Minor.

### `lib/mock-data.ts` (14 lines) — alias shim
- Pure re-export: `demoContacts as mockContacts`, `demoDeals as mockDeals`, `demoAgents as mockAgents`, `demoActivity as mockActivity`, `demoKPIs as mockKPIs`, `demoRevenueChartData as revenueChartData`, `demoAgentAccuracyData as agentAccuracyData`.
- **Naming schism:** half the codebase imports `mockAgents`/`mockActivity` (dashboard, agents page), the other half imports `demoContacts`/`demoDeals`/`demoAgents` directly (hooks, contacts/[id], dashboard). Two names for identical data → confusing. `dashboard/page.tsx` imports from BOTH `@/lib/mock-data` (mockAgents, mockActivity) AND `@/lib/demo-data` (demoDashboard) in the same file.

### `lib/demo-mode.ts` (1 line)
- `export const isDemoMode = process.env.NEXT_PUBLIC_DEMO_MODE === 'true'`.
- But callers inconsistently re-read the env inline: `useRole.ts:19`, `agents/page.tsx:568,592`, `dashboard/page.tsx` (`DEMO_MODE` local const) all do `process.env.NEXT_PUBLIC_DEMO_MODE === "true"` directly instead of importing this constant. Three+ duplicated literals of the same check.

---

## Hooks (read in full)

| Hook | Auth source | Data source | Pattern |
|------|-------------|-------------|---------|
| `useWorkspace` | `supabase.auth.getUser()` | **`supabase.from("workspaces")`** (DIRECT) | B — bypasses FastAPI |
| `useContacts` | `supabase.auth.getSession()` | `apiClient.listContacts/create/update/delete` | A |
| `useDeals` | `supabase.auth.getSession()` | `apiClient.listDeals/create/update/delete` | A |
| `useAgents` | `supabase.auth.getSession()` | `apiClient.listAgents/triggerAgent/updateAgent` | A — **but DEAD: no page/component imports useAgents** |
| `useRole` | `supabase.auth.getSession()` | raw `fetch(${FASTAPI}/me)` | C |
| `useJobPoller` | `supabase.auth.getSession()` | raw `fetch(${FASTAPI}/jobs/:id)` 2s poll | C |

- `useContacts`/`useDeals`/`useAgents` are near-identical boilerplate: each re-implements `getSession()→token+workspaceId→"Not authenticated"` guard in 4 places (fetch + create + update + delete). ~60 lines of duplicated auth-plumbing per hook that could be one `useAuthedRequest()` helper. **Prime homogenization target.**
- Error-string drift: useContacts/useAgents say `"Not authenticated"`; useDeals says `"No workspace found"` for the same condition (:57).
- `useDeals.rowToDeal` (:20) reads `health_score` via an ugly `(row as unknown as Record<string,number>).health_score ?? 100` cast even though `DealRow.health_score` is a typed field — leftover from when the column didn't exist. `useDeals` also silently **drops** `assignedAgent`/`notes`/`healthScore` defaulting and never maps `contact_id`.
- `useAgents` being completely unused is notable: agents page hand-rolls the fetch (Pattern C) and Sidebar hand-rolls Supabase (Pattern B), so the one "correct" Pattern-A hook for agents is orphaned.

---

## Components (skimmed)

- `layout/ClientShell.tsx` — no data access (pure layout/mode prop passthrough).
- `layout/Header.tsx` — `supabase.auth.getSession()` + `apiClient.listActivity(workspaceId, token, 8)` for the notifications bell (Pattern A). Third reader of activity_events.
- `layout/Sidebar.tsx` — **Pattern B**: direct `supabase.from("agents").select("name,status").limit(4)` for the "Nexus" widget (no workspace filter → RLS-dependent). Also `supabase.auth.signOut()`.
- `ui/CommandPalette.tsx` — `supabase.auth.getSession()` + `apiClient.aiQuery()` (Pattern A).
- `ui/{Avatar,Badge,Button,Card,ConfirmDialog,LogActivityModal}.tsx` — presentational, no data access.

---

## Auth / middleware / routes

- `proxy.ts` — exports `async function proxy(request)` + `config.matcher`. **Non-standard filename**: Next.js convention is `middleware.ts` exporting `middleware`. However: the BUILD proves it IS wired — `.next/server/middleware.js` stub loads chunk `[root-of-the-server]__0i3~0l6._.js`, which contains the exact `_next/static|_next/image` matcher regex from proxy.ts. So Next 16/Turbopack picked it up (likely via `next.config.ts` or a convention I didn't read). **Refuted my initial "dead middleware" hypothesis** — but the filename is still a homogenization/onboarding hazard (a new dev grepping for `middleware.ts` finds nothing). VERIFY in next.config.ts how it's registered.
- Refreshes the Supabase session cookie (`supabase.auth.getUser()`), skips entirely in demo mode (avoids ~25s timeout when Supabase unreachable — good comment :9-11).
- `app/auth/callback/route.ts` — signup-fix work. Handles PKCE (`exchangeCodeForSession`), OTP (`verifyOtp`), explicit error, and the cross-device fallback (`/login?confirmed=1`). Rebuilds public origin from `x-forwarded-host`/`x-forwarded-proto` for Railway proxy. Comment :24 mentions "riphere.com" (note: spelled riphere, while callback fallback/DEPLOY may say otherwise — cross-check domain).
- `app/(app)/layout.tsx` — server-side auth gate: `getUser()` → redirect `/login`; no `workspace_id` → redirect `/onboarding`; then **Pattern B** `from("workspaces").select("mode")`.

---

## Data flow summary (non-demo)

```
Browser (React 19 client components)
  │  createBrowserClient().auth.getSession()  ──► Supabase Auth (token + user_metadata.workspace_id)
  │
  ├─[Pattern A ~95%]─► apiClient.* ──fetch(Bearer)──► FastAPI (NEXT_PUBLIC_FASTAPI_URL)
  │                                                      └─► Postgres (system of record) + Celery/Redis jobs
  │
  ├─[Pattern B ~4 sites]─► supabase.from("workspaces"|"agents") / supabase.channel(activity_events)
  │                          ──direct──► Supabase Postgres  (RLS is the ONLY tenant guard here)
  │
  └─[Pattern C few]─► raw fetch(${FASTAPI}/me | /jobs/:id | /agents) ──► FastAPI

Server components:  createServerClient(cookies).auth.getUser() + .from("workspaces")  (Pattern B)
Middleware (proxy.ts): refresh session cookie (skipped in demo)
Job polling: useJobPoller → fetch(${FASTAPI}/jobs/:id) every 2s
SSE: app/api/events/route.ts proxies ${FASTAPI}/workspaces/:id/events  ── ORPHANED, no consumer
Workspace identity: ALWAYS from supabase user_metadata.workspace_id (single source) — never from a cookie/API claim
```

---

## RISKS (evidence-backed)

### Multi-tenancy / auth (auto-high+)
1. **[HIGH] Tenant isolation for Pattern-B reads depends ENTIRELY on Supabase RLS, with the browser anon key.** `Sidebar.tsx:131` (`from("agents")` no workspace filter), `useWorkspace.ts:46` and `layout.tsx:34` (`from("workspaces").eq("id",wsId)` where `wsId` comes from client-readable `user_metadata`), and `dashboard:316` Realtime filter `workspace_id=eq.<id>`. If any RLS policy on `agents`/`workspaces`/`activity_events` is missing or permissive, a user can read other tenants' rows directly — the FastAPI authorization layer is bypassed for these paths. The agents query has NO explicit workspace_id predicate at all, so it is 100% RLS-reliant. **Needs RLS policy audit on those 3 tables.**
2. **[HIGH] `workspace_id` is sourced from `user_metadata` (client-mutable surface).** Everywhere (`useContacts/useDeals/useAgents/dashboard/Header/...`) reads `session.user.user_metadata.workspace_id`. `user_metadata` (vs `app_metadata`) is writable by the user via `supabase.auth.updateUser` — and indeed `onboarding/page.tsx:82` does exactly `updateUser({ data: { workspace_id } })`. A user could set their own `workspace_id` to another tenant's id; FastAPI must independently verify membership (UserRow.workspace_id) and NOT trust the JWT's user_metadata. Pattern-B direct reads (which trust it for the `.eq` filter) are the exposure. **Verify FastAPI re-checks workspace membership server-side and that this isn't the only guard.**
3. **[MEDIUM] SSE proxy passes the bearer token as a URL query param** — `app/api/events/route.ts:9` (`?token=`), echoed by proxy.ts comment "EventSource cannot send custom headers". Tokens in URLs leak into access logs, referrer headers, browser history. It's currently orphaned (no consumer) so impact is latent, but if wired up as-is it's a token-leak vector. Either delete the route or move to a cookie/short-lived ticket.

### Correctness / reliability
4. **[MEDIUM] Dual live-activity mechanisms can diverge & double-render.** Dashboard seeds via REST (`listActivity`) then pushes via Realtime (`postgres_changes`); both write `liveActivity`. No dedup by id between the seed and the first Realtime INSERT could double-show an event; and if Realtime is unconfigured on the Supabase project, the feed silently stops updating with no fallback to the existing `/api/events` SSE proxy. Two overlapping push systems (Realtime + orphaned SSE) for one feature.
5. **[LOW] Stub Supabase client fires real network calls in demo for Pattern-B sites.** `Sidebar.tsx` `.from("agents")` and dashboard `.channel()` are not guarded by `isDemoMode`, so in demo mode they hit the stub `http://localhost:54321` / `demo-key` and fail silently (caught/empty). Harmless today but violates the "hooks short-circuit before real calls" assumption in supabase.ts:262.
6. **[LOW] `useDeals.rowToDeal` defensive cast `(row as unknown as Record<string,number>).health_score`** (:20) indicates schema/type drift between `DealRow` and what FastAPI returns; brittle. Also never maps `contact_id`, so deal→contact linking is lost through this hook.

### Config / build
7. **[MEDIUM] `.env.example` does not match what the code reads.** Code requires `NEXT_PUBLIC_SUPABASE_URL` + `NEXT_PUBLIC_SUPABASE_ANON_KEY` (supabase.ts:254-255). `.env.example` lists both the `NEXT_PUBLIC_*` vars AND non-public `SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY`/`SUPABASE_JWT_SECRET` (backend vars). It's a shared root env for FastAPI+web, but a web-only dev copying it could miss that the browser needs the `NEXT_PUBLIC_` pair — and supabase.ts throws a hard error at startup if they're absent (and not in demo). Minor onboarding trap.
8. **[LOW] `proxy.ts` vs `middleware.ts` naming.** Functionally wired (confirmed in build) but discoverability/convention hazard. Standardize to `middleware.ts`.

---

## INCONSISTENCIES (homogenization backlog — user wants this product homogenized)

1. **Three data-access styles** for the backend: `apiClient.*` (A), `supabase.from` (B), raw `fetch(${FASTAPI})` (C). Pick one (A) and convert B3/Sidebar agents + C/agents-page + C/useRole + C/useJobPoller to apiClient methods (add `apiClient.getMe()`, `apiClient.getJob(id)`).
2. **`activity_events` read 3 ways** (REST seed, Realtime push, Header REST) + a 4th orphaned SSE route. Consolidate to one mechanism.
3. **`mock*` vs `demo*` naming schism.** `mock-data.ts` is a pure alias of `demo-data.ts`. Dashboard imports from both files. Kill `mock-data.ts`, rename all `mockX`→`demoX`.
4. **`isDemoMode` constant duplicated inline.** `demo-mode.ts` exports it, but `useRole`, `agents/page`, `dashboard`, `api-client`, `supabase` each re-read `process.env.NEXT_PUBLIC_DEMO_MODE === "true"`. Import the constant everywhere.
5. **`useAgents` hook is dead code.** Agents page (Pattern C raw fetch) and Sidebar (Pattern B supabase) both reimplement agent fetching instead of using it. Either adopt the hook or delete it; right now there are 3 agent-fetch implementations.
6. **Duplicated auth-plumbing** in every hook + page: `getSession()→token+wsId→guard` repeated ~30 times across the tree (grep: 30+ `supabase.auth.getSession()` sites). Extract a shared `useAuth()`/`getAuthContext()` helper.
7. **HTTP verb drift in api-client:** `updateTask`=PUT vs all other updates=PATCH.
8. **Error-message drift:** "Not authenticated" (useContacts/useAgents) vs "No workspace found" (useDeals) vs "No workspace found. Please complete onboarding." (useWorkspace) for the same missing-session/workspace condition.
9. **Connector field name drift:** `ConnectorRow.service` / demo `getConnectorStatus` uses `service`, but `contacts/page.tsx:982` consumes `getConnectors()` as `{provider: string}[]`. `service` vs `provider` mismatch — one of them is reading undefined.
10. **Module-system mix in api-client.ts:** ESM `import` at top, CommonJS `require('./demo-data')` inside 3 methods (lines 209/224/409).
11. **Demo stubs split across two files:** big demo dataset is in `demo-data.ts`, but contact briefs / email stubs / timelines / revenue history / deal-contact map are hardcoded at the top of `api-client.ts` (lines 4-100). Move them into demo-data.ts so api-client is pure transport.
12. **Two demo-token conventions:** dashboard & pipeline & tasks pass literal `"demo-workspace-1"`/`"demo-token"` to apiClient in their DEMO_MODE branches (e.g. dashboard:250, pipeline:394, tasks:214), which only work because apiClient short-circuits on the env flag — the literal args are inert. Confusing; the demo branch should not pretend to pass real ids.
13. **`getSupabase()` `@deprecated` shim** in supabase.ts:301 with zero remaining callers — the "migration" it references is done; delete it.
14. **`proxy.ts` filename** ≠ Next convention `middleware.ts` (see risk 8).

---

## CLAIMS made by this area (to verify in Phase 2)

- (UI copy, Sidebar) "NovaCRM / Agentic Intelligence", "LIVE" badge on Agents, "All systems operational", Nexus "{N} active" — the LIVE/active counts are driven by a real `from("agents")` query (Sidebar:131), so the dot is genuinely data-backed (not faked) when Supabase reachable. ✓ plausible.
- (api-client comment :118) network/CORS failures are logged not swallowed — TRUE, `apiFetch` catch logs then rethrows.
- (supabase.ts :300) `getSupabase` "kept for backward compat during migration" — migration appears COMPLETE (0 callers); claim is stale.
- (proxy.ts :9) demo mode skips Supabase refresh to avoid "~25s network timeout" — plausible, code returns early when IS_DEMO. ✓
- (auth/callback comments) PKCE same-browser + OTP cross-browser + cross-device fallback all handled — code matches the comments (3 branches present). ✓ (functional correctness = Phase 2 live test).
- (demo-data) agent model strings: "claude-sonnet-4-6", "xgboost-v2.1-crm", "whisper-large-v3 + claude-haiku", "sentence-transformers/all-MiniLM-L6-v2", "cardiffnlp/twitter-roberta-base-sentiment", "heuristic-v3 + gpt-4o-mini" — these are DEMO seed strings, not proof the backend runs these models. Verify against FastAPI agent impls before treating as real capability claims.
- (scoreClarity demo stub) `model_used: 'claude-sonnet-4-6'` — demo stub only.

## Open questions for synthesizer
- Confirm this branch (`fix/signup-confirm-redirect`) vs actual `master` — brief said master/deployed.
- Read `next.config.ts` to confirm exactly how `proxy.ts` is registered as middleware (turbopack config? `experimental`?). Build artifact proves it's active, but the mechanism matters for the homogenization rename.
- RLS policy audit on `workspaces`, `agents`, `activity_events` (Pattern-B + Realtime tables) — the security verdict hinges on this.
- Does FastAPI independently verify `workspace_id` membership (not trust JWT `user_metadata`)? Risk 2 hinges on this.
- Is `/api/events` SSE route truly dead, or consumed by something outside this scope (mobile? a future feature)? If dead, delete (token-in-URL risk).
- Connector `service` vs `provider`: which side is wrong (api-client/backend vs contacts/page.tsx:982)?
