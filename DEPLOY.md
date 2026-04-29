# NovaCRM — Railway Deployment Checklist

## 1. Prerequisites

| Requirement | Notes |
|---|---|
| Railway account | railway.app — connect GitHub repo `rippere/crm-agentic` |
| Supabase project | supabase.com — free tier is fine |
| Google Cloud project | For Gmail OAuth (optional for demo mode) |
| Slack app | For HITL workflows (optional) |

---

## 2. Environment Variables

### API, Worker & Beat services (set on all three)

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | [REQUIRED] | Supabase connection string — get from Supabase → Settings → Database → Connection string (URI). Use the **pooler** URL if available (resolves IPv6 issues). Format: `postgresql+asyncpg://...` |
| `SUPABASE_URL` | [REQUIRED] | e.g. `https://xyzxyz.supabase.co` |
| `SUPABASE_SERVICE_ROLE_KEY` | [REQUIRED] | Supabase → Settings → API → `service_role` key |
| `SUPABASE_JWT_SECRET` | [REQUIRED] | Supabase → Settings → API → JWT Secret |
| `SECRET_KEY` | [REQUIRED] | Any 32+ char random string (used for Fernet encryption). Generate: `python3 -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `ANTHROPIC_API_KEY` | [REQUIRED] | From console.anthropic.com |
| `REDIS_URL` | [REQUIRED] | Add a Redis plugin in Railway; it auto-sets this var |
| `FRONTEND_URL` | [REQUIRED] | Your Railway web service URL, e.g. `https://novacrm.up.railway.app` |
| `GOOGLE_CLIENT_ID` | [OPTIONAL] | Gmail OAuth — see Section 4 |
| `GOOGLE_CLIENT_SECRET` | [OPTIONAL] | Gmail OAuth — see Section 4 |
| `SLACK_CLIENT_ID` | [OPTIONAL] | Slack connector OAuth |
| `SLACK_CLIENT_SECRET` | [OPTIONAL] | Slack connector OAuth |
| `SLACK_SIGNING_SECRET` | [OPTIONAL] | Slack → App Settings → Basic Information → Signing Secret. Required for HITL Block Kit handler |
| `SLACK_HITL_CHANNEL` | [OPTIONAL] | Channel for HITL approval cards (default: `general`) |
| `HUNTER_API_KEY` | [OPTIONAL] | hunter.io key for contact enrichment |

### Web service only

| Variable | Required | Description |
|---|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | [REQUIRED] | Same as `SUPABASE_URL` above |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | [REQUIRED] | Supabase → Settings → API → `anon` key |
| `NEXT_PUBLIC_FASTAPI_URL` | [REQUIRED] | Your Railway API service URL, e.g. `https://novacrm-api.up.railway.app` |
| `NEXT_PUBLIC_DEMO_MODE` | [OPTIONAL] | Set `true` for a fully mocked demo with no backend dependency |

---

## 3. Railway Services

Create **4 services** (+ 1 optional Flower) in a single Railway project from the same GitHub repo.

| Service name | Root directory | Start command |
|---|---|---|
| `api` | `apps/api` | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| `worker` | `apps/api` | `celery -A app.workers.celery_app.celery_app worker --loglevel=info --concurrency=2` |
| `beat` | `apps/api` | `celery -A app.workers.celery_app.celery_app beat --loglevel=info` |
| `web` | `apps/web` | `node server.js` |
| `flower` *(optional)* | `apps/api` | `celery -A app.workers.celery_app.celery_app flower --port=$PORT` |

Railway config files are already committed:
- `apps/api/railway.toml` — used by api / worker / beat
- `apps/api/railway-flower.toml` — copy to `railway.toml` in the flower service config
- `apps/web/railway.toml` — used by web

**Add a Redis plugin** to the project. Railway auto-injects `REDIS_URL` into all services in the project.

---

## 4. Google Cloud OAuth Setup (Gmail connector)

1. Go to [console.cloud.google.com](https://console.cloud.google.com) → APIs & Services → Credentials
2. Create OAuth 2.0 Client ID → Application type: **Web application**
3. Add authorized redirect URI:
   ```
   https://<your-api-service>.up.railway.app/auth/gmail/callback
   ```
   For local dev add: `http://localhost:8000/auth/gmail/callback`
4. Copy **Client ID** → `GOOGLE_CLIENT_ID`
5. Copy **Client Secret** → `GOOGLE_CLIENT_SECRET`
6. Enable the **Gmail API** under APIs & Services → Library

---

## 5. Slack App Setup (HITL workflows)

1. Go to [api.slack.com/apps](https://api.slack.com/apps) → Create New App → From scratch
2. **OAuth & Permissions** → Redirect URLs → add:
   ```
   https://<your-api-service>.up.railway.app/auth/slack/callback
   ```
3. **OAuth Scopes** (Bot Token Scopes): `chat:write`, `channels:read`, `users:read`
4. **Basic Information** → App Credentials → copy **Signing Secret** → `SLACK_SIGNING_SECRET`
5. **Interactivity & Shortcuts** → Request URL:
   ```
   https://<your-api-service>.up.railway.app/slack/interactions
   ```
6. Install to workspace → copy **Bot User OAuth Token** → `SLACK_BOT_TOKEN` (add to API env if you customise the Slack client)

---

## 6. Supabase Database Setup

The API backend uses your Supabase Postgres directly. On first deploy:

1. Go to Supabase → SQL Editor
2. Run the contents of `apps/api/migrations/init_docker.sql` — it is idempotent and safe to re-run
3. This creates all tables including pgvector extension (`vector` column on `contacts`)
4. Ensure **pgvector** is enabled: Supabase → Database → Extensions → enable `vector`

**Connection string:** Use the **Session mode pooler** URL from Supabase → Settings → Database → Connection Pooling. This resolves IPv6-only restrictions on Railway's shared IPs. Format:
```
postgresql+asyncpg://postgres.[project-ref]:[password]@aws-0-us-east-1.pooler.supabase.com:5432/postgres
```

---

## 7. Demo Mode

To run the frontend with rich mock data and no backend dependency:

```
NEXT_PUBLIC_DEMO_MODE=true
```

All 44 API client methods have demo stubs. The full UI works including pipeline, contacts, reports, agents, calls, and the AI assistant.
