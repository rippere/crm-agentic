# Phase 1 — API Domain Routers Audit (contacts, deals, tasks, projects, search, messages, events)

Repo: `/tmp/crm-signup-fix` (git worktree of production master; HEAD on branch `fix/signup-confirm-redirect`, top commit `429da2f`).
Scope files (all under `apps/api/app/routers/`): contacts.py (750 LOC), deals.py (576), tasks.py (216), projects.py (207), search.py (148), messages.py (159), events.py (152).
Read in full. Also read supporting: dependencies.py, database.py, services/auth.py, services/deal_health.py, main.py, and models (contact, deal, task, project, message, clarity_score, activity_event, user). Compared against sibling routers calls.py, workspaces.py, agents.py, ai.py for homogenization.

---

## 1. Architecture / data flow

- **Auth + tenancy model.** Every endpoint depends on `get_current_user` (dependencies.py:18) which verifies a Supabase ES256/RS256 JWT via JWKS (services/auth.py), looks up `User` by `supabase_uid`, and **auto-provisions** the user + workspace on first hit. Tenant scoping is enforced *manually, per-endpoint* by the line `if current_user.workspace_id != workspace_id: raise 403`. There is NO row-level security, NO dependency that injects the scoped workspace, NO middleware — it is copy-pasted into every handler. `get_workspace_id` (dependencies.py:97) exists but is unused by any router (grep: zero hits).
- **Persistence.** SQLAlchemy async (`AsyncSession` from `get_db`, database.py:19). One session per request via `async_sessionmaker(expire_on_commit=False)`. Writes follow add → flush/commit → refresh. Most write endpoints also append an `ActivityEvent` row in the same transaction.
- **Datastore.** Postgres (asyncpg) for all CRUD; pgvector (`Vector(384)`) on `contacts.embedding` for semantic search (search.py uses raw `text()` SQL with `<=>` cosine distance). A secondary path in contacts.py reads from **Supabase REST** (`app.services.supabase_rest.get_row`) as a fallback when a contact is not found in local Postgres (compose_email, enrich) — implies a dual-write/dual-read split between local PG and Supabase that exists nowhere else.
- **Async work.** Several endpoints enqueue Celery tasks (`.delay(...)`) and return `{job_id, status:"queued"}`: contacts score/enrich, deals health/optimize, search embed, messages reprocess. Job status is polled via `agents.py GET /jobs/{job_id}`.
- **External APIs in the request path (synchronous):** Anthropic (`compose_email` uses **blocking** `_anthropic.Anthropic(...).messages.create` on the event loop; `pre_meeting_brief` uses `AsyncAnthropic`; messages score-clarity calls `score_clarity` service). Gmail send (contacts send-email).
- **Realtime.** events.py exposes an SSE stream (`GET /workspaces/{id}/events`) that holds the request's `AsyncSession` open and polls `activity_events` every 3s in a `while not request.is_disconnected()` loop.

---

## 2. CLAIMS (assertions made in code/docstrings/naming — for the claims register)

