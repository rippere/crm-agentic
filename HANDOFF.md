# NovaCRM — Session Handoff
**Date:** 2026-04-29  
**Session scope:** Boot stack → rigorous testing → demo polish → deployment prep  
**Git:** `a07c2a4` on `master` — pushed to `git@github.com:rippere/crm-agentic.git`

---

## Current State — Everything Working

### Services (local dev)
| Service | How to start | Port |
|---|---|---|
| Postgres | `docker start crm-local-pg` | 5433 |
| Redis | `docker start crm-redis` | 6379 |
| API | `cd apps/api && .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 > /tmp/crm-api.log 2>&1 &` | 8000 |
| Next.js | `cd apps/web && node_modules/.bin/next dev` | 3000 |
| Celery worker | `cd apps/api && .venv/bin/celery -A app.workers.celery_app.celery_app worker --loglevel=info` | — |
| Celery beat | `cd apps/api && .venv/bin/celery -A app.workers.celery_app.celery_app beat --loglevel=info` | — |

### Auth (for API testing)
Test Supabase user: `test@novacrm.dev` / `Test1234!`

Get a fresh token:
```bash
ANON_KEY="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImlsZmlieGZsbmVsc3NsbGdzemV4Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzY5MDMzMDUsImV4cCI6MjA5MjQ3OTMwNX0.NgwE9wd_eS31onVKSmAPhlhKEHIv3a6kc2GBdxopM20"
curl -s "https://ilfibxflnelssllgszex.supabase.co/auth/v1/token?grant_type=password" \
  -H "apikey: $ANON_KEY" -H "Content-Type: application/json" \
  -d '{"email":"test@novacrm.dev","password":"Test1234!"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])"
# Then call POST /auth/verify to auto-provision the user in local DB
```

---

## What Was Built This Session

### Bugs Found and Fixed

**1. Anthropic client using `os.getenv("")` (empty string)**  
Files: `apps/api/app/routers/contacts.py`, `apps/api/app/routers/ai.py`  
The client was created at module import time with `os.getenv("ANTHROPIC_API_KEY", "")`. Since the API key is in `.env` (loaded by pydantic Settings) but not in the shell environment, `os.getenv` returned `""` and every request to `/compose` or `/ai/query` returned 500/503.  
Fix: instantiate `anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)` lazily per-request.

**2. `next build` exit 1 — missing Suspense boundaries**  
Files: `apps/web/src/app/auth/slack/callback/page.tsx`, `apps/web/src/app/(app)/connectors/page.tsx`  
Next.js 16 requires `useSearchParams()` to be inside a `<Suspense>` boundary. Both pages failed at static generation.  
Fix: extracted each into an `Inner` component, wrapped in `<Suspense>` in the default export.

**3. Web Dockerfile using `npm ci` on a pnpm project**  
File: `apps/web/Dockerfile`  
Fixed to use `corepack enable && pnpm install --frozen-lockfile --ignore-scripts`.

---

### Phase 10–12 Features (implemented in prior session, tested + committed this session)

#### API — 44 routes total
| New endpoint | Description |
|---|---|
| `GET /me` | User profile + role from local DB |
| `POST /workspaces/{id}/invite` | Supabase admin invite email via service role key |
| `GET /workspaces/{id}/contacts/{cid}/timeline` | Aggregated: messages, deals, call summaries, activity events |
| `POST /workspaces/{id}/contacts/{cid}/brief` | Pre-meeting intelligence brief via Claude Haiku |
| `POST /workspaces/{id}/contacts/{cid}/send-email` | Send via connected Gmail connector |
| `PATCH /workspaces/{id}/contacts/{cid}/status` | Update contact status, logs ActivityEvent |
| `GET /workspaces/{id}/deals/history` | 6-month closed-won revenue buckets |
| `GET /workspaces/{id}/deals/stale` | Deals with health_score ≤ threshold |
| `PATCH /workspaces/{id}/deals/{id}` | Update stage/value/health |
| `GET /workspaces/{id}/pipeline/suggestions` | AI-generated action suggestions |
| `POST /workspaces/{id}/pipeline/optimize` | Enqueue Celery optimizer job |
| `GET /workspaces/{id}/events` | SSE stream of ActivityEvent rows (cursor-based) |
| `POST /mcp` | JSON-RPC MCP server (initialize / tools/list / tools/call) |
| `POST /slack/interactions` | HMAC-verified Slack Block Kit handler (HITL approve/dismiss) |

#### MCP Tools (via `POST /mcp`)
- `list_contacts` — filter by query/status/limit
- `list_deals` — filter by stage/limit
- `stale_deals` — deals with health ≤ threshold
- `pipeline_summary` — total value, win rate, stage breakdown

#### Celery Workers
- `check_stale_deals_hitl` — daily 9am UTC: finds stale deals, generates Claude Haiku email draft, posts Slack Block Kit approval card, stores `hitl_pending` ActivityEvent
- `deal_health_worker` — after scoring, fires `deal_alert` ActivityEvent for health ≤ 25 with stage-specific next-best-action suggestions

#### Web — New UI
| Feature | File |
|---|---|
| 4-step onboarding wizard (name → mode → connectors → invite) | `src/app/onboarding/page.tsx` |
| Bulk contact actions (checkbox selection, floating BulkActionBar, Set Status, Enrich All) | `src/app/(app)/contacts/page.tsx` |
| Contact drawer: Timeline tab + Pre-Meeting Brief modal | `src/app/(app)/contacts/page.tsx` |
| Send via Gmail in EmailComposerModal | `src/app/(app)/contacts/page.tsx` |
| Revenue Trend & Forecast chart (linear regression, 3-month projection) | `src/app/(app)/reports/page.tsx` |
| `useRole` hook — calls `GET /me`, exposes `isAdmin` | `src/hooks/useRole.ts` |
| Settings: admin-only invite card + save disabled for non-admins | `src/app/(app)/settings/page.tsx` |

