# Phase 2 — TARGET (high): Direct browser→Supabase table reads under the anon key

Scope swept: `/tmp/crm-signup-fix/apps/web/src` for `.from(` / `.rpc(` / `.channel(`.
Goal: enumerate every DIRECT table read from the browser under the anon key, record
file:line + table + client-side workspace filter + whether it reads workspace-owned data,
and determine how many of the ~13 app pages do direct table reads vs go through the
FastAPI apiClient. Then EMPIRICALLY test whether the direct anon reads leak cross-tenant data.

Target Supabase project: https://ilfibxflnelssllgszex.supabase.co
Creds source: /mnt/external/Projects/crm-agentic/apps/web/.env.local (anon + JWT secret), /tmp/.crm-svc-key (service role).

================================================================================
## 1. GREP SWEEP (raw)
================================================================================
Command:
    cd /tmp/crm-signup-fix/apps/web/src
    grep -rn "\.from("    --include="*.ts" --include="*.tsx" .   # then .rpc(  then .channel(

Raw `.from(` hits (with JS Array.from noise removed by inspection):
    app/(app)/layout.tsx:34:        .from("workspaces")        <-- REAL Supabase table read
    components/layout/Sidebar.tsx:132:   .from("agents")        <-- REAL Supabase table read (the known seed)
    hooks/useWorkspace.ts:46:          .from("workspaces")     <-- REAL Supabase table read
    (all other ".from(" hits are JS `Array.from(...)` — reports/page.tsx:122,
     pipeline/page.tsx:454/474, agents/page.tsx:99, lib/api-client.ts:487/595)

`.rpc(`  hits: NONE (grep exit 1)
`.channel(` hits as a standalone token: NONE — BUT `supabase.channel(` exists (see §3).

Cross-check via `.select(` (catches any aliased table read) — only 3, and they line up exactly:
    hooks/useWorkspace.ts:47:        .select("*")
    components/layout/Sidebar.tsx:133:  .select("name, status")
    app/(app)/layout.tsx:35:           .select("mode")

Cross-check via `supabase` token: every other usage in the tree is `.auth.*`
(getUser / getSession / signOut / signUp / exchangeCodeForSession / updateUser /
refreshSession) — i.e. AUTH calls, NOT table reads. Confirmed by reading each file.

================================================================================
## 2. THE THREE DIRECT TABLE READS (in context)
================================================================================

--- SITE A: components/layout/Sidebar.tsx:130-138  (the known seed) ---
    const supabase = createBrowserClient();
    supabase
      .from("agents")
      .select("name, status")
      .limit(4)
      .then(({ data }) => { if (data && data.length > 0) setNexusAgents(data); });
  Table:            agents
  Workspace-owned?  YES (agents.workspace_id exists; data is per-tenant)
  Client-side ws filter? NO. No .eq("workspace_id", …). Relies 100% on RLS.
  Client:           createBrowserClient() -> ANON key (browser).

--- SITE B: hooks/useWorkspace.ts:45-50 ---
    const { data, error: wsError } = await supabase
      .from("workspaces")
      .select("*")
      .eq("id", workspaceId)        // workspaceId = user.user_metadata.workspace_id
      .single();
  Table:            workspaces
  Workspace-owned?  YES (it IS the tenant row)
  Client-side filter? YES — .eq("id", workspaceId) where workspaceId comes from the
                      caller's own JWT user_metadata. Self-scoping; cannot name another tenant
                      without already knowing+matching their id, and RLS still gates it.
  Client:           createBrowserClient() -> ANON key (browser).

--- SITE C: app/(app)/layout.tsx:33-37  (SERVER component, not browser) ---
    const { data: workspace } = await supabase
      .from("workspaces")
      .select("mode")
      .eq("id", workspaceId)        // workspaceId from server-validated user_metadata
      .single();
  Table:            workspaces
  Workspace-owned?  YES
  Client-side filter? YES — .eq("id", workspaceId).
  Client:           createServerClient(cookieStore) -> ANON key, but runs SERVER-SIDE
                    in the (app) layout, authenticated via the user's cookie session.
                    NOTE: this is NOT a "browser" read; it's an SSR read. Still anon-keyed.
                    Also fully bypassed when NEXT_PUBLIC_DEMO_MODE=true (layout returns early).

Key fact from lib/supabase.ts:251-297 — BOTH createBrowserClient() and createServerClient()
use process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY. There is NO service-key usage anywhere in
apps/web/src. So every direct read above executes under the ANON role + the user's JWT (if any).

