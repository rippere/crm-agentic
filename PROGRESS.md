# CRM-agentic Build Progress

## Completed
- [2026-04-23] Phase 1: Full monorepo + auth + Supabase schema + hooks (Tasks 1a-1h)
- [2026-04-23] Phase 2: FastAPI service + Gmail OAuth + Celery + Claude extraction (Tasks 2a-2i)
- [2026-04-23] Phase 3: PM UI pages — /connectors, /inbox, /tasks, /projects + dashboard KPIs (Tasks 3a-3g)
- [2026-04-23] Phase 4: Sales intelligence — email composer, lead scorer, pipeline optimizer, sentiment analyzer, Celery Beat (Tasks 4a-4g)

- [2026-04-28] Phase 5a: Slack OAuth connector + ingest pipeline (Tasks 5a)
- [2026-04-28] Phase 5b: pgvector semantic contact embeddings + AI search (Tasks 5b)

## Current Phase
Phase 5 — Advanced ML (5c, 5d remaining)

## Next Tasks
- 5c: Call Summarizer (Whisper + Claude Sonnet) — audio upload → transcript → summary
- 5d: XGBoost lead scorer trained on real data (requires 100+ contacts with outcomes)
- 5e: Contact auto-enrich — pull LinkedIn/Clearbit data on new contacts
- 5f: Deal health scoring — time-in-stage decay + engagement signals

## Blockers (must be resolved before first run)
- Supabase project: create at supabase.com, fill NEXT_PUBLIC_SUPABASE_URL + NEXT_PUBLIC_SUPABASE_ANON_KEY + SUPABASE_SERVICE_ROLE_KEY + SUPABASE_JWT_SECRET
- Google Cloud: create OAuth 2.0 client, fill GOOGLE_CLIENT_ID + GOOGLE_CLIENT_SECRET, add redirect URI http://localhost:8000/auth/gmail/callback
- ANTHROPIC_API_KEY: needed for email composer + extraction + sentiment
- SECRET_KEY: any 32+ char random string for Fernet encryption

## Phase 3 Architecture Summary

### New pages added
```
apps/web/src/app/(app)/
├── connectors/page.tsx     Gmail OAuth connect/sync/disconnect cards
├── inbox/page.tsx          Message list + slide-out detail drawer
├── tasks/page.tsx          Kanban board (dnd-kit) — Open/In Progress/Done
└── projects/page.tsx       Client-side grouping of tasks by contact_id
```

### Modified pages
- `dashboard/page.tsx` — PM KPI cards (Tasks Extracted, Avg Clarity, Open Tasks, Messages Ingested) gated on workspace mode 'pm'|'both'
- `contacts/page.tsx` — Messages tab in drawer + AI Email Composer modal (calls POST /compose)

### api-client.ts additions
- getConnectors, getGmailAuthUrl, triggerGmailSync, deleteConnector
- createTask, updateTask
- composeEmail

## Phase 4 Architecture Summary

### New FastAPI endpoints
- `POST /workspaces/{id}/contacts/{contact_id}/compose` — Claude Sonnet email draft
- `POST /workspaces/{id}/contacts/{contact_id}/score` — enqueues score_lead Celery task

### New Celery workers
```
apps/api/app/workers/
├── score_contact.py    Heuristic lead scorer — base 50, status/revenue/deal adjustments
└── pipeline.py         Heuristic pipeline optimizer — stage bonus + staleness penalty
```

### New services
```
apps/api/app/services/
└── sentiment.py        Claude Haiku sentiment analysis — wired into ingest.py
```

### Celery Beat
- `celery_app.py` — beat_schedule: nightly-pipeline-optimize at 2am UTC
- `docker-compose.yml` — `beat` service added (same image as worker)

### Agents page
- Start button calls `apiClient.triggerAgent()` — shows job_id toast
- Polls `GET /agents` every 5s while any agent is status=processing
