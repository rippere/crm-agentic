---
type: process
status: verified
consumes: [Supabase JWT, Google OAuth code, Slack OAuth code, Workspace, User]
produces: [Connector, Workspace, User, Agent roster]
---

# auth

A user's Google/Slack account is exchanged for an encrypted, workspace-bound Connector the ingest workers can later act on.

## Input → Movement → Output

A signed-in user hits `/connectors/{gmail,slack}/auth`, which mints an HMAC-signed `state` carrying their workspace_id and returns a provider consent URL. The provider redirects to `/auth/{gmail,slack}/callback`, where the code is exchanged for tokens, the account email is resolved, and the tokens are Fernet-encrypted. A `connectors` row is upserted (workspace_id + service + external_email) and the browser is bounced to `/connectors?connected=...`.

## Why this shape

The OAuth `state` is otherwise a forgeable value; signing `{wid, exp, nonce}` with `SECRET_KEY` lets the callback recover a *verified* workspace_id instead of trusting the raw redirect, closing a cross-tenant bind (`services/oauth_state.py:1-8`). Tokens are never stored in plaintext — a SHA-256-derived Fernet key encrypts them at rest (`services/crypto.py:9-19`). Note this connector-OAuth "auth" is distinct from *user* auth (Supabase JWT verified via JWKS in `services/auth.py:25`, `routers/auth.py:89`).

## Steps

1. Build signed state bound to workspace_id — `services/oauth_state.py:43` (`build_state`), used at `routers/gmail.py:115`, `routers/slack.py:76`.
2. Return provider consent URL with scopes — Gmail `routers/gmail.py:107-127` (scopes :92-97); Slack `routers/slack.py:64-78` (scopes :42-54).
3. Callback verifies state → workspace_id — `services/oauth_state.py:54` (`verify_state`), called `gmail.py:141` / `slack.py:92`.
4. Exchange code for tokens — Gmail `routers/gmail.py:146-159`; Slack `routers/slack.py:96-108`.
5. Resolve external account email — Gmail profile `gmail.py:165-173`; Slack `users.info` `slack.py:120-130` (falls back to `team_id:user_id`).
6. Encrypt tokens — `gmail.py:176-177`, `slack.py:132` via `encrypt_token`.
7. Upsert Connector row — `gmail.py:180-204`, `slack.py:134-155`.

## If you change this

- **Hits:** `models/connector.py` (`service`, `encrypted_token`, `refresh_token`, `external_email`, `last_sync`, `message_count` — connector.py:16-23); the ingest workers that decrypt these tokens (`services/gmail_client.py:12`, `services/slack_client.py:11`); `_derive_connector_status` (`gmail.py:42-87`).
- **Does not hit:** scoring, discovery, outreach.

## Surfaces

| Surface | Role |
|---|---|
| Frontend "Connectors" page | initiates OAuth, lands redirect |
| Google / Slack OAuth servers | issue codes + tokens |
| ingest workers | downstream consumer of the stored Connector |

## See

- Objects: [[Connector]], [[Workspace]], [[User]], [[Agent]]
- Source: `apps/api/app/routers/gmail.py`, `apps/api/app/routers/slack.py`
