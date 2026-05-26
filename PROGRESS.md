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

## Current Phase
Phase 4 — Sales Agent Intelligence + PM Feature Polish

## Next Task
Task 4a: Wire the remaining agent intelligence gaps:
- Implement POST /workspaces/{id}/messages/{msg_id}/score-clarity endpoint so users can trigger on-demand clarity scoring from the inbox (currently only runs during ingest)
- Add "Score Clarity" button to the inbox page MessageDrawer that calls the new endpoint
- Implement GET /workspaces/{id}/connectors/{id}/status endpoint with live sync stats
- Add tasks page filter by contact_id (the /tasks?contact=<id> link from /projects already works via URL param, but the tasks page doesn't yet filter on it)

Task 4b: FastAPI vector search integration
- The /contacts/search endpoint exists but pgvector embeddings need to be verified end-to-end
- Add POST /workspaces/{id}/contacts/embed-all Celery task to batch-embed all contacts on demand

## Blockers
- Supabase credentials not set in this environment (# TODO: add real credentials in .env.local) — code reads from env vars correctly but no live DB available for integration testing
- Anthropic API key not set — Claude-based services (extraction, clarity, sentiment, email composer) require real key for integration testing; unit tests are fully mocked
