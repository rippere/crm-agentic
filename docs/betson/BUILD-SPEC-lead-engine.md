# NovaCRM — Autonomous Lead Engine — Build Spec

**Status:** Ready-to-build architecture spec (reconciled from six independently-drafted sections + adversarial critique). **Owner:** lead architect. **Date:** 2026-09-10.
**Repo:** `crm-agentic` (`/mnt/external/Projects/crm-agentic`). **Extends:** the shipped Betson lead-gen module (migration `023_outbound_engagement.sql`, `docs/betson/BUILD-SPEC-leadgen.md`, `docs/betson/HANDOFF-betson-leadgen-2026-08-13.md`).

---

## §0. TL;DR + thesis

The Autonomous Lead Engine turns the shipped, human-driven outbound module (leads → segments → sequences → HITL approve → engagement scoring) into an **operator-supervised autonomous funnel**: an operator says *"find leads in Burlington, begin GTM"* in the in-app chatbot; a **hybrid discovery spine** (a structured places-API defines a deduped venue universe, then an LLM deep-research pass rubric-scores each venue and writes closing context) produces scored rows in the **existing `leads` table**; a per-stage **delegative-graph clamp** (`auto`/`ask`/`off`, fail-closed) governs every outward send; a single **versioned psychology playbook** governs drafting, reply-reading, and escalation from one source of truth; and SMS follow-up (TCPA-gated) extends the same event-sourced engagement stream. Nothing here invents a new architectural layer — every table follows the 023 house shape, every worker copies the `engagement_score.py`/`agents.py` shapes, every router copies the shipped 403-guard + ORM-first + Celery-trigger/poll conventions, and every migration is hand-numbered, mirrored into `init_docker.sql`, and hand-applied to prod (no runner).

This document reconciles six draft sections that collided on migration numbering, schema ownership, the discovery worker contract, sentiment representation, the LLM client, the authority resolver, and the `sequence_sender` edit order. **All collisions are resolved below (§0.1) and are binding — do not re-litigate them.** A separate context will scaffold **Increment 1 (Discovery)** cold from this document.

---

## §0.1. Resolved Collisions ledger

Every row is a **decided** resolution. The `Rn` column is the binding-resolution id; §2/§3 encode each one.

| # | Collision (from the adversarial critique) | Resolution | Rn |
|---|---|---|---|
| C1 | Four sections each author their own migration `024` (`024_discovery_engine.sql` / `024_escalation_controls.sql` / `024_sales_playbook.sql` / `024_lead_engine.sql`); on-disk max is `023`. | Schema is **split by build increment**, not one monolith. `024_lead_engine_discovery.sql` (Inc 1), `025_escalation_controls.sql` (Inc 2), `026_sales_playbook.sql` (Inc 3), SMS = **no migration** (event-sourced on 023). Numbers assigned once here (§3.3 ledger); each hand-applied to prod + mirrored into `init_docker.sql`. | R1 |
| C2 | The `datamodel` monolith (`024_lead_engine.sql`, 8 tables) re-defines discovery/escalation/psychology/SMS entities with incompatible columns; `discovery_run.py`/model registration authored twice. | **Reject the monolith as a single migration.** Each increment owns its own tables (per the R1 assignment). The monolith's *good ideas* (discovery-first `leads` reuse, `external_id` dedup, event-sourced SMS) are preserved; its `scoring_rubrics`, `psychology_playbooks`, `stage_controls`(as re-def), `sms_configs`, `sms_messages`, `action_proposals`, `leads.sms_consent_*` are **dropped** in favor of the increment-owned designs below. | R1, R4, R8 |
| C3 | Three incompatible discovery worker contracts: `run_market_discovery(ws, run_id)` (run-row-first) vs `run_discovery(ws, locality, criteria)` (fire-and-forget) vs `.delay(str(run_id))` (single arg). | **One contract:** `services/discovery.py::dispatch_discovery_run(workspace_id, request, db)` creates the `discovery_runs` row **then** enqueues `app.workers.discovery.run_market_discovery(workspace_id, run_id)`. Delete every `run_discovery(ws, locality, criteria)` variant. | R2 |
| C4 | Worker summary keys (`{venues_found, scored, leads_inserted, ...}`) don't match what the web poller renders (`{found, inserted, skipped}`). | **One summary schema**, shared by worker and web poller: `{run_id, workspace_id, locality, found, scored, inserted, skipped, status}`. | R2 |
| C5 | Rubric is both a Python config module (`discovery_rubric.DEFAULT_RUBRIC` + JSONB snapshot) and a DB table (`scoring_rubrics` + `discovery_runs.rubric_id` FK). | **Python config module only** for the first build: `discovery_rubric.DEFAULT_RUBRIC` + per-run JSONB snapshot into `discovery_runs.rubric`. Drop the `scoring_rubrics` table. | R4 |
| C6 | Discovery writes its fit score to `lead.score`, which the hourly `engagement_score` worker owns and overwrites; escalation then misreads a fit score as an engagement score. | **Fit score ≠ engagement score.** Discovery writes fit (0–100) to `lead.custom_fields.discovery.fit_score`, **never** `lead.score`. `lead.score` stays the engagement score owned by `engagement_score`. The escalation decider reads the engagement score and **ignores leads with zero engagement events**. | R5 |
| C7 | Qualitative venue fields live in three places: `custom_fields.discovery` (discovery), `score_detail` (psychology reads), `discovered_venues` columns (datamodel). | **Single path:** `lead.custom_fields.discovery.{fit_summary, why_it_works, best_outreach_angle, key_risks}`. Discovery writes; psychology distiller + drafting read this exact path. | R6 |
| C8 | Each LLM caller (`discovery_research`, `playbook_distill`, escalation decider) constructs its own `AsyncAnthropic`; two config sections add `ANTHROPIC_MODEL_SMART` with conflicting defaults (`"claude-sonnet-4-6"` vs `""`); a third id `ANTHROPIC_MODEL_RESEARCH` proliferates. | **Shared client (build-order 0):** `app/services/llm.py::get_async_anthropic_client()` cached singleton; all four callers import it. Model ids come from config only: `ANTHROPIC_MODEL_FAST` + `ANTHROPIC_MODEL_SMART`, each ONE non-empty env-sourced default. No model literal in logic. Drop `ANTHROPIC_MODEL_RESEARCH` / `PLAYBOOK_DISTILL_MODEL`. | R7 |
| C9 | Sentiment is both a TEXT enum (escalation) and a numeric −100..100 scale (datamodel). No section builds the classifier that writes it. | **TEXT vocab:** `positive \| neutral \| negative \| objection \| booking \| unsubscribe`, stored at `engagement_event.metadata.sentiment`. Reject the numeric scale. A **new owned** classifier (`app/workers/reply_sentiment.py`) writes it. | R8, R9 |
| C10 | Discovery appends a **write** tool `discover_market` into `mcp_server.TOOLS`; the action_bus wraps *every* `mcp_server.TOOLS` entry as a non-actuating `auto` read tool — silently exposing a write past the clamp. | **`mcp_server.TOOLS` stays READ-ONLY.** Register `discover_market` **only** through the action_bus with `actuating=True` + `authority_key`. Collapse `discover_market`/`trigger_discovery` into one tool. | R10 |
| C11 | Two authority systems: the per-stage clamp inside `sequence_sender._run_tick`, and the action_bus's independent permissive `resolve_authority` stub — a send can bypass the operator's cap. | **One shared resolver:** `app/services/authority.py::resolve_authority(workspace_id, stage, action, db)` reads the one `stage_controls` table. BOTH `sequence_sender._run_tick` AND `action_bus.dispatch` call it before any outward send. Delete the action_bus stub. | R11 |
| C12 | `DEFAULT_STAGE_MODE` ships `new`/`contacted` = `auto` → day-zero autonomous cold-email with no opt-in. | **Fail-closed:** `DEFAULT_STAGE_MODE = 'ask'` for **every** stage, plus a workspace-level `autonomy_enabled` master switch defaulting **FALSE**. Any `auto` requires explicit operator opt-in. | R12 |
| C13 | SMS and escalation both rewrite `sequence_sender._run_tick`/`_deliver`; psychology changes `_draft_body`'s signature — three uncoordinated edits to one function. | **Explicit edit order:** escalation lands the `_run_tick` control-flow rewrite first; SMS threads `enrollment` through `_deliver(db, workspace_id, step, lead, subject, body, enrollment)`; psychology makes drafting params keyword-optional: `_draft_body(step, lead, *, workspace_id=None, db=None)` with a DB-less fallback. | R13 |
| C14 | Two opt-out state models (event `type='unsubscribed'` vs `leads.sms_consent_*` column); TCPA quiet-hours unenforced; email-engagement-as-consent legality unverified. | SMS is **event-sourced only** on 023's `engagement_events` (channel `sms` + types already in the 023 CHECK); no new SMS tables, no `leads` consent columns. `_send_sms` enforces two hard preconditions (prior email engagement; lead-local 8am–9pm quiet-hours). Documented **LEGAL-REVIEW gate** on consent basis before any live SMS. | R14 |
| C15 | Operator control-plane (auto/ask/off UI, escalation queue, call-outcome form) has API but no web surface; discovery has no demo-mode seed. | **First build web scope:** chat trigger UI + discovery-run progress + discovered-lead listing in the existing `/leads` surface (demo-mode branches + seed). Stage-control UI, escalation queue, and post-call outcome form are **scoped out of Inc 1** and land with Inc 2. | R15 |
| C16 | Decision-3 targets a full autonomous loop, but chat is stateless and job→next-action continuation is browser-poller-only. | First build is **operator-present** (browser poller drives the chat follow-up). Server-side job→next-action continuation lands with Inc 2 (uses `discovery_runs` + escalation decision rows). Say so; don't pretend Inc 1 is the full loop. | R16 |

---

## §1. Architecture overview — how it EXTENDS the shipped leadgen module

The engine is a set of increments layered onto the shipped 023 module. It reuses, by name, these shipped conventions (grounded in `BUILD-SPEC-leadgen.md` / the shipped code):

