# NovaCRM System Map

A walkable graph of the FastAPI backend (`apps/api`): the nouns (models/tables), the verbs (worker/router movements), and what a change hits. The **code is the source of truth** — every card cites `path:line`; this map never becomes a second spec. Built on ICM.

## Where I am / where to go

| I need to… | Go to |
|---|---|
| understand one model/table | `objects/<cluster>/<Name>.md` |
| see all nouns at a glance | `objects/_index.md` |
| understand a movement (auth, send, ingest…) | `processes/<verb>.md` |
| know what a change hits | `effects/CONTEXT.md` |
| the rules of this map | `CONTEXT.md`, `_meta/schema.md` |

## Noun clusters

| Cluster | Nouns |
|---|---|
| `crm-core` | Contact, Deal, Task, Project, Commitment, ContactNote, DealNote, ActivityEvent |
| `comms` | Message, CallSummary, Connector, WebhookLog, EngagementEvent |
| `lead-engine` | Lead, LeadSegment, LeadSegmentMember, DiscoveryRun, Campaign |
| `sequences` | Sequence, SequenceStep, SequenceEnrollment |
| `intelligence` | ClarityScore, KpiSnapshot, Agent, ~~DealHealthHistory~~, ~~MetricTemplate~~ |
| `tenancy` | Workspace, User |

## Verbs

`auth` · `ingest` · `enrich-score` · `discover` · `outreach-send` · `transcribe` — see `processes/`.

## Name collisions & traps (state once, here)

- **Lead vs Contact** — Lead = raw pre-CRM prospect (`leads`); Contact = human-curated CRM record (`contacts`). `promote_lead` mints a Contact from a Lead.
- **Two "auth"** — connector OAuth (gmail/slack, `processes/auth.md`) vs *user* auth (Supabase JWT, `services/auth.py`). Different concerns, shared filename.
- **`workspace_id`** — the tenancy backbone; ~25 tables carry it. Isolation is enforced at `get_workspace_id` (`dependencies.py:122-131`), not per-model.
- **EngagementEvent vs ActivityEvent** — EngagementEvent = machine scoring signal (feeds lead score); ActivityEvent = human-readable audit feed.
- **ContactNote vs DealNote** — identical shape, different FK (contact_id vs deal_id).
- **`followup_sequences.py`** — misnamed: it is stale-deal Slack HITL over Deal/Contact/Message, touches NO sequence model. Rename candidate → `stale_deal_hitl.py` (the task is already `check_stale_deals_hitl`).
- **DealHealthHistory (GHOST)** — read endpoints exist but return `[]`; live score is `Deal.health_score`. **MetricTemplate (GHOST)** — fully unwired.

## Universes

`live` = in force, implement against · `leftover` = present, off main path · `ghost` = filed, not wired — do NOT implement against. Two ghosts today (above).

## Freshness

Verified 2026-09-15 against branch `feat/lead-engine-discovery` @ `60ecf76`. Re-verify Hits/Does-not-hit against source before relying on them.
