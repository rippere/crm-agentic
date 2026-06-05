# Phase 1 Read — Celery Workers Subsystem

Scope: `/tmp/crm-signup-fix/apps/api/app/workers/` (production master worktree).
Files: celery_app.py, ingest.py, slack_ingest.py, pipeline.py, score_contact.py,
enrich_contact.py, embed_contacts.py, deal_health_worker.py, followup_sequences.py,
transcribe.py, pm_agent.py.

---

## 1. Topology / deployment

Celery app `crm_agentic` (`celery_app.py`), broker AND result backend both = `REDIS_URL`
(default `redis://localhost:6379/0`). Serializer json. timezone UTC. `task_track_started=True`.

Railway services (one Dockerfile, different start commands):
- `railway-worker.toml`  → `celery ... worker --loglevel=info --concurrency=2`  (prefork, 2 procs)
- `railway-beat.toml`    → `celery ... beat --loglevel=info`
- `railway-flower.toml`  → `celery ... flower --port=$PORT --broker=$REDIS_URL`  (monitoring UI)
- `railway.toml`         → the FastAPI web app (`/health` healthcheck)
All restart `ON_FAILURE`, maxRetries 3. NOTE: only ONE worker service and it consumes the
default queue — there is NO queue routing (`task_routes`) at all, so the heavy CPU-bound
Whisper transcription, the sentence-transformer embedding job, and the latency-sensitive
ingest/enrich all share the same 2 prefork slots. Concurrency=2 is a hard ceiling on all
background work for ALL tenants combined.

