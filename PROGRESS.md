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

## Current Phase
Phase 4 — Sales Agent Intelligence + PM Feature Polish

## Next Task
Phase 4 complete. All agent intelligence + PM feature polish tasks done.

## Blockers
- Supabase credentials not set in this environment (# TODO: add real credentials in .env.local) — code reads from env vars correctly but no live DB available for integration testing
- Anthropic API key not set — Claude-based services (extraction, clarity, sentiment, email composer) require real key for integration testing; unit tests are fully mocked
