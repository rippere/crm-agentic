# NovaCRM Phase 1 — API Core (auth, multi-tenancy, rate limiting)

Repo: `/tmp/crm-signup-fix` (git worktree of production master). HEAD `429da2f`
("fix(auth): rescue auth params that fall back to the Site URL"). App version `0.1.0`.
Title in code: "CRM-Agentic API"; product name elsewhere: "NovaCRM".

Scope read in full: `apps/api/app/main.py`, `config.py`, `dependencies.py`, `database.py`,
`limiter.py`, `services/auth.py`, `routers/auth.py`, `routers/workspaces.py`. Plus, to verify
the tenancy/rate-limit story across the codebase: every other router (`contacts`, `deals`,
`projects`, `tasks`, `messages`, `calls`, `agents`, `search`, `ai`, `events`, `gmail`, `slack`,
`slack_interactions`, `mcp_server`), `models/user.py`, `models/workspace.py`,
`services/oauth_state.py`, `services/crypto.py`, `services/supabase_rest.py`, and all SQL
migrations (`migrations/001_unified_schema.sql`, `005`, `init_docker.sql`).

---

## 1. Auth model (Supabase JWT verification)

**`services/auth.py`** — the verification core.
- Supabase user access_tokens are signed **ES256 (ECDSA P-256)**. Public key fetched lazily
  from the project JWKS endpoint `{SUPABASE_URL}/auth/v1/.well-known/jwks.json`, cached 300s
  (`PyJWKClient(..., cache_jwk_set=True, lifespan=300)`).
- `verify_supabase_jwt(token)`: gets signing key from JWT header `kid`, then
  `pyjwt.decode(token, signing_key, algorithms=["ES256","RS256"], options={"verify_aud": False,
  "require": ["sub","exp","iat"]})`. Raises `ValueError` on expiry/invalid.
