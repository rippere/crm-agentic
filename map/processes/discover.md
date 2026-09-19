---
type: process
status: verified
consumes: [DiscoveryRun, places-provider venues, scoring rubric, Claude]
produces: [Lead (source='discovery'), DiscoveryRun.stats, ActivityEvent]
---

# discover

A locality is swept for candidate venues, each is LLM-scored against a weighted rubric, and the fits are upserted into the Leads table as a repeatable discovery run. **Newest verb — active `feat/lead-engine-discovery` branch.**

## Input → Movement → Output

`POST /discovery/runs` (or the chatbot `discover_market` action) goes through the single `dispatch_discovery_run` seam, which creates a `discovery_runs` row (status='queued'), commits it before dispatch, and enqueues `run_market_discovery`. The worker marks the run running, builds a deduped venue universe from the places-provider waterfall, scores every venue concurrently (bounded by `DISCOVERY_LLM_CONCURRENCY`), and upserts each fit into the existing `leads` table with the fit record in `custom_fields.discovery`. It finalizes status (succeeded/partial/failed) with stats and logs a `market_discovered` event; progress is polled via `GET /jobs/{job_id}`.

## Why this shape

It reuses the `leads` table + import_leads ON CONFLICT idiom rather than a new table so cross-run dedup rides the existing `idx_leads_ws_extid` partial unique index — a rediscovered venue is UPDATEd, never duplicated (`workers/discovery.py:227-268`). Fit lands in `custom_fields.discovery.fit_score`, deliberately NOT `lead.score`, because `score`/`score_detail` stay owned by the hourly engagement_score worker (R5, `discovery.py:100-118`). The run row is committed *before* the task is enqueued to close a dispatch-before-commit race (`services/discovery.py:82-102`). The 0-100 is computed in Python from seven 1-5 LLM subscores so scoring is deterministic (`services/discovery_rubric.py`).

## Steps

1. Dispatch seam: validate provider+rubric, create+commit run, enqueue task, audit event — `services/discovery.py:44-137`.
2. Worker loads run, marks running — `workers/discovery.py:189-210`.
3. Build deduped venue universe via places waterfall — `discovery.py:213-220`; `services/places.py::discover_venue_universe`.
4. Concurrent per-venue LLM scoring, semaphore-bounded, never-raising — `discovery.py:150-172` (`_score_all`); `services/discovery_research.py::score_venue`.
5. Per-row SAVEPOINT upsert into leads, `(xmax=0)` insert-vs-update detection — `discovery.py:229-268`.
6. Finalize status + stats + `market_discovered` event — `discovery.py:270-295`.

## Partial-wiring note

END-TO-END WIRED: `discovery.router` registered (`main.py:156`), seam enqueues a real task, worker persists Leads. Ghost/incomplete pieces: (a) only `GooglePlacesProvider` is concrete — `YelpProvider`/`FoursquareProvider` are key-gated STUBS behind the same interface (`services/places.py:14-16`); (b) `market_context` to `score_venue` ships EMPTY — the seam Inc-3's "psychology spine" fills (`discovery.py:223`). With no places key, the run completes `partial` with `found==0` rather than erroring. Both (a) and (b) are the BUILD-SPEC verbatim (lines 201, 238, 656) — Inc-2/3 follow-ups, **not** debt; do not build them to "complete" this. One real nit from a2a review: `partial`+`found==0` conflates "no provider configured" with "market genuinely empty", which a user reads as "no leads exist". Optional (S) fix: emit `stats.reason="no_provider_configured"` when no provider is `available()` and surface it in the poller. *[a2a review 2026-09-15]*

## Trigger

On-demand only — NO beat entry, NO `*_all` dispatcher. Enqueued by `dispatch_discovery_run` (`services/discovery.py:110`).

## If you change this

- **Hits:** `services/places.py`, `discovery_research.py`, `discovery_rubric.py`, `services/actions/discovery.py` (chatbot caller of the same seam); `models/discovery_run.py`, `models/lead.py` (`custom_fields.discovery` + `idx_leads_ws_extid`); `routers/agents.py` `GET /jobs/{id}`; engagement_score reads the leads it writes.
- **Does not hit:** auth, ingest, transcribe.

## Surfaces

| Surface | Role |
|---|---|
| `POST /discovery/runs` + chatbot `discover_market` | trigger a run |
| `GET /jobs/{job_id}` | report progress |
| Leads UI / discovery-run leads endpoint | consume produced leads (ordered by fit_score) |

## See

- Objects: [[DiscoveryRun]], [[Lead]]
- Source: `apps/api/app/workers/discovery.py`, `apps/api/app/services/discovery.py`