DB engine: every worker hand-rolls its OWN `create_async_engine` from `os.getenv("DATABASE_URL")`
(falling back to SUPABASE_URL with a postgres:// → postgresql+asyncpg:// rewrite). It does NOT
reuse `app.database.engine` (which sets `pool_pre_ping=True`). Per-task engines created on every
call → no `pool_pre_ping`, no shared pool. See inconsistencies.

---

## 2. Beat schedule (celery_app.py lines 27–48)

| name | task | schedule (UTC) | args |
|------|------|----------------|------|
| nightly-pipeline-optimize | pipeline.optimize_pipeline | 02:00 daily | [] |
| nightly-deal-health | deal_health_worker.compute_deal_health | 02:15 daily | [] |
| daily-hitl-followup | followup_sequences.check_stale_deals_hitl | 09:00 daily | [] |
| pm-health-check | pm_agent.run_health_check | every 30 min | [] |

### *** CRITICAL BUG: two of four scheduled tasks crash every run ***
- `optimize_pipeline(self, workspace_id)` (pipeline.py:104) REQUIRES `workspace_id`.
- `compute_deal_health(self, workspace_id)` (deal_health_worker.py:112) REQUIRES `workspace_id`.
Beat invokes both with `args: []`. Celery will raise
`TypeError: optimize_pipeline() missing 1 required positional argument: 'workspace_id'`
on EVERY scheduled fire (02:00 and 02:15 nightly). There is NO wrapper that loops over
workspaces, NO default value, NO `select(Workspace)` anywhere in workers/ (grep confirmed empty).
→ The nightly pipeline-optimize and deal-health jobs have NEVER successfully run from beat.
   They only work when invoked manually from the routers (`deals.py:109`, `deals.py:260`) which
   pass `str(workspace_id)` via `.delay()`. So the *scheduled/automated* product promise is dead;
   only the manual "recompute now" buttons function.
- The OTHER two beat tasks are fine: `check_stale_deals_hitl(self)` and `run_health_check(self)`
  take only `self` — they iterate all workspaces internally. So they DO run on schedule.

This asymmetry is the smoking gun: the two tasks written workspace-scoped were never adapted to
the "fan out over all workspaces" pattern the other two use. test_workers.py never exercises the
beat schedule, so CI is green while prod cron silently throws.

---

## 3. Per-task behavior, idempotency, retry, failure modes

### ingest.py — Gmail (574 lines, the core)
Tasks:
- `process_gmail_sync(connector_id)` (name app.workers.ingest.process_gmail_sync)
- `enrich_message(message_id)` — shared per-message enrichment (ALSO used by slack_ingest)
- `reprocess_workspace_messages(workspace_id)` — user-triggered "Re-run enrichment"

Flow (`_run_sync`): load connector → bounded pagination (INGEST_MAX_PAGES default 10 pages × 100
= 1000 msgs; sets `truncated=True` when capped, relies on next sync + dedupe to resume) →
Stage 1 fetch+dedupe+header-parse (no Claude) gated by `_is_automated_sender` →
Stage 2 concurrent Claude Haiku relevance prefilter via `asyncio.gather` →
Stage 3 insert relevant msgs (processed=False, relevant=True), link contact (link-only,
never auto-creates), flush → bump connector.last_sync + message_count → commit →
OFF critical path: `enrich_message.delay(mid)` per inserted message.

Idempotency: dedupe on (workspace_id, external_id) SELECT before insert (ingest.py:214-221).
Comment at top claims "UNIQUE workspace_id + external_id" but the Message model (message.py)
has NO UniqueConstraint / unique index on (workspace_id, external_id) — dedup is application-level
SELECT-then-INSERT only. Under the concurrency=2 worker + Pub/Sub double-delivery this is a
TOCTOU race that CAN double-insert (two syncs for the same connector interleave). The claimed
DB-level UNIQUE does not exist. (HIGH — see risks.)

Relevance prefilter fail-open: on Claude error returns True ("include by default", ingest.py:125,144).
Reasonable, but means an Anthropic outage floods the DB with unfiltered email + enqueues enrich
for all of them.

`enrich_message` (_run_enrich_message, ingest.py:338): extract_tasks + analyze_sentiment +
score_clarity, each wrapped in its own try/except (one failure doesn't lose the others), then
`message.processed=True`. NO de-dupe of tasks here — if `enrich_message` is retried or the same
message is enqueued twice, tasks are inserted AGAIN (no delete-before-insert, unlike reprocess).
Since there is no retry config this is only a double-enqueue risk, but the gmail push webhook can
enqueue the same sync repeatedly.

`reprocess_workspace_messages` (ingest.py:443): DUPLICATES the entire enrich body inline instead
of calling `_run_enrich_message`. It DOES delete tasks before re-extract (ingest.py:497-498) and
upserts clarity — so reprocess is idempotent but enrich_message is not, and the two copies of the
same logic will drift. Big homogenization target.

Retry/DLQ: NONE. No `acks_late`, no `autoretry_for`, no `max_retries`, no `self.retry`, no
`task_reject_on_worker_lost`, no dead-letter queue, no time limits (grep across app/ returned
empty). With Redis as broker and `acks_late` default False, a task is acked the moment the worker
picks it up; if the worker is killed (Railway redeploy, OOM from Whisper/torch) mid-task the
message is LOST, not redelivered. No DLQ to inspect failures. "restartPolicyMaxRetries 3" is the
*process* restart, not task redelivery.

### slack_ingest.py — Slack
`process_slack_sync(connector_id)`. Imports `_link_contact` and `enrich_message` FROM ingest.py
(good reuse). list_conversations (im,mpim,public_channel — NOTE: NOT private_channel, despite the
module docstring line 6 saying "public/private channels") up to 3 pages → get_history (limit 200,
single page — no pagination, so channels with >200 msgs lose history beyond the newest 200) →
dedupe on (workspace_id, external_id) where external_id = f"{channel_id}:{ts}" → insert →
enqueue enrich.
Auth handling is the BEST in the subsystem: `SlackAuthError` is caught, persisted as a
`connector_auth_error` ActivityEvent (because Connector has no last_error column — confirmed,
connector.py has no such field), and last_sync is deliberately NOT bumped so the failure stays
visible to monitoring (slack_ingest.py:104-109). This is a deliberate, well-reasoned pattern that
the Gmail path does NOT replicate (gmail just logs+breaks the loop, then still bumps last_sync).

### pipeline.py — heuristic win-prob optimizer
`optimize_pipeline(workspace_id)`. Loads open deals (stage NOT IN closed_won/closed_lost),
computes `_compute_win_probability` (base 30 + STAGE_BONUS + value>50k +5 − staleness; clamp 0..95),
writes `deal.ml_win_probability`, logs one `pipeline_optimized` ActivityEvent. Idempotent
(overwrite). Whole-workspace single transaction. CRASHES from beat (no workspace_id) — see §2.

### score_contact.py — heuristic lead scorer
`score_lead(contact_id, workspace_id)`. base 50 + status/deal_count/revenue, clamp 0..100,
label hot/warm/cold, writes `contact.ml_score` JSONB + a `lead_score_updated` ActivityEvent.
Idempotent. Invoked from contacts.py:245 only (not scheduled). NOTE the scoring REPLACES the whole
ml_score dict including signals — and enrich_message's sentiment step (ingest.py:393-400) ALSO
writes contact.ml_score["signals"]. These two writers race / clobber each other's signals with
no coordination (last-writer-wins on the JSONB column).

### embed_contacts.py — vector backfill
`embed_workspace_contacts(workspace_id)`. Iterates ALL contacts in workspace, `embed_text` via
sentence-transformers all-MiniLM-L6-v2 (384-dim), writes `contact.embedding`. Docstring: "Safe to
run multiple times — existing embeddings are overwritten." True. Loads the ~80MB ST model in the
worker process (lru_cache) → first call pins memory; runs on the SAME 2-slot worker as everything
else. Triggered from search.py:123 & :147 (two call sites). No batching of encode() — one model
call per contact (N sequential encodes); large workspaces = slow + holds the worker slot.

### deal_health_worker.py — nightly health
`compute_deal_health(workspace_id)`. For each active deal: find last Message.received_at for
linked contact → `services.deal_health.compute_health(stage, stage_changed_at, last_message_at)`
→ write `deal.health_score`; if score ≤ 25 emit a `deal_alert` ActivityEvent (warning) with
NEXT_BEST_ACTION. Idempotent. CRASHES from beat (no workspace_id) — see §2. N+1 query: one
Message SELECT per deal (deal_health_worker.py:70-76).

### followup_sequences.py — HITL follow-ups (daily 09:00, WORKS)
`check_stale_deals_hitl()` (no args → runs from beat). For workspaces having BOTH slack AND gmail
connectors: find active deals health_score ≤ 40 (limit 5/ws) that have no `hitl_pending`
ActivityEvent in last 7 days (dedupe via `meta.like('%"deal_id": "<id>"%')` LIKE on a JSON string
— brittle string match, see risks) → draft email via Claude Haiku → persist `hitl_pending`
ActivityEvent with full draft in meta → post Slack Block Kit (Approve/Dismiss buttons) →
consumed by routers/slack_interactions.py. Skips deals with no contact email.
Idempotency: the 7-day LIKE-on-meta gate. If the draft succeeds but the Slack post fails
(slack_ingest.py:182), the hitl_pending row is ALREADY committed → that deal is suppressed for 7
days even though no human ever saw the Slack card. Silent drop of a follow-up.
NOTE: brand-new deals default health_score=100 (deal.py) and only become eligible (≤40) AFTER
compute_deal_health runs — but compute_deal_health is the beat task that CRASHES (§2). So in prod,
health_score is only ever lowered by the MANUAL "recompute" button; if no one clicks it, every
deal stays at 100 forever and the daily HITL follow-up finds NOTHING to do. The two bugs compound:
the dead nightly job neuters the working daily job.

### transcribe.py — call transcription
`transcribe_call(call_summary_id, audio_path)`. Whisper (base, lru_cache) transcribe →
Claude Sonnet summary+action_items → persist to call_summaries → `finally:` unlink temp audio.
Triggered from calls.py:97 with a tempfile path written by the WEB process
(tempfile.NamedTemporaryFile delete=False). FAILURE MODE: if the worker runs on a DIFFERENT
machine/container than the web process (it does — separate Railway service), `audio_path` is a
path on the web container's filesystem that the worker CANNOT see → `_transcribe_audio` raises
FileNotFoundError, the `finally` unlink also can't find it, the call_summary row stays with
empty transcript forever, and there is NO retry. This only works if web+worker share a volume,
which Railway services do NOT by default. (HIGH — cross-process temp file via local path.)
Also: exceptions from transcribe/Claude propagate (only the cleanup is guarded) → task fails with
no retry, audio already deleted by finally on the happy-ish path but on FileNotFound the file
never existed. Whisper+torch in the same 2-slot worker can OOM the box.

### pm_agent.py — "PM Agent" health monitor (every 30 min, WORKS)
`run_health_check()` (no args). (1) Agents stuck in 'processing' > 30m → set status='error' +
pm_alert. (2) Connectors with last_sync > 48h → pm_alert warning. (3) Projects older than 24h
with zero tasks → pm_alert info. (4) Heartbeat ActivityEvent per workspace (distinct Agent
workspace_ids). Idempotent-ish but emits a NEW heartbeat event every 30 min for every workspace →
unbounded activity_events growth (48 rows/workspace/day just from heartbeats, more with alerts;
stale-connector + empty-project checks RE-FIRE every 30 min with no suppression → duplicate alerts
spam). No dedupe on alerts. Uses its own `_get_session` that reads DATABASE_URL with NO
SUPABASE_URL fallback (unlike the others) — minor inconsistency.

---

## 4. asyncio pattern (all tasks)

Every task body does `asyncio.get_event_loop().run_until_complete(_run(...))`. On Python 3.11
(Dockerfile FROM python:3.11-slim) `asyncio.get_event_loop()` with no running loop is DEPRECATED
and, in a fresh Celery prefork child that has no current event loop set, can raise
`DeprecationWarning` now / `RuntimeError: There is no current event loop` in future Python. More
practically: reusing get_event_loop() (vs asyncio.run) means the loop is NOT closed between task
runs in the same prefork child; the per-task `create_async_engine` creates a new asyncpg pool bound
to that reused loop each call → connection/pool accumulation over the worker's lifetime. The
codebase mixes sync (`anthropic.Anthropic`) and async (`anthropic.AsyncAnthropic`) clients across
files with no consistent rule.

---

## 5. Claims (verbatim from code/docstrings) vs reality

- ingest.py:8 "Deduplicate against messages table (UNIQUE workspace_id + external_id)" →
  FALSE: no DB UNIQUE constraint exists (message.py). App-level SELECT only.
- embed_contacts.py:5 "Safe to run multiple times — existing embeddings are overwritten." → TRUE.
- pipeline.py docstring `optimize_pipeline(workspace_id)` → signature accurate, but beat calls it
  with no arg (celery_app.py:31) → scheduled invocation is BROKEN.
- enrich_contact.py:9 "Only non-null fields are updated — existing data is never overwritten." →
  TRUE (guards `and not contact.X` on every field).
- slack_ingest.py:6 docstring "public/private channels" → FALSE: code requests
  `types="im,mpim,public_channel"` (no private_channel) (slack_ingest.py:95).
- transcribe.py:1 "cached after first load", "Clean up temp audio file" → caching TRUE; cleanup
  TRUE but predicated on the file being reachable, which cross-container it is not.
- pm_agent.py:4 "Catches silent failures across all subsystems" → partial; it itself is one of the
  jobs that runs, but it cannot catch the beat TypeError crashes of the other two jobs (those fail
  in beat/worker before touching the DB, leave no activity_event, no stuck Agent row).
- followup_sequences.py:8 "store a hitl_pending ActivityEvent so the interactions endpoint can
  resolve it" → consumer exists (routers/slack_interactions.py). TRUE.

---

## 6. Risks (file:line)

1. [CRITICAL] celery_app.py:28-37 — beat passes `args: []` to optimize_pipeline /
   compute_deal_health which require workspace_id → TypeError every nightly run; the two flagship
   "nightly AI" jobs never run on schedule. Untested (test_workers.py only tests pure helpers).
2. [HIGH] transcribe.py:112 + calls.py:80-97 — audio temp file written by web process, path passed
   to worker on a separate container; worker can't read it → transcription silently never completes,
   no retry. Cross-process local-path coupling.
3. [HIGH] ingest.py:214 + message.py — dedupe is SELECT-then-INSERT with NO DB unique constraint;
   concurrency=2 + Pub/Sub re-delivery → duplicate Message rows (TOCTOU). Docstring claims a UNIQUE
   that doesn't exist.
4. [HIGH/multi-tenant] All workers: NO retry/acks_late/DLQ; worker death on Railway redeploy or
   Whisper/torch OOM loses in-flight tasks for ALL tenants with no redelivery and no dead-letter to
   replay. Single shared queue + concurrency=2 means one tenant's big embed/transcribe starves
   every other tenant's ingest.
5. [MEDIUM] followup_sequences.py:163-181 — hitl_pending committed BEFORE Slack post; if post
   fails the deal is suppressed 7 days with no human ever notified. Silent follow-up loss.
6. [MEDIUM] followup_sequences + compute_deal_health interaction — deals default health=100,
   only lowered by compute_deal_health, which is the CRASHING beat job → in prod the daily HITL
   sweep finds nothing because nothing ever drops to ≤40 unless an admin manually clicks recompute.
7. [MEDIUM] pm_agent.py:112-122 + 80-88 — heartbeat + stale/empty alerts re-emit every 30 min with
   no suppression → activity_events table grows unbounded and alert spam (same warning every cycle).
8. [MEDIUM] score_contact (ml_score replace) vs ingest enrich sentiment (ml_score["signals"] write)
   — two uncoordinated writers to contact.ml_score JSONB, last-writer-wins, can drop signals.
9. [LOW] followup_sequences.py:107 — dedupe via `ActivityEvent.meta.like('%"deal_id": "<uuid>"%')`
   string match on a JSON-in-VARCHAR column; brittle, no index, full scan.
10.[LOW] All workers create per-task `create_async_engine` without pool_pre_ping (vs database.py
   which has it) → stale-connection errors against the Supabase pooler after idle.
11.[LOW] asyncio.get_event_loop() (deprecated on 3.11) reused across task runs → pool accumulation,
   future RuntimeError risk.

---

## 7. Inconsistencies (homogenization targets)

- FOUR near-identical `_get_async_session`/`_make_session`/`_get_session` helpers copy-pasted
  across pipeline.py, score_contact.py, embed_contacts.py, deal_health_worker.py,
  enrich_contact.py, followup_sequences.py, transcribe.py, ingest.py, slack_ingest.py, pm_agent.py
  — with DIVERGENT logic: some fall back to SUPABASE_URL, some don't (pm_agent.py:31, ingest.py:39
  do NOT fall back; slack_ingest.py:31-38 has the most complete rewrite). None reuse
  app.database.engine. Should be ONE shared factory.
- Periodic-task pattern split: followup_sequences & pm_agent fan out over all workspaces internally
  (take no args, work from beat). pipeline & deal_health are workspace-scoped (take workspace_id,
  CRASH from beat). Pick ONE pattern. Either give the latter a no-arg "all workspaces" wrapper or
  have beat enqueue per-workspace.
- Claude model string drift: `claude-haiku-4-5` (ingest.py, sentiment.py, extraction.py) vs
  `claude-haiku-4-5-20251001` (enrich_contact.py:122, followup_sequences.py:50). Sonnet is
  consistently `claude-sonnet-4-6`. Centralize model IDs.
- anthropic client style drift: sync `Anthropic` (enrich_contact, transcribe, ingest reprocess
  path) vs async `AsyncAnthropic` (ingest live path, followup_sequences). No rule.
- Auth-failure handling: slack_ingest persists SlackAuthError as ActivityEvent + refuses to bump
  last_sync (gold standard). gmail ingest just logs and breaks, then STILL bumps last_sync →
  masks the failure. Should mirror Slack's approach.
- enrich_message (ingest.py:338) is the shared enrichment path BUT reprocess_workspace_messages
  (ingest.py:443) re-implements the same extract/sentiment/clarity block inline instead of calling
  it — two copies that already differ (reprocess deletes tasks first; enrich does not). Collapse.
- Gmail push webhook (gmail.py:451) passes the request-scoped `db` into a FastAPI
  `background_tasks.add_task(_trigger_ingest_for_email, email, db)`; that session is closed when the
  request returns → background task runs on a closed session (latent; adjacent to workers).
- Two distinct "PM" concepts collide: pm_agent.py "PM Agent" = deployment-health monitor, while
  the Project/Task models are product PM features. Naming will confuse.

---

## 8. Data flow

Triggers → Celery (Redis broker) → worker:
- Gmail: routers/gmail.py manual sync OR Pub/Sub push webhook → process_gmail_sync.delay(connector_id)
  → GmailClient (Gmail REST) fetch → Postgres `messages` → per-message enrich_message.delay →
  extraction/sentiment/clarity services (Claude) → `tasks`, `clarity_scores`, contacts.ml_score.
- Slack: routers/slack.py → process_slack_sync.delay → Slack Web API → `messages` → enrich_message.
- Calls: routers/calls.py upload → tempfile → transcribe_call.delay(call_id, path) → Whisper +
  Claude Sonnet → `call_summaries`.
- Scheduled (beat→Redis→worker): pipeline.optimize_pipeline (BROKEN), deal_health.compute_deal_health
  (BROKEN), followup_sequences.check_stale_deals_hitl (→ Claude draft → Slack Block Kit →
  activity_events hitl_pending → slack_interactions resolves → email send), pm_agent.run_health_check
  (→ activity_events).
Datastores: Postgres (Supabase, asyncpg) for all persistence + pgvector embeddings; Redis as
Celery broker+backend; external APIs: Gmail, Slack, Anthropic, Hunter.io, OpenAI-Whisper (local).
All DB access is workspace_id-scoped in queries (multi-tenant by column), EXCEPT enrich_contact._run
(ingest of contact) which loads Contact by id WITHOUT workspace filter (enrich_contact.py:142) and
_run_enrich_message loads Message by id WITHOUT workspace filter (ingest.py:357) and Contact by id
without ws filter (ingest.py:389-391) — these run from trusted internal enqueue so the id is already
ws-derived, but they are not defense-in-depth scoped.

## 9. External deps
fastapi, sqlalchemy[asyncio], asyncpg, celery[redis], httpx, anthropic==0.34.2, pgvector,
sentence-transformers, openai-whisper, flower, slowapi. System: ffmpeg, libgomp1 (Dockerfile).