| # | Claim | Source | Verdict |
|---|-------|--------|---------|
| C1 | "search.router must precede contacts.router: GET /contacts/search would otherwise be shadowed by GET /contacts/{contact_id}" | main.py:116-120 | TRUE — main.py mounts search before contacts. But fragile (ordering-by-comment). |
| C2 | Semantic search "Falls back to ILIKE name/company search if no embeddings exist yet" | search.py:6 docstring | PARTLY MISLEADING — fallback uses `func.lower(col).contains(...)` (LIKE with auto-escaped wildcards), not ILIKE, and includes email too. Behaves differently from contacts.py list search which uses real `ilike("%q%")`. |
| C3 | upsert_task_by_external / upsert_project_by_external are "Idempotent create-or-update keyed on (workspace_id, external_id)" | tasks.py:129, projects.py:159 | PLAUSIBLE in code, but NOT enforced by a DB unique constraint — see R-? . Idempotency relies solely on the SELECT-then-insert, which races. |
| C4 | delete_contact "Delete a contact and all cascade-linked records" | contacts.py:442 | TRUE via FK ondelete: deals→SET NULL, messages→SET NULL, tasks→SET NULL (contact_id nullable). So "cascade-linked records" are NOT deleted, they are orphaned (contact_id set null). Docstring overstates/ misleads — nothing is cascade-*deleted*. |
| C5 | reprocess_messages is a "non-destructive re-enrichment + relevance-flagging pass" | messages.py:150 | Unverifiable here (logic is in worker); claim is about worker behavior. |
| C6 | deals/history returns "Monthly closed-won revenue for the last N months" | deals.py:166 | BUGGY — buckets keyed by 3-letter month name only; 13–24 month ranges collide same month across years; bucket-seed loop (now−30*i) and fill loop (ts.month) can disagree. See R5. |
| C7 | probability-trend is "synthetic from current score + deal age", "Deterministic jitter ... stable across requests" | deals.py:550,570 | PARTLY FALSE — uses Python builtin `hash(str(deal_id)+str(i))`, which is salted per-process (PYTHONHASHSEED) and NOT stable across workers/restarts. "stable across requests" only holds within one process lifetime. See R6. |
| C8 | score-clarity persists `model_used="claude-sonnet-4-6"` | messages.py:100 | TRUE as written, but the actual model is decided inside `score_clarity` service — the stored string is hardcoded and may not match the model that ran. Claim is a guess, not measured. |
| C9 | ClarityScoreResponse / messages list expose clarity + tasks eager-loaded | messages.py:127-130 | TRUE — uses `selectinload` (no N+1 here). Good. |
| C10 | events SSE "polling every 3 seconds" / seeds cursor at connection time | events.py:3,112 | TRUE in code. |
| C11 | bulk_deal_action caps "Maximum 100 deals per bulk operation" | deals.py:488 | TRUE. |
| C12 | compose_email docstring: "using Claude Sonnet" + TODO "needs ANTHROPIC_API_KEY in env" | contacts.py:265-266 | FALSE/STALE — model is actually `claude-haiku-4-5-20251001` (contacts.py:310), not Sonnet. TODO left in shipped code. |
| C13 | contacts create/update validates status ∈ {lead,prospect,customer,churned} | contacts.py:64,408,482 | TRUE for those 3 endpoints; CSV import (contacts.py:188) silently coerces bad status → "lead" instead of erroring. |
| C14 | require_admin "Raise 403 if the user's role is not 'admin'" (deals health/optimize) | dependencies.py:88, deals.py:101,254 | TECHNICALLY TRUE but VACUOUS — auto-provision sets every self-serve user to role="admin" (dependencies.py:76). So the admin gate gates nothing for normal users. See R2. |

---

## 3. RISKS (evidence-backed)

### Multi-tenancy / auth (auto high+)

- **R1 (HIGH) — Tenant isolation is manual and unenforced by construction; one missing line = cross-tenant breach.** Every handler re-implements `if current_user.workspace_id != workspace_id: 403`. There is no defense-in-depth (no RLS, no scoped-session dependency). agents.py shows the *other* convention (`Agent.workspace_id == current_user.workspace_id`, no path workspace_id at all) — i.e. two different tenancy styles coexist, raising the odds a future endpoint forgets the check. Evidence: contacts.py:61/104/129/…, agents.py:45/58 (different style), dependencies.py has unused `get_workspace_id` that was presumably meant to centralize this.
- **R2 (HIGH) — `require_admin` is effectively a no-op for self-provisioned tenants.** dependencies.py:76 hardcodes `role="admin"` for every auto-provisioned user, while the User model default is `"member"` (models/user.py:18). The only admin-gated endpoints in scope — `POST /deals/health` and `POST /pipeline/optimize` (deals.py:101,254) — therefore impose no real privilege boundary. Either the gate is security theater or the auto-provision role is wrong; they contradict each other.
- **R3 (MEDIUM, tenancy-adjacent) — Auto-provisioning trusts client-supplied `workspace_id` from JWT `user_metadata`.** dependencies.py:46-69: on first hit, if `user_metadata.workspace_id` names a workspace that doesn't exist yet, the code **creates** that workspace and binds the user to it as admin. Supabase user_metadata is user-writable in many configs; if so, a user could steer themselves into / create an arbitrary workspace id. Needs confirmation of whether user_metadata is server-controlled, but the trust boundary is worth flagging.

