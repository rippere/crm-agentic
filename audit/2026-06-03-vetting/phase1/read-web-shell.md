# NovaCRM — Web Shell / Auth / Routing audit notes (Phase 1)

Scope: `/tmp/crm-signup-fix/apps/web/src/app` (layouts, `(app)` group, routing, auth guards,
login/onboarding/auth-callback, navigation/ClientShell). Plus supporting lib/hooks/components
that determine how auth is enforced and how demo mode behaves.

Repo: `/tmp/crm-signup-fix` — git worktree, branch `fix/signup-confirm-redirect`, HEAD `429da2f`
("fix(auth): rescue auth params that fall back to the Site URL"). This is the deployed master
line with a signup/confirmation-redirect fix in flight.

---

## 1. Route map & which routes are guarded

App Router tree under `src/app`:

- `layout.tsx` (ROOT) — pure HTML/body shell + metadata/viewport. **No auth.** (`src/app/layout.tsx`)
- `page.tsx` — public marketing **landing page** (`"use client"`). Contains `AuthParamsRescue`. **No auth.**
- `login/page.tsx` — public login/signup (Supabase email+password). **No auth (public).**
- `onboarding/page.tsx` — public 4-step workspace-creation wizard. **No server guard** (see RISK).
- `auth/callback/route.ts` — Supabase email-confirm / magic-link / recovery handler (server Route Handler).
- `auth/gmail/callback/page.tsx`, `auth/slack/callback/page.tsx` — OAuth bounce pages → forward code/state to FastAPI.
- `api/events/route.ts` — SSE proxy to FastAPI. Auth = token as **query param** (EventSource limitation).
- `(app)/layout.tsx` — **THE auth guard.** Server component. Wraps all the following:
  - `(app)/dashboard`, `contacts` (+`[id]`), `pipeline` (+`[id]`), `reports`, `agents`, `inbox`,
    `calls`, `tasks`, `projects` (+`[id]`), `connectors`, `settings`.
- There is **no `(app)/page.tsx`** — the route group has only `layout.tsx`. `/dashboard` is the de-facto
  app home; every landing-page CTA and the login redirect target `/dashboard` directly.

### How auth is enforced per page
- **Single choke point:** `(app)/layout.tsx` is the *only* server-side auth gate. It:
  1. Short-circuits entirely if `NEXT_PUBLIC_DEMO_MODE === "true"` (renders shell, **no auth**).
  2. `const { data: { user } } = await supabase.auth.getUser();` → `if (!user) redirect("/login")`.
     (Good: uses `getUser()` which re-validates the JWT with Supabase, not just `getSession()`.)
  3. Reads `workspace_id` from `user.user_metadata`; `if (!workspaceId) redirect("/onboarding")`.
  4. Queries `workspaces` table (anon-key server client) for `mode`, passes `mode/email/name` to `ClientShell`.
- **Individual `(app)/*` pages do NOT re-check auth.** They are all `"use client"` and trust the layout.
  Each page independently calls `supabase.auth.getSession()` on mount **only to obtain the access token +
  `workspace_id`** for FastAPI calls — not as a guard. If no session, they silently `return` (render empty),
  relying on the layout having already redirected. Confirmed in: dashboard:261, settings:50, contacts:972,
  tasks:223, pipeline:400/450/470/493, inbox:234, projects:249 & [id]:64, pipeline/[id]:166, contacts/[id]:197,
  calls:297, agents:574, plus hooks useDeals/useContacts/useAgents/useRole/useWorkspace.
- **Authorization (role):** only `settings/page.tsx` does any RBAC, client-side, via `useRole()` (hits
  FastAPI `/me`). It disables Save/Invite/Delete and hides the Team card when `!isAdmin`. This is **UI-only**
  enforcement; real enforcement must live in FastAPI (out of this scope but flagged).

---

## 2. The middleware that isn't: `src/proxy.ts` (DEAD CODE — high-signal finding)

- `src/proxy.ts` is written exactly like Next.js auth middleware: it imports `@supabase/ssr`
  `createServerClient`, calls `await supabase.auth.getUser()` to refresh the session cookie, and exports a
  `config.matcher` covering all non-static routes.