---

## Test Results

**29/29 endpoints passing** against local stack with real ES256 JWT from Supabase.

Spot-check results:
- `/compose` → Claude Haiku generated personalized subject + body
- `/ai/query` → natural language pipeline answer grounded in workspace data
- `/contacts/{id}/brief` → full markdown pre-meeting brief
- `/contacts/{id}/timeline` → deal_stage + activity events correctly aggregated
- `POST /mcp tools/call pipeline_summary` → `Win rate: 100%, Active: 1 ($22,000 in pipeline)`
- SSE `/events` → HTTP 200 `text/event-stream`, stream open
- `next build` → exit 0, 12 pages compiled, no errors

---

## Deployment

### Production Build
```bash
cd apps/web && node_modules/.bin/next build  # exit 0, ~3.5s compile
```

### Railway (recommended — same setup as EMM)
1. New Project → Deploy from GitHub → `rippere/crm-agentic`
2. Create 4 services with these root dirs + commands:

| Service | Root dir | Start command |
|---|---|---|
| web | `apps/web` | `node server.js` |
| api | `apps/api` | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| worker | `apps/api` | `celery -A app.workers.celery_app.celery_app worker --loglevel=info --concurrency=2` |
| beat | `apps/api` | `celery -A app.workers.celery_app.celery_app beat --loglevel=info` |

3. Add **Redis** plugin → set `REDIS_URL` on api/worker/beat
4. Use existing Supabase `DATABASE_URL` (already has pgvector extension at Supabase project level)
5. Set all env vars from `.env.example` at repo root
6. **web** only needs `NEXT_PUBLIC_*` vars + `NEXT_PUBLIC_DEMO_MODE=false` (or `true` for demo)

### Demo Mode
Set `NEXT_PUBLIC_DEMO_MODE=true` on the web service. The full UI runs with rich mock data — no backend dependency. All 44 API client methods have demo stubs.

---

## What's Left Before Public Launch

### Blockers
1. **Google OAuth credentials** — `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` are empty. Gmail connector OAuth won't work until these are created in Google Cloud Console and added to env.
2. **`SLACK_SIGNING_SECRET`** — Needed by `slack_interactions.py` to verify Slack requests. Already in `config.py` as `SLACK_SIGNING_SECRET: str = ""` — just needs the value from your Slack app settings.
3. **Onboarding workspace_id sync** — After the wizard creates a workspace via direct Supabase insert, `user.user_metadata.workspace_id` should be updated via the Supabase admin API so the value is available on subsequent sessions without requiring `/auth/verify`. Currently the API's `get_current_user` dependency handles this correctly, but the web session token won't have the metadata populated.

### Nice-to-have
- `POST /workspaces/{id}/contacts` — no create contact route yet; add to `contacts.py` if you want a functional "New Contact" button beyond the onboarding wizard
- Rate limiting on `/mcp` and `/ai/query` before public launch (add `slowapi`)
- Flower dashboard for Celery job monitoring (add `flower` to `requirements.txt`, create a Railway service)
- Mobile responsive pass on new components (BulkActionBar, timeline drawer)

---

## Key File Map

```
crm-agentic/
├── .env.example                          ← all required env var keys
├── docker-compose.yml                    ← full local stack incl. pgvector migration
├── apps/api/
│   ├── .env                              ← secrets (gitignored)
│   ├── railway.toml                      ← Railway build/start config
│   ├── requirements.txt                  ← Python deps
│   ├── app/
│   │   ├── main.py                       ← router registration (44 routes)
│   │   ├── config.py                     ← pydantic Settings, loads .env
│   │   ├── dependencies.py               ← get_current_user, require_admin
│   │   ├── routers/
│   │   │   ├── contacts.py               ← timeline, brief, send-email, compose, status
│   │   │   ├── deals.py                  ← history, stale, suggestions, health, optimize
│   │   │   ├── auth.py                   ← /me, /auth/verify, /invite
│   │   │   ├── mcp_server.py             ← JSON-RPC MCP (4 tools)
│   │   │   ├── slack_interactions.py     ← HITL approve/dismiss
│   │   │   └── events.py                 ← SSE stream
│   │   ├── services/
│   │   │   ├── gmail_client.py           ← send_message()
│   │   │   └── slack_client.py           ← post_hitl_block()
│   │   └── workers/
│   │       ├── followup_sequences.py     ← HITL beat task (9am UTC)
│   │       └── deal_health_worker.py     ← health scoring + deal_alert events
│   └── migrations/
│       └── init_docker.sql               ← full schema, idempotent, safe to re-run
├── apps/web/
│   ├── railway.toml                      ← Railway build/start config
│   ├── Dockerfile                        ← pnpm, standalone output
│   └── src/
│       ├── app/(app)/
│       │   ├── contacts/page.tsx         ← bulk actions, timeline, brief, send-email
│       │   ├── reports/page.tsx          ← revenue forecast chart
│       │   └── settings/page.tsx         ← invite card, role gating
│       ├── app/onboarding/page.tsx       ← 4-step onboarding wizard
│       ├── hooks/useRole.ts              ← GET /me → isAdmin
│       └── lib/
│           ├── api-client.ts             ← all 44 API calls + demo stubs
│           └── demo-data.ts              ← rich mock data (954 lines)
```