### Correctness / reliability

- **R4 (HIGH) — `get_db` never rolls back; a failed write poisons the session and (for SSE) hangs forever.** database.py:19-21 yields the session inside `async with` with no try/except/rollback. For normal requests a failed `commit()` raises and the session is discarded at context exit (tolerable), but: (a) any handler that catches an exception after a partial flush and continues will operate on a dirty session; (b) the **events.py SSE** generator (events.py:122-143) reuses the *same* long-lived session in a loop and wraps the query in `except Exception: yield ": heartbeat"`. A transient DB error there leaves the session in a failed transaction state, so every subsequent 3s poll throws and is swallowed as a heartbeat — the client silently receives no events until it reconnects. No `rollback()` exists anywhere in the codebase (grep: 0 hits).
- **R5 (MEDIUM) — `deals_history` month bucketing is wrong for >12 months and can mis-bucket.** deals.py:178-195: buckets are keyed by `month_abbr[...]` (Jan..Dec) with no year. With `months` up to 24 (validated `le=24`, deals.py:162), two same-named months in different years collapse into one bucket. Also the seed loop keys on `now - 30*i` month while the fill loop keys on `deal.updated_at.month` and only adds `if key in buckets`; near month boundaries (30-day approximation) a legitimately-in-range deal can be silently dropped or land in the wrong month. Revenue chart can under/over-report.
- **R6 (MEDIUM) — `probability-trend` uses process-salted `hash()` for "deterministic" jitter.** deals.py:571: `hash(str(deal_id)+str(i))` depends on PYTHONHASHSEED → different per worker process and across restarts. The docstring claims stability "across requests" (deals.py:570); in a multi-worker deploy the same deal renders different trend lines depending on which worker serves it. Should use hashlib or a seeded PRNG.
- **R7 (MEDIUM) — `stale_deals` reports misleading signals.** deals.py:142-146 calls `compute_health(..., last_message_at=None)` unconditionally, so every stale deal gets a "No messages linked (−20 pts)" signal regardless of actual message history, and the recomputed signals can disagree with the stored `health_score` shown alongside them. The real health worker presumably passes a real `last_message_at`; this endpoint fakes it.
- **R8 (MEDIUM) — `compose_email` blocks the event loop.** contacts.py:308-314 instantiates the **synchronous** `anthropic.Anthropic` client and calls `.messages.create(...)` (no `await`) inside an async handler. This blocks the entire event loop for the duration of the LLM call (seconds). `pre_meeting_brief` (contacts.py:738) correctly uses `AsyncAnthropic`. Inconsistent and a real latency/throughput hazard under load.
- **R9 (MEDIUM) — No pagination on any list/export endpoint → unbounded full-table reads per tenant.** `list_contacts` (contacts.py:96-119), `list_deals` (deals.py:42-60), `list_messages` (messages.py:115-134, also eager-loads clarity_score+tasks for *all* messages), `list_projects` (projects.py:67), `list_tasks` (tasks.py:67) take no limit/offset and return every row for the workspace. `export_contacts_csv` / `export_deals_csv` likewise load all rows into memory then stream a single `iter([buf.getvalue()])` (contacts.py:147, deals.py:91) — not actually streamed. Large tenants → slow responses, memory spikes, and a cheap DoS vector. (By contrast calls.py:117, events.py:59, ai.py:66 do cap with `.limit(...)`, so the inconsistency is internal.)
- **R10 (LOW/MEDIUM) — `contact_timeline` fan-out + unbounded.** contacts.py:566-656 issues 4 separate unbounded queries (messages, calls, deals, activity events) and merges in Python with no limit. The activity-event match uses `ActivityEvent.meta.like(f"%contact:{contact_id}%")` (contacts.py:641) — a non-sargable leading-wildcard LIKE on an unindexed `meta` String column; full scan of activity_events per call.
- **R11 (LOW) — `deal_timeline` matches activity by fuzzy title substring.** deals.py:404-411 correlates events to a deal via `ActivityEvent.description.ilike(f"%{deal.title}%") OR type=='deal_moved'`. Any deal whose title is a substring of another deal's title (or empty title) pulls in unrelated events; `type=='deal_moved'` with no description filter returns *every* deal-moved event in the workspace. Timeline is approximate/incorrect, not authoritative.
- **R12 (LOW) — CSV import has no row cap / size guard and commits all-or-nothing at the end.** contacts.py:154-222 reads the whole upload (`await file.read()`), iterates unlimited rows, and does one `commit()`. A large file → memory blow-up; one bad row mid-stream that triggers a DB error loses the entire batch (and the per-row upsert SELECT makes it O(n) round-trips → N+1 on import). calls.py enforces `MAX_UPLOAD_MB`; contacts import does not.
- **R13 (LOW) — CSV export writes a dict into the `ml_score` column.** contacts.py:141 writes `c.ml_score or 0`, but `ml_score` is a JSONB dict (model contact.py:24, e.g. `{"value":50,...}`). The exported CSV cell will contain a Python dict repr, not a score number. Mismatch with the column header `ml_score`.
- **R14 (LOW) — SSE shares one DB session across a long-lived connection and sleeps 3s on the request worker.** events.py:122-143 (see also R4). With many concurrent dashboards this pins a connection-from-pool per open tab for the tab's lifetime; pool exhaustion under modest fan-out. No `Last-Event-ID` resume, no max-duration.

