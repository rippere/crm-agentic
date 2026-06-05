# NovaCRM — DB Schema / Migrations / RLS Audit (Phase 1)

Scope: `/tmp/crm-signup-fix/apps/api/migrations/*.sql` (13 files: 000–011 + init_docker.sql)
Cross-referenced against: `apps/api/app/models/*.py`, `app/database.py`, `app/config.py`,
`app/dependencies.py`, `app/services/supabase_rest.py`, `app/services/auth.py`, routers,
`docker-compose.yml`, `DEPLOY.md`, `.env.example`.

Worktree: branch `fix/signup-confirm-redirect`, HEAD `429da2f` (worktree of `crm-agentic` master line / deployed code).

---

## 0. TL;DR — the headline finding

**RLS is enabled in the schema but is NEVER enforced at runtime, because every database path uses a
superuser / service-role credential that bypasses RLS by design.**

- `app/database.py` opens a SQLAlchemy asyncpg engine on `settings.DATABASE_URL`.
- `DATABASE_URL` is documented (DEPLOY.md L43, L118–121) as the Supabase **Session-mode pooler URL connecting as the `postgres` role** (`postgresql+asyncpg://postgres.[ref]:...`). In Postgres, the `postgres` role is the table owner / superuser, and **RLS does not apply to table owners or BYPASSRLS roles unless `FORCE ROW LEVEL SECURITY` is set.** No migration ever runs `ALTER TABLE ... FORCE ROW LEVEL SECURITY`.
- The REST fallback (`services/supabase_rest.py`) authenticates with `SUPABASE_SERVICE_ROLE_KEY` (L14, L19–20). The service-role key is explicitly a **RLS-bypassing** credential in Supabase.
- The user's own JWT is verified (`services/auth.py`) ONLY to resolve `supabase_uid → User.workspace_id`. The JWT is **never** used to open a DB connection. So `auth.uid()` inside every RLS policy is effectively NULL/irrelevant at the data tier.

