# Change-impact index — "if you are changing X, open these"

A catalog, not a copy of the waterfalls. When this index and a card disagree, the card (which cites source) wins — fix this file. First-order guidance only; follow the named cards for detail.

## If you are changing…

| Changing… | Open first | Because |
|---|---|---|
| **Workspace / workspace_id** | `objects/tenancy/Workspace.md`, `User.md` | tenancy backbone; ~25 tables + `get_workspace_id` (`dependencies.py:122-131`) |
| **auth / OAuth / tokens** | `processes/auth.md`, `objects/comms/Connector.md` | encrypted-token store + JWKS user-auth split; `services/crypto.py`, `oauth_state.py` |
| **Message schema / ingest** | `processes/ingest.md`, `objects/comms/Message.md` | graph_only + dedup + enrich fan-out; ripples to Contact/Task/ClarityScore |
| **Contact fields / scoring** | `processes/enrich-score.md`, `objects/crm-core/Contact.md` | 4 scorer workers + beat schedule (`celery_app.py`) |
| **Deal health / win-prob** | `objects/crm-core/Deal.md`, `intelligence/DealHealthHistory.md` | live score is `Deal.health_score`; the History table is a GHOST (writer missing) |
| **Lead / discovery** | `processes/discover.md`, `objects/lead-engine/Lead.md`, `DiscoveryRun.md` | active branch; provider stubs + empty market_context seam; fit ≠ lead.score |
| **Sequences / sending** | `processes/outreach-send.md` + all `objects/sequences/*` | beat ticker, HITL gate, guarded send boundary; enrollment uniqueness lives in DB |
| **Segments / audiences** | `objects/lead-engine/LeadSegment.md`, `LeadSegmentMember.md` | static-join vs dynamic-filter fork in `campaign_enroll.py` |
| **Calls / transcription** | `processes/transcribe.md`, `objects/comms/CallSummary.md` | isolated verb; Whisper + Claude; temp-file cleanup |
| **KPIs / metrics** | `objects/intelligence/KpiSnapshot.md` | free-form (domain, metric); MetricTemplate is a GHOST, not its schema |

## What points INTO this tree from outside (ask the owner — not visible from here)

These consumers break silently on a schema/route change; nothing in the tree references them:
- **`novacrm` MCP server** (`routers/mcp_server.py`) — exposes Contact/Deal/KPI to Claude Code MCP tools (`mcp__novacrm__*`).
- **PM/ops agents** (crm-self-healer, crm-pm, project-sync, kpi-anomaly) — hit `/projects`, `/tasks/by-external`, `/kpi`, `/deals/funnel`. The by-external upsert contract (Task/Project/Commitment `external_id`) is a hard external dependency.
- **Railway** (4 services) + **celery beat schedule** — cron cadences in `workers/celery_app.py` are the real trigger for enrich-score/outreach-send/discover fan-out.
- **Supabase auth (GoTrue)** — owns the JWT; `app_metadata.workspace_id` is the only trusted tenant-binding source.