- **Schema house shape (023):** `id UUID PK gen_random_uuid()`; `workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE` as the first column; TEXT + inline-CHECK enums; `JSONB NOT NULL DEFAULT '{}'`; `created_at`/`updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()` (updated_at `onupdate=func.now()` in ORM); workspace-first `idx_<table>_ws_*` indexes with `IF NOT EXISTS`; `ENABLE ROW LEVEL SECURITY` + `DROP POLICY IF EXISTS "<t>_policy"` + `CREATE POLICY "<t>_policy" USING (workspace_id = (SELECT workspace_id FROM users WHERE supabase_uid = auth.uid()))`. RLS is **ENABLE-only** (FORCE is the separate `013_force_rls.sql` lineage; see §6). Every migration is **hand-numbered, mirrored into `init_docker.sql` (tables + indexes only, no RLS/policy), and hand-applied to prod — there is no runner** (HANDOFF §4).
- **Leads reuse (023):** discovered venues become rows in the **existing `leads` table** (`source='discovery'`), never a new prospect store. Cross-run venue dedup rides the **existing partial unique index `idx_leads_ws_extid`** (`leads.external_id = '<provider>:<place_id>'`). `leads.custom_fields` JSONB (023) carries the durable discovery fit record; `leads.score`/`score_detail` stay owned by `engagement_score`.
- **Provider-waterfall shape:** `services/places.py` mirrors `services/enrichment.py` (`Protocol` + `available()` + key-gated + never-raise + `default_providers()`), with the *deliberate semantic difference* documented in the module docstring (enrichment fills missing fields first-provider-wins; discovery **unions + dedupes** venues into a complete universe).
- **Worker house shape (`engagement_score.py`):** sync `@celery_app.task(name="...", bind=True)` → `asyncio.run(_async(...))`; own `_get_async_session()` reusing `PGBOUNCER_CONNECT_ARGS`; primitive `str` args cast to `uuid.UUID` inside; writes rows + one `ActivityEvent`; returns a small JSON-serializable summary dict. On-demand workers (discovery, distill) have **no `*_all` dispatcher and no `beat_schedule` entry**.
- **Dispatch/poll (`agents.py`):** router/service enqueues with `.delay(...)`, calls `_mark_job_dispatched(task.id, str(workspace_id))` (tenant-scoped Redis owner marker), returns `202 {status:'queued', job_id}`; progress polled via the **existing** `GET /jobs/{job_id}` — never a new poller. Web reuses `useJobPoller`.
- **Router conventions:** bare `router = APIRouter()` (tags at registration in `main.py`); every path `/workspaces/{workspace_id}/...`; first-line 403 guard `if current_user.workspace_id != workspace_id: raise HTTPException(403)`; `get_db` + `get_current_user`; inline Pydantic (`from_attributes`); literal-tuple validation → 422; `ActivityEvent` audit on writes; ORM-first + `supabase_rest.get_row` fallback before 404; **static sub-paths declared before `/{id}`**.
- **Upsert idiom (`import_leads.py`):** `pg_insert(Lead).values(...).on_conflict_do_update(index_elements=[...], set_={...})`.
- **HITL reuse (`outreach.py`):** `park`/`escalate` both leave the enrollment `status='waiting'`, so they surface on the **existing** `/outreach/pending`; approval already writes the `'approved'` engagement_event the new gate consumes.
- **Web 4-layer stack:** route → hook → `api-client` (with an `if (isDemoMode)` branch on every method) → `demo-data`; dark zinc/indigo theme; `useJobPoller` for long jobs.

