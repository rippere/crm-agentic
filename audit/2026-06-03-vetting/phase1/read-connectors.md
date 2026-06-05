# Phase 1 Read — Connectors / OAuth subsystem (Gmail + Slack)

Scope read in full: `apps/api/app/routers/gmail.py`, `routers/slack.py`,
`routers/slack_interactions.py`, `services/gmail_client.py`, `services/slack_client.py`,
`services/oauth_state.py`, `services/crypto.py`. Cross-referenced: `config.py`,
`models/connector.py`, `dependencies.py`, `services/auth.py`, `workers/ingest.py`,
`workers/slack_ingest.py`, `workers/followup_sequences.py`.

Worktree/branch note: scope says "production master", but `git rev-parse --abbrev-ref HEAD`
reports `fix/signup-confirm-redirect` (HEAD 429da2f). The connector files themselves were
last touched by the commits b40a0ef / 74a589b / 426d9c2 / c5d14c3 / 8b2475d / f1071eb /
d93bf0d / 1a5961e. So this *is* the deployed connector code, just checked out on a signup-fix
branch. Flag for synthesizer: confirm this worktree == prod master for the connector files.

---

## What the subsystem does

Two third-party connectors per workspace (`connectors` table, one row per
workspace+service+external_email):

- **Gmail**: OAuth2 auth-code flow → store encrypted access+refresh tokens → Celery
  `process_gmail_sync` pulls Primary-inbox mail, Claude-filters for deal relevance, inserts
  Messages, extracts Tasks. Also: `users.watch()` push subscription + Pub/Sub push webhook to
  trigger incremental syncs. Outbound: HITL approval sends email via Gmail.
- **Slack**: OAuth2 v2 user-token flow (xoxp- user scopes) → store encrypted user token →
  Celery `process_slack_sync` pulls DM/channel history, dedupes, inserts Messages. Events API
  webhook is *meant* to trigger syncs. HITL Block Kit buttons posted to a channel; button
  clicks hit `/slack/interactions`.

Token at rest: Fernet, key = base64url(SHA256(SECRET_KEY)). OAuth `state`: HMAC-SHA256 over
`{wid, exp, nonce}` keyed by the *same* SECRET_KEY, 600 s TTL.

---

## Token / data flow

1. `GET /workspaces/{id}/connectors/{svc}/auth` → tenancy check
   (`current_user.workspace_id != workspace_id` → 403) → `build_state(workspace_id)` → returns
   provider auth URL.
2. Provider redirects to `GET /auth/{svc}/callback?code&state` (NO auth dependency — public).
   `verify_state(state)` recovers a *verified* workspace_id (HMAC). Exchange code → tokens →
   fetch profile email → `encrypt_token` → upsert Connector. Redirect to FRONTEND_URL.
