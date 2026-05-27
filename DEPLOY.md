# NovaCRM — Production Deployment Checklist

> **Audit date:** 2026-05-25  
> **Auditor:** automated production-readiness pass

---

## What Was Fixed in Code (This Audit)

| File | Change | Line(s) |
|---|---|---|
| `apps/api/app/main.py` | Added stdlib `logging` with JSON-style formatter to stdout. All log output now goes to stdout with `level=`, `logger=`, `duration_ms=` fields. | 1–35 |
| `apps/api/app/main.py` | Added HTTP request logging middleware (method, path, status, duration_ms). Health endpoint excluded to avoid log noise. | ~80–95 |
| `apps/api/app/main.py` | `/health` endpoint upgraded: now pings the database with `SELECT 1` and returns `{"status":"ok","database":"ok"}` or `{"status":"degraded","database":"error","database_error":"..."}`. Returns HTTP 200 in both cases to avoid Railway killing the container on a transient DB blip. | 117–137 |
| `apps/api/app/services/auth.py` | Replaced `print(..., file=sys.stderr)` with `logger.debug` / `logger.warning`. Removed `import sys`. | 30–32 |
| `apps/api/app/dependencies.py` | Replaced `print(..., file=sys.stderr)` with `logger.warning`. Removed inline `import sys`. | 34–35 |
| `apps/api/app/workers/pipeline.py` | `_get_async_session()` now prefers `DATABASE_URL` over `SUPABASE_URL` (was only reading `SUPABASE_URL`, ignoring the canonical `DATABASE_URL`). Added `+asyncpg` guard to avoid double-replacement. | 34–40 |
| `apps/api/app/workers/score_contact.py` | Same `DATABASE_URL`-first fix as pipeline.py. | 24–31 |
| `apps/api/migrations/005_activity_severity_error.sql` | **New migration.** Drops the broken `severity CHECK ('info','success','warning')` constraint and replaces it with `('info','success','warning','error')`. The HITL interaction handler (`slack_interactions.py`) writes `severity='error'` on failure paths, which would cause a Postgres constraint violation on every HITL error. | new file |
| `apps/api/.env.example` | Added missing `DATABASE_URL`, `SLACK_CLIENT_ID`, `SLACK_CLIENT_SECRET`, `SLACK_SIGNING_SECRET`, `SLACK_HITL_CHANNEL`, `HUNTER_API_KEY` to the example file. These are all required/optional vars that Settings references but were absent from the example. | full file |

---

## Critical: Secrets in `apps/web/.env.local`

**`apps/web/.env.local` contains real credentials and is NOT committed** (`.gitignore` covers `.env*`). However:

- It contains a real `ANTHROPIC_API_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, and `SUPABASE_JWT_SECRET`.
- These are production Supabase credentials for project `ilfibxflnelssllgszex`.
- **Rotate these immediately** if this file was ever accidentally staged or shared:
  - Rotate Supabase service role key: Supabase → Settings → API → Regenerate
  - Rotate Anthropic API key: console.anthropic.com → API Keys → Revoke & reissue
- Set these values via Railway's dashboard (never in `.env.local` in a container build).

---

## Environment Variables to Set in Railway

### API, Worker, Beat services (set on all three Railway services)

| Variable | Required | Where to get it |
|---|---|---|
| `DATABASE_URL` | **REQUIRED** | Supabase → Settings → Database → Connection Pooling → **Session mode** URL. Must be prefixed `postgresql+asyncpg://`. Use the pooler (not direct) to avoid Railway IPv6 routing issues. |
| `SUPABASE_URL` | **REQUIRED** | `https://<project-ref>.supabase.co` — Supabase → Settings → API |
| `SUPABASE_SERVICE_ROLE_KEY` | **REQUIRED** | Supabase → Settings → API → `service_role` key |
| `SUPABASE_JWT_SECRET` | **REQUIRED** | Supabase → Settings → API → JWT Secret |
| `SECRET_KEY` | **REQUIRED** | Generate: `python3 -c "import secrets; print(secrets.token_urlsafe(32))"` — used for Fernet encryption of OAuth tokens. Must be the same on all API, worker, and beat services. |
| `ANTHROPIC_API_KEY` | **REQUIRED** | console.anthropic.com → API Keys |
| `REDIS_URL` | **REQUIRED** | Add a **Redis plugin** in Railway — it auto-injects `REDIS_URL` into all services in the project. |
| `FRONTEND_URL` | **REQUIRED** | Your Railway web service URL, e.g. `https://novacrm.up.railway.app`. OAuth callbacks are derived from this. |
| `GOOGLE_CLIENT_ID` | optional | Gmail connector — see Section 4 |
| `GOOGLE_CLIENT_SECRET` | optional | Gmail connector — see Section 4 |
| `SLACK_CLIENT_ID` | optional | Slack connector OAuth |
| `SLACK_CLIENT_SECRET` | optional | Slack connector OAuth |
| `SLACK_SIGNING_SECRET` | optional | Slack → App → Basic Information → Signing Secret. Required for HITL Block Kit handler. If unset, signature verification is skipped (dev-only behavior). |
| `SLACK_HITL_CHANNEL` | optional | Slack channel name for HITL approval cards (default: `general`) |
| `HUNTER_API_KEY` | optional | hunter.io — contact enrichment |

