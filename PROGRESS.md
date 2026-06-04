# CRM-agentic Build Progress

## Completed

- [2026-05-26] Phase 1a: Monorepo restructure — apps/web, apps/api stub, packages/types
- [2026-05-26] Phase 1b: Unified 11-table Supabase schema with RLS and workspace isolation (001_unified_schema.sql)
- [2026-05-26] Phase 1c: Supabase client with full Database types + createServerClient/createBrowserClient; api-client.ts with full typed FastAPI methods
- [2026-05-26] Phase 1d: Login page, onboarding wizard (4-step), app layout auth guard, useWorkspace hook
- [2026-05-26] Phase 1e: All hooks (useContacts, useDeals, useAgents) wired to FastAPI; demo-data.ts for demo mode; Realtime removed (activity via FastAPI SSE instead)
- [2026-05-26] Phase 1f: Sidebar extended with PM routes (/inbox, /tasks, /projects, /connectors, /settings) + workspace mode gating
- [2026-05-26] Phase 1g: Seed script updated for multi-tenant schema (workspace + contacts/deals/agents/activity all scoped by workspace_id)
- [2026-05-26] Phase 2: Full FastAPI backend — main.py, config, database, all 11 models, all routers (auth, workspaces, contacts, deals, agents, messages, tasks, gmail, slack, search, calls, ai, events, slack_interactions, mcp_server), all services (auth, crypto, deal_health, embedding, extraction, gmail_client, sentiment, slack_client, supabase_rest), all workers (celery, ingest, deal_health, embed_contacts, enrich_contact, followup_sequences, pipeline, score_contact, slack_ingest, transcribe), requirements.txt, Dockerfile
- [2026-05-26] Phase 3: All PM UI pages built — /inbox, /tasks (kanban drag-and-drop), /connectors (Gmail/Slack OAuth), /projects (grouped by contact with clarity scores)
- [2026-05-26] Phase 4 (partial): Agent intelligence wired — triggerAgent, composeEmail, scoreContact, enrichContact, getMeetingBrief, getContactTimeline all connected to FastAPI endpoints
- [2026-05-26] Test suite: 288 tests, full coverage across all routers and services
- [2026-05-26] Demo mode: complete demo data layer (demo-data.ts, demo-mode.ts) with realistic stubs for all 5 sales pages; live at Railway
- [2026-05-26] Session: Created apps/api/app/services/clarity.py (Claude Sonnet clarity scoring); wired into ingest.py (scores each new message on ingestion); updated messages router to return enriched response with clarity_score + tasks via selectinload; added 5 clarity service tests + 2 message router tests; 288 tests pass
- [2026-05-27] Task 4a: POST /messages/{id}/score-clarity endpoint (on-demand Claude Sonnet scoring with upsert); GET /connectors/{id}/status endpoint (live sync stats); "Score Clarity" button in inbox MessageDrawer (updates list badge + drawer in real time); /tasks?contact=<id> filter (kanban filtered by contact, header shows context, Suspense wrapper for useSearchParams); scoreClarity() and getConnectorStatus() added to api-client with demo stubs
- [2026-05-28] Task 4b: POST /contacts/embed-all endpoint with contacts_total count; contacts page embed button wired to useJobPoller (real pending/started/success/failure states); demo semantic search returns filtered demoContacts with ranked similarity; 2 new tests for embed-all
- [2026-05-28] Task 4c: Dashboard deal health widget — top 3 stale deals (with "View all" footer); per-deal "View" links to /pipeline; 30s polling useEffect for live stale deal data via extracted pollToken/pollWorkspaceId state
- [2026-05-28] Task 4d: /settings page — workspace editor (name + mode via updateWorkspace()), invite form (inviteTeammate()), danger zone with ConfirmDialog type-to-confirm delete modal, profile section with email and sign-out
- [2026-05-28] Task 4e: Agents page polish — per-card Run button wired to triggerAgent() + per-card useJobPoller (pending/started/success/failure); last-run timestamp from live getAgentActivity() API call; success/failure badges (CheckCircle/XCircle) update after each job; 7-point recharts LineChart accuracy sparkline per card seeded from last 7 activity events; AgentDetailPanel Run button also uses useJobPoller; apiClient.getAgentActivity() added
- [2026-05-30] Phase 5a: GitHub Actions CI (.github/workflows/ci.yml — web tsc+build, api pytest); root-level conftest.py injects mock env vars so 295 tests pass without real credentials; fixed 22 broken tests: Gmail/Slack router state signing (build_state), Slack interactions autouse signature bypass fixture, tasks test missing external_id attribute
- [2026-05-30] Phase 5b: Contact detail page at /contacts/[id] — identity card, ML score, semantic tags, revenue, associated deals (with health bar), tasks (open/done split), timeline, meeting brief modal, email compose modal; ExternalLink icon in drawer header; contact_id filter added to GET /deals and GET /tasks routers; api-client updated (listDeals opts, getTasks opts.contactId)
- [2026-05-30] Phase 5c: Gmail push webhooks — POST /workspaces/{id}/connectors/gmail/subscribe (calls Gmail users.watch() to register Pub/Sub); POST /webhooks/gmail/push (receives Pub/Sub notifications, verifies GMAIL_WEBHOOK_SECRET, triggers Celery ingest); GMAIL_WEBHOOK_SECRET + GMAIL_PUBSUB_TOPIC added to config + .env.example; 9 new tests; total 304 tests pass