3. Sync endpoints (tenancy-checked) enqueue Celery. Workers decrypt via `crypto.decrypt_token`.
4. Gmail 401 → reactive refresh in `GmailClient._refresh_access_token` → re-encrypt access token,
   commit. Slack: no refresh (user tokens don't expire; revocation → `SlackAuthError`).

---

## CLAIMS (assertion → reality)

| # | Claim (where) | Verdict |
|---|---|---|
| C1 | crypto.py: "Derive a 32-byte Fernet key from SECRET_KEY using SHA-256" | TRUE. `Fernet(b64url(sha256(SECRET_KEY)))`. |
| C2 | oauth_state.py docstring: signed state lets callback recover *verified* workspace_id, rejects forged/expired/tampered | TRUE. HMAC compare_digest + exp check + UUID parse. nonce present but NOT persisted/checked → not single-use (see R-low). |
| C3 | gmail_client.py module docstring: "Handles ... 401-triggered refresh, and re-encryption" | PARTLY. Reactive 401 refresh exists; but `_get_valid_access_token` never consults `token_expiry` (proactive refresh missing) and refresh is only attempted once. `token_expiry` column is never written anywhere (grep: only the model defines it). |
| C4 | slack_client.py: "Slack user tokens (xoxp-) don't expire unless revoked, so no refresh logic needed" | TRUE for classic user tokens. Note: token rotation (if enabled on the app) would break this, but not enabled here. |
| C5 | slack.py `_verify_slack_signature` docstring: HMAC-SHA256 v0 + 5-min replay window; returns True when secret empty (dev) | TRUE to code. Fails *open* when `SLACK_SIGNING_SECRET==""`. |
| C6 | slack_interactions.py `_verify_slack_signature` comment: "Fail closed ... Prod sets SLACK_SIGNING_SECRET" | TRUE to code. Fails *closed* (opposite of C5 — see I1). |
| C7 | gmail.py `_verify_pubsub_secret` docstring: True if GMAIL_WEBHOOK_SECRET empty (dev) or matches | TRUE. Shared-secret-in-querystring only; no Google OIDC JWT verification (see R2). |
| C8 | gmail.py push webhook docstring: "Always returns 204 so Pub/Sub does not retry" | MOSTLY. Decode errors → 204. But an *invalid secret* raises HTTP 403 (not 204) — contradicts "always 204" and will cause Pub/Sub to retry on secret mismatch. |
| C9 | gmail.py `_derive_connector_status`: error/pending/stale/active from real state incl. revoked-token ActivityEvent | TRUE for Slack (slack_ingest persists `connector_auth_error`). FALSE-by-omission for Gmail: Gmail refresh failure never persists `connector_auth_error`, so a revoked Gmail token shows "stale", not "error" (see I3/R3). |
| C10 | slack_interactions.py: hitl_id re-parsed via `str(uuid.UUID(...))` to block LIKE-wildcard smuggling | TRUE. Canonical UUID → only hex+dashes, neutralizes `%`/`_` in the `meta LIKE` lookup. Good hardening. |
| C11 | slack_interactions.py docstring: approve "sends the email via Gmail, marks resolved, updates contact last_activity" | TRUE functionally. BUT no workspace authorization on *who* clicked (see R1). |
| C12 | slack.py module docstring lists `POST /…/slack/subscribe — verify Events API URL` | STALE/FALSE: no `/subscribe` route exists in slack.py (only auth/callback/sync/events). Docstring over-claims. |
| C13 | gmail.py header docstring lists `DELETE /workspaces/{id}/connectors/{connector_id}` and it removes connector | TRUE (delete_connector, tenancy-checked, hard delete). |
| C14 | auth.py (services) docstring: Supabase user tokens are ES256, JWKS cached 300s, SUPABASE_JWT_SECRET unused | TRUE. `pyjwt.decode(algorithms=["ES256","RS256"])`. Note RS256 also accepted (alg flexibility). |

### Scopes requested (verifiable)
- Gmail (`GMAIL_SCOPES`): `gmail.readonly`, `gmail.send`, `openid`, `email`. `access_type=offline`,
  `prompt=consent` (forces refresh_token issuance every time). Reasonable; `gmail.send` is required
  for HITL outbound.
- Slack (`SLACK_USER_SCOPES`, **user_scope** not bot scope): channels/groups/im/mpim read+history,
  `chat:write`, `users:read`, `users:read.email`. `chat:write` as a *user* scope means HITL messages
  post **as the authorizing user**, not as a bot — see I4.

---

## RISKS (evidence-backed)

### R1 — HITL approve has NO multi-tenant authorization on the actor (HIGH, security/multi-tenancy)
`routers/slack_interactions.py:240-256`. The pending-event lookup is **global**:
```
select(ActivityEvent).where(type=="hitl_pending", meta.like(f'%"hitl_id": "{hitl_id}"%')).limit(1)
```
No `workspace_id` filter, and nothing ties the *Slack user who clicked* to the workspace whose
Gmail connector then sends the email. `_handle_approve` reads `workspace_id` from the event's own
meta (`meta["workspace_id"]`, line 92), resolves *that* workspace's Gmail connector, and sends.
Signature verification only proves the request came from *some* Slack workspace with the shared
signing secret — Slack signing secret is per *Slack app*, shared across **all** customer Slack
workspaces that installed the app. So any user in any installing Slack workspace who learns/guesses
a `hitl_id` (a bare UUID, posted into a channel as button `value`, and echoed in logs) can approve a
send on another tenant's Gmail. hitl_id is unguessable (uuid4), which mitigates blind forgery, but
there is still zero authorization binding actor→tenant, and the value travels through Slack channels.
Automatically HIGH per audit rule (cross-tenant auth). Fix: filter the lookup by the workspace
derivable from the Slack `team_id` in the interaction payload, and require the connector's
`external_email` team to match.

### R2 — Gmail push webhook accepts shared-secret-in-URL only, no Pub/Sub OIDC verification (HIGH)
`routers/gmail.py:372-383, 405-430`. Auth = `?secret=` query param compared with
`hmac.compare_digest`. The secret rides in the URL → captured in proxy/LB/access logs, browser
history, Referer. Google Pub/Sub push supports signed OIDC JWTs (`Authorization: Bearer`) which this
endpoint ignores. Worse, default `GMAIL_WEBHOOK_SECRET==""` → `_verify_pubsub_secret` returns True →
**any unauthenticated POST** can enqueue a sync for an arbitrary `emailAddress` (the email is
attacker-controlled in the body). Impact is bounded (only triggers a sync of a connector that
already exists; `_trigger_ingest_for_email` matches by `external_email`), so it's a DoS / forced-sync
amplification vector rather than data exfil — but it's an unauthenticated trigger on a multi-tenant
table. HIGH.

### R3 — Gmail token refresh failure is silently terminal; never marks connector "error" (HIGH)
`services/gmail_client.py:37-61, 68-81`. On 401, `_refresh_access_token` calls
`resp.raise_for_status()`. If the refresh token is revoked/expired (Google returns 400
`invalid_grant`), this raises `httpx.HTTPStatusError`, which in `ingest.py:_run_sync` is caught by the
broad `except Exception` around `list_messages` (line 189) → just `break`s, then the worker proceeds
to **bump `connector.last_sync = now`** (line 308) as if the sync succeeded. Net effects:
(a) unlike Slack (`_record_auth_failure`), Gmail never writes a `connector_auth_error` ActivityEvent,
so `_derive_connector_status` can never return "error" for Gmail — it returns "active"/"stale";
(b) bumping last_sync masks the failure (shows "active"). A user whose Gmail auth is revoked sees a
healthy connector that silently ingests nothing. Asymmetry with the deliberate Slack design ("Do NOT
bump last_sync"). HIGH (auth/observability of a security-relevant state).

### R4 — Single static encryption key from SECRET_KEY; no rotation/versioning (MEDIUM)
`services/crypto.py:9-13`. Fernet key = SHA256(SECRET_KEY). Same `SECRET_KEY` also keys OAuth-state
HMAC (`oauth_state._sign`). Consequences: (1) one secret compromise → decrypt every stored
access+refresh token across all tenants AND forge OAuth state; (2) no key id/version embedded → can't
rotate without a re-encrypt migration of every `connectors.encrypted_token`/`refresh_token`;
(3) deriving a Fernet key by SHA256 of a possibly-low-entropy human secret bypasses Fernet's intended
`generate_key()`. Tokens are encrypted at rest (good), but the key-management story is fragile.
MEDIUM (defense-in-depth / blast radius), not auth-bypass on its own.

### R5 — Slack callback resolves email with the brand-new USER token, can collapse identity to {team}:{user} (MEDIUM, correctness/tenancy-adjacent)
`routers/slack.py:118-131`. If `users.info` fails or returns no email, `external_email` falls back to
`f"{team_id}:{slack_user_id}"`. Two different real users in the same Slack workspace who both lack a
visible email would each get distinct synthetic IDs (fine), but the upsert key is
(workspace_id, service, external_email) — a user who *first* connects without an email
(`{team}:{user}`) and *later* with an email creates a **second** connector row rather than updating
the first. Stacking connectors per workspace is also unbounded (no per-service uniqueness enforced in
the model — `models/connector.py` has no unique constraint on (workspace_id, service)). The sync
endpoints (`slack_sync`, `gmail_sync`) do `scalar_one_or_none()` on (workspace_id, service) and will
**raise MultipleResultsFound (500)** if two connectors of the same service exist for a workspace.
MEDIUM.

### R6 — `BackgroundTasks` hold the request-scoped DB session after the response is sent (MEDIUM, reliability)
`routers/gmail.py:449` and `routers/slack.py:284` and `routers/slack_interactions.py:254-256` pass the
`Depends(get_db)` session into `background_tasks.add_task(...)`. FastAPI closes the `get_db`
dependency (session teardown) when the response is returned, but the background task runs *after*
that. Using a closed/closing AsyncSession in the background task is a use-after-teardown: it can
raise, or commit on a session whose connection was already returned to the pool. `_handle_approve`
does real writes (event resolution, contact update, email send) on this session. This likely
"works" intermittently and fails under load/teardown races. The Celery workers correctly build their
own sessions (`_get_async_session`); the webhook/interaction background tasks do not. MEDIUM
(reliability; HITL send path).

### R7 — Slack signing secret is per-app and shared across all installing tenants (MEDIUM, design)
`routers/slack_interactions.py:44-59` + R1. Signature verification authenticates the *Slack app*, not
the customer. In a multi-workspace Slack distribution this secret is identical for every tenant, so
"valid signature" is necessary-not-sufficient for tenant isolation. Reinforces R1. MEDIUM on its own.

### R8 — `asyncio.get_event_loop().run_until_complete(...)` in every Celery task (LOW→MEDIUM, deprecation/runtime)
`workers/slack_ingest.py:242`, `workers/ingest.py:434/440/574`, + 8 other workers. On Python 3.12
`get_event_loop()` with no running loop is deprecated and raises `DeprecationWarning`/can error in a
fresh thread; prefork Celery workers can hit "Event loop is closed" after the first task on a worker
process. Pervasive, not connector-specific. LOW (works today) but a latent footgun.

### R9 — Token-exchange / profile HTTP calls have no timeout (LOW)
`routers/gmail.py:146-171` and `routers/slack.py:96-124` use `httpx.AsyncClient()` with no `timeout`
(httpx default is 5s connect/read, so not infinite — but the Gmail `profile_resp.raise_for_status()`
at line 170 will 500 the callback if Google's profile API hiccups, aborting an otherwise-successful
token exchange and losing the just-issued tokens). SlackClient/`ack_response_url` do set `timeout=15`.
Inconsistent and the callback path is fragile. LOW.

---

## INCONSISTENCIES (homogenization targets)

- **I1 — Two contradictory Slack signature verifiers.** `routers/slack.py:_verify_slack_signature`
  fails **open** (returns True when secret empty); `routers/slack_interactions.py:_verify_slack_signature`
  fails **closed** (returns False). Same function name, duplicated body, opposite security posture.
  Also `slack.py` uses `Header`-injected params; `slack_interactions.py` reads `request.body()` then
  separate headers. Consolidate into one `services/slack_signing.py`, fail-closed, single replay
  window constant (both use 300 but as literals).
- **I2 — Two `_build_redirect_uri()` / two scope lists / two callback shapes** duplicated across
  gmail.py and slack.py. Same structure, copy-pasted. A shared connector-OAuth base (provider config
  table + generic initiate/callback) would remove ~150 lines of parallel logic.
- **I3 — Auth-failure persistence is Slack-only.** `slack_ingest._record_auth_failure` writes
  `connector_auth_error` ActivityEvents; the Gmail ingest path has no equivalent, yet
  `_derive_connector_status` (gmail.py) is written to *read* those events generically. Gmail
  connectors therefore can never reach "error" status. Homogenize: GmailClient refresh failure should
  raise a typed `GmailAuthError` (mirror `SlackAuthError`) and the worker should `_record_auth_failure`.
- **I4 — Slack posts as a *user* (user_scope + xoxp- token), not a bot.** `SLACK_USER_SCOPES` has
  `chat:write` under `user_scope`; `followup_sequences` posts HITL blocks with the connector's user
  token to `SLACK_HITL_CHANNEL` ("general"). So approval prompts appear as if sent by the connecting
  human, and only channels that user is in are postable. Most CRMs use a bot token for this. Decide
  bot-vs-user and homogenize; current choice is unusual and surprising.
- **I5 — `external_email` is overloaded as the connector identity key** and means three different
  things: a real Gmail address (gmail), a real Slack email OR `{team}:{user}` (slack callback), and is
  *queried* as a bare `team_id` (slack events webhook) and a bare email (gmail push webhook). The name
  "external_email" no longer matches its use as a generic external identity. Rename to
  `external_identity` / add explicit `team_id`/`account_id` columns.
- **I6 — DB-session lifecycle differs** between Celery workers (own `_make_session`/`_get_async_session`,
  correct) and webhook/interaction background tasks (reuse request session, R6). Pick one pattern.
- **I7 — `uuid` imported but unused** in `routers/gmail.py` (line 18) and `routers/slack.py` (line 16)
  and `slack_interactions.py` imports both `uuid` and `from uuid import UUID` (uses both). Minor; lint.
- **I8 — Connector model has `token_expiry` column that is dead** (never written/read; C3). Either wire
  proactive refresh off it or drop it. The model also lacks a unique constraint on
  (workspace_id, service[, external_email]) that the upsert/`scalar_one_or_none` logic assumes (R5).
- **I9 — Tenancy enforcement style varies.** Connector routers inline
  `if current_user.workspace_id != workspace_id: 403`. A `get_workspace_id` dependency exists in
  `dependencies.py` but is unused by any router (grep returned nothing) — the path-param + manual
  compare pattern won everywhere. Homogenize on one (dependency-injected workspace scoping is safer:
  it can't be forgotten).

---

## CRITICAL FUNCTIONAL BUG (call out loudly)

**B1 — Slack Events API ingest webhook is dead code / never matches a connector.**
`routers/slack.py:223-240` `_trigger_slack_ingest_for_team` looks up
`Connector.external_email == team_id` (bare team id). But the **only** place a Slack connector's
`external_email` is set is the callback (`slack.py:127/130`), which stores either a **real email** or
`f"{team_id}:{slack_user_id}"` — **never** a bare `team_id`. Confirmed by grep: no code path ever
writes `external_email = <bare team_id>`. Therefore every `event_callback` logs
`slack_push_no_connector team_id=…` and **no real-time Slack ingest ever fires**; Slack only ever
syncs via the manual/scheduled `process_slack_sync`. This is a feature shipped (commit 74a589b "feat:
Slack Events API push webhook") that cannot work as written. Severity: this is a HIGH correctness bug
for a claimed feature (real-time Slack). Fix: look up by the team component, e.g. store/compare a
dedicated `team_id`, or match `external_email.like(f"{team_id}:%")` AND real-email rows mapped via a
team table.

(Gmail's equivalent push lookup, by contrast, DOES match: `external_email` for gmail == the real
address, and the Pub/Sub payload carries `emailAddress`. So Gmail push is wired correctly; Slack push
is not — another asymmetry.)

---

## Open questions for synthesizer
- Is this worktree truly prod master for connectors? (HEAD is on a signup branch.)
- Is the Slack app a single multi-tenant distribution (one signing secret/client) or per-tenant? This
  determines whether R1/R7 are exploitable cross-customer or only intra-customer.
- Is `GMAIL_WEBHOOK_SECRET` / `SLACK_SIGNING_SECRET` actually set in the deployed env? (`.env` not read
  here; both default to "" → fail-open for Gmail push and slack.py events.)
- Is there an Alembic migration adding a unique constraint on connectors(workspace_id, service)? Not
  found in scope; would turn R5 from latent into enforced.