- BUT: the file is named `proxy.ts` (not `middleware.ts`) and exports a function named `proxy`
  (not the required `middleware`). Next.js auto-registers middleware **only** from `middleware.ts`/`.js` at
  the project root or `src/`. So **this never runs.**
- Verified:
  - No `middleware.ts`/`.js` exists in source or in git (`git ls-files` → only `apps/web/src/proxy.ts`).
  - `git log --follow` on proxy.ts: it was **added** as `proxy.ts` in commit `7d9cf5c`, never as middleware;
    last touched in `f6a2b26` ("proxy timeout"). No middleware.ts ever existed/was deleted in history.
  - Nothing imports/re-exports `proxy` (grep of `src` shows only its own definition + unrelated word usages).
  - A compiled `.next/server/middleware.js` exists but is a **stale build artifact** (grep shows 0 `getUser`,
    no real matcher) and is older/unrelated to current source; `.next` is a build dir, not source of truth.
- **Consequences of it being dead:**
  - Supabase **session cookies are never refreshed at the edge.** On an expired access token, the *only*
    refresh path is whatever the per-page browser client does. The server component layout calls
    `getUser()` with cookies that the server client **cannot rewrite** (its `set/remove` are no-ops — see
    supabase.ts:289-294, comment literally says "handled by middleware"… which doesn't exist). So a user with
    an expired-but-refreshable session can get bounced to `/login` by the layout even though they're "logged in,"
    until the client SDK silently refreshes and a reload succeeds. Flaky-auth UX risk.
  - The comment in `supabase.ts` ("Server components can't set cookies directly; handled by middleware") is now
    **false documentation** — the middleware it refers to is inert.

---

## 3. Auth flows (signup / confirm / login)

### Signup + email confirmation (the in-flight fix)
- `login/page.tsx` signup: `supabase.auth.signUp({ email, password, options: { emailRedirectTo:
  `${origin}/auth/callback` } })`. On success shows "check your email," flips to login mode.
- `auth/callback/route.ts` (server) handles the confirmation click:
  - Whitelists `next` to same-site relative only (`startsWith('/') && !startsWith('//')`) → good (open-redirect safe).
  - Rebuilds public origin from `x-forwarded-host`/`x-forwarded-proto` because "Behind Railway's proxy…"
    redirects must stay on the public domain. Comment references **riphere.com** (note spelling; see inconsistency).
  - If `?error`/`?error_code` → `/login?error=confirm`.
  - PKCE: `exchangeCodeForSession(code)` (needs verifier cookie from same browser).
  - OTP/token_hash: `verifyOtp({ type, token_hash })` (cross-device safe).
  - Fallthrough: `/login?confirmed=1` ("email confirmed server-side, just sign in").
- `page.tsx` `AuthParamsRescue` (client, runs on the **landing page**): catches Supabase redirects that
  "fall back to the Site URL" when the callback URL isn't in Supabase's redirect allowlist:
  - `?code=` → `router.replace('/auth/callback?code=…')` (hand to the server route).
  - hash `error`/`error_code` → `/login?error=confirm`.
  - hash `access_token`+`refresh_token` (implicit flow) → `setSession(...)` then `/dashboard`, else `/login?confirmed=1`.
  - NOTE: there is a polarity oddity — on `setSession` **success** it routes to `/dashboard`, but on **error**
    it routes to `/login?confirmed=1` (a *success*-toned message "Email confirmed! Sign in"). So a genuine
    set-session failure shows a green "confirmed" banner. Minor but misleading. (page.tsx:42-44)
- `login/page.tsx` reads `?error=confirm` → red "invalid/expired link" and `?confirmed=1` → green "Email confirmed!".

### Login
- `signInWithPassword` → on success `router.push('/dashboard')`. Generic error copy "Invalid email or password."

### Onboarding (workspace creation)
- Step 2 `createWorkspace()`: `getSession()` (must be authed), `apiClient.createWorkspace({name,slug,mode}, token)`,
  then **writes `workspace_id` into JWT** via `supabase.auth.updateUser({ data: { workspace_id }})` and
  `refreshSession()` so the new JWT carries it (this is exactly what `(app)/layout.tsx` reads). Slug derived
  client-side from name (lowercase/hyphenate/strip).
- Steps 3 (Gmail/Slack connect) & 4 (invite) are **cosmetic**: connect buttons open `auth_url` in a new tab and
  optimistically set "Connected" (handleConnectGmail/Slack), and invite just sets `inviteSent=true` — it does
  **not** call `apiClient.inviteTeammate`. "Go to Dashboard" → `/dashboard`.

---

## 4. ClientShell / navigation

- `(app)/layout.tsx` → `ClientShell mode userEmail userName`. In demo mode it passes `mode="both"` and no
  user identity.
- `ClientShell.tsx` (`"use client"`): responsive chrome only (mobile drawer vs desktop hover-rail, body-scroll
  lock, ⌘K command palette). Renders `Sidebar` + `CommandPalette`. **No auth.** Command palette `onSubmit`
  just `console.log("[NovaCRM AI]", value)` — the "AI search" in the shell is a stub.
- `Sidebar.tsx`: nav groups Workspace/Intelligence/System. Mode-gates items via `hideModes`:
  - `pipeline`,`reports` hidden for `pm`; `tasks`,`projects` hidden for `sales`. `both` shows all.
  - Mode-gating is **presentational only** — the routes still exist and are reachable by URL in any mode
    (e.g. a `pm` workspace can open `/pipeline` directly; nothing blocks it).
  - "Nexus" panel fetches real agents directly from Supabase: `supabase.from("agents").select("name,status").limit(4)`
    — i.e. the sidebar talks to the DB directly (anon key + RLS), bypassing FastAPI. Only place in the shell
    that does direct DB reads.
  - Logout: `supabase.auth.signOut()` → `/login`.
- `Header.tsx` also spins up a browser client + `getSession()` on mount (token for its own fetches); not a guard.

---

## 5. Demo mode behavior (`NEXT_PUBLIC_DEMO_MODE`)

Default is **off** (`.env.example: NEXT_PUBLIC_DEMO_MODE=false`). When `=== "true"`:
- `(app)/layout.tsx`: **bypasses ALL auth** — renders the shell with `mode="both"`, no user. Every protected
  page is reachable with zero credentials.
- `supabase.ts createBrowserClient`: if Supabase env vars are missing, builds a **stub client** pointed at
  `http://localhost:54321` with key `"demo-key"` (so nothing throws); hooks short-circuit before real calls.
- `proxy.ts`: returns early (skips token refresh) — comment: avoids "~25s network timeout" when Supabase is
  unreachable. (Moot, since proxy doesn't run anyway.)
- `api-client.ts`: **every** method has an `isDemoMode` branch returning canned/`demo-data` fixtures (deals,
  contacts, tasks, messages, connectors, calls, briefs, AI answers, CSV blobs built client-side, etc.).
- `useRole.ts`: returns `role="admin"` immediately in demo (so settings RBAC is fully unlocked in demo).
- `useDeals.ts` & friends: seed state from `demoDeals` etc. `workspace-mode-context.tsx`: in demo, persists the
  selected mode to `localStorage` (`novacrm_demo_mode`) and hydrates from it; in real mode it's fixed to the prop.
- `dashboard/page.tsx`: demo branch sets `mode="both"`, PM KPIs from `demoDashboard`, stale deals + revenue
  history from api-client demo stubs.
- Demo workspace mode default = `both` (demo-data.ts:15). demoDeals has a full fixture set; KPIs look realistic.

So demo mode is a **fully offline, auth-free, fixture-backed** showcase. The danger is purely operational:
if `NEXT_PUBLIC_DEMO_MODE=true` is ever set in the real deployment, the entire app is public and shows fake data.

---

## 6. Data flow (this subsystem)

Two distinct client paths plus one server path:
1. **Server (guard):** `(app)/layout.tsx` → `@supabase/ssr` server client (cookies) → `getUser()` (validates) →
   direct `workspaces` table read for `mode`. Tenant isolation here = **Supabase RLS** (anon key).
2. **Client (data):** each `(app)` page / hook → browser Supabase client `getSession()` → extract
   `session.access_token` + `user_metadata.workspace_id` → `apiClient` → `fetch ${NEXT_PUBLIC_FASTAPI_URL}/...`
   with `Authorization: Bearer`. **All multi-tenant data goes through FastAPI keyed by a client-supplied
   `workspace_id`.** The web app trusts `user_metadata.workspace_id`; real isolation must be enforced server-side
   in FastAPI (out of scope but the entire tenancy story depends on it).
3. **Realtime:** dashboard subscribes to Supabase Realtime `activity_events` filtered by `workspace_id` (direct).
   Sidebar reads `agents` directly. So the web app uses Supabase **directly** for: auth, the layout's workspace
   `mode`, dashboard realtime activity, and sidebar agent status — everything else is FastAPI.
- `useDeals` (dashboard KPIs source) initializes real-mode deals to `[]` and only fills from FastAPI; if the API
  is unreachable/empty, **production dashboard KPIs render all-zero** (won $0, 0 deals, 0% win) with no error UI.

---

## 7. Claims made by this area (to verify elsewhere)
(UI copy on the public landing page is marketing and largely unsubstantiated by this subsystem.)
- Landing: "6 AI Agents Running · 94.7% Accuracy", "F1: 0.947", model name-drops (all-MiniLM-L6-v2, XGBoost v2,
  LightGBM, GPT-4o Fine-tuned, Whisper Large v3, Claude 3.5, RoBERTa), "48% Open / 22% Reply Rate",
  "SOC 2 Type II", "99.9% uptime", "GDPR Compliant", "No credit card required". None are backed by anything in web.
- The agent **activity log** on the landing page is **hardcoded** static rows (not live), despite "Live/streaming"
  labels — pure decoration.
- `metadata` (layout.tsx): "AI-native CRM powered by semantic sorting, ML lead scoring, and autonomous agents."
- Code comments (verifiable against reality):
  - supabase.ts: "Server components can't set cookies directly; handled by middleware" → **false** (no middleware).
  - proxy.ts: behaves as middleware but is inert (filename/exports wrong).
  - auth/callback: open-redirect guard + forwarded-host rebuild → **true** as written.
  - login: signup `emailRedirectTo` → `/auth/callback` → **true**.
  - next.config.ts: `typescript.ignoreBuildErrors: true` "Runtime behavior is correct" (Supabase types resolve to
    `never` w/o generated types) — build-time type safety is **off** for the whole web app.

## 8. Risks (evidence-backed; multi-tenant/auth = high+)
- **Dead auth middleware → no edge session refresh.** `src/proxy.ts` never runs (named proxy, not middleware;
  no `middleware.ts` in source/git). Server layout's Supabase client cannot rewrite cookies (no-op set/remove,
  supabase.ts:289-294). Result: stale/expired-but-refreshable sessions can be mis-bounced to /login; relies on
  client SDK refresh + reload. HIGH (auth correctness/reliability).
- **Single-point auth guard.** All protection lives in `(app)/layout.tsx:21-31`. Pages don't re-verify. If a
  route is ever added outside `(app)`, or the group is restructured, it's unguarded by default. `/onboarding`
  already demonstrates this: it's a public route that *assumes* an authed session and only fails at the API call
  (onboarding/page.tsx:70-75) — an unauthenticated user sees the full wizard. MEDIUM-HIGH.
- **Tenant isolation is delegated, never enforced in web.** `workspace_id` is read from client-controlled
  `user_metadata` and sent to FastAPI; the layout reads the `workspaces` table with the anon key. Everything
  rests on Supabase RLS + FastAPI checks. If either is missing/misconfigured, cross-tenant access is possible.
  Cannot be confirmed from web alone → must verify FastAPI/RLS. HIGH (multi-tenancy).
- **Demo-mode kill switch is a single env var that disables all auth.** `(app)/layout.tsx:10` returns the app
  with no auth when `NEXT_PUBLIC_DEMO_MODE=true`; `useRole` returns admin. A misconfigured prod env = fully
  public app + admin everywhere. HIGH (operational/auth).
- **TypeScript build errors ignored app-wide** (`next.config.ts:8`). Type regressions (incl. auth-shaped data)
  won't fail the build. MEDIUM.
- **SSE token in URL** (`api/events/route.ts`): access token as query param → lands in logs/proxies/history.
  Inherent to EventSource but still a token-leak surface. MEDIUM.
- **Misleading success banner on confirm failure** (`page.tsx:42-44`): setSession error → `/login?confirmed=1`
  (green "Email confirmed!"). LOW (UX correctness).
- **Production dashboard KPIs silently render zeros** if FastAPI is down/empty (`useDeals.ts:37-67`,
  dashboard computeKPIs) — looks like real "$0 / 0% win" rather than an error/empty state. LOW-MEDIUM.

## 9. Inconsistencies / homogenization targets
- **Three different demo-mode accessors** for the same env var:
  `lib/demo-mode.ts` (`isDemoMode`), inline `process.env... === "true"` in ~12 files, and module-level consts
  named both `DEMO_MODE` (layout, dashboard) and `IS_DEMO` (proxy, workspace-mode-context). No single import.
- **Two Supabase client factories coexist with a deprecated third:** `lib/supabase.ts` `createBrowserClient`/
  `createServerClient` wrappers, BUT `auth/callback/route.ts` and `proxy.ts` import `createServerClient`
  **directly from `@supabase/ssr`** (bypassing the wrapper), and `getSupabase()` is a `@deprecated` shim still
  exported. Pick one.
- **Auth-state reads are inconsistent:** the secure path (`getUser()`) is used only in the layout; everywhere
  else uses `getSession()` (token extraction). Fine for token-fetch, but there's no shared "useSession/useAuth"
  hook — every page re-implements `getSession().then(...) → workspace_id/token` (dashboard, settings, contacts,
  tasks, pipeline, inbox, projects, calls, agents, useDeals, useContacts, etc.). Prime candidate for one hook.
- **`workspace-mode-context.tsx` appears unused in the live path.** The layout passes `mode` straight to
  ClientShell; pages fetch their own mode (dashboard calls `getWorkspace` again). The Provider/`useWorkspaceMode`
  exist but I found no wiring in `(app)/layout` — likely dead/parallel state. (Confirm consumers in Phase 2.)
- **Dual data-access styles:** sidebar + dashboard hit Supabase **directly** (`from("agents")`, Realtime),
  while all other reads go through FastAPI `apiClient`. Mixed source-of-truth.
- **Mode-gating is presentational only** (Sidebar `hideModes`) with no route-level enforcement — a `pm` user can
  still load `/pipeline`/`/reports` by URL (and vice-versa). Naming/contract mismatch with the "mode" concept.
- **Domain naming drift:** callback comment says `riphere.com`; landing/footer say `riphere`? Actually footer is
  "© 2026 NovaCRM". Product is "NovaCRM" but the JWT/proxy/domain references and Railway hosting suggest the
  deployed host differs — flag the `riphere.com` string in `auth/callback/route.ts:24` for consistency review.
- **Onboarding invite is a no-op** (sets `inviteSent` only) while Settings invite actually calls
  `apiClient.inviteTeammate` — duplicated concept, divergent behavior.
- **Landing "Log in" + "Start Free" both link to `/dashboard`** (page.tsx:78-90), not `/login`. Relies on the
  layout to redirect unauthenticated users back to `/login`. Works, but the nav semantics are wrong and depend on
  the guard chain.

## 10. Open questions for synthesizer / Phase 2
- Does FastAPI enforce `workspace_id` ownership on every `/workspaces/{id}/...` route, and is Supabase RLS on for
  `workspaces`/`agents`/`activity_events` (web reads these directly)? Tenancy verdict depends on it.
- Is `NEXT_PUBLIC_DEMO_MODE` definitely `false` in the production Railway env? (No way to tell from repo.)
- Is `workspace-mode-context` actually mounted anywhere, or fully dead?
- Was `proxy.ts` *meant* to be `middleware.ts`? (Strongly looks like a rename/typo regression — likely the root
  cause behind the very "session falls back to Site URL" class of bugs this branch is fixing.)
