---
type: process
status: verified
consumes: [Connector, Gmail messages, Slack conversations]
produces: [Message, Contact, Task, ClarityScore, ActivityEvent]
---

# ingest

A connected inbox or workspace is walked and every human message is turned into a deduplicated Message row, with relevant ones enriched off the critical path.

## Input → Movement → Output

A Celery task loads the Connector, pages the provider (Gmail `category:primary OR in:sent`, or Slack DMs+channels), and dedupes each candidate against `messages` on (workspace_id, external_id). Automated senders are dropped, then a concurrent Claude Haiku pre-filter labels each surviving human message relevant or not; relevant ones are stored in full and enqueued for enrichment, irrelevant ones stored metadata-only (`graph_only=True`, no body) to preserve weak-tie graph edges. A follow-up `enrich_message` task extracts Tasks, scores clarity, and folds sentiment into the contact.

## Why this shape

Ingestion is a Celery worker, not inline in the sync endpoint, because a full mailbox walk is unbounded (paged, capped at `INGEST_MAX_PAGES`, `workers/ingest.py:259`) and each message costs an LLM round-trip — doing it in-request would time out the HTTP call. Enrichment is a *second* enqueued task (`ingest.py:485-490`) so a Claude failure on one message can't fail the whole ingest. Metadata-only storage exists because letting the relevance LLM decide what *exists* in the DB deleted exactly the weak ties a warm-intro graph is made of (`ingest.py:401-409`).

## Steps

1. Load connector, bounded pagination of stubs — `workers/ingest.py:278-316`.
2. Dedupe + parse headers + drop automated senders — `ingest.py:318-361` (`_is_automated_sender` :70).
3. Concurrent Haiku relevance pre-filter via `asyncio.gather` — `ingest.py:391-399`.
4. Insert every human message (relevant=full body, else graph_only); auto-create lead Contacts for relevant *inbound* only — `ingest.py:410-475` (`_link_contact` :99-153).
5. Bump `connector.last_sync` + `message_count`, enqueue per-message enrichment — `ingest.py:477-490`.
6. `enrich_message`: extract_tasks + analyze_sentiment + score_clarity, mark processed — `ingest.py:511-598`.
7. Slack path mirrors this — `workers/slack_ingest.py:70-238`; Slack auth errors persist an ActivityEvent and do NOT bump last_sync — `slack_ingest.py:99-111`.

## Trigger

On-demand via `POST /connectors/{gmail,slack}/sync` (`gmail.py:236`, `slack.py:185`) and provider push webhooks (`gmail.py:420` Pub/Sub, `slack.py:256` Events API). **NO celery beat entry — never scheduled.**

## If you change this

- **Hits:** `services/gmail_client.py` / `services/slack_client.py` (token decrypt + refresh + list/get); `services/extraction.py`, `services/clarity.py`, `services/sentiment.py`; Message/Contact/Task/ClarityScore models; `_link_contact` shared by slack_ingest + backfill/reprocess (`ingest.py:156`, `:616`).
- **Does not hit:** discovery, outreach, transcribe.

## Surfaces

| Surface | Role |
|---|---|
| `/connectors/*/sync` + provider webhooks | trigger the sync task |
| Celery worker | runs the walk + enrich |
| enrich-score, deal-health | downstream readers of Message rows (graph_only excluded) |

## See

- Objects: [[Message]], [[Contact]], [[Task]], [[ClarityScore]], [[Connector]]
- Source: `apps/api/app/workers/ingest.py`, `apps/api/app/workers/slack_ingest.py`