- [2026-06-01] Phase 6a: Deal detail page /pipeline/[id] — identity card (value, health, ML win prob, stage badge), metadata, associated contact card (ExternalLink to /contacts/[id]), notes, stage mover grid (all other stages), tasks (contact-scoped), activity timeline; pipeline board DealCard refactored to div with hover-visible ExternalLink icon; getDeal demo stub fixed; getDealTimeline added; FastAPI GET /deals/{id}/timeline endpoint; 2 new tests; 305 tests pass
- [2026-06-01] Phase 6b: Slack Events API push webhook — POST /webhooks/slack/events with HMAC-SHA256 signature verification (5-min replay-attack window), url_verification challenge, event_callback triggers Celery sync; 3 new tests; SLACK_SIGNING_SECRET added to .env.example; 308 tests pass
- [2026-06-01] Phase 6c: CSV export — GET /contacts/export + GET /deals/export (StreamingResponse text/csv); exportContactsCsv()/exportDealsCsv() in api-client (fetch Blob + browser download trigger); Export CSV buttons on contacts page and pipeline page; demo mode generates CSV from in-memory data; 4 new tests; 312 tests pass

- [2026-06-02] Phase 7a: Rate-limit headers — applied @limiter.limit() to all expensive/AI endpoints: auth/verify (30/min), compose (10/min), brief (10/min), enrich (5/min), score-clarity (10/min), embed-all (2/min), call upload (10/min)
- [2026-06-02] Phase 7b: Playwright E2E smoke tests — playwright.config.ts; e2e/smoke.spec.ts (8 tests: dashboard, contacts, pipeline, deal detail, agents, inbox, tasks, settings); CI e2e job builds demo-mode app + runs chromium, uploads failure artifacts
- [2026-06-02] Phase 7c: Supabase Realtime activity feed — replaced EventSource/SSE in dashboard with supabase.channel().on('postgres_changes', INSERT, activity_events); cleanup on unmount
- [2026-06-02] Phase 7d: Bulk deal operations — POST /workspaces/{id}/deals/bulk (move_stage|delete, max 100 IDs); DealCard checkboxes (hover visible, always visible in selection mode); fixed bottom toolbar with Move Stage dropdown + Delete; apiClient.bulkDealAction(); fixed time-dependent test; 318 tests pass