================================================================================
## 3. REALTIME CHANNEL (4th direct-Supabase data path, not a .from read)
================================================================================
app/(app)/dashboard/page.tsx:308-330
    const channel = supabase
      .channel(`activity-feed:${workspaceId}`)
      .on("postgres_changes", {
          event: "INSERT", schema: "public", table: "activity_events",
          filter: `workspace_id=eq.${workspaceId}`,        // <-- client-side ws filter PRESENT
        }, (payload) => { ... })
      .subscribe();
  Table:            activity_events (workspace-owned)
  Client-side ws filter? YES — filter: workspace_id=eq.${workspaceId}
  This is a Realtime WebSocket subscription under the anon key + user session, NOT a REST
  table read. Realtime also enforces RLS on the underlying table for row delivery.
  (My initial `.channel(` grep missed it because the call is `supabase.channel(` split across lines.)

================================================================================
## 4. PER-PAGE CLASSIFICATION — apiClient (FastAPI) vs direct table read
================================================================================
Command:
  for f in app/(app)/**/page.tsx: count apiClient. ; count .from("<table>") ; count supabase.channel(

  app/(app)/agents/page.tsx        apiClient=1  direct_from=0  channel=0
  app/(app)/calls/page.tsx         apiClient=3  direct_from=0  channel=0
  app/(app)/connectors/page.tsx    apiClient=6  direct_from=0  channel=0
  app/(app)/contacts/[id]/page.tsx apiClient=4  direct_from=0  channel=0
  app/(app)/contacts/page.tsx      apiClient=13 direct_from=0  channel=0
  app/(app)/dashboard/page.tsx     apiClient=9  direct_from=0  channel=1  (realtime, §3)
  app/(app)/inbox/page.tsx         apiClient=2  direct_from=0  channel=0
  app/(app)/pipeline/[id]/page.tsx apiClient=4  direct_from=0  channel=0
  app/(app)/pipeline/page.tsx      apiClient=5  direct_from=0  channel=0
  app/(app)/projects/[id]/page.tsx apiClient=4  direct_from=0  channel=0
  app/(app)/projects/page.tsx      apiClient=4  direct_from=0  channel=0
  app/(app)/reports/page.tsx       apiClient=0  direct_from=0  channel=0  (pure client-compute/charts)
  app/(app)/settings/page.tsx      apiClient=3  direct_from=0  channel=0
  app/(app)/tasks/page.tsx         apiClient=3  direct_from=0  channel=0

CONCLUSION on the ~13 pages:
  * ZERO of the app *page.tsx* files perform a direct `.from()` table read.
  * 13 of 14 page.tsx files route their data exclusively through apiClient (FastAPI).
    (reports/page.tsx makes no data call at all — derives charts client-side.)
  * 1 page (dashboard) opens a direct Supabase Realtime channel (filtered by workspace_id),
    in addition to its apiClient calls.
  * The ONLY direct REST table reads in the whole web app live in:
      - the shared (app) SERVER layout (workspaces, SSR, anon key + cookie)  [layout.tsx]
      - the Sidebar layout component (agents, browser, anon key)             [Sidebar.tsx]  <- seed
      - the useWorkspace hook (workspaces, browser, anon key)                [useWorkspace.ts]
  => Total DIRECT Supabase table-read sites: 3 (Sidebar agents, layout workspaces, useWorkspace workspaces).
     Plus 1 Realtime channel (dashboard activity_events).
  => Data architecture is "FastAPI apiClient for everything except: workspace bootstrap (2x) +
     sidebar agent badge (1x) + dashboard live feed (1x)."

================================================================================
## 5. EMPIRICAL TEST — do the direct ANON reads leak workspace-owned data? (RUNTIME)
================================================================================
The high-severity hypothesis: a browser direct read under the anon key (esp. Sidebar's
`agents` read, which has NO client-side workspace filter) leaks other tenants' data.
I tested this against the LIVE Supabase REST API.

--- 5a. Anon (logged-out) read of agents — exactly Sidebar's query ---
  $ curl "$URL/rest/v1/agents?select=name,status&limit=4" -H "apikey:$ANON" -H "Authorization:Bearer $ANON"
    []
    [HTTP 200]
  $ curl -I "$URL/rest/v1/agents?select=*" -H "apikey:$ANON" -H "Authorization:Bearer $ANON" -H "Prefer:count=exact"
    HTTP/2 200
    content-range: */0
  => Anon sees ZERO agent rows. (RLS-blocked signature: 200 + empty + */0, not an error.)

--- 5b. Ground truth via SERVICE key (RLS bypassed) ---
  $ curl -I ".../agents?select=*" -H "apikey:$SVC" ... -H "Prefer:count=exact"
    content-range: 0-26/27                 => 27 agents exist
  $ per-workspace distribution (service key):
    9dbfbe4d (CRM)            -> 7 agents
    cd7196e7 (test)           -> 7 agents
    f54dbd3f (…+p2-takeover)  -> 7 agents
    583e7c4e (Demo Workspace) -> 6 agents
  $ workspaces count (service): content-range 0-3/4  => 4 workspaces exist.
  => So if RLS were broken, an anon/auth browser read would return up to 27 cross-tenant rows.
     Anon returned 0 (5a) — RLS is ENABLED and denies anon SELECT.

--- 5c. AUTHENTICATED user, EXACT Sidebar query (NO client-side ws filter) ---
  Minted a valid HS256 Supabase user JWT signed with SUPABASE_JWT_SECRET from .env.local:
    claims: aud=authenticated, role=authenticated, sub=41c783ad-… (a REAL user in ws 9dbfbe4d/CRM),
            user_metadata.workspace_id=9dbfbe4d-… , exp=+1h.  (token len 513)
  $ curl ".../agents?select=name,status&limit=4" -H "apikey:$ANON" -H "Authorization:Bearer $USERJWT"
    [{"name":"Email Composer","status":"processing"},
     {"name":"Call Summarizer","status":"active"},
     {"name":"Pipeline Optimizer","status":"active"},
     {"name":"Sentiment Analyzer","status":"active"}]
    [HTTP 200]
  $ COUNT with NO filter: content-range 0-6/7
  $ distinct workspaces visible: {'9dbfbe4d-2e0d-4fca-944c-6960bf6b586d': 7}
  => Authenticated CRM user sees EXACTLY their own 7 agents and 0 of the other 20.
     RLS scopes rows to the caller's workspace SERVER-SIDE, even though Sidebar sends no filter.

--- 5d. FORCED cross-tenant read (CRM user explicitly names another workspace) ---
  $ curl ".../agents?select=name&workspace_id=eq.cd7196e7-…(test ws)" -H "apikey:$ANON" -H "Authorization:Bearer $USERJWT"
    []
    [HTTP 200]
  => Even explicitly requesting another tenant's agents returns [] . No cross-tenant leak.

--- 5e. workspaces + contacts confirmation ---
  $ workspaces, authenticated CRM user, no filter:  content-range 0-0/1 ; body=[{id:9dbfbe4d,name:CRM}]
    => sees only own 1 of 4 workspaces.
  $ contacts (anon key, direct):  HTTP 200 ; content-range */0  => RLS blocks anon.

================================================================================
## 6. VERDICT
================================================================================
The TARGET hypothesis — "direct browser→Supabase table reads under the anon key leak
workspace-owned data" — is REFUTED at runtime for this deployment.

  * Direct anon-key table-read sites = 3 (Sidebar:agents, layout:workspaces, useWorkspace:workspaces)
    + 1 Realtime channel (dashboard:activity_events).
  * Sidebar's `agents` read carries NO client-side workspace_id filter — the only thing
    standing between it and 27 cross-tenant rows is RLS.
  * RLS IS enabled and correctly partitions agents/workspaces/contacts by workspace_id:
      - anon  -> 0 rows (*/0)
      - authenticated CRM user (no client filter) -> exactly own 7 agents, own 1 workspace
      - forced cross-tenant request -> [] .
  * 13/14 app pages use the FastAPI apiClient exclusively for data; 0 pages do a direct .from()
    read; 1 page additionally uses a workspace-filtered Realtime channel.

Residual risk (NOT a confirmed vuln, defense-in-depth note):
  - The Sidebar read’s safety is INVISIBLE in the client code; it depends entirely on an RLS
    policy on `agents`. If that policy were ever dropped/misconfigured (e.g. during a migration),
    this exact query would silently begin returning all tenants' agent names+statuses, because
    there is no client-side workspace_id guard as a second layer. Recommend adding
    `.eq("workspace_id", workspaceId)` to the Sidebar query (and an RLS regression test) so a
    single policy mistake doesn't become a cross-tenant disclosure. Severity of the *current*
    state: low (RLS observed enforcing isolation).
