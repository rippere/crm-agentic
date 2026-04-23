# CRM-agentic Build Progress

## Completed
- [2026-04-23] Phase 1: Monorepo restructure (Task 1a)
- [2026-04-23] Phase 1: Unified 11-table Supabase schema (Task 1b)
- [2026-04-23] Phase 1: Supabase client + types update (Task 1c)
- [2026-04-23] Phase 1: Auth pages — login, onboarding, auth guard (Task 1d)
- [2026-04-23] Phase 1: Hooks wired to real Supabase, Realtime enabled (Task 1e)
- [2026-04-23] Phase 1: Sidebar extended with PM routes (Task 1f)
- [2026-04-23] Phase 1: Seed script updated for multi-tenant schema (Task 1g)
- [2026-04-22] Phase 2: FastAPI scaffold — main.py, config.py, database.py, Dockerfile, requirements.txt (Task 2a)
- [2026-04-22] Phase 2: SQLAlchemy ORM models for all 11 tables (Task 2b)
- [2026-04-22] Phase 2: Auth service (Supabase JWT verify), dependencies (get_current_user, get_workspace_id) (Task 2c)
- [2026-04-22] Phase 2: Crypto service — Fernet encrypt/decrypt with SHA-256 derived key (Task 2d)
- [2026-04-22] Phase 2: Core routers — auth, workspaces, contacts, deals, agents, messages, tasks (Task 2e)
- [2026-04-22] Phase 2: Gmail OAuth flow — /auth URL, /callback, /sync, DELETE connector (Task 2f)
- [2026-04-22] Phase 2: Celery workers — celery_app.py, ingest task with dedup + Claude extraction (Task 2g)
- [2026-04-22] Phase 2: Claude extraction service — claude-haiku-4-5, returns JSON task list (Task 2h)
- [2026-04-22] Phase 2: docker-compose.yml updated — api builds from apps/api/, worker service added (Task 2i)

## Current Phase
Phase 3 — Frontend wiring to FastAPI + UI polish

## Next Task
Task 3a: Update Next.js api-client.ts to call FastAPI endpoints (replace Supabase direct calls for Gmail/agents/tasks flows)
Task 3b: Add Connectors page (Gmail OAuth button → /connectors?connected=gmail landing)
Task 3c: Tasks page — list + create + status toggle, wired to FastAPI /workspaces/{id}/tasks

## Blockers
- Supabase project not yet created — env vars (NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY) need to be filled in .env before the app can connect to a real database
- Google Cloud OAuth credentials needed for Gmail connector — GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET in .env
- ANTHROPIC_API_KEY needed for Claude extraction (claude-haiku-4-5)

## Phase 2 Architecture Summary

### apps/api/ structure (35 files)
```
apps/api/
├── Dockerfile                    FROM python:3.12-slim, uvicorn on port 8000
├── requirements.txt              fastapi, uvicorn, sqlalchemy[asyncio], asyncpg,
│                                 python-jose, cryptography, celery[redis], httpx,
│                                 anthropic, pydantic-settings
├── .env.example                  all required env vars documented
└── app/
    ├── main.py                   FastAPI app, CORS, lifespan, all routers mounted
    ├── config.py                 Pydantic BaseSettings reading from .env
    ├── database.py               async SQLAlchemy engine + AsyncSession factory
    ├── dependencies.py           get_current_user, get_workspace_id Depends()
    ├── models/                   11 SQLAlchemy ORM models (1 per table)
    │   ├── workspace.py, user.py, contact.py, deal.py, agent.py
    │   ├── activity_event.py, connector.py, message.py, task.py
    │   ├── metric_template.py, clarity_score.py
    ├── routers/                  8 routers
    │   ├── auth.py               POST /auth/verify (auto-provisions users row)
    │   ├── workspaces.py         GET/POST /workspaces
    │   ├── contacts.py           GET contacts + POST score stub
    │   ├── deals.py              GET deals
    │   ├── agents.py             GET agents + POST /{id}/run stub
    │   ├── messages.py           GET messages
    │   ├── tasks.py              GET/POST/PUT tasks
    │   └── gmail.py              OAuth URL, callback, sync trigger, delete
    ├── services/
    │   ├── auth.py               verify_supabase_jwt, extract_supabase_uid
    │   ├── crypto.py             Fernet encrypt/decrypt (SHA-256 of SECRET_KEY)
    │   ├── gmail_client.py       GmailClient (httpx, 401→refresh flow)
    │   └── extraction.py         extract_tasks() → claude-haiku-4-5 → JSON tasks
    └── workers/
        ├── celery_app.py         Celery instance with Redis broker
        └── ingest.py             process_gmail_sync task: fetch→dedup→store→extract
```

### docker-compose.yml changes
- api service: now builds from `./apps/api` with all env vars wired through
- worker service: added (same image, celery worker entrypoint)
- redis: unchanged