---

## 4. INCONSISTENCIES (for homogenization — the user wants this product homogenized)

1. **Tenant-scope idiom differs by router.** Domain routers (contacts/deals/tasks/projects/messages/events/calls/workspaces) take `{workspace_id}` in the path and check `current_user.workspace_id != workspace_id`. agents.py takes **no** path workspace_id and filters by `current_user.workspace_id` directly. Two mental models for the same concept; `get_workspace_id` dependency exists but is used by neither. Pick one (recommended: a `WorkspaceScope` dependency).
2. **Two different "search contacts" implementations.** search.py `semantic_search` fallback uses `func.lower(col).contains(...)` over name/company/email; contacts.py `list_contacts` uses `or_(col.ilike("%q%"))` over name/email/company. Different operators (contains vs ilike), different wildcard semantics (contains auto-escapes user `%`/`_`; the ilike path treats them as wildcards), different return shapes (search returns dicts with `similarity`; list returns `ContactResponse`). Duplicated, divergent logic for one user-facing feature.
3. **HTTP verb for update is inconsistent.** Contacts/deals/projects/workspaces use `PATCH` for partial update; tasks uses `PUT` for `update_task` (tasks.py:185) *and* `PUT` for the external upsert. Projects upsert is `PUT .../by-external/...` (consistent w/ tasks) but project partial update is `PATCH`. Mixed PUT/PATCH semantics across resources.
4. **Status-code / response style for DELETE is inconsistent.** contacts/deals/tasks declare `status_code=204` on the decorator and return `None`; projects.py and calls.py instead return an explicit `Response(status_code=204)` (projects.py:207, calls.py:193). events/agents have their own shapes. Same outcome, 3 spellings.
5. **List ordering inconsistent.** tasks/projects/messages/activity order newest-first (`created_at.desc()` / `received_at.desc()`); `list_contacts` (contacts.py:117) and `list_deals` (deals.py:58) return **unordered** (DB default order). User-facing lists will appear in arbitrary order for contacts/deals but sorted elsewhere.
6. **`"all"` sentinel handling is ad hoc.** Only deals.py:54 and contacts.py:108 special-case `status/stage == "all"`. Tasks/projects filters don't. Frontend contract for "no filter" is implicit and uneven.
7. **ActivityEvent `type` taxonomy is abused.** `update_contact_status` writes `type="deal_moved"` for a *contact* status change (contacts.py:498) — wrong domain. Contact create/update/delete use `contact_created/contact_updated/contact_deleted` but the status change reuses a deal event type. Event types are free-form strings (no enum), so the activity feed/timeline filtering is unreliable. (deal_timeline R11 keys off exactly this string.)
8. **Local DB vs Supabase REST dual-source only in contacts.** compose_email/enrich (contacts.py:277-286, 351) fall back to Supabase REST when a row is missing locally; no other router does this. Implies an incomplete/uncertain migration between local Postgres and Supabase as source of truth — a latent split-brain. Worth a decision: which store is authoritative.
9. **Validation lives in handlers as inline sets, duplicated.** `allowed_statuses = {"lead","prospect","customer","churned"}` is redefined 3× in contacts.py (64, 408, 482) and as `_VALID_STAGES` once in deals.py (459). No shared enum / Pydantic `Literal` (deals bulk uses `Literal` for action but not for stage). No model-level CHECK constraints. CSV import diverges further by *coercing* invalid status to a default instead of rejecting.
10. **Rate-limit coverage is uneven.** LLM/expensive endpoints mostly carry `@limiter.limit`, but `create_contact`, `update_contact`, `create_deal`, bulk ops, list/export, reprocess_messages, embed (non-`-all`), pipeline/optimize have **no** limiter. The `/embed` vs `/embed-all` pair (search.py:112 vs 127) is itself duplicated (same Celery task), one limited, one not.
11. **Idempotent upserts lack a DB unique constraint.** Task.external_id / Project.external_id are plain nullable String columns (models/task.py:17, project.py:17) with no unique index on `(workspace_id, external_id)`. The "idempotent" upserts (tasks.py:121, projects.py:151) do SELECT-then-insert and will create duplicates under concurrent sync runs. The docstrings promise idempotency the schema doesn't guarantee.
12. **Pydantic response timestamp typing is inconsistent.** Some responses type `created_at: datetime` (deals/contacts/events), tasks/projects/messages hand-serialize to ISO `str` via a `_to_response` helper, and projects requires `created_at: str` (non-optional) while others allow `| None`. Three serialization conventions for timestamps.
13. **`import insert` (contacts.py:11) is unused** — dead import; only `or_`, `select` are used. Minor, but indicative of churn.