### Web service only

| Variable | Required | Where to get it |
|---|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | **REQUIRED** | Same as `SUPABASE_URL` above |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | **REQUIRED** | Supabase → Settings → API → `anon` key |
| `NEXT_PUBLIC_FASTAPI_URL` | **REQUIRED** | Your Railway API service URL, e.g. `https://novacrm-api.up.railway.app` |
| `NEXT_PUBLIC_DEMO_MODE` | optional | Set `true` for fully mocked demo with no backend dependency |

---

## Railway Services

Create **4 services** (+ 1 optional Flower) in a single Railway project from the same GitHub repo.

| Service name | Root directory | Start command |
|---|---|---|
| `api` | `apps/api` | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| `worker` | `apps/api` | `celery -A app.workers.celery_app.celery_app worker --loglevel=info --concurrency=2` |
| `beat` | `apps/api` | `celery -A app.workers.celery_app.celery_app beat --loglevel=info` |
| `web` | `apps/web` | `node server.js` |
| `flower` *(optional)* | `apps/api` | `celery -A app.workers.celery_app.celery_app flower --port=$PORT` |

Railway config files:
- `apps/api/railway.toml` — used by `api`, `worker`, and `beat` services (points to Dockerfile, sets healthcheckPath `/health`)
- `apps/api/railway-flower.toml` — copy this as the config for the `flower` service
- `apps/web/railway.toml` — used by `web` service

**Add a Redis plugin** to the Railway project. It auto-injects `REDIS_URL` into all services.

> Note: Worker and beat services use the same Dockerfile as the API but with a different start command overridden in Railway's service settings. The `railway.toml` healthcheck (`/health`) only applies to the API service — override it to `/` (or disable) for worker/beat, which don't expose HTTP.

---

## Supabase Database Setup

The API uses Supabase Postgres directly (SQLAlchemy + asyncpg). On first deploy:

### Step 1 — Enable pgvector extension
Supabase Dashboard → Database → Extensions → search `vector` → Enable.

### Step 2 — Run migrations in order

Go to Supabase → SQL Editor and run each file in order:

```
apps/api/migrations/001_unified_schema.sql   # 11-table schema + RLS policies
apps/api/migrations/002_vector_embeddings.sql # vector(384) column + HNSW index
apps/api/migrations/003_deal_health.sql       # health_score + stage_changed_at on deals
apps/api/migrations/004_call_summaries.sql    # call_summaries table
apps/api/migrations/005_activity_severity_error.sql  # FIX: adds 'error' to severity CHECK
```

> `init_docker.sql` is for local Docker only (no RLS). Do NOT run it on Supabase production.

All SQL files use `IF NOT EXISTS` / `DROP CONSTRAINT IF EXISTS` guards and are safe to re-run.

### Connection string format

Use the **Session mode pooler** URL from Supabase → Settings → Database → Connection Pooling:

```
postgresql+asyncpg://postgres.[project-ref]:[password]@aws-0-us-east-1.pooler.supabase.com:5432/postgres
```

Note the `postgresql+asyncpg://` scheme — asyncpg requires this prefix. Railway's shared IPs may not be in the Supabase direct-connection allowlist, so the pooler URL is required.

---

## Google Cloud OAuth Setup (Gmail connector)

> The Gmail redirect URI in this app is built as:  
> `{FRONTEND_URL}/auth/gmail/callback` (handled by the Next.js frontend, which passes `code` to the backend).  
> The backend's `/auth/gmail/callback` endpoint is **not** the Google redirect target — the frontend page is.