- [2026-06-03] Phase 8a: Contact CSV import — POST /workspaces/{id}/contacts/import (multipart CSV, upsert by email, return {imported, skipped, errors}); Import CSV button with result toast on /contacts page; importContactsCsv() in api-client with demo stub; 3 new tests
- [2026-06-03] Phase 8b: Notifications mark-all-read — localStorage-persisted last-read timestamp; unread count badge based on events newer than last-read; "Mark all read" button in panel header; unread events highlighted with indigo bg + dot
- [2026-06-03] Phase 8c: Deal win probability trend chart — GET /workspaces/{id}/deals/{id}/probability-trend (deterministic 30-day synthetic trend from deal age + ml_win_probability); AreaChart (recharts, indigo gradient) on deal detail page; getDealProbabilityTrend() in api-client with demo stub; 3 new tests
- [2026-06-03] Phase 8d: Reports avg cycle time KPI — 5th card "Avg Cycle Time" (days from createdAt to close) added to /reports KPI row; grid updated to 5 cols
- [2026-06-03] Bug fix: removed `from __future__ import annotations` + `uuid as uuid_mod` alias from 6 FastAPI routers (calls, slack, gmail, projects, mcp_server, slack_interactions, search) causing PydanticUndefinedAnnotation with Pydantic v2.9; 324 tests pass (up from 318)

- [2026-06-04] Phase 9a: Bulk contact delete — POST /workspaces/{id}/contacts/bulk (action: delete, max 100); Delete button in contacts BulkActionBar with ConfirmDialog; bulkContactAction() in api-client; 3 new tests
- [2026-06-04] Phase 9b: Saved filters — contacts filterStatus + filterScore persisted to localStorage; deal title/company search on pipeline board with localStorage persistence
- [2026-06-04] Phase 9c: Activity log page /activity — full workspace timeline with type filter chips and Load More infinite scroll; GET /workspaces/{id}/activity gains event_type + offset params; Activity added to sidebar; 15-event demo stub; 2 new tests
- [2026-06-04] Phase 9d: Deal forecast widget — GET /workspaces/{id}/deals/forecast groups active deals by expected_close month; recharts BarChart on dashboard; getDealForecast() in api-client with demo data; 2 new tests

## Current Phase
Phase 9 — Polish, UX, and new features (complete)

## Next Task
Phase 10 (suggested): (a) Search global command palette — Cmd+K modal searching across contacts, deals, and tasks at once; (b) Notification preferences — per-event-type opt-in/opt-out stored in localStorage, filter activity feed; (c) Deal notes editor — rich textarea with Markdown preview on deal detail page; (d) Contact merge — POST /workspaces/{id}/contacts/merge {primary_id, duplicate_id} merges tasks/messages/deals onto primary then deletes duplicate.

## Blockers
- No live Railway deployment URL configured in .env — Railway service URLs must be set via Railway dashboard env vars (FRONTEND_URL, NEXT_PUBLIC_FASTAPI_URL). No URL found in local .env files; this is expected for local dev.
- Local DATABASE_URL points to localhost:5433 (Docker Postgres) — /health returns `degraded` locally unless docker-compose is running. Supabase production credentials ARE present in apps/api/.env and apps/web/.env.local.
- GMAIL_PUBSUB_TOPIC and GMAIL_WEBHOOK_SECRET not set — Gmail push notifications won't work until these are configured via Railway/Render dashboard + Google Cloud Console.
- SLACK_SIGNING_SECRET not set — Slack Events API webhook will reject all requests in production until configured via Slack app settings.

## Resolved (previously listed as blockers)
- [2026-05-28] Supabase credentials confirmed present in apps/api/.env and apps/web/.env.local (SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_JWT_SECRET, NEXT_PUBLIC_SUPABASE_ANON_KEY all set)
- [2026-05-28] Anthropic API key confirmed present in both .env files
- [2026-05-28] Google OAuth credentials (GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET) confirmed present
- [2026-05-28] Slack OAuth credentials (SLACK_CLIENT_ID, SLACK_CLIENT_SECRET) confirmed present
- [2026-05-28] Smoke test: 295/295 tests pass; TypeScript clean; FastAPI starts and serves 52 routes; /health responds (degraded only due to local Docker DB not running)