---

## 5. OPEN QUESTIONS (for synthesizer / Phase 2 stress test)

- Is Supabase `user_metadata.workspace_id` server-controlled or user-writable? Determines whether R3 is a real privilege-escalation/tenant-creation vector.
- Is the deployment multi-worker (gunicorn/uvicorn workers >1)? If yes, R6 (hash jitter) and R4/R14 (per-connection SSE sessions, pool sizing) bite harder.
- Is there any DB-level RLS on Supabase that backstops the manual `workspace_id` checks, or is the FastAPI check the only gate? (Strongly affects R1 severity.)
- Authoritative store for contacts: local Postgres or Supabase REST? The dual-read fallback (Inconsistency 8) suggests this is unsettled.
- Are there alembic migrations adding unique constraints on `(workspace_id, external_id)` not visible in the model files? (R/Inconsistency 11.)

---

## 6. Things that are actually GOOD (so synthesis doesn't over-rotate on negatives)

- messages.py list + score-clarity use `selectinload` — no N+1 on the messages feed.
- deals bulk action validates action via `Literal`, caps at 100, validates stage.
- Consistent 403/404 pattern and HTTPException usage across all in-scope handlers.
- search.py raw-SQL pgvector path correctly parameterizes (`:vec`,`:wid`,`:lim`) — no SQL injection.
- JWT verification (services/auth.py) is sound: JWKS-based, requires sub/exp/iat, handles expiry.
- Route ordering within contacts.py/deals.py correctly places static subpaths before `/{id}`.