- `extract_supabase_uid(payload)` → `uuid.UUID(payload["sub"])`.
- Module docstring explicitly states `SUPABASE_JWT_SECRET` is NOT used here ("it only covers the
  static anon/service-role tokens"). Yet `config.py` declares `SUPABASE_JWT_SECRET: str`
  (required, no default) and README/DEPLOY call it "REQUIRED … backend auth." So the secret is a
  **required env var that is never read by the verification path** — load-bearing only as a
  deploy gate, misleading as documented "backend auth."

Observations / concerns:
- `algorithms=["ES256","RS256"]` — accepts RS256 in addition to ES256. The signing key comes
  from JWKS so this is not the classic alg-confusion (no shared HMAC secret here), but it is
  broader than the documented "ES256 only" and worth tightening to `["ES256"]`.
- `verify_aud=False` — audience unverified. Supabase tokens carry `aud="authenticated"`; not
  checking it is conventional for Supabase but means any token from this project (incl. ones
  minted for a different intended audience) is accepted as long as signature+exp valid.
- **`dependencies.py:36`** — `except (ValueError, Exception) as e:` — `Exception` already
  subsumes `ValueError`; the tuple is redundant/dead and (more importantly) the bare `Exception`
  catch means ANY error inside provisioning logic surfaces as a 401 "Could not validate
  credentials" (misleading; can mask real bugs/DB errors as auth failures).

**Token extraction**: `OAuth2PasswordBearer(tokenUrl="/auth/verify", auto_error=True)` is
instantiated **three times** independently — `dependencies.py:15`, `routers/auth.py:29`,
and implicitly the dependency in other routers reuse `get_current_user`. Duplicated `oauth2_scheme`
in `routers/auth.py` is redundant with `dependencies.py`.

### User provisioning (auto-provision on first hit)

Two SEPARATE provisioning code paths that disagree:

**A. `dependencies.get_current_user` (dependencies.py:43-82)** — runs on EVERY authenticated
request when the user row is absent:
- Reads `workspace_id` from JWT `user_metadata.workspace_id` (string → UUID; silently `pass` on
  bad UUID, leaving `workspace_id=None`).
- If `workspace_id` present and Workspace row missing → creates a Workspace with
  `name=slug=email-localpart` (or `str(workspace_id)[:8]`), `mode="sales"`.
- Creates `User(supabase_uid, workspace_id, email, role="admin")`. **No default agents seeded.**

**B. `routers/auth.verify` POST `/auth/verify` (auth.py:56-111)** — the documented login path:
- If user absent → creates a BRAND NEW Workspace (`name=f"{email} Workspace"`,
  `slug=str(uuid4())[:8]`, `mode="sales"`), user `role="admin"`, **AND seeds 7 default agents**
  (`_DEFAULT_AGENTS`), then best-effort pushes `workspace_id` into Supabase `user_metadata` via
  admin API (`_sync_workspace_metadata`).
- If user present and JWT `user_metadata.workspace_id` differs from DB → **reassigns
  `user.workspace_id` to the value from the JWT** (auth.py:102-105). Trusts client-influenceable
  metadata to move a user between workspaces (see risk R3).

These two paths produce **different workspace shapes** (path A: no agents, slug from email;
path B: 7 agents, random slug) for the same "first login" event depending on whether the user
hits `/auth/verify` first or any other protected route first. This is a real homogenization/
correctness problem — provisioning is duplicated and divergent across `dependencies.py`,
`routers/auth.py`, AND a third copy in `routers/workspaces.create_workspace` (which also seeds
`_DEFAULT_AGENTS` by importing them from `routers.auth`).

**Role mismatch**: every provisioning path sets `role="admin"` (dependencies.py:76, auth.py:88,
workspaces.py:92). But `models/user.py:18` and the SQL CHECK (`001:20`) default role to
`"member"`. So the DB default is dead — every real user is created as admin. `require_admin`
therefore never meaningfully gates anyone in normal flows (single-user-per-workspace = everyone
is admin). The CHECK constraint allows only `('admin','member')`.

---

## 2. Multi-tenancy — how workspace_id scoping is enforced

### Two nominal layers; only ONE is real.

**Layer 1 — DB Row-Level Security (RLS) — PRESENT IN SQL, NON-FUNCTIONAL AT RUNTIME.**
`migrations/001_unified_schema.sql:160-205` enables RLS on all 11 tables and defines policies
of the form:
```sql
USING (workspace_id = (SELECT workspace_id FROM users WHERE supabase_uid = auth.uid()))
```
Problems making this decorative for the API:
1. **The API never sets `auth.uid()`.** `auth.uid()` reads the JWT claim from the Postgres GUC
   `request.jwt.claims`, which PostgREST/Supabase sets per-request. The FastAPI backend connects
   with raw **SQLAlchemy + asyncpg** (`database.py:6`, `create_async_engine(DATABASE_URL)`) and
   NEVER issues `SET LOCAL request.jwt.claims` / `set_config(...)`. So inside every API query
   `auth.uid()` is NULL → the subquery yields NULL → `workspace_id = NULL` is never true.
2. **But the app demonstrably returns rows** (324 tests pass, product deployed). The only way
   both can be true: the connection role **bypasses RLS**. DEPLOY.md:121 mandates the connection
   string `postgresql+asyncpg://postgres.[project-ref]:...@...pooler.supabase.com/postgres` —
   i.e. the Supabase project **owner/superuser-class role**. Table owners and superusers bypass
   RLS unless `ALTER TABLE ... FORCE ROW LEVEL SECURITY` is set, which it is NOT anywhere.
   Net: RLS is effectively OFF for 100% of API traffic. It is "security theater" — present in
   the schema, advertised in DEPLOY.md ("11-table schema + RLS policies"), but enforcing nothing
   for the backend. (It WOULD apply to any direct PostgREST/anon-key access, but the app routes
   everything through the service-role-class backend.)
3. `migrations/init_docker.sql` (local dev) has **no RLS at all** (header: "Full schema init for
   self-hosted Postgres (no Supabase RLS)"). So dev and prod differ in nominal posture but are
   identical in effect (no RLS enforced in either).
   - No test sets RLS context (`grep set_config / auth.uid / SET LOCAL` in tests → none). RLS is
     entirely unexercised.

**Layer 2 — Application-layer guard — THE ONLY REAL TENANCY CONTROL.**
The actual isolation is a hand-rolled pattern repeated in EVERY workspace-scoped handler:
```python
if current_user.workspace_id != workspace_id:
    raise HTTPException(403, "Access denied")
... select(Model).where(Model.id == x, Model.workspace_id == workspace_id)
```
- `workspace_id` comes from the URL path (`/workspaces/{workspace_id}/...`); the guard compares
  it to `current_user.workspace_id` (derived from the verified JWT → DB user row). Combined with
  the `.where(... == workspace_id)` filter, this gives correct per-row isolation **as long as the
  guard is present and the filter is present**.
- Coverage audit (manual, per handler): contacts, deals, projects, tasks, messages, calls,
  events, search, ai, gmail (workspace routes), slack (workspace routes), mcp_server,
  workspaces — ALL enforce the guard. `agents.py` is the lone stylistic outlier: it does NOT take
  a `{workspace_id}` path param and instead scopes directly with
  `Agent.workspace_id == current_user.workspace_id` (dependencies.py-derived). Functionally safe,
  but inconsistent with the rest of the API surface (see inconsistencies).
- The guard is **copy-pasted ~50+ times** verbatim. There is a ready-made dependency
  `dependencies.get_workspace_id` (returns `current_user.workspace_id`, 400 if none) that is
  **defined but used by ZERO routers** — the homogenization opportunity is to replace the
  copy-pasted guard with a single dependency that validates path `workspace_id == user.workspace_id`.
  Today `get_workspace_id` is dead code.
- 55 test assertions reference "Access denied"/FORBIDDEN/403, so the app-layer guard is
  reasonably well covered by tests.

### Tenancy trust-boundary edge cases found

- **`routers/auth.verify` workspace reassignment (auth.py:102-105)**: if the JWT's
  `user_metadata.workspace_id` differs from the stored value, the server overwrites
  `user.workspace_id` with the JWT value, **without checking the user has any right to that
  workspace**. `user_metadata` is settable via Supabase `updateUser()` from the client (anon key)
  in many Supabase configs. If a user can write their own `user_metadata.workspace_id` to an
  arbitrary victim workspace UUID, the next `/auth/verify` silently moves them into it and
  `get_current_user` then treats them as a member (admin!) of that workspace → full cross-tenant
  read/write. Severity: this is the single highest-impact finding (HIGH/critical depending on
  whether Supabase project allows self-service `user_metadata` writes — needs runtime confirmation).
- **`slack_interactions._handle_approve` (slack_interactions.py:92, 169-177)**: derives
  `workspace_id` from server-stored event `meta` (trusted, server-minted), and the Contact lookup
  `select(Contact).where(Contact.id == contact_id)` is **NOT workspace-scoped** (line 173-176).
  Because `contact_id` also comes from the same server-stored meta, this is not directly
  attacker-controlled, so it's low risk — but it is a pattern violation (an unscoped Contact query)
  and would become a vuln if meta were ever populated from less-trusted input.
- **`contacts.compose_email` / `enrich` Supabase REST fallback**: `get_row("contacts",
  {"id":..., "workspace_id":...})` IS workspace-scoped (good), using the service-role key via
  `services/supabase_rest.py`. Fine.
- **Webhooks (no JWT, by design)**: `POST /webhooks/gmail/push`, `POST /webhooks/slack/events`,
  `POST /slack/interactions`. These have no `get_current_user`; they authenticate via shared
  secret / HMAC signature and resolve the workspace from connector lookups by email/team_id.
  - Gmail push: `_verify_pubsub_secret` returns **True when `GMAIL_WEBHOOK_SECRET` is empty**
    ("accept all (dev/test only)"). In prod with the secret unset, the ingest webhook is
    **unauthenticated** — anyone who knows/guesses a connected Gmail address can POST to trigger
    ingest for that connector (DoS / forced-sync). Fail-OPEN. (Slack interactions, by contrast,
    fail CLOSED — see below.)
  - Slack Events (`routers/slack.py:206`): `_verify_slack_signature` returns **True when
    `SLACK_SIGNING_SECRET` is empty** — also fail-OPEN in dev mode.
  - Slack interactions (`routers/slack_interactions.py:44`): `_verify_slack_signature` returns
    **False when secret empty** — fail-CLOSED. This is the safe choice **and it is inconsistent
    with the other two webhook verifiers** (two fail open, one fails closed; see inconsistencies).
    `main.py:57` logs a startup warning if `SLACK_SIGNING_SECRET` is missing.

### OAuth state / token crypto (supporting tenancy)
- `services/oauth_state.py`: `state` is `base64(payload).sig` where `sig = HMAC-SHA256(SECRET_KEY,
  payload_b64)`, payload `{wid, exp, nonce}`, TTL 600s. `verify_state` checks HMAC
  (constant-time) + expiry and returns the workspace_id from the **verified** payload. Solid — the
  OAuth callbacks (`gmail_callback`, `slack_callback`) derive `workspace_id` from verified state,
  not from a raw query param. Good.
  - `nonce` is generated but **never stored/checked** → state is replayable within its 600s TTL.
    Low severity (callbacks are idempotent upserts), but the docstring implies anti-forgery
    completeness; nonce gives no replay protection as implemented.
- `services/crypto.py`: connector OAuth tokens encrypted with Fernet, key =
  `urlsafe_b64encode(sha256(SECRET_KEY))`. Symmetric, deterministic from SECRET_KEY. DEPLOY.md
  notes SECRET_KEY "Must be the same on all API, worker, and beat services." Reasonable; entire
  token-at-rest security collapses to SECRET_KEY secrecy.

---

## 3. Rate limiting coverage

**Setup (`limiter.py`, `main.py:72-74`):** `slowapi` `Limiter(key_func=_rate_key)`,
`SlowAPIMiddleware` added, `RateLimitExceeded` handler registered. Default storage is
**in-memory** (no `storage_uri` passed → slowapi defaults to in-process memory).

**KEY FUNCTION IS BROKEN (`limiter.py:5-10`):**
```python
def _rate_key(request):
    user = getattr(request.state, "user", None)
    if user is not None:
        return str(getattr(user, "id", get_remote_address(request)))
    return get_remote_address(request)
```
`request.state.user` is **NEVER set anywhere in the codebase** (`grep "state.user"` → zero hits;
`get_current_user` returns the user but never assigns it to `request.state`). So the `user is not
None` branch is **dead code** and the limiter ALWAYS falls back to `get_remote_address`, i.e.
client IP. Consequences:
- Per-user limits are actually per-IP. Multiple users behind one NAT/office IP/corporate proxy
  share one bucket (false positives). Conversely a single user rotating IPs evades limits.
- **Behind Railway/any proxy, `get_remote_address` reads the socket peer, which is the
  proxy/load-balancer IP** unless `X-Forwarded-For` handling is configured (it is NOT — no
  `ProxyHeadersMiddleware`/forwarded-for parsing). So in production every request may share the
  proxy's IP → the limiter could throttle ALL tenants together, or (if peer is distinct per
  edge) be ineffective. Either way the documented intent ("authenticated user_id when available")
  is not met.
- **In-memory storage** means limits are per-process and reset on deploy; with multiple
  API workers/replicas (Railway scales horizontally) the effective limit is `N_workers ×
  configured` and is not shared. Not production-grade.

**Coverage (which endpoints have `@limiter.limit`):** only 9 endpoints, applied ad-hoc:
- `auth.verify` 30/min · `search.embed-all` 2/min · `ai.query` 20/min · `messages.score-clarity`
  10/min · `mcp.mcp_endpoint` 20/min · `contacts.compose_email` 10/min · `contacts.enrich` 5/min
  · `contacts.brief` 10/min · `calls.upload` 10/min.
- **NOT rate-limited:** all list/CRUD endpoints (contacts/deals/tasks/projects list, create,
  update, delete, bulk), CSV import/export, the SSE `/events` stream, OAuth initiate/callback,
  webhooks, `/auth/verify` is limited but `/me` and `/workspaces/{id}/invite` (which sends real
  emails via Supabase admin API!) are NOT. The invite endpoint is an unthrottled outbound-email
  trigger gated only by admin role (which everyone has).
- Decorator-based, so coverage is per-endpoint opt-in — easy to forget, and most expensive
  endpoints (Claude calls in `deals`/`ai`, bulk ops, exports) are unprotected or inconsistently
  protected. No global default limit.

---

## 4. CORS / misc (main.py)
- CORS allowlist = `FRONTEND_URL` + `CORS_ORIGINS` (comma list) + localhost:3000/3001, plus
  optional `CORS_ORIGIN_REGEX`. `allow_credentials=True` with `allow_methods=["*"]`,
  `allow_headers=["*"]`. With an explicit allowlist this is OK; the regex is operator-supplied
  (config.py comment example `r"https://(.*\.)?riphere\.com"` — note brand spelled "riphere"
  here vs "NovaCRM" product name; the comment in config is just an example).
- `/health` returns HTTP 200 even when DB/Redis are down ("degraded") by design (Railway probe).
  Claims to check DB + Redis; it does.
- Startup warns when `SLACK_SIGNING_SECRET` missing (because slack_interactions fails closed).

---

## CLAIMS (verifiable assertions made by this area)

| Claim | Where | True? |
|---|---|---|
| "User access_tokens are signed with ES256" | services/auth.py:5 docstring | TRUE-ish — but decode also accepts RS256 (auth.py:47) |
| "SUPABASE_JWT_SECRET is not used here" | services/auth.py:6-8 | TRUE in verify path — yet README/DEPLOY label it "REQUIRED backend auth" (contradiction) |
| "11-table schema + RLS policies" / RLS provides workspace isolation | DEPLOY.md:105; 001_unified_schema.sql:158 | FALSE in effect — RLS bypassed by owner role, auth.uid() never set; isolation is app-layer only |
| init_docker "no RLS" / "Do NOT run on Supabase prod" | init_docker.sql:2, DEPLOY.md:112 | TRUE (init_docker has no RLS); prod path keys RLS on auth.uid() that the API never provides |
| Rate-limit "uses authenticated user_id when available, else client IP" | limiter.py:6 | FALSE — request.state.user never set; always IP |
| Fail-closed: "without signing secret we must reject" (Slack interactions) | slack_interactions.py:41-44 | TRUE — but Slack Events + Gmail push fail OPEN (inconsistent) |
| OAuth state is signed/expiring/anti-forgery, nonce included | oauth_state.py:5,48 | PARTLY — signed+expiring TRUE; nonce stored/checked? NO → replayable in TTL |
| Connector tokens encrypted at rest (Fernet) | crypto.py | TRUE — key derived from SECRET_KEY via sha256 |
| Default user role "member" | models/user.py:18; 001:20 | MISLEADING — every provisioning path hardcodes role="admin"; default is dead |
| "/health checks DB + Redis connectivity" | main.py:138 | TRUE; returns 200 even when degraded (intentional) |
| Supabase REST fallback is workspace-scoped | contacts.py:278,351 | TRUE (get_row filters on workspace_id) |
| 324 tests pass (Phase 8) | git log b40a0ef/85077f4 | Asserted in commit msg; not re-run here |

---

## RISKS (evidence-backed; multi-tenancy/auth ⇒ HIGH+)

1. **CRITICAL/HIGH — Self-service workspace takeover via JWT user_metadata.** auth.py:102-105
   reassigns `user.workspace_id` to whatever `user_metadata.workspace_id` the JWT carries, with
   no authorization check. If the Supabase project permits client `updateUser({data:{workspace_id}})`
   (common default), a user can point themselves at any victim workspace UUID and gain admin
   read/write to it on next `/auth/verify`. Needs runtime confirmation of Supabase metadata
   write policy; treat as CRITICAL until disproven.

2. **HIGH — RLS is non-functional; tenancy rests entirely on copy-pasted app guards.**
   001_unified_schema.sql:160-205 enables RLS keyed on `auth.uid()`, but the asyncpg backend
   never sets the JWT GUC and connects as the owner role (DEPLOY.md:121) which bypasses RLS (no
   `FORCE`). One forgotten `if current_user.workspace_id != workspace_id` guard or one missing
   `.where(workspace_id==...)` in any current/future handler = silent cross-tenant data exposure,
   with NO database safety net. The defense-in-depth the schema advertises does not exist.

3. **HIGH — Broken rate-limit key (effectively no per-user limiting; possibly global throttle in
   prod).** limiter.py:5-10 branches on `request.state.user` which is never set → always IP; behind
   Railway's proxy with no forwarded-for handling the "IP" is the proxy's, so limits may either
   collapse all tenants into one bucket or be evaded. In-memory storage is per-process and not
   shared across replicas. The protection is illusory where it matters (auth, AI, MCP).

4. **MEDIUM/HIGH — Gmail push + Slack Events webhooks fail OPEN when their secret env var is
   unset.** gmail.py:378-382 and slack.py:206-207 return True (accept) on empty secret. If a
   secret is missing in prod (easy misconfig; only SLACK_SIGNING_SECRET is warned about at
   startup, GMAIL_WEBHOOK_SECRET is not), the ingest webhooks are unauthenticated — forced sync /
   resource-exhaustion against any known connector email. Inconsistent with slack_interactions
   which fails closed.

5. **MEDIUM — Divergent, triplicated user/workspace provisioning** (dependencies.py:43-82 vs
   auth.py:82-98 vs workspaces.py:86-104). Path A seeds NO agents; paths B/C seed 7. Same "first
   login" yields different workspace state depending on entry route → inconsistent UX and latent
   bugs. `get_workspace_id` dependency exists to consolidate the guard but is unused (dead code).

6. **MEDIUM — Everyone is admin.** All provisioning hardcodes role="admin" while the schema/model
   default ("member") is dead. `require_admin` (used by deals.py:101,255 etc.) gates nothing in
   practice → privileged actions (pipeline optimize, deal-health recompute, teammate invite that
   sends real email) are open to every workspace user. The "member" role is unreachable.

7. **LOW/MEDIUM — Auth decode broader than documented:** `algorithms=["ES256","RS256"]` +
   `verify_aud=False` (auth.py:47-49). Not exploitable via JWKS today, but contradicts the
   "ES256-only" doc and removes an audience check; tighten to ES256 + verify aud="authenticated".

8. **LOW — `except (ValueError, Exception)`** in dependencies.py:36 — redundant tuple; bare
   Exception masks provisioning/DB errors as 401, hindering diagnosis.

9. **LOW — OAuth state replay within 600s** (oauth_state.py): nonce minted but never persisted/
   checked. Callbacks are idempotent so impact is minimal, but the anti-forgery story is overstated.

10. **LOW — invite endpoint unthrottled outbound email** (auth.py:131 `/workspaces/{id}/invite`)
    — no rate limit; admin-only but every user is admin. Spam/abuse vector through Supabase admin
    invite API.

---

## INCONSISTENCIES (for homogenization — user wants the product HOMOGENIZED)

1. **Tenancy enforcement style is split.** ~13 routers use the URL `{workspace_id}` path param +
   `if current_user.workspace_id != workspace_id: 403` guard. `agents.py` ALONE drops the path
   param and scopes via `current_user.workspace_id` directly. Pick ONE pattern. Better: a shared
   `Depends(verify_workspace_access)` dependency replacing all ~50 copy-pasted guards (and finally
   using/replacing the orphaned `get_workspace_id`).

2. **The 403 guard is copy-pasted 50+ times** verbatim instead of a dependency. `get_workspace_id`
   in dependencies.py was clearly meant to centralize this but is imported/used nowhere.

3. **User provisioning logic is triplicated and divergent** across dependencies.py, routers/auth.py,
   routers/workspaces.py — different agent-seeding, different slug logic. Should be one
   `provision_user_workspace()` service.

4. **Webhook signature verification disagrees on fail-open vs fail-closed.** slack_interactions =
   fail CLOSED (correct); slack Events + gmail push = fail OPEN. Three near-duplicate
   `_verify_slack_signature` implementations exist (slack.py and slack_interactions.py each define
   their own; gmail has its own `_verify_pubsub_secret`). Consolidate into one verifier that fails
   closed in prod.

5. **`oauth2_scheme = OAuth2PasswordBearer(...)` instantiated 3×** (dependencies.py:15, auth.py:29,
   agents reuse via dependency) — should be a single shared instance.

6. **`SUPABASE_JWT_SECRET` is required + documented as "backend auth" but unused by the verifier.**
   Either wire it (for the static-token path) or stop requiring/advertising it.

7. **Role model is contradictory:** DB/model default `member`, all code writes `admin`, CHECK
   allows only those two. Decide the real role model; today it's effectively single-role.

8. **RLS posture differs dev vs prod in wording only:** init_docker (no RLS) vs 001 (RLS on) —
   but both yield "no RLS enforced for the API." Either make RLS real (set JWT GUC per request +
   non-owner role + FORCE RLS) or drop the policies and stop advertising them, so docs match
   reality.

9. **Inline imports everywhere** (`from app.models... import X` inside function bodies across
   nearly every handler "to avoid circular imports"). Pervasive; a structural smell pointing at a
   models/router import-cycle that should be untangled once, not worked around per-call.

10. **Naming: "CRM-Agentic" (FastAPI title, package `crm-agentic`) vs "NovaCRM" (README/UI/MCP
    serverInfo) vs config-comment brand "riphere".** Three names for one product.

11. **Rate limiting is opt-in per endpoint and wildly uneven** (5 vs 10 vs 20 vs 30 /min with no
    documented rationale; most write/AI endpoints unprotected). No central policy.

---

## DATA FLOW (this subsystem)
Client (Next.js) → obtains Supabase ES256 JWT (Supabase Auth) → sends `Authorization: Bearer
<jwt>` → FastAPI `OAuth2PasswordBearer` extracts token → `get_current_user` →
`verify_supabase_jwt` (JWKS public-key verify, 300s cache) → `select User by supabase_uid` →
(auto-provision User+Workspace[+agents] if absent) → handler enforces
`current_user.workspace_id == path workspace_id` then `select(...).where(workspace_id==...)` via
SQLAlchemy/asyncpg against **Supabase Postgres** (connection = project owner role through Session
pooler; RLS bypassed). Background work → Celery/Redis. External calls: Anthropic (AI endpoints),
Google/Gmail + Slack APIs (OAuth + ingest), Supabase Admin API (invite, metadata sync) and
Supabase REST (service-role fallback reads). Rate limiting via in-memory slowapi keyed (intended:
user_id; actual: client IP).

## EXTERNAL DEPS
Supabase (Auth/JWKS, Postgres, Admin API, REST), Anthropic Claude (Sonnet/Haiku), Google/Gmail
API (+ Pub/Sub push), Slack API (OAuth, Events, interactions), Redis (Celery broker/result),
PyJWT, SQLAlchemy+asyncpg, slowapi, cryptography(Fernet), httpx, FastAPI/Starlette.

## OPEN QUESTIONS (need runtime confirmation in Phase 2)
- Does the Supabase project allow clients to write `user_metadata.workspace_id` (drives R1
  severity: CRITICAL vs contained)?
- Is `GMAIL_WEBHOOK_SECRET` / `SLACK_SIGNING_SECRET` actually set in prod? (drives R4.)
- What exact DB role does the prod `DATABASE_URL` use, and is `FORCE ROW LEVEL SECURITY` set
  anywhere? (Confirms R2 — strongly implied owner-bypass.)
- Behind Railway, what does `get_remote_address` actually return (proxy IP vs client)? (R3 impact.)
- How many API replicas run? (In-memory limiter shard count for R3.)