**Grounding citations (load-bearing shipped facts — verify at scaffold time):** `leads` table + `custom_fields` JSONB + `idx_leads_ws_extid` + `source`/`stage` CHECKs are defined in `apps/api/migrations/023_outbound_engagement.sql`; `leads.stage CHECK IN ('new','contacted','engaged','qualified','converted','lost')` and `leads.source CHECK IN ('import','manual','web','api','referral','event')` (023); `LEAD_SOURCES` tuple at `apps/api/app/routers/leads.py:43` (verified: `("import","manual","web","api","referral","event")`); `engagement_events.channel CHECK IN ('email','sms')` and `type CHECK` already admits `delivered/bounced/replied/unsubscribed` (023); `_mark_job_dispatched(task_id, workspace_id)` + `GET /jobs/{id}` in `apps/api/app/routers/agents.py`; `sequence_sender._draft_body(step, lead)` and `_deliver(...)` + HITL gate in `apps/api/app/workers/sequence_sender.py`; on-disk migration max is `023` (verified `ls apps/api/migrations/`). **`ActivityEvent` field consistency:** `ActivityEvent.meta` is a **TEXT** column holding a JSON string — always `meta=json.dumps({...})` (matching `import_leads.py`/`agents.py`); every new section uses this form (the escalation/discovery drafts' bare-`ActivityEvent(...)` calls are corrected to pass `meta=json.dumps(...)` where they attach structured data).

---

## §2. Build increments (in order)

### Increment 1 — Discovery Engine (FIRST BUILD, fully specified)

The flagship net-new capability and the scaffold target. A chatbot prompt drives the hybrid spine → scored rows in `leads`. This increment ships **standalone**: it depends on nothing from Inc 2–4 except the shared LLM client (§3.1), which is built first.

#### 2.1.1 Data model — migration `024_lead_engine_discovery.sql`

One new table, `discovery_runs` (run bookkeeping for a long-running job). No other schema change beyond one `leads` CHECK enum value. Follows the 023 house shape verbatim.

```sql
-- ─── 024_lead_engine_discovery.sql ───────────────────────────────────────────
-- Autonomous Lead Engine, Increment 1 (Discovery). Adds discovery_runs and
-- widens leads.source to admit 'discovery'. Idempotent (IF NOT EXISTS + DROP ...
-- IF EXISTS). NOT executed automatically — apply by hand to Supabase prod. The
-- same DDL minus RLS is mirrored into init_docker.sql.

-- widen the shipped leads.source CHECK (023 names it leads_source_check implicitly)
ALTER TABLE leads DROP CONSTRAINT IF EXISTS leads_source_check;
ALTER TABLE leads ADD CONSTRAINT leads_source_check
  CHECK (source IN ('import','manual','web','api','referral','event','discovery'));

CREATE TABLE IF NOT EXISTS discovery_runs (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id  UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  locality      TEXT NOT NULL,                          -- "Burlington, VT"
  provider      TEXT,                                   -- places provider(s) used
  status        TEXT NOT NULL DEFAULT 'queued'
                  CHECK (status IN ('queued','running','succeeded','partial','failed')),
  params        JSONB NOT NULL DEFAULT '{}',            -- categories, radius_m, max_venues, requested provider
  rubric        JSONB NOT NULL DEFAULT '{}',            -- snapshot of DEFAULT_RUBRIC (or per-run override) used
  stats         JSONB NOT NULL DEFAULT '{}',            -- {found, scored, inserted, skipped, errors}
  job_id        TEXT,                                   -- Celery task id (mirrors agents.py marker)
  error         TEXT,
  started_at    TIMESTAMPTZ,
  completed_at  TIMESTAMPTZ,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_discovery_runs_ws_status  ON discovery_runs (workspace_id, status);
CREATE INDEX IF NOT EXISTS idx_discovery_runs_ws_created ON discovery_runs (workspace_id, created_at DESC);

ALTER TABLE discovery_runs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "discovery_runs_policy" ON discovery_runs;
CREATE POLICY "discovery_runs_policy" ON discovery_runs
  USING (workspace_id = (SELECT workspace_id FROM users WHERE supabase_uid = auth.uid()));
```

Note `locality` (not `market`) — the column name matches the shared worker summary key (R2/C4). `init_docker.sql` ownership: this increment owns the `discovery_runs` mirror and the inline-`CREATE TABLE leads` source-CHECK edit (see §3.3). No other section mirrors `discovery_runs`.

**`leads` mapping (discovery upsert):**

| lead column | discovery source |
|---|---|
| `source` | `'discovery'` (new enum value) |
| `external_id` | `'<provider>:<place_id>'` — dedup key via existing `idx_leads_ws_extid` |
| `company` | venue name |
| `name` / `email` / `phone` / `title` | best contact name / email / phone / role |
| `score` | **left at default (0)** — engagement score, owned by `engagement_score` (R5) |
| `score_detail` | **not written by discovery** (R5) |
| `stage` | `'new'` |
| `custom_fields.discovery` | the durable fit record (below) |

`custom_fields.discovery` (durable — survives the hourly engagement rescore that overwrites `lead.score`/`score_detail`):
```json
{ "run_id","provider","place_id","category","area","address","lat","lng","website",
  "fit_score","tier","rubric_scores":{criterion:1..5},"weights":{...},
  "fit_summary","why_it_works","best_outreach_angle","key_risks",
  "best_contact","contact_role","contact_email","contact_phone",
  "research_confidence","best_scouting_window","primary_source_url","contact_source_url" }
```
The **four qualitative fields** (`fit_summary`, `why_it_works`, `best_outreach_angle`, `key_risks`) are the single shared contract (R6) that the psychology distiller and drafting read. `GET /discovery/runs/{run_id}/leads` filters `leads WHERE custom_fields->'discovery'->>'run_id' = :run_id`.

#### 2.1.2 Load-bearing finding (drives the acceptance test)

The ground-truth sheet's **Overall Score is deterministic**: the weighted mean of the seven 1–5 subscores × 20 (= `100 / scale_max`). Verified by hand against the live sheet:
- Rí Rá `[T:5, S/P:5, G/D:5, BF:4.5, PF:4.5, YR:5, C:5]` → `5(.25)+5(.20)+5(.15)+4.5(.15)+4.5(.10)+5(.05)+5(.10) = 4.875 → ×20 = 97.5` == sheet F2 ✓
- ECHO `[4.5,5,4.5,5,4.5,5,5]` → `4.75 → ×20 = 95.0` == sheet F3 ✓

**Implication:** the LLM produces only the seven 1–5 subscores + qualitative context; the overall (0–100) and tier are computed **in Python** by the rubric module — making score correlation testable without depending on LLM determinism.

#### 2.1.3 Rubric-as-config — `app/services/discovery_rubric.py` (R4)

```python
DEFAULT_RUBRIC: dict = {
  "scale_max": 5,
  "criteria": [
    {"key":"traffic",               "label":"Traffic Potential",      "weight":0.25, "what_5_means":"...", "why_it_matters":"..."},
    {"key":"social_photo",          "label":"Social / Photo Behavior", "weight":0.20, "...":"..."},
    {"key":"group_dwell",           "label":"Group / Dwell Time",      "weight":0.15, "...":"..."},
    {"key":"brand_fit",             "label":"Brand Fit",               "weight":0.15, "...":"..."},
    {"key":"placement_feasibility", "label":"Placement Feasibility",   "weight":0.10, "...":"..."},
    {"key":"year_round",            "label":"Year-Round Strength",     "weight":0.05, "...":"..."},
    {"key":"contactability",        "label":"Contactability",          "weight":0.10, "...":"..."},
  ],
  "tiers": [ {"tier":"A+","min":95},{"tier":"A","min":90},{"tier":"A-","min":85},{"tier":"B+","min":80},{"tier":"B","min":0} ],
}

def validate_rubric(rubric: dict) -> None:
    """Raise ValueError if weights don't sum to ~1.0 (abs tol 1e-3), keys not unique, or scale_max<=0."""

def compute_overall(subscores: dict[str, float], rubric: dict = DEFAULT_RUBRIC) -> float:
    """sum(subscores[k]*weight_k) * (100/scale_max); round(…, 1). Missing subscore => 0 for that criterion."""

def tier_for(overall: float, rubric: dict = DEFAULT_RUBRIC) -> str:
    """First tier (descending min) whose min <= overall."""
```
Weights are config data. `DEFAULT_RUBRIC` is the seed; a run may override via `DiscoveryRunRequest.rubric` (validated → 422), and the effective rubric is snapshotted into `discovery_runs.rubric` for reproducibility. Weights (Traffic 0.25, Social/Photo 0.20, Group/Dwell 0.15, Brand Fit 0.15, Placement 0.10, Year-Round 0.05, Contactability 0.10) sum to 1.00 and mirror the sheet's Scoring Guide; tiers `A+ ≥95, A ≥90, A- ≥85, B+ ≥80, B ≥0`. **No `scoring_rubrics` DB table** in this build.

#### 2.1.4 Places provider abstraction — `app/services/places.py` (R3)

Mirrors `enrichment.py`'s `Protocol` + key-gated waterfall + `default_providers()` + never-raise contract. Semantics differ (documented in the module docstring): discovery **unions venues across providers and dedupes** to form the complete universe.

```python
@dataclass(frozen=True)
class PlaceResult:
    provider: str; place_id: str; name: str
    category: str | None; address: str | None; locality: str | None
    lat: float | None; lng: float | None
    phone: str | None; website: str | None; source_url: str | None

@runtime_checkable
class PlacesProvider(Protocol):
    name: str
    def available(self) -> bool: ...
    async def search(self, *, market: str, categories: list[str] | None,
                     radius_m: int | None, max_results: int) -> list[PlaceResult]: ...
        # Must never raise: on error log and return [].

class GooglePlacesProvider:  # name="google_places"; available() -> bool(settings.GOOGLE_PLACES_API_KEY)
    ...                      # httpx.AsyncClient(timeout=...), Places Text Search + Place Details
class YelpProvider: ...      # gated on settings.YELP_API_KEY (keyed stub)
class FoursquareProvider: ...# gated on settings.FOURSQUARE_API_KEY (keyed stub)

def default_providers() -> list[PlacesProvider]: ...   # ordered; available ones union
def _dedupe_key(p: PlaceResult) -> str: ...            # normalized (name + locality) lowercased, or f"{provider}:{place_id}"

async def discover_venue_universe(*, market: str, categories: list[str] | None = None,
    radius_m: int | None = None, max_venues: int = 60,
    providers: list[PlacesProvider] | None = None) -> list[PlaceResult]:
    """Union across available providers, dedupe by _dedupe_key, cap at max_venues. Never raises."""
```
Key-gate degradation: no provider configured → returns `[]`, run completes `partial` with `stats.found = 0` (not a 500). **Which places API is primary (Google/Yelp/Foursquare) is an OPEN QUESTION (§6)** — the abstraction lets it slot later; ship `GooglePlacesProvider` behind the interface as the first concrete rung.

#### 2.1.5 Deep-research / scoring service — `app/services/discovery_research.py` (R3, R7)

The LLM pass. Guarded, patchable async boundary that **never raises** (mirrors `sequence_sender._draft_body`). **Imports the shared client** `get_async_anthropic_client()` from `app/services/llm.py` (R7) — no inline `AsyncAnthropic()`. Model id from `settings.ANTHROPIC_MODEL_SMART` (config only, never a literal).

```python
from app.services.llm import get_async_anthropic_client
from app.config import settings

@dataclass
class VenueScore:
    subscores: dict[str, float]          # criterion.key -> 1..5
    overall: float                       # from compute_overall (0..100)
    tier: str                            # from tier_for
    fit_summary: str | None; why_it_works: str | None
    best_outreach_angle: str | None; key_risks: str | None
    best_contact: str | None; contact_role: str | None
    contact_email: str | None; contact_phone: str | None
    research_confidence: str             # "High" | "Medium" | "Low"
    best_scouting_window: str | None
    raw: dict

async def _research_venue(place: PlaceResult, rubric: dict, market_context: str, *, client=None) -> dict:
    """One messages.create(model=settings.ANTHROPIC_MODEL_SMART, ...) asking for STRICT JSON:
       {subscores:{key:1..5 for each rubric criterion}, fit_summary, why_it_works,
        best_outreach_angle, key_risks, best_contact, contact_role, contact_email,
        contact_phone, research_confidence, best_scouting_window}. Parse; on any failure
        return {}. Never raises. Patchable seam for tests (inject client / monkeypatch)."""

async def score_venue(place: PlaceResult, *, rubric: dict = DEFAULT_RUBRIC,
                      market_context: str = "", client=None) -> VenueScore:
    """client defaults to get_async_anthropic_client(); when settings.ANTHROPIC_API_KEY is
       empty the guarded call short-circuits. Call _research_venue; clamp subscores to
       [1,scale_max]; overall=compute_overall; tier=tier_for. On empty LLM result:
       subscores={}, overall=0, tier='B', research_confidence='Low', hard-facts only."""
```
Note the qualitative keys are exactly the R6 four (`fit_summary`, `why_it_works`, `best_outreach_angle`, `key_risks`) plus contact fields — no `potential_placement` divergence. `market_context` is the seam the psychology spine (Inc 3) later fills; ships empty so discovery stands alone.

#### 2.1.6 Worker — `app/workers/discovery.py` (R2)

House shape copied from `engagement_score.py`. On-demand (no `*_all`, no beat entry).

```python
async def _run_discovery(workspace_id: str, run_id: str) -> dict:
    # 1. load discovery_runs row (scoped by ws); status='running', started_at=now; commit.
    # 2. universe = await discover_venue_universe(market=run.locality, **run.params)
    # 3. sem = asyncio.Semaphore(settings.DISCOVERY_LLM_CONCURRENCY); score all venues concurrently
    #    via score_venue(...) (each guarded; a failure counts an error, never aborts the run).
    # 4. per scored venue: build lead kwargs (mapping table) writing fit into
    #    custom_fields.discovery.fit_score (NOT lead.score), then
    #    pg_insert(Lead).values(...).on_conflict_do_update(
    #        index_elements=[Lead.workspace_id, Lead.external_id],
    #        set_={custom_fields, name, email, phone, title, company, updated_at})
    #    — reuses the import_leads.py upsert idiom; ON CONFLICT refreshes an existing discovered lead.
    # 5. accumulate stats; ActivityEvent(type="market_discovered", agent_name="Discovery Engine",
    #    description=f"Discovered {found} venues in {locality}: {inserted} new", severity="info",
    #    meta=json.dumps(summary)).
    # 6. status='succeeded' (errors==0) else 'partial'; unhandled fatal -> 'failed' + error;
    #    completed_at=now; write stats; commit. Return the summary dict (below).

@celery_app.task(name="app.workers.discovery.run_market_discovery", bind=True)
def run_market_discovery(self, workspace_id: str, run_id: str) -> dict:
    return asyncio.run(_run_discovery(workspace_id, run_id))
```

**Worker summary dict (shared with the web poller — the ONE schema, R2/C4):**
```python
{ "run_id": str, "workspace_id": str, "locality": str,
  "found": int, "scored": int, "inserted": int, "skipped": int, "status": str }
```
The web poller renders exactly these keys: *"Found {found} venues, {inserted} loaded to Leads."*

#### 2.1.7 Dispatch seam — `app/services/discovery.py` (R2)

The ONE dispatch path, called by both the router and the chatbot action.

```python
# app/services/discovery.py
async def dispatch_discovery_run(workspace_id: uuid.UUID, request: "DiscoveryRunRequest",
                                 db: AsyncSession) -> DiscoveryRun:
    """SHARED SEAM used by BOTH POST /discovery/runs AND the action_bus discover_market action.
       1. Validate (provider vs PLACES_PROVIDERS, rubric via validate_rubric -> ValueError|422).
       2. snapshot effective rubric; create discovery_runs row (status='queued'); flush for id;
          COMMIT the run row BEFORE dispatch (avoids the dispatch-before-commit race — a fast
          worker must find the row).
       3. guarded dispatch:
            try: from app.workers.discovery import run_market_discovery
                  from app.routers.agents import _mark_job_dispatched
                  t = run_market_discovery.delay(str(workspace_id), str(run.id))
                  _mark_job_dispatched(t.id, str(workspace_id)); run.job_id = t.id
            except ImportError: run.job_id = 'pending'
       4. ActivityEvent(type='discovery_run_started', agent_name='System',
                        meta=json.dumps({...})); commit; return run."""
```
`DiscoveryRunRequest`/`DiscoveryRunResponse` Pydantic schemas live in the router module (§2.1.8) and are imported here (or co-located in `services/discovery.py` and imported by the router — either is acceptable; keep one definition).

#### 2.1.8 API surface — `app/routers/discovery.py`

Bare `router = APIRouter()`; standard conventions; static `/runs` before `/runs/{run_id}`.

```python
DISCOVERY_STATUSES = ("queued","running","succeeded","partial","failed")
PLACES_PROVIDERS   = ("google_places","yelp","foursquare")

class DiscoveryRunRequest(BaseModel):
    locality: str
    categories: list[str] | None = None
    radius_m: int | None = None
    provider: str | None = None          # validated vs PLACES_PROVIDERS -> 422
    rubric: dict | None = None           # validate_rubric() -> 422 on bad weights
    max_venues: int = 60

class DiscoveryRunResponse(BaseModel):   # model_config = {"from_attributes": True}
    id: uuid.UUID; workspace_id: uuid.UUID; locality: str; provider: str | None
    status: str; params: dict; rubric: dict; stats: dict; job_id: str | None
    error: str | None; started_at: datetime | None; completed_at: datetime | None
    created_at: datetime | None; updated_at: datetime | None

@router.post("/workspaces/{workspace_id}/discovery/runs", status_code=202, response_model=DiscoveryRunResponse)  # calls dispatch_discovery_run
@router.get ("/workspaces/{workspace_id}/discovery/runs", response_model=list[DiscoveryRunResponse])              # paginated limit/offset
@router.get ("/workspaces/{workspace_id}/discovery/runs/{run_id}", response_model=DiscoveryRunResponse)           # ORM-first + get_row fallback -> 404
@router.get ("/workspaces/{workspace_id}/discovery/runs/{run_id}/leads", response_model=list[LeadResponse])       # WHERE custom_fields->'discovery'->>'run_id' = run_id
```
Progress polled via the existing `GET /jobs/{job_id}` using the returned `job_id`; no new poller.

#### 2.1.9 Chatbot trigger + action bus (Inc 1 slice) — reused-read-tools + ONE actuating action (R10, R11)

Inc 1 ships the **minimal** chatbot path so the operator can drive discovery by prompt. The shared LLM client (§3.1) and the action-bus scaffold land here; the full escalation clamp lands in Inc 2.

- **`app/routers/mcp_server.py` — NO write tool added.** `TOOLS`/`TOOL_HANDLERS` stay **read-only** (R10). Do **not** append `discover_market`.
- **`app/services/action_bus.py` (NEW):** registry + `dispatch`. At import, wraps each read tool from `mcp_server.TOOLS`/`TOOL_HANDLERS` as a **non-actuating** `ActionSpec` (`actuating=False`, `authority_key=None`). `ActionResult`/`ActionSpec` dataclasses per the draft. `dispatch(name, args, workspace_id, db, current_user, confirmed=False)` calls the **shared** `resolve_authority` (§3.2) for actuating specs; read tools resolve to `auto` without a stage. The independent permissive stub is **deleted** (R11).
- **`app/services/actions/discovery.py` (NEW):** the ONE actuating discovery action. Its handler calls `dispatch_discovery_run(workspace_id, DiscoveryRunRequest(**args), db)` (R2/R10) — no phantom `run_discovery`. Registered with `actuating=True`, `authority_key="discovery"`. In Inc 1, discovery is inbound R&D with no outward comms; the shared resolver treats a stage-less actuating action per its default (which, given R12's fail-closed default and the master switch off, yields `ask`/`off` unless the operator has enabled autonomy — the chat surfaces a Confirm button via `needs_confirmation`). Single arg schema: `{locality, categories?, max_venues?}` (collapses `discover_market`/`trigger_discovery`, R10/C10).
- **`app/services/actions/__init__.py` (NEW):** imports each action module and calls `action_bus.register(SPEC)` so the registry self-populates on import.
- **`app/routers/ai.py` (EDIT):** extract `_build_workspace_snapshot(workspace_id, db)` from `answer_crm_query` (no behavior change to `/ai/query`); add `run_agent_turn(...)` bounded tool-use loop (`MAX_TOOL_ITERS=6`, `AsyncAnthropic` + `MODEL_SMART` via the shared client) + `POST /workspaces/{workspace_id}/ai/chat` + its Pydantic schemas (`ChatMessage`/`ChatRequest`/`ChatActionOut`/`ChatResponse`). `workspace_id` comes from the URL + 403 guard and is passed into every `dispatch(...)`; the model never supplies it. Recursion guard: `ask_crm` calls the non-agentic `answer_crm_query`; `run_agent_turn`/`POST /ai/chat` is not registered as a tool.

#### 2.1.10 Web (Inc 1 scope, R15)

Discovery-first web ships the chat trigger + progress + discovered-lead listing; the operator control-plane UI is Inc 2.

- **`apps/web/src/lib/api-client.ts` (EDIT):** `aiChat(workspaceId, messages, confirm, token)` with an `if (isDemoMode)` canned-response branch → `POST /workspaces/{workspaceId}/ai/chat`.
- **`apps/web/src/hooks/useChat.ts` (NEW):** `"use client"`; demo branch; `sendMessage(text)` appends the user msg, calls `aiChat`, appends the assistant answer, and if a `job_id` returns starts a `useJobPoller` on `GET /jobs/{job_id}`; a `useEffect` on the poller state appends the completion line rendered from the R2 summary keys (*"Found {found} venues, {inserted} loaded to Leads"*) and triggers a `/leads` refetch, then `reset()`. Exposes `needs_confirmation` so the panel can render a Confirm button that re-calls `sendMessage` with `confirm=<action>`.
- **`apps/web/src/components/chat/ChatPanel.tsx` (NEW)** + **`apps/web/src/app/(app)/assistant/page.tsx` (NEW):** dark theme, `Loader2 animate-spin` for the running-job state, `role="alert"` errors.
- **`apps/web/src/lib/demo-data.ts` (EDIT):** `demoChatMessages` seed **and** a `demoDiscoveryRun` + ~16 photobooth-flavored `demoLeads` with `source:'discovery'` + `custom_fields.discovery` so `/leads` renders discovered leads under `NEXT_PUBLIC_DEMO_MODE` with no backend (R15 demo-mode branch + seed).
- **`apps/web/src/components/layout/Sidebar.tsx` (EDIT):** add an "Assistant" `NavItem` (e.g. `Sparkles`), shown in all modes (no `hideModes`).
- **`/leads` surface:** the existing leads table/detail already renders `source` and `custom_fields`; add a `discovery` source badge + a fit-score/why-it-works detail block reading `custom_fields.discovery`. No new leads page.

#### 2.1.11 Config additions (Inc 1)

`apps/api/app/config.py` (owned here for Inc 1; §3.4 is the full ledger): `GOOGLE_PLACES_API_KEY: str = ""`, `YELP_API_KEY: str = ""`, `FOURSQUARE_API_KEY: str = ""`, `DISCOVERY_LLM_CONCURRENCY: int = 5`, `DISCOVERY_MAX_VENUES: int = 60`. The shared model-id fields `ANTHROPIC_MODEL_FAST`/`ANTHROPIC_MODEL_SMART` are added with the shared LLM client (§3.1), also in this increment.

#### 2.1.12 Files to create (Inc 1, exact paths)

- `apps/api/migrations/024_lead_engine_discovery.sql`
- `apps/api/app/models/discovery_run.py` → `DiscoveryRun` (the ONE definition, R1/C2)
- `apps/api/app/services/llm.py` (build-order 0 — §3.1)
- `apps/api/app/services/discovery.py` (dispatch seam)
- `apps/api/app/services/places.py`
- `apps/api/app/services/discovery_rubric.py`
- `apps/api/app/services/discovery_research.py`
- `apps/api/app/services/action_bus.py`
- `apps/api/app/services/actions/__init__.py`
- `apps/api/app/services/actions/discovery.py`
- `apps/api/app/workers/discovery.py`
- `apps/api/app/routers/discovery.py`
- `apps/api/tests/test_discovery_rubric.py` (no-LLM, deterministic — the reproducibility proof)
- `apps/api/tests/test_discovery_places.py` (waterfall union/dedupe/key-gate, mocked httpx)
- `apps/api/tests/test_discovery_worker.py` (mocked provider + monkeypatched `_research_venue`; asserts upsert + run row + summary keys)
- `apps/api/tests/test_action_bus.py` (registry reuse; unknown action; resolver wiring)
- `apps/api/tests/test_ai_chat.py` (tool loop; discover action → `dispatch_discovery_run`; 403; needs_confirmation)
- `apps/api/tests/fixtures/burlington_ground_truth.json` (16 venues + subscores + tier + contact, transcribed from the sheet)
- `apps/api/tests/fixtures/burlington_places_fixture.json` (recorded places-API response for offline CI — §2.1.13)
- `apps/api/scripts/burlington_acceptance.py` (the end-to-end diff harness)
- `apps/web/src/hooks/useChat.ts`, `apps/web/src/components/chat/ChatPanel.tsx`, `apps/web/src/app/(app)/assistant/page.tsx`

**Shared-file edits (Inc 1):** `apps/api/app/models/__init__.py` (+`DiscoveryRun`), `apps/api/migrations/init_docker.sql` (discovery_runs mirror + leads source-CHECK), `apps/api/app/routers/leads.py` (+`"discovery"` to `LEAD_SOURCES:43`), `apps/api/app/workers/celery_app.py` (+`"app.workers.discovery"` to `include=[]`, no beat entry), `apps/api/app/main.py` (+`discovery` router), `apps/api/app/routers/ai.py` (snapshot extract + chat loop), `apps/api/app/config.py` (§2.1.11 + §3.1 fields), `apps/web/src/lib/api-client.ts`, `apps/web/src/lib/demo-data.ts`, `apps/web/src/components/layout/Sidebar.tsx`. Ownership per §4.

#### 2.1.13 Verification (Inc 1) — observed, not asserted

| # | Gate | Command / observation | Pass bar |
|---|---|---|---|
| V1 | Migration applies clean + idempotent | `psql "$SCRATCH_DB" -f 024_lead_engine_discovery.sql` twice; then `\d discovery_runs` | exit 0 both runs; table + 2 indexes present |
| V2 | Widened source CHECK | `INSERT ... source='discovery'` succeeds; bogus value rejected | as stated |
| V3 | init_docker builds from empty | `psql "$SCRATCH_DB2" -f init_docker.sql`; `grep -c "CREATE TABLE" init_docker.sql` | +1 vs baseline; no RLS lines in the discovery banner |
| V4 | **Rubric reproducibility (keystone, no LLM)** | `pytest tests/test_discovery_rubric.py`; feed 16 ground-truth subscore vectors through `compute_overall` | each == sheet Overall ±0.1 (Rí Rá 97.5, ECHO 95, …); `tier_for` reproduces every tier |
| V5 | **Rubric weights match the sheet** | a test step asserts `DEFAULT_RUBRIC` weights == the sheet's Scoring Guide tab values before scoring | exact equality (blocks scoring if drifted) |
| V6 | Places coverage (offline) | run `discover_venue_universe` against `burlington_places_fixture.json` | ≥13/16 ground-truth names appear (fuzzy), 0 dupes by `_dedupe_key` |
| V7 | Worker summary keys | `test_discovery_worker` asserts the returned dict has exactly `{run_id,workspace_id,locality,found,scored,inserted,skipped,status}` | exact key set (R2/C4) |
| V8 | Idempotency | re-run same locality | leads UPDATED not duplicated (`external_id` unique holds; `stats.inserted==0` on 2nd pass); a 2nd `discovery_runs` row exists |
| V9 | Degradation | unset Places key → `partial`, `found=0`, no 500; unset `ANTHROPIC_API_KEY` → venues upserted with hard facts + `research_confidence:"Low"` | as stated |
| V10 | Chatbot trigger | `test_ai_chat`: stub model emits tool_use for the discovery action → asserts `dispatch_discovery_run` invoked, non-empty `job_id`, no caller-supplied ws; cross-ws → 403; authority `ask`/master-off → `needs_confirmation=True`, no dispatch | as stated |
| V11 | Fit ≠ engagement | assert discovery writes `custom_fields.discovery.fit_score` and leaves `lead.score==0` | as stated (R5) |
| V12 | **Burlington acceptance (firm gate)** | §2.1.14 | coverage ≥12/16; Pearson r ≥0.6; tier agreement ≥0.7 |
| V13 | Adversarial | hand the acceptance harness to the **verifier** subagent to re-run and refute the numbers before any is reported true | verifier confirms |

#### 2.1.14 Burlington acceptance test (FIRM — the first build's acceptance bar)

A concrete, runnable gate. Diff against the ground-truth sheet `docs/betson/Burlington_Photo_Booth_Prospect_Master.xlsx` (16 venues, sheet "Master Prospects").

- **Fixture format (offline CI):** `burlington_places_fixture.json` is a recorded `discover_venue_universe` result — a JSON array of `PlaceResult` dicts (`provider, place_id, name, category, address, locality, lat, lng, phone, website, source_url`), captured once from a live `GooglePlacesProvider.search(market="Burlington, VT", categories=[hospitality, brewery, museum, music], max_venues=60)` run and committed. `burlington_ground_truth.json` is the 16-venue sheet transcription: `[{name, subscores:{7 keys 1..5}, overall, tier, contact_email}]`. **Transcription owner:** Inc 1 implementer (a checklist step; confirm the sheet has a contact-email column before relying on contact-accuracy).
- **Fuzzy-match function (pinned):** `normalized_token_set_ratio(a, b) >= 0.85`, where normalization = lowercase, strip punctuation, collapse whitespace, drop stopwords `{the, a, and, &, co, company, llc, inc, restaurant, bar, pub}`, then `rapidfuzz.fuzz.token_set_ratio / 100`. If `rapidfuzz` is not desired as a dependency, hand-roll token-set Jaccard over the normalized token sets with the same 0.85 threshold. State the chosen implementation in the harness header.
- **Pearson r:** hand-rolled in stdlib (no numpy/scipy dependency) over matched venues' produced `fit_score` vs sheet Overall.
- **Runnable harness** (`scripts/burlington_acceptance.py`): loads the fixture, runs `discover_venue_universe` (fixture-backed) → `score_venue` per venue (live `ANTHROPIC_API_KEY`, or a recorded LLM fixture for pure-offline CI) → `compute_overall`/`tier_for`, then diffs. Emits an inspectable table (venue, sheet score, produced score, sheet tier, produced tier, contact match) and the three metrics.
- **Firm pass bars (gate, not diagnostic):** venue coverage **≥ 12/16** matched (fuzzy ≥0.85 on name); **Pearson r ≥ 0.6** between produced fit-score and sheet Overall on matched venues; **tier agreement ≥ 0.7** (fraction whose produced tier equals the sheet tier). A run below any bar **fails** the increment. V5 (weights match the sheet) must pass before the run.
- **External spend gate (§6):** the live end-to-end run bills a Google Places API key and paid Anthropic calls — flagged as an external spend gate, same tier as SMS 10DLC. Offline CI uses the fixtures and does not bill.

---

### Increment 2 — Escalation graph + reply-sentiment

Replaces the binary `sequence_steps.requires_approval` gate with the two-layer control primitive (PROPOSE from signals, then CLAMP by the per-stage operator cap), builds the **missing reply-sentiment classifier** (R9), and lands the shared authority resolver (R11) and fail-closed defaults (R12). This is where the operator control-plane web UI lands (R15) and where server-side loop continuation begins (R16).

#### 2.2.1 Data model — migration `025_escalation_controls.sql` (R1)

Three tables: `stage_controls` (per-workspace × per-stage cap + thresholds, the name R11's resolver reads), `workspace_autonomy` (the workspace-level master switch, R12), and `escalation_decisions` (append-only audit + the future model-governed seam). All 023 house shape; RLS ENABLE-only; mirrored into `init_docker.sql` (no RLS) under banner `-- ─── ESCALATION CONTROLS (mirror of 025_escalation_controls.sql) ───`.

- **`stage_controls`** — `stage TEXT NOT NULL CHECK (stage IN ('new','contacted','engaged','qualified','converted','lost'))`, `mode TEXT NOT NULL DEFAULT 'ask' CHECK (mode IN ('auto','ask','off'))`, `config JSONB NOT NULL DEFAULT '{}'` (`{"thresholds":{"book_score":70,"send_floor":0}}`), timestamps, `UNIQUE (workspace_id, stage)`, `idx_stage_controls_ws (workspace_id, stage)`. **Default mode is `ask`** (R12) — a workspace with no row falls back to `DEFAULT_STAGE_MODE='ask'`.
- **`workspace_autonomy`** — `workspace_id UNIQUE`, `autonomy_enabled BOOLEAN NOT NULL DEFAULT FALSE` (R12 master switch), `settings JSONB NOT NULL DEFAULT '{}'`, timestamps. The resolver treats `autonomy_enabled=FALSE` as forcing every actuating proposal to `ask`/`off` regardless of per-stage `auto`.
- **`escalation_decisions`** — append-only (mirrors `engagement_events`: `occurred_at` + `created_at`, no `updated_at`). `lead_id` (CASCADE), `enrollment_id` (SET NULL), `stage`, `proposed_action TEXT CHECK IN ('send','escalate','stop','hold')`, `final_action TEXT CHECK IN ('send','park','escalate','stop','hold')`, `mode`, `score INTEGER`, `sentiment TEXT CHECK (sentiment IN ('positive','neutral','negative','objection','booking','unsubscribe'))` (R8 vocab), `reason TEXT`, `decided_by TEXT DEFAULT 'threshold' CHECK IN ('threshold','model','human')` (future-model seam), `metadata_` (`mapped_column("metadata", JSONB, ...)`). Indexes: `(workspace_id, lead_id, occurred_at DESC)`, `(workspace_id, enrollment_id)`, `(workspace_id, final_action)`.

The legacy `sequence_steps.requires_approval` column is **retained** (additive migration); the sender stops reading it. `stage_controls` **replaces** the datamodel monolith's `stage_controls` re-def and the escalation draft's `escalation_controls` name — one table (R11).

#### 2.2.2 Decision service — `app/services/escalation.py` (pure, no DB)

Per the escalation draft: `STAGE_MODES`, `PROPOSED_ACTIONS`, `FINAL_ACTIONS`, `SENTIMENTS = ("positive","neutral","negative","objection","booking","unsubscribe")` (R8), `DECIDERS`. `DEFAULT_STAGE_MODE: dict[str,str]` = **`'ask'` for every one of the six stages** (R12). `DEFAULT_THRESHOLDS = {"book_score":70,"send_floor":0}`. `_CLAMP[proposed][mode] -> final` (`ask` downgrades outward sends to `park`; `off` → `hold`; escalation surfaces except under `off`). `propose_action(...)`, `clamp_action(...)`, `decide_action(...) -> EscalationDecision`. The future `decide_action_model(...)` seam (`decided_by="model"`) reads `settings.ANTHROPIC_MODEL_SMART` via the shared client (R7) — design placeholder, not built.

#### 2.2.3 Shared authority resolver — `app/services/authority.py` (R11)

```python
# app/services/authority.py
async def resolve_authority(workspace_id: uuid.UUID, stage: str, action: str,
                            db: AsyncSession) -> str:
    """Returns 'auto' | 'ask' | 'off'. Reads the ONE stage_controls table + workspace_autonomy.
       - If workspace_autonomy.autonomy_enabled is FALSE (default) -> never 'auto' for an
         actuating action: return min('ask', per-stage mode) (i.e. 'off' stays 'off', else 'ask').
       - Else read stage_controls(workspace_id, stage).mode, falling back to
         DEFAULT_STAGE_MODE[stage] ('ask'). Read tools / non-actuating actions -> 'auto'.
       Never widens what a caller can do; only narrows."""
```
BOTH `sequence_sender._run_tick` (before any send) AND `action_bus.dispatch` (before any actuating handler) call this. The action_bus's independent stub is deleted (R11/C11). Any actuating send routed through the bus now resolves against the same table as the tick — closing the clamp-bypass hole.

#### 2.2.4 Reply-sentiment classifier — `app/workers/reply_sentiment.py` (NEW, R9)

The missing piece the critique flagged. Classifies inbound `replied` engagement_events and writes `metadata.sentiment`.

- Worker house shape (`engagement_score.py`): `@celery_app.task(name="app.workers.reply_sentiment.classify_reply", bind=True)` → `asyncio.run(_classify(workspace_id, event_id))`; own `_get_async_session()`; imports `get_async_anthropic_client()` from `app/services/llm.py` (R7) + `MODEL_FAST`; guarded/never-raises. Loads the `replied` event, builds the classification prompt from the active playbook's `render_reader_rubric()` (Inc 3; before Inc 3 a baked default rubric), asks for one of the R8 vocab values, writes it into `event.metadata_['sentiment']`, commits. On any failure leaves sentiment unset (the decider treats `None` as neutral-hold).
- **Dispatch:** the shipped engagement webhook (`outreach.py`) already enqueues `score_lead_engagement.delay(...)` on inbound `replied`; add a guarded `classify_reply.delay(str(ws), str(event_id))` beside it (same try/except pattern). No beat entry.
- `celery_app.py include=[]` gains `"app.workers.reply_sentiment"`.

#### 2.2.5 Worker integration — `sequence_sender._run_tick` (R13, edit order step 1)

Escalation lands the `_run_tick` control-flow rewrite **first** (R13). Adds `_load_stage_mode`/`_latest_sentiment` loaders; replaces the `requires_approval` HITL gate with the `resolve_authority` → `decide_action` → clamp flow; writes an `EscalationDecision` row per decision; `park`/`escalate` leave the enrollment `status='waiting'` (surfaces on the existing `/outreach/pending`); a prior `'approved'` event short-circuits to send. Adds an `escalated` counter to the tick summary + `sequence_tick` ActivityEvent. **Precedence fix (critique low-1):** `off` mode suppresses even a stale `approved` short-circuit — the kill switch wins. **Audit-truth fix (critique low-2):** when a clamped `send` is refused downstream (e.g. SMS TCPA), the decision row records the refusal reason (`final_action='hold'`, `reason=...`) rather than claiming a send that did not happen. The gate calls the drafting seam as `_draft_body(step, lead, workspace_id=ws_uuid, db=db)` (R13 keyword-optional signature).

#### 2.2.6 API + web (R15)

- `app/routers/escalation.py` (NEW): `GET/PUT /escalation/controls[/{stage}]` (upsert per-stage mode; 422 on bad stage/mode), `GET /escalation/queue` (waiting enrollments joined to newest decision; `needs_judgment = final_action=='escalate'`), `POST /escalation/leads/{lead_id}/call-outcome` (human-fed outcome re-enters the graph event-sourced: emits a `converted` engagement_event where applicable, sets stage/enrollment per `_OUTCOME_MAP`, writes an `EscalationDecision(decided_by='human')`, enqueues `score_lead_engagement`), and a `PUT /escalation/autonomy` toggling `workspace_autonomy.autonomy_enabled` (the master switch, R12).
- **Web (R15, lands in Inc 2):** an escalation-controls page (per-stage auto/ask/off + master-switch toggle), the escalation queue surface, and the post-call outcome form, each with `api-client` methods + demo-mode seeds. This is explicitly **not** in Inc 1.

#### 2.2.7 Server-side loop continuation (R16)

Inc 2 introduces the server-side job→next-action linkage: on a terminal discovery/outreach job, a decision row drives the next proposed action under the operator's caps without a live browser. Inc 1 remains operator-present (browser poller); this increment is where the autonomous continuation actually begins.

#### 2.2.8 Files (Inc 2)

Create: `apps/api/migrations/025_escalation_controls.sql`, `app/models/stage_control.py`, `app/models/workspace_autonomy.py`, `app/models/escalation_decision.py`, `app/services/escalation.py`, `app/services/authority.py`, `app/workers/reply_sentiment.py`, `app/routers/escalation.py`, tests `test_escalation_service.py`, `test_authority.py`, `test_reply_sentiment_worker.py`, `test_escalation_router.py` + web pages/hooks/api-client for the control plane.
Edit (shared): `init_docker.sql` (3 tables mirror), `models/__init__.py` (3 models), `main.py` (escalation router), `sequence_sender.py` (`_run_tick` rewrite — R13 step 1; `_load_stage_mode`/`_latest_sentiment`; calls `resolve_authority`), `outreach.py` (enqueue `classify_reply` beside `score_lead_engagement`), `celery_app.py` (`+reply_sentiment` include), `action_bus.py` (dispatch calls `resolve_authority`), `test_sequence_sender_worker.py` (new gate fixtures — coordinated with Inc 4 per R13/§4).

#### 2.2.9 Verification (Inc 2)

Decision truth table (`propose × clamp` matrix, ~45 rows, all pass); resolver returns `ask` for a fail-closed workspace even where per-stage is `auto` until the master switch is on (R12 observed); reply-sentiment worker classifies a fixture `replied` event into the R8 vocab and writes `metadata.sentiment` (offline, LLM stubbed); router 403/422/upsert/queue/call-outcome (converted event emitted, re-score enqueued — patched `.delay`); worker state machine per branch (auto+send → `_deliver`; ask+send → waiting/queued, no send; escalate → waiting + `escalation_raised`; negative/unsub → stopped; off → skipped even with a stale approved; approved → sends unless off); migration applies on scratch DB (`\dt`, `\dp` shows policies); full-suite regression green.

---

### Increment 3 — Sales-Psychology Spine

ONE shared, versioned playbook artifact governing drafting, reply-reading, and escalation from a single source of truth (decision #8). Reconciled to the psychology draft's `sales_playbooks`/`sales_playbook_sources` design (the datamodel monolith's `psychology_playbooks` is dropped, R1/C2).

#### 2.3.1 Data model — migration `026_sales_playbook.sql` (R1)

Two tables, 023 house shape, RLS ENABLE-only, mirrored into `init_docker.sql` (no RLS) under banner `-- ─── SALES PSYCHOLOGY SPINE (mirror of 026_sales_playbook.sql) ───`.

- **`sales_playbooks`** — versioned immutable snapshots: `version INTEGER NOT NULL`, `status TEXT DEFAULT 'draft' CHECK IN ('draft','active','archived')`, `doc JSONB` (the structured `PlaybookDoc`), `summary TEXT`, `source_digest JSONB`, `distilled_by TEXT`, timestamps, `UNIQUE (workspace_id, version)`, `idx_playbooks_ws_version (workspace_id, version DESC)`, and the **partial unique** `idx_playbooks_ws_active ON sales_playbooks (workspace_id) WHERE status='active'` (enforces exactly one active per workspace in-DB).
- **`sales_playbook_sources`** — provenance, owned child CASCADE: `playbook_id`, `kind TEXT CHECK IN ('vault','web','seed','manual')`, `ref`, `title`, `excerpt`, `weight`, `metadata_`, `created_at`.

#### 2.3.2 Interface — `app/services/playbook.py`

`get_active_playbook(workspace_id, db) -> Playbook` (never None, never raises; `Playbook.default()` version 0 when none active). Pure accessors + rendered rubric blocks the three consumers concatenate: `render_draft_context(lead, step, channel)` (drafting), `render_reader_rubric()` (the reply-sentiment classifier's rubric — consumed by Inc 2's `reply_sentiment.py`), `render_escalation_rubric()`. `PlaybookDoc` Pydantic schema (voice / angles / objections / signals / next_best_actions). `playbook_seed.py::default_playbook_doc()` bakes a valid doc from the Burlington sheet's `Best Outreach Angle`/`Why It Works`/`Fit Summary`/`Key Risks` columns so day-zero drafting works before any distillation.

**Cold-start data contract (R6/C-critique):** the distiller's seed reads the qualitative fields from **`lead.custom_fields.discovery.{why_it_works, best_outreach_angle, fit_summary, key_risks}`** — the exact path discovery writes (R6), not `score_detail`, not `discovered_venues`.

#### 2.3.3 Distillation worker — `app/workers/playbook_distill.py`

Worker house shape; on-demand (no beat). Imports `get_async_anthropic_client()` + `MODEL_SMART` from `app/services/llm.py` (R7) — no inline `AsyncAnthropic`, no `PLAYBOOK_DISTILL_MODEL` env. Gathers sources through guarded never-raise boundaries: `vault_source.fetch(topics, limit)` (`app/services/vault_source.py` shells `ALFRED_QUERY_BIN`, default `~/alfred-v2/.venv/bin/alfred query`; absent → `[]`), the `custom_fields.discovery` seed, optional web (deferred). Synthesizes one guarded Claude call → strict `PlaybookDoc` JSON; on missing key/model → keep current active, return `{"status":"skipped"}`. Persists `version=max+1` as `status='draft'` (HITL — operator activates), source rows, one `ActivityEvent`. `celery_app.include += "app.workers.playbook_distill"`.

#### 2.3.4 Drafting wiring (R13, edit order step 3)

Psychology makes drafting params **keyword-optional** (R13): `_draft_body(step, lead, *, workspace_id=None, db=None)`. When `workspace_id`/`db` are supplied, `_draft_body` loads `pb = await get_active_playbook(workspace_id, db)` and prepends `pb.render_draft_context(lead, step, channel)` to the prompt, stamping `metadata_["playbook_version"] = pb.version` on the `sent`/`queued` engagement_event. When absent (DB-less callers, tests), it falls back to the shipped template/guarded-Claude path unchanged — so Inc 2's `_run_tick` (which passes `workspace_id=ws_uuid, db=db`) and Inc 4's `_send_sms` both work against the one signature. Same block injected into `outreach._draft_for_step`.

#### 2.3.5 Files (Inc 3)

Create: `026_sales_playbook.sql`, `app/models/sales_playbook.py`, `app/models/sales_playbook_source.py`, `app/services/playbook.py`, `app/services/playbook_seed.py`, `app/services/vault_source.py`, `app/workers/playbook_distill.py`, `app/routers/playbook.py`, tests (`test_playbook_service.py`, `test_playbook_distill_worker.py`, `test_playbook_router.py`, `test_playbook_drafting.py`). Edit: `init_docker.sql` (2 tables), `models/__init__.py` (2 models), `main.py` (playbook router), `celery_app.py` (`+playbook_distill`), `sequence_sender.py` (`_draft_body` keyword-optional — R13 step 3), `outreach.py` (`_draft_for_step` playbook injection + version stamp).

#### 2.3.6 Verification (Inc 3)

Migration applies + the two-active-rows INSERT fails on `idx_playbooks_ws_active` (proves one-active in-DB); models import; `get_active_playbook(empty-ws)` returns version 0 with Burlington angle text (day-zero drafting); distiller runs offline (one draft row, `status in {drafted,skipped}`, never raises); drafting consumes the playbook (sentinel preamble + version stamp observed on the engagement_event); router `GET/distill/activate` flips active; acceptance ties to discovery (distill after a Burlington run reads `custom_fields.discovery` and covers the seed angles).

---

### Increment 4 — SMS / Twilio channel (A2P 10DLC) — LATER increment (R14)

Replaces the SMS stub in `sequence_sender._deliver` with a real, provider-abstracted, **TCPA-gated** SMS channel, **event-sourced onto 023's `engagement_events`** (R1/R14). **ZERO schema migration:** `engagement_events` already permits `channel='sms'` and types `delivered/bounced/replied/unsubscribed` (023); opt-out is a `type='unsubscribed'` event, not a column (R14/C14). No `sms_configs`/`sms_messages`/`leads.sms_consent_*` (the datamodel monolith's SMS tables are dropped).

#### 2.4.1 Provider abstraction — `app/services/sms_client.py`

`GmailClient` idiom (raw `httpx==0.27.2`, no `twilio` SDK). `SmsProvider` ABC (`send(...)` never-raises returning `{delivered, channel, provider, sid, to, status, reason}`; `verify_signature(url, params, signature)` fail-closed via the Twilio `X-Twilio-Signature` HMAC-SHA1 algorithm). `TwilioProvider`. `get_sms_provider(settings=None) -> SmsProvider | None` (None when creds absent → caller skips send; `telnyx`/`bandwidth` raise `NotImplementedError`).

#### 2.4.2 TCPA gate — sender preconditions (R14)

In `_send_sms(db, workspace_id, step, lead, body, enrollment)`, two **hard preconditions** (same tier as auth):

1. **Prior email engagement** — `_lead_email_engaged(...)` True iff ≥1 `engagement_event` with `channel='email'` and `type in ('opened','clicked','replied')`. Unmet → hard refusal, no provider call (`reason='tcpa_precondition_unmet'`).
2. **Lead-local quiet-hours 8am–9pm** — `_lead_local_quiet_hours(lead)` derives timezone from **area code / venue state**; if unknown or outside the window → defer (`reason='quiet_hours'`, no provider call). This closes the critique's live-TCPA-violation hole (the shipped `_in_quiet_hours` is UTC-only).

Plus `_lead_sms_opted_out(...)` (any `type='unsubscribed'` event → STOP). **Twilio A2P 10DLC brand+campaign registration is a HARD external prerequisite** (§6 escalation gate); env-var creds; the HMAC-verified inbound webhook reuses the module's existing webhook hardening. **LEGAL-REVIEW gate (R14/§6):** whether prior email engagement is a lawful TCPA consent basis must clear legal review before any live SMS; the email-engagement check is a relevance filter, and a real express-opt-in signal is the intended consent basis.

#### 2.4.3 `_deliver` signature + edit order (R13, step 2)

SMS threads `enrollment` through **`_deliver(db, workspace_id, step, lead, subject, body, enrollment)`** (the email path ignores it), and updates the single call site inside **escalation's already-rewritten send branch** (R13: escalation's `_run_tick` rewrite lands first; SMS merges into it, not against shipped 023 code). SMS's drafting reuses `_draft_body(step, lead, *, workspace_id=..., db=...)` (R13 keyword-optional).

#### 2.4.4 Inbound webhooks — `app/routers/sms_webhooks.py`

Two routes copying the engagement-webhook hardening (no auth dep, fail-closed signature verify, `@limiter.limit`, URL-workspace binding + cross-tenant guards, append-only event write, guarded score enqueue): `POST /workspaces/{ws}/webhooks/sms/status` (maps Twilio status → `delivered`/`bounced` event) and `POST /workspaces/{ws}/webhooks/sms/inbound` (`STOP`/keywords → `unsubscribed` + halt enrollments; else `replied`; unknown `From` → 200 empty TwiML). Single-workspace MVP: inbound is bound to one workspace and asserted at startup (multi-tenant number routing deferred, §6).

#### 2.4.5 Config + files (Inc 4)

`config.py`: `SMS_PROVIDER='twilio'`, `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_MESSAGING_SERVICE_SID`, `TWILIO_FROM_NUMBER`, `SMS_STATUS_CALLBACK_BASE` (all `""`, env-sourced). Create: `app/services/sms_client.py`, `app/routers/sms_webhooks.py`, `tests/test_sms_client.py`, `tests/test_sms_webhooks.py`. Edit: `sequence_sender.py` (`_send_sms` + preconditions + `_deliver` enrollment param — R13 step 2), `main.py` (sms_webhooks router), `test_sequence_sender_worker.py` (SMS precondition cases — coordinated with Inc 2 per §4). No `requirements.txt` change; no migration.

#### 2.4.6 Verification (Inc 4)

Unit (no network): `verify_signature` on Twilio's published vector (True; flipped byte → False; empty token → False); `send()` patched httpx (201 → delivered; 400/timeout → delivered=False, no raise); **TCPA precondition (load-bearing):** `_send_sms` with no email engagement → `tcpa_precondition_unmet` and `provider.send` **zero calls**; outside quiet-hours → `quiet_hours`, zero calls; opted-out → `opted_out`; status webhook (valid sig → `delivered` event + score enqueue; tampered → 403; other-workspace lead → 404); inbound `STOP` → `unsubscribed` + enrollment stopped. Integration (staging Twilio + verified handset): real text arrives; StatusCallback flips to `delivered`; `STOP` → `unsubscribed` + subsequent tick refuses; re-score moves `lead.score` (proves channel-agnostic scorer). 10DLC prod: no carrier-filter error codes 30034/30007.

---

## §3. Cross-cutting concerns

### §3.1 Shared LLM client — `app/services/llm.py` (R7, build-order 0)

Built **first**, before any LLM caller. Kills the inline-`AsyncAnthropic` + hardcoded-model-literal anti-pattern.

```python
import anthropic
from app.config import settings

_async_client: anthropic.AsyncAnthropic | None = None

def get_async_anthropic_client() -> anthropic.AsyncAnthropic:
    global _async_client
    if _async_client is None:
        _async_client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _async_client

MODEL_FAST  = settings.ANTHROPIC_MODEL_FAST    # reply-sentiment, quick answers
MODEL_SMART = settings.ANTHROPIC_MODEL_SMART   # agentic tool loop, deep-research scoring, distillation
```
**All four callers import this singleton** (R7): `discovery_research.score_venue`, `playbook_distill._run_distill`, `reply_sentiment.classify_reply`, and the future escalation `decide_action_model`. None constructs its own `AsyncAnthropic`. `app/services/llm.py` is a build-order dependency of Inc 1 (discovery_research) and every later LLM caller.

### §3.2 Authority resolver — `app/services/authority.py` (R11)

Single choke point for every outward send (§2.2.3). Reads the one `stage_controls` table + `workspace_autonomy`. Called by `sequence_sender._run_tick` and `action_bus.dispatch`. Delivered in Inc 2; the Inc 1 action_bus is written to call it from day one (before Inc 2, a thin `authority.py` shipping with Inc 1 returns fail-closed `ask`/`off` for actuating actions with the master switch defaulting off — no permissive stub ever exists).

### §3.3 Migration + init_docker ledger (R1)

**On-disk max is `023`.** Assignments (each hand-applied to prod, mirrored into `init_docker.sql` tables+indexes-only, no runner):

| Migration file | Increment | Tables created | init_docker mirror owner |
|---|---|---|---|
| `024_lead_engine_discovery.sql` | 1 (Discovery) | `discovery_runs`; widens `leads.source` CHECK (+`'discovery'`) | Inc 1 owns the `discovery_runs` mirror + the inline `CREATE TABLE leads` source-CHECK edit |
| `025_escalation_controls.sql` | 2 (Escalation) | `stage_controls`, `workspace_autonomy`, `escalation_decisions` | Inc 2 |
| `026_sales_playbook.sql` | 3 (Psychology) | `sales_playbooks`, `sales_playbook_sources` | Inc 3 |
| *(none)* | 4 (SMS) | — event-sourced on 023 `engagement_events` | — |

**No table is created by more than one migration file, and no table is CREATE'd twice in `init_docker.sql`** (fixes C2/C10-init). **Renumber rule vs the parallel photobooth slice:** `docs/betson/BUILD-SPEC-photobooth-slice-2026-09-02.md` also eyes `024`/`025`. **This spec's assignments win for the Autonomous Lead Engine.** Whichever migration lands in prod first keeps its number; the other renumbers to the next free slot, and the implementer records the landed number in a one-line ledger comment at the top of `init_docker.sql` (there is no runner to track it). FK ordering across files is safe: 024 references only `workspaces`/`users`/`leads` (all pre-023); 025 references `workspaces`/`users`/`leads`/`sequence_enrollments` (023); 026 references `workspaces`/`users` only.

### §3.4 Config additions ledger (single owner per field, R7/R8/C-config)

One config edit, owned by the increment that first needs the field; later increments treat it as pre-existing.

| Field | Default | Owner | Notes |
|---|---|---|---|
| `ANTHROPIC_MODEL_FAST` | `"claude-haiku-4-5"` | Inc 1 (with `llm.py`) | env-overridable; ONE non-empty default; used by reply-sentiment + quick answers |
| `ANTHROPIC_MODEL_SMART` | `"claude-sonnet-5"` | Inc 1 (with `llm.py`) | env-overridable; ONE non-empty default; agentic loop, deep-research scoring, distillation. Operators may raise to `claude-opus-5` for higher-stakes drafting. **Verified current ids (no date suffix):** `claude-opus-5`/`claude-sonnet-5`/`claude-haiku-4-5`. Never a literal in logic. |
| `GOOGLE_PLACES_API_KEY` / `YELP_API_KEY` / `FOURSQUARE_API_KEY` | `""` | Inc 1 | provider key-gates |
| `DISCOVERY_LLM_CONCURRENCY` / `DISCOVERY_MAX_VENUES` | `5` / `60` | Inc 1 | |
| `SMS_PROVIDER` … `SMS_STATUS_CALLBACK_BASE` | `"twilio"` / `""` | Inc 4 | never hardcoded; secrets from env only |

`ANTHROPIC_MODEL_RESEARCH` and `PLAYBOOK_DISTILL_MODEL` from the drafts are **dropped** (R7/C8) — the research and distill passes both use `MODEL_SMART`.

---

## §4. Per-file ownership table

Every new + shared-edited file, and which increment owns it. Shared edits list the owning increment; where two increments touch one file, the edit order (R13) is stated.

| File | Kind | Owner | Notes |
|---|---|---|---|
| `app/services/llm.py` | new | **Inc 1** | build-order 0; shared by all LLM callers (R7) |
| `app/services/authority.py` | new | **Inc 1** (ships fail-closed), **Inc 2** completes | resolver read by tick + action_bus (R11) |
| `migrations/024_lead_engine_discovery.sql` | new | Inc 1 | discovery_runs + leads source-CHECK |
| `app/models/discovery_run.py` | new | Inc 1 | the ONE `DiscoveryRun` (R1/C2) |
| `app/services/discovery.py` | new | Inc 1 | `dispatch_discovery_run` seam (R2) |
| `app/services/places.py` / `discovery_rubric.py` / `discovery_research.py` | new | Inc 1 | |
| `app/services/action_bus.py` | new | Inc 1; Inc 2 wires `resolve_authority` | calls `authority.resolve_authority` (R11) |
| `app/services/actions/{__init__,discovery}.py` | new | Inc 1 | ONE discovery action (R10) |
| `app/workers/discovery.py` | new | Inc 1 | `run_market_discovery(ws, run_id)` (R2) |
| `app/routers/discovery.py` | new | Inc 1 | |
| `apps/web/src/hooks/useChat.ts`, `components/chat/ChatPanel.tsx`, `app/(app)/assistant/page.tsx` | new | Inc 1 | |
| `migrations/025_escalation_controls.sql` | new | Inc 2 | stage_controls + workspace_autonomy + escalation_decisions |
| `app/models/{stage_control,workspace_autonomy,escalation_decision}.py` | new | Inc 2 | |
| `app/services/escalation.py` | new | Inc 2 | pure decider |
| `app/workers/reply_sentiment.py` | new | Inc 2 | the missing classifier (R9) |
| `app/routers/escalation.py` + web control-plane pages | new | Inc 2 | operator UI (R15) |
| `migrations/026_sales_playbook.sql` | new | Inc 3 | |
| `app/models/{sales_playbook,sales_playbook_source}.py` | new | Inc 3 | |
| `app/services/{playbook,playbook_seed,vault_source}.py` | new | Inc 3 | |
| `app/workers/playbook_distill.py`, `app/routers/playbook.py` | new | Inc 3 | |
| `app/services/sms_client.py`, `app/routers/sms_webhooks.py` | new | Inc 4 | |
| `migrations/init_docker.sql` | shared | each increment mirrors ONLY its own tables | per §3.3 ledger; no table CREATE'd twice |
| `app/models/__init__.py` | shared | each increment appends its own models | Inc 1: DiscoveryRun; Inc 2: 3; Inc 3: 2 |
| `app/config.py` | shared | field owner per §3.4 | later increments treat fields as pre-existing |
| `app/routers/leads.py` (`LEAD_SOURCES:43`) | shared | **Inc 1** only | +`"discovery"` (single owner; fixes C-low duplicate) |
| `app/workers/celery_app.py` (`include=[]`) | shared | each increment appends its own worker | Inc 1: discovery; Inc 2: reply_sentiment; Inc 3: playbook_distill; no beat entries |
| `app/main.py` (router includes) | shared | each increment appends its own router | coordinate the include block |
| `app/routers/ai.py` | shared | Inc 1 | snapshot extract + chat loop |
| `app/routers/mcp_server.py` | shared | **NO write tool** (R10) | stays read-only |
| `app/routers/outreach.py` | shared | Inc 2 (`+classify_reply` enqueue), Inc 3 (`_draft_for_step` playbook) | |
| `app/workers/sequence_sender.py` | shared | **Inc 2 first** (`_run_tick` rewrite), **Inc 3** (`_draft_body` keyword-optional), **Inc 4 last** (`_deliver` enrollment param, SMS branch) | R13 edit order — each edit merges into the prior, not against shipped 023 |
| `apps/api/tests/test_sequence_sender_worker.py` | shared | Inc 2 + Inc 4 coordinate into ONE fixture change | `_lead` gains stage/score/sentiment; `_deliver` gains enrollment |
| `apps/web/src/lib/{api-client,demo-data}.ts`, `components/layout/Sidebar.tsx` | shared | Inc 1 (chat + discovery seed), Inc 2 (control-plane) | |

---

## §5. Verification plan (observed, not asserted — per increment)

The doctrine: **"done" means OBSERVED working, not asserted.** Run it, read the result, check the count; for any non-trivial finding, the **verifier** subagent tries to refute it before it is reported true. Baselines from the shipped module: API boots with **173 routes** and the full suite is **733 passed, 1 failed** (a pre-existing date-bomb in `test_deals.py`, unrelated) as of the 2026-08-13 HANDOFF — new routers/workers add to the pass count; the pre-existing failure stays.

- **Inc 1 (Discovery):** §2.1.13 table (V1–V13) + the firm Burlington gate §2.1.14. Keystone gates: V4 (rubric reproduces all 16 sheet scores ±0.1 with no LLM), V7 (worker summary key set exact), V11 (fit ≠ engagement), V12 (coverage ≥12/16, r ≥0.6, tier ≥0.7). App boots (`import app.models; from app.main import app`); `pytest -q` no prior-green test broken; web `tsc --noEmit` + demo `pnpm build` clean; browser (Playwright) drives `/assistant` → prompt → running-job → "Found N venues" → rows on `/leads`.
- **Inc 2 (Escalation + reply-sentiment):** §2.2.9. Keystone: fail-closed default observed (a fresh workspace never auto-fires a send until the master switch is on — R12), the reply-sentiment classifier writes an R8-vocab value (no more inert `_latest_sentiment` returning None), and a send routed through the action_bus resolves against the same `stage_controls` as the tick (R11 — no clamp bypass).
- **Inc 3 (Psychology):** §2.3.6. Keystone: two-active INSERT rejected in-DB; day-zero `get_active_playbook` usable; drafting stamps `playbook_version` on the engagement_event; the distiller seed reads `custom_fields.discovery` (R6).
- **Inc 4 (SMS):** §2.4.6. Keystone: TCPA preconditions block the provider call (zero `provider.send` calls when unmet or outside quiet-hours); opt-out is a single event source of truth; no live send until the LEGAL-REVIEW + 10DLC gates clear.
- **Cross-cutting:** RLS parity — `pg_policies` shows a policy per new table on the prod-DDL DB and zero policy lines in the `init_docker.sql` banners; prod↔Docker column-set diff identical (only RLS lines differ). Note that RLS is ENABLE-only and inert against the API service role — tenant isolation rests on app-level `.where(workspace_id==...)` filters; §6 tracks the FORCE-RLS follow-up and an isolation test.

---

## §6. Open questions (deliberately undecided)

1. **Which places API is primary** — Google Places vs Yelp vs Foursquare. The abstraction (§2.1.4) is provider-agnostic; ship `GooglePlacesProvider` behind the interface; others are keyed stubs.
2. **Exact score→stage thresholds** — `DEFAULT_THRESHOLDS.book_score=70`/`send_floor=0` (§2.2.2) are placeholders aligned to `engagement_score`'s existing `>=70="hot"` band; real cut-points are config-overridable per stage without a migration.
3. **First vault-distillation scope** — proposed narrow default: seed (`custom_fields.discovery`) + one targeted vault query (e.g. "cold-outreach objection handling"); web deferred. Exact topic list is open.
4. **TCPA legal basis** — whether prior email engagement is a lawful consent basis for marketing SMS. **A documented LEGAL-REVIEW gate blocks any live SMS** until resolved; the intended basis is a real express-opt-in signal, with email-engagement as a relevance filter (R14).
5. **FORCE RLS follow-up** — all new tables ship ENABLE-only (matching 023); prod isolation against the API service role requires a `013_force_rls.sql`-style registration + an isolation test. Deliberate follow-up, not automatic.
6. **External spend gates** — the live Burlington run bills a Google Places key + paid Anthropic calls; live SMS bills Twilio + requires A2P 10DLC brand/campaign registration. Both are escalation-worthy external gates (credentials/spend), flagged here, not completable by the scaffold.
7. **Multi-tenant SMS number routing** — a shared Twilio Messaging Service exposes one inbound URL that cannot carry `workspace_id`; single-workspace MVP asserts one workspace at startup. Multi-tenant needs a deferred `workspace_sms_numbers` table (next free migration after 026) + resolve-by-`To`-number + per-workspace auth-token signature verification — critically so STOP opt-outs cannot mis-route.
8. **Chat persistence / autonomous continuation depth** — Inc 1 chat is stateless (browser-poller-driven, R16); Inc 2 adds server-side job→next-action linkage. A `chat_sessions`/`chat_messages` table for cross-device history + escalation replay is a later decision.

---

## §7. Deploy notes

- **Manual migration apply (no runner).** Apply each migration by hand to Supabase prod **in increment order**: `024_lead_engine_discovery.sql` → `025_escalation_controls.sql` → `026_sales_playbook.sql`. The Docker path gets the tables via the `init_docker.sql` mirror (tables + indexes only, no RLS). Record the landed migration number in the `init_docker.sql` header ledger (there is no runner to track it). SMS (Inc 4) adds **no migration**.
- **Idempotency is necessary but not sufficient.** Because every migration uses `CREATE TABLE IF NOT EXISTS`, "no error on re-run" does not prove correctness — after applying, **diff the resulting column set against the ORM model** on a scratch DB (a second run must be a no-op, and the columns must match the model). No table name may be created by more than one migration file or twice in `init_docker.sql` (§3.3 guarantees this).
- **Env / secrets.** Inc 1: `GOOGLE_PLACES_API_KEY` (+ optional `YELP`/`FOURSQUARE`), `ANTHROPIC_MODEL_FAST`/`SMART` (defaults `claude-haiku-4-5`/`claude-sonnet-5`; env-overridable — confirm the intended ids against the live model list before first live run). Inc 4: Twilio creds + Messaging Service SID, and A2P 10DLC registration complete, before any live SMS. Deploy API + web as usual (Railway).
- **Order of operations for the shared `sequence_sender.py`.** Land Inc 2's `_run_tick` rewrite, then Inc 3's `_draft_body` keyword-optional change, then Inc 4's `_deliver` enrollment param + SMS branch (R13) — each merges into the prior increment's output, never against shipped 023 code.