Net effect: **tenant isolation is 100% application-enforced** via the `if current_user.workspace_id != workspace_id: 403` guard repeated in each router, plus `.where(Model.workspace_id == workspace_id)` on every query. The RLS policies in 001/006/008 are **defense-in-depth that is currently inert**. Any router that forgets the guard or the WHERE clause = cross-tenant leak with **no DB backstop**. (Routers sampled all DO carry the guard; that's the only thing preventing leakage.)

This is the single most important thing for the synthesizer: the elaborate RLS work (esp. migration 008's "fix") buys nothing at runtime given the current connection model. It is not wrong to have it, but it is **falsely reassuring** — the comments in 008 imply RLS now "works", when in fact no query is ever subject to it.

---

## 1. File-by-file

### 000_original_schema.sql — LEGACY / single-tenant (pre-workspace)
- 4 tables: contacts, deals, agents, activity_events. **No workspace_id, no users, no RLS.**
- `contacts.email TEXT UNIQUE NOT NULL` (GLOBAL unique), `name/company NOT NULL`.
- `agents.type TEXT NOT NULL UNIQUE` (global unique on type).
- Uses `pgcrypto` for `gen_random_uuid()`.
- Superseded entirely by 001. Appears to be dead/historical but still in the dir (drift risk — see §3).

### 001_unified_schema.sql — the real multi-tenant base (11 tables)
- Adds workspaces, users, connectors, messages, tasks, metric_templates, clarity_scores; re-defines contacts/deals/agents/activity_events WITH `workspace_id NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE`.
- **Constraint drift vs 000:**
  - `contacts.email` → nullable, and unique scope changed to `UNIQUE (workspace_id, email)` (per-tenant). `name/company/role` now nullable.
  - `agents.type` → nullable, **no UNIQUE** (needed because seed inserts 6 agents per workspace; a global unique on `type` would break multi-workspace seeding).
- RLS: `ENABLE ROW LEVEL SECURITY` on all 11 tables (L160–170). Policies L175–205.
  - workspaces: explicit INSERT (`WITH CHECK (true)`) + SELECT (own ws). No UPDATE/DELETE policy.
  - users: INSERT/SELECT own row (`supabase_uid = auth.uid()`). No UPDATE/DELETE.
  - 9 other tables: a single `FOR ALL` policy `USING (workspace_id = (SELECT workspace_id FROM users WHERE supabase_uid = auth.uid()))`. **No `WITH CHECK`** → under RLS these would block reads of other tenants but the `USING` clause alone does NOT constrain INSERT column values (WITH CHECK governs INSERT/UPDATE row validity); a malicious INSERT with a foreign workspace_id is not blocked by a USING-only policy. Moot today because RLS is bypassed, but relevant once/if they switch to anon-key + JWT.
  - **`call_summaries` is created in 004, which never enables RLS or adds a policy → that table has NO RLS at all even in the Supabase model.** Same story would apply to any future table that forgets it.
- Indexes: messages(workspace_id,processed), messages(contact_id), tasks(workspace_id,status), connectors(workspace_id,service). Note: at this point most FK columns (contacts.workspace_id, agents.workspace_id, etc.) are UN-indexed; 008 backfills them.
- `clarity_scores.model_used` DEFAULT `'claude-sonnet-4-6'` (also in init_docker). Hard-coded model name baked into schema default — drift magnet when models change.

### 002_vector_embeddings.sql
- `CREATE EXTENSION vector` + `contacts.embedding vector(384)` + HNSW index (m=16, ef_construction=64), cosine ops.
- Matches `models/contact.py` (`Vector(384)`) and `routers/search.py` (cosine `<=>`). Consistent.

### 003_deal_health.sql
- `deals.health_score INT DEFAULT 100 CHECK 0..100` + `deals.stage_changed_at TIMESTAMPTZ DEFAULT NOW()`.
- Index `idx_deals_workspace_health (workspace_id, health_score)`.
- Matches `models/deal.py`. Consistent.

### 004_call_summaries.sql
- New table call_summaries (workspace_id, contact_id, transcript, summary, action_items JSONB, model_used DEFAULT 'whisper-base', etc.).
- Indexes: (workspace_id, call_date DESC), (contact_id).
- **MISSING: no `ENABLE ROW LEVEL SECURITY`, no policy.** Inconsistent with the 001 pattern. (Inert today due to service-role bypass, but a real gap in the stated security model.)

### 005_activity_severity_error.sql
- Drops + re-adds `activity_events_severity_check` to include `'error'`.
- Comment claims `slack_interactions.py` writes `severity='error'` on HITL failures and the old CHECK caused a constraint violation on every HITL error path. **Plausible/verifiable claim** (file exists; see §4 claims). DEPLOY.md L19, L220–222 reinforce this as a required prod migration.
- **init_docker.sql does NOT include 'error'** in its activity_events CHECK (L93 still `('info','success','warning')`) → drift between the two schema sources (see §3).

### 006_projects_table.sql — introduces a BROKEN RLS policy
- projects table (workspace_id, name, status CHECK active/completed/archived, contact_id).
- `CREATE POLICY projects_policy USING (workspace_id::text = current_setting('app.workspace_id', true))`.
- **`app.workspace_id` GUC is NEVER set anywhere in the codebase** (grep confirms: only references are this line + 008's comment). So even if RLS were enforced, this policy evaluates against an unset GUC → `current_setting(..., true)` returns NULL → policy matches nothing → projects invisible. This is the bug 008 documents.

### 007_project_tasks.sql
- `tasks.project_id UUID REFERENCES projects(id) ON DELETE SET NULL` + `idx_tasks_project_id`.
- **DUPLICATE of 011** (see below). 007 and 011 add the SAME column and a same-purpose index. Idempotent guards make it harmless to run both, but it's redundant/confusing — and 011's existence implies 007 was believed un-applied in prod.

### 008_rls_indexes.sql — "WS-K" RLS + index hygiene
- Recreates projects_policy to the auth.uid() pattern (fixing 006's dead GUC policy) — but see §0: still inert at runtime because connection is service-role/superuser.
- Adds the missing workspace_id FK indexes: clarity_scores, activity_events, agents, metric_templates, contacts, projects.
- Comment claims messages/tasks/connectors/deals/call_summaries already had theirs "in earlier migrations." **Partially inaccurate:** deals' workspace index is a COMPOSITE `(workspace_id, health_score)` (003) and call_summaries' is `(workspace_id, call_date DESC)` (004) — those serve workspace-prefixed lookups, OK. But there is **no standalone `messages(workspace_id)` index**; messages only has `(workspace_id, processed)` (001) — fine as a left-prefix. So the claim is roughly true in effect (left-prefix coverage) but loosely worded.

### 009_message_relevant.sql
- `messages.relevant BOOLEAN` (nullable; NULL = "not yet evaluated"). Matches `models/message.py` L24. Consistent.

### 010_task_project_external_id.sql
- `tasks.external_id TEXT` + `projects.external_id TEXT` + partial unique indexes `(workspace_id, external_id) WHERE external_id IS NOT NULL`.
- Matches models (task.py L17, project.py L17). Consistent. Good pattern (mirrors messages.external_id dedup).

### 011_tasks_project_id.sql — adds tasks.project_id (AGAIN)
- Same `ALTER TABLE tasks ADD COLUMN IF NOT EXISTS project_id ...` as 007, plus `idx_tasks_project`.
- Comment: "no migration ever added it ... any insert/select referencing project_id 500'd in prod — tasks were effectively uninsertable." This DIRECTLY CONTRADICTS 007 which already adds the column. Strong signal that **007 was never applied to production** (consistent with DEPLOY.md only listing 001–005). See §3.

### init_docker.sql — self-hosted Postgres (Docker), "no Supabase RLS"
- Single consolidated schema: all 13 tables incl. embedding, health_score, call_summaries, in one file; HNSW index; seed block creating "NovaCRM Demo" workspace + 6 seed agents (with hard-coded model names + accuracy numbers).
- Uses `uuid-ossp` extension (vs 000's `pgcrypto`) yet still calls `gen_random_uuid()` (which is pgcrypto/pg13+ core, not uuid-ossp's `uuid_generate_v4()`) — extension declared doesn't match the function used (works on pg16 because gen_random_uuid is built-in, but the `uuid-ossp` CREATE EXTENSION is vestigial/misleading).
- **No RLS at all** (intentional, per header). No projects/metric_templates? — projects table is ABSENT from init_docker.sql entirely (it only has the 11 base + call_summaries = 12 tables; projects, and thus tasks.project_id/external_id and projects.external_id, are MISSING). So **Docker local schema is missing projects, tasks.project_id, tasks.external_id, projects.external_id, messages.relevant** → diverges from the SQLAlchemy models. A Docker-based dev/test env would 500 on the exact `project_id`/`external_id`/`relevant` paths that 009/010/011 were written to fix on Supabase. Major two-source drift.
- activity_events severity CHECK still lacks 'error' (see 005). So Docker reproduces the original HITL-error constraint-violation bug.
- Seed numbers (accuracy 94.2/87.1/91.8/89.5/85.3/92.0, tasks_today counts) are fabricated demo values — fine for a demo, but these are the "metrics" surfaced as if real.

---

## 2. Data flow (how data actually moves)

1. Client (Next.js, anon key) authenticates with Supabase Auth → gets ES256 user JWT.
2. Client calls FastAPI with `Authorization: Bearer <jwt>`.
3. `dependencies.get_current_user` verifies JWT via JWKS (auth.py), extracts `sub`=supabase_uid, looks up `users` row (auto-provisions user+workspace on first hit, role hard-coded `'admin'`).
4. Routers derive `workspace_id` from the User row (`get_workspace_id`) and enforce tenancy in Python: `if current_user.workspace_id != path_workspace_id: 403`, plus `.where(Model.workspace_id == ...)`.
5. All reads/writes go through SQLAlchemy asyncpg as the **postgres/pooler role** → RLS bypassed. A secondary REST path (`supabase_rest.get_row/list_rows`) hits Supabase PostgREST with the **service_role** key → RLS bypassed. (REST path is used by contacts.py as a cloud fallback.)
6. Celery workers connect directly via `DATABASE_URL`/`SUPABASE_URL` (asyncpg) — also RLS-bypassing; they operate cross-workspace by design (e.g., nightly pipeline, embeddings).

Datastores: Supabase Postgres (prod, pgvector) OR self-hosted pg16 (Docker). Redis (Celery broker). Supabase Auth (identity). External: Anthropic, Gmail/Google OAuth, Slack, Hunter, Whisper (transcription).

---

## 3. Inconsistencies / drift (HOMOGENIZATION targets)

1. **Two competing schema sources that disagree:** numbered migrations (Supabase prod) vs `init_docker.sql` (Docker). init_docker is MISSING: projects table, tasks.project_id, tasks.external_id, projects.external_id, messages.relevant, and the 'error' severity value. → Docker schema cannot satisfy the SQLAlchemy models; prod and local diverge. Single source of truth needed (e.g., generate init_docker from the migration chain, or adopt Alembic).
2. **Duplicate migrations 007 and 011** both add `tasks.project_id` (+ near-duplicate indexes `idx_tasks_project_id` vs `idx_tasks_project`). 011's comment asserts the column never existed in prod → implies 007 was never run. Migration chain is not reliably applied in order; no migration tracking table (no Alembic/version table) — they're hand-run via Supabase SQL Editor (DEPLOY.md L102).
3. **Undocumented prod migrations:** DEPLOY.md "run in order" list stops at 005. 006–011 are NOT listed anywhere in DEPLOY.md. Operationally these may or may not be applied on prod → schema state is ambiguous (this is exactly how 011 happened).
4. **RLS pattern inconsistency across tables:** 001 uses `auth.uid()` subquery; 006 used `current_setting('app.workspace_id')` (dead); 008 re-homogenizes projects back to auth.uid(). call_summaries (004) has NO RLS at all. Even post-008 the family is uneven (no WITH CHECK clauses; no UPDATE/DELETE policies on workspaces/users).
5. **RLS is inert vs the connection model** — the biggest "disagreement": schema says "multi-tenant via RLS," runtime says "multi-tenant via Python ifs." The two security stories don't match. Either FORCE RLS + connect with the user JWT (anon key + `request.jwt`), or stop pretending RLS is the boundary and document app-tier as the boundary.
6. **Extension mismatch:** 000 uses `pgcrypto`; init_docker uses `uuid-ossp` but still calls `gen_random_uuid()` (a pgcrypto/core function). Cosmetic but a footgun on non-pg16.
7. **Hard-coded model names in schema defaults** (`clarity_scores.model_used = 'claude-sonnet-4-6'`, `call_summaries.model_used = 'whisper-base'`, seed agents' models). These drift the moment the app upgrades models; they belong in config, not DDL defaults.
8. **Legacy 000_original_schema.sql** is single-tenant and contradicts 001 (global UNIQUE email, NOT NULL name/company, agents.type UNIQUE). It's dead but present; running it after 001 is a no-op due to IF NOT EXISTS but it misleads readers. Candidate for deletion/archival.
9. **`agents.type` semantics:** 000 had it globally UNIQUE; 001 dropped uniqueness; seed + workers look up agents by `type` within a workspace. No `UNIQUE (workspace_id, type)` exists, so duplicate agent types per workspace are possible (seed runs once, but POST /agents or re-seed could dupe).

---

## 4. Claims this area makes (for the claims register)

- "Unified 11-table schema" (001 header) — TRUE (11 tables in 001; project/call_summaries added later make 13 total).
- 005/DEPLOY: "slack_interactions.py writes severity='error'; original CHECK caused a constraint violation on every HITL error path" — code file exists; CHECK in 001/init lacks 'error'; consistent → LOOKS TRUE.
- 008 comment: "006 policy relied on app.workspace_id GUC that is never configured at runtime — so the policy never matched" — VERIFIED TRUE (grep: GUC never set).
- 008 comment: messages/tasks/connectors/deals/call_summaries "carry theirs in earlier migrations" — LOOSELY TRUE (left-prefix/composite indexes exist; no standalone messages(workspace_id), but (workspace_id,processed) covers it).
- 011 comment: "tasks were effectively uninsertable / project_id 500'd in prod" because no migration added the column — CONTRADICTED by 007 in-repo; TRUE only if 007 was never applied to prod (likely).
- 002 header: "384-dim all-MiniLM-L6-v2" — matches model + embedding service → LOOKS TRUE.
- init_docker header: "Full schema init" — FALSE in practice: missing projects + several columns vs models.
- init_docker header: "no Supabase RLS" — TRUE (intentional).
- DEPLOY L112: "Do NOT run init_docker.sql on Supabase production" — sensible; also means prod never gets the consolidated form, reinforcing drift.
- Seed agent accuracy/metrics numbers — fabricated demo values, presented as metrics.

---

## 5. Risks (evidence-backed)

- **CRITICAL — RLS provides no real tenant isolation; only app code does.** `database.py:6` + DEPLOY.md L43/L118 (postgres/pooler role) + `supabase_rest.py:19-20` (service_role). No `FORCE ROW LEVEL SECURITY` anywhere. A single missing `workspace_id` guard/WHERE in any current or future router = cross-tenant data exposure with zero DB backstop. Multi-tenancy/auth → at least HIGH; functionally CRITICAL because the entire RLS layer is inert.
- **HIGH — call_summaries has no RLS policy at all** (004). If they ever flip to JWT/anon-key enforcement (the apparent intent of 001/008), call_summaries (transcripts, summaries — sensitive) would be wide open. `004_call_summaries.sql` (no ENABLE/POLICY).
- **HIGH — Schema-source drift (migrations vs init_docker).** init_docker.sql missing projects + tasks.project_id/external_id + projects.external_id + messages.relevant → Docker env 500s on the same paths 009/010/011 fixed; tests run against a schema that isn't prod. `init_docker.sql` (no projects table; no relevant col).
- **MEDIUM — No migration versioning / hand-run order.** Duplicate 007/011, undocumented 006–011 in DEPLOY.md, no Alembic/version table (DEPLOY L102 "run each file in SQL Editor"). Prod schema state is ambiguous; this is how 011's prod outage happened.
- **MEDIUM — USING-only RLS policies (no WITH CHECK).** 001 L188-205. If RLS were enforced, INSERT/UPDATE with a foreign workspace_id would not be blocked. Latent risk for the "switch to real RLS" path.
- **LOW–MEDIUM — Auto-provisioning hard-codes role='admin'** (dependencies.py:76; auth.py:88). Every first-touch user becomes workspace admin; combined with inert RLS, role checks are the only privilege boundary and they grant admin by default.
- **LOW — Hard-coded model-name defaults in DDL** (001/init clarity_scores, call_summaries, seed agents). Stale-by-design; cosmetic correctness risk.
- **LOW — uuid-ossp vs gen_random_uuid mismatch** in init_docker (works on pg16, breaks on engines lacking core gen_random_uuid).
- **LOW — agents: no UNIQUE(workspace_id,type)** → duplicate agent types possible per workspace.

---

## 6. Index vs query-pattern check (quick verdict: mostly covered post-008)

- contacts: list by (workspace_id[, status]) → idx_contacts_workspace (008) covers ws; status filter not indexed (idx_contacts_status only exists in 000, NOT re-created in 001/008) → status filter does seq-within-ws (acceptable at small N).
- contacts semantic search: HNSW embedding index (002) used by search.py cosine query → good. But the ANN ORDER BY is combined with `WHERE workspace_id = :wid` — HNSW can't use the workspace filter, so it post-filters; at multi-tenant scale this returns fewer than `limit` rows or scans extra. Known pgvector limitation; minor.
- deals: list by workspace → idx_deals_workspace_health(workspace_id,health_score) left-prefix covers ws; by (id,workspace_id) PK covers. stage filter not separately indexed (idx_deals_stage only in 000).
- tasks: (workspace_id,status) idx (001) + project_id idx (007/011) + (workspace_id,external_id) partial unique (010). order_by created_at not indexed → fine.
- messages: (workspace_id,processed) (001), (contact_id) (001), (workspace_id,external_id) unique (001). messages.py orders by received_at desc nulls_last — NOT indexed (no received_at index) → potential sort cost on large inboxes. LOW.
- activity_events: idx_activity_events_workspace (008) + idx_activity_created(created_at DESC) exists only in 000 (NOT in 001/init) → the prod-critical events query `WHERE workspace_id=? ORDER BY created_at DESC` (events.py:56-58) has NO composite (workspace_id, created_at DESC) index. Polling loop (events.py:114-134) hits this repeatedly. MEDIUM perf risk at scale; recommend `idx_activity_events_ws_created (workspace_id, created_at DESC)`.
- call_summaries: (workspace_id, call_date DESC) (004) matches calls.py order_by desc(call_date) → good.

Strongest missing index: **activity_events(workspace_id, created_at DESC)** for the activity feed + polling.

---

## 7. Key files
- apps/api/migrations/001_unified_schema.sql — canonical multi-tenant schema + RLS (inert at runtime).
- apps/api/migrations/008_rls_indexes.sql — RLS "fix" + FK index backfill (fix is inert).
- apps/api/migrations/init_docker.sql — divergent Docker schema (missing projects + cols).
- apps/api/app/database.py — superuser/pooler engine (RLS-bypass root cause).
- apps/api/app/services/supabase_rest.py — service_role REST path (RLS-bypass).
- apps/api/app/dependencies.py — JWT→User→workspace_id; app-tier tenancy + admin default.
- DEPLOY.md — documents prod migration order 001–005 only (006–011 undocumented).
