# NovaCRM — Agentic CRM

AI-native CRM with autonomous agents for Gmail/Slack ingestion, lead scoring, deal health monitoring, call transcription, and semantic contact search.

## Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 16 (App Router, TypeScript) |
| Backend | FastAPI (async SQLAlchemy, Python 3.11) |
| Workers | Celery + Redis (Beat for nightly tasks) |
| Database | Postgres 16 + pgvector |
| Auth | Supabase (ES256 JWT) |
| AI | Claude Sonnet / Haiku (Anthropic) + Whisper |

## Quickstart (Docker Compose)

**Prerequisites:** Docker, a [Supabase](https://supabase.com) project, and an [Anthropic API key](https://console.anthropic.com).

```bash
git clone <repo>
cd crm-agentic

# 1. Copy and fill env vars
cp .env.example .env
#    Required: NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY,
#              SUPABASE_SERVICE_ROLE_KEY, SUPABASE_JWT_SECRET,
#              SECRET_KEY, ANTHROPIC_API_KEY

# 2. Build and start everything (postgres, redis, api, worker, beat, web)
docker compose up --build

# App: http://localhost:3000
# API: http://localhost:8000/docs
```

The `migrate` service runs `apps/api/migrations/init_docker.sql` automatically on first boot. No manual schema setup needed.

## Quickstart (local dev)

```bash
# Backend (Python 3.11+)
cd apps/api
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Start local postgres (pgvector image) if not using Supabase
docker run -d --name crm-pg -p 5432:5432 \
  -e POSTGRES_PASSWORD=devpass -e POSTGRES_DB=crmdb \
  pgvector/pgvector:pg16

# Apply schema
psql postgresql://postgres:devpass@localhost:5432/crmdb \
  -f migrations/init_docker.sql

# Start API
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Start Celery worker (separate terminal)
celery -A app.workers.celery_app.celery_app worker --loglevel=info

# Frontend (Node 20+)
cd apps/web
npm install
npm run dev   # http://localhost:3000
```

## Demo Mode

No backend? Set `NEXT_PUBLIC_DEMO_MODE=true` in `apps/web/.env.local` to run entirely on mock data:

```bash
echo "NEXT_PUBLIC_DEMO_MODE=true" > apps/web/.env.local
cd apps/web && npm run dev
```

## Features

### Contacts
- Semantic AI search (pgvector + all-MiniLM-L6-v2)
- Auto-enrich: Hunter.io email finder + Claude Haiku inference from messages
- AI email composer (Claude Sonnet)
- Lead scoring (heuristic + Celery)

### Pipeline
- Kanban deal board with drag-and-drop stages
- Deal health scoring: stage staleness decay + engagement silence penalty
- Stale deal alerts on dashboard

### Inbox
- Gmail OAuth connector: sync, extract contacts + tasks via Claude
- Slack OAuth connector: DM + channel ingestion
- Sentiment analysis per message (Claude Haiku)

### Calls
- Audio upload (mp3, m4a, wav, ogg, webm, flac — 50 MB max)
- Whisper transcription → Claude Sonnet summary + action items
- /calls page with processing indicator, summary drawer, transcript viewer

### Agents
- Nightly pipeline optimizer (Celery Beat, 02:00 UTC)
- Nightly deal health scorer (Celery Beat, 02:15 UTC)

## Environment Variables

See [`.env.example`](.env.example) for the full reference with descriptions.

**Required to run:**
- `NEXT_PUBLIC_SUPABASE_URL` + `NEXT_PUBLIC_SUPABASE_ANON_KEY` — Supabase project
- `SUPABASE_SERVICE_ROLE_KEY` + `SUPABASE_JWT_SECRET` — backend auth
- `SECRET_KEY` — Fernet encryption for stored OAuth tokens
- `ANTHROPIC_API_KEY` — Claude models (email composer, enrichment, call summary)
- `DATABASE_URL` — Postgres connection string (asyncpg format)
- `REDIS_URL` — Celery broker

**Optional:**
- `GOOGLE_CLIENT_ID/SECRET` — Gmail OAuth
- `SLACK_CLIENT_ID/SECRET` — Slack OAuth
- `HUNTER_API_KEY` — contact email enrichment (free tier: 25 req/month)