1. Go to [console.cloud.google.com](https://console.cloud.google.com) → APIs & Services → Credentials
2. Create OAuth 2.0 Client ID → Application type: **Web application**
3. Authorized redirect URIs — add **both**:
   ```
   https://<your-web-service>.up.railway.app/auth/gmail/callback
   ```
   For local dev:
   ```
   http://localhost:3000/auth/gmail/callback
   ```
4. Copy **Client ID** → `GOOGLE_CLIENT_ID`
5. Copy **Client Secret** → `GOOGLE_CLIENT_SECRET`
6. Enable the **Gmail API** under APIs & Services → Library

---

## Slack App Setup (HITL workflows)

> The Slack redirect URI is built as:  
> `{FRONTEND_URL}/auth/slack/callback` (Next.js frontend page, not the API directly).

1. Go to [api.slack.com/apps](https://api.slack.com/apps) → Create New App → From scratch
2. **OAuth & Permissions** → Redirect URLs → add:
   ```
   https://<your-web-service>.up.railway.app/auth/slack/callback
   ```
3. **User Token Scopes** (not Bot): `channels:read`, `channels:history`, `chat:write`, `groups:read`, `groups:history`, `im:read`, `im:history`, `mpim:read`, `mpim:history`, `users:read`, `users:read.email`
4. **Basic Information** → App Credentials → copy **Signing Secret** → `SLACK_SIGNING_SECRET`
5. **Interactivity & Shortcuts** → Request URL:
   ```
   https://<your-api-service>.up.railway.app/slack/interactions
   ```
   (This points at the API service, not the web service — this is correct.)
6. Install to workspace

> Note: HITL Slack messages are posted using the **user token** from the connected Slack account (stored as a connector), not a bot token. The user must be in the target channel. `SLACK_HITL_CHANNEL` defaults to `general`.

---

## Health Check

The `/health` endpoint (used by Railway's healthcheckPath) now:
- Returns `{"status":"ok","database":"ok"}` when DB is reachable
- Returns `{"status":"degraded","database":"error","database_error":"..."}` on DB failure
- Always returns HTTP 200 (Railway healthcheck — container is kept alive; monitoring should alert on `status != "ok"` in the body)

---

## Celery Beat Schedule

The beat service runs three scheduled tasks:

| Task | Schedule | Description |
|---|---|---|
| `pipeline.optimize_pipeline` | 02:00 UTC daily | Recomputes win-probability heuristics for all open deals |
| `deal_health_worker.compute_deal_health` | 02:15 UTC daily | Scores deal health (0-100) based on stage age and activity |
| `followup_sequences.check_stale_deals_hitl` | 09:00 UTC daily | Drafts follow-up emails for stale deals, posts to Slack for HITL approval |

Beat requires Redis (used as the scheduler backend). The beat service does **not** process tasks — it only enqueues them. At least one worker service must be running.

---

## Error Handling & Observability

**What's in place:**
- Structured log lines to stdout in key=value format (`level=INFO logger=app.main method=POST path=/...`)
- Request logging middleware on all non-health routes (method, path, status, duration_ms)
- Health endpoint now reports DB connectivity
- Celery tasks log via Celery's built-in logging (visible in Railway logs)

**What's NOT in place (manual action required):**
- No Sentry or external error tracking. To add Sentry:
  1. `uv pip install sentry-sdk[fastapi]`
  2. Add `SENTRY_DSN=https://...@sentry.io/...` to Railway env vars
  3. In `apps/api/app/main.py`, add before creating the `app`:
     ```python
     import sentry_sdk
     if dsn := os.getenv("SENTRY_DSN"):
         sentry_sdk.init(dsn=dsn, traces_sample_rate=0.1)
     ```
- No alerting on `status=degraded` in `/health` — set up Railway or an external uptime monitor to alert on body content.

---

## Known Issues / Remaining Manual Steps

### 1. Run migration 005 on production Supabase
File: `apps/api/migrations/005_activity_severity_error.sql`  
The `severity='error'` value is written by `slack_interactions.py` on HITL failure paths. Without this migration, every HITL error will cause a Postgres constraint violation and fail silently.

### 2. Set all required Railway env vars
See the environment variables table above. The minimum set to boot:
`DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_JWT_SECRET`, `SECRET_KEY`, `ANTHROPIC_API_KEY`, `REDIS_URL`, `FRONTEND_URL`

### 3. Verify `FRONTEND_URL` is the production web URL
OAuth redirect URIs for both Gmail and Slack are derived from `FRONTEND_URL`. If this is wrong, OAuth flows will redirect users to the wrong domain.

### 4. Register OAuth redirect URIs with Google and Slack
Both providers require explicit allowlisting of redirect URIs. Localhost URIs work for dev but must be supplemented with production URIs for Railway deployment. See Sections 4 and 5 above.

### 5. Celery worker and beat services must share `SECRET_KEY` with the API
The Fernet encryption key for OAuth tokens is derived from `SECRET_KEY`. If worker and beat have a different `SECRET_KEY` than the API, token decryption will silently fail and OAuth syncs will break.

### 6. Enable pgvector extension in Supabase
Required before running migration 002. Supabase → Database → Extensions → `vector`.

### 7. Add Sentry DSN (optional but recommended)
See Observability section above. Without external error tracking, errors only appear in Railway log streams.

### 8. Rotate credentials if `apps/web/.env.local` was ever shared
See Critical section above.

---

## Demo Mode

To run the frontend with rich mock data and no backend dependency:

```
NEXT_PUBLIC_DEMO_MODE=true
```

All 44 API client methods have demo stubs. The full UI works including pipeline, contacts, reports, agents, calls, and the AI assistant. Safe to enable on the web service while the backend is being set up.
