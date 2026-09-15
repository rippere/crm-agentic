# System-map findings — next-step debt

Surfaced while building the ICM system map (2026-09-15) and adjudicated by a two-sided
adversarial (a2a) review — Defense (intentional?) vs Prosecution (debt?), both grounded in
code + git history + `docs/betson/BUILD-SPEC-lead-engine.md`. Each finding is folded into its
own card (linked below); this file is the consolidated to-do so the next implementer has one
list. **None of this is in the NovaCRM task queue by choice** — it lives with the map.

## Priority order

| # | Finding | Verdict | Action | Effort | Card |
|---|---|---|---|---|---|
| 1 | `DealHealthHistory` never written | **Fix now** — shipped UI-first (Phase 13k, PROGRESS #30, 2026-07-13), live AreaChart + `momentum-check` AI endpoint have rendered empty in prod ~2 months. Migration `021` documents the intended writer; never built. | Add one `DealHealthHistory(...)` INSERT at the tail of `workers/deal_health_worker.py` (already loops deals + has score + session) + a daily celery-beat entry. Table/indexes/RLS/readers all exist. | S | `objects/intelligence/DealHealthHistory.md` |
| 3 | `followup_sequences.py` misnamed | Low — naming hazard (it's stale-deal Slack HITL, not sequence logic; real sequence engine is `campaign_enroll.py` + `sequence_sender.py`) | Rename → `stale_deal_hitl.py`; update the celery include + beat schedule ref (task is already `check_stale_deals_hitl`). | S | catalog collision list in `routing.md` |
| 2 | `MetricTemplate` dead model | Low — Phase-2 orphan (commit `672235b`), no documented purpose | Delete model + `__init__` entries in a dead-code sweep (drop table in a later migration), or leave a "reserved, unused" note. Defer unless sweeping. | S | `objects/intelligence/MetricTemplate.md` |
| 5 | `SequenceEnrollment` uniqueness not on model | Low — **parity only, no runtime risk**. The unique index IS in `migrations/023_outbound_engagement.sql:194` + `init_docker.sql:380`; house style is migration-as-source-of-truth. | Optional: mirror `__table_args__ = (UniqueConstraint("campaign_id","lead_id"),)` on the model for readability. | S | `objects/sequences/SequenceEnrollment.md` |
| 4 | `discover` partial (provider stubs, empty market_context) | **Not debt** — spec-verbatim (BUILD-SPEC lines 201/238/656); Yelp/Foursquare stubs + empty `market_context` are Inc-2/3 by design. | Do NOT build the stubs to "complete" it. One optional nit: disambiguate `partial`+`found==0` (no provider configured vs empty market) via `stats.reason="no_provider_configured"`. | S | `processes/discover.md` |

## Branch routing (important)

- **#4 only** belongs to `feat/lead-engine-discovery` — it *is* that branch's work.
- **#1, #2, #3, #5** are pre-existing debt in the **intelligence** and **sequences** clusters,
  untouched by that branch. Do **not** bundle them onto the lead-engine PR — separate small changes.

## Map bookkeeping

- Built on branch: `feat/lead-engine-discovery` @ `60ecf76`; map committed separately on its own branch off `master`.
- Committed entry file is `routing.md` (see `_meta/schema.md` — repo gitignores CLAUDE.md/AGENTS.md at every depth). `map/CLAUDE.md` + `map/AGENTS.md` are byte-identical local twins that do not commit; regenerate with `cp routing.md CLAUDE.md && cp routing.md AGENTS.md`.
- Walk test passed 2026-09-15 (entry + hub + one card ≈ 1.1k tokens; citations + See-links resolve).
- Re-verify any `Hits`/`Does-not-hit` against source before relying on it — the code is the source of truth, not these cards.
