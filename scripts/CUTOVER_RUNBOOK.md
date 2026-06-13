# NovaCRM Hardening — Ops Cutover Runbook (PR #4)

Consolidated, ordered checklist for everything PR #4 (`hardening/2026-06-13`) needs from ops.
Everything risky in the PR is **inert by default** (three flags off, RLS role unchanged), so the
PR is safe to **merge + deploy first** and turn features on deliberately afterward.

Flags shipped (all default OFF): `DB_RLS_CONTEXT_ENABLED`, `LLM_BUDGET_ENABLED`, `LONG_QUEUE_ENABLED`.

---

## 0. Merge + deploy (safe, no coordination required)
- Merge PR #4 to `master`; let Railway redeploy api + web + worker + beat.
- Nothing changes behaviorally on deploy: the claims fix + F7 erasure go live; RLS, spend cap,
  and queue isolation stay inert until their flags are flipped below.

## 1. Quick wins (independent, do anytime)
- [ ] **Gmail webhook** — set `GMAIL_WEBHOOK_SECRET` and `GMAIL_PUBSUB_TOPIC` in the **api** service
      env (Railway). Until set, the (now fail-closed) webhook rejects everything, so Gmail push
      ingest is dead.
- [ ] **Slack** — confirm `SLACK_SIGNING_SECRET` is set in the api env (sources disagreed; verify).
- [ ] **Deal notes feature** — apply migration `014_deal_notes.sql` to prod Supabase.
- [ ] **F2 workspace binding** — run `scripts/backfill-ws-b-app-metadata.py` against prod to move
      existing users' `workspace_id` into server-only `app_metadata`, then confirm a login still
      resolves the workspace.
- [ ] **F6 beat** — after deploy, confirm a scheduled cycle runs `SUCCESS` and recomputes at least
      one deal `health_score` off the default 100.

## 2. Enable queue isolation (F5) — coordinated, one deploy
Routing of reprocess/transcribe to the `long` queue is gated by `LONG_QUEUE_ENABLED` (default off).
To turn it on **without breaking those tasks**, do BOTH together:
- [ ] Set `LONG_QUEUE_ENABLED=true` in the api **and** worker env.
- [ ] Change the **worker** start command to consume both queues:
      `celery -A app.workers.celery_app.celery_app worker --loglevel=info -Q default,long`
      (or add a second worker: `... worker -Q long --concurrency=1`).
- Leaving it off is fine and safe — it just means heavy jobs share the default pool as today.

## 3. Optional: enable the LLM spend cap (F5)
- [ ] Set `LLM_BUDGET_ENABLED=true` and tune `LLM_BUDGET_TOKENS_PER_WINDOW` /
      `LLM_BUDGET_WINDOW_SECONDS` once you pick a per-workspace ceiling. Defaults are effectively
      off; the cap fails **open** on Redis errors (it is a cost guard, not a security control).

## 4. RLS backstop cutover (F3) — the real isolation switch, do deliberately
The per-request tenant context (`set_tenant_context`) and migration `013` are shipped but **inert**
until the API connects as a non-BYPASSRLS role with `DB_RLS_CONTEXT_ENABLED=true`. Full authoritative
runbook is in the header of `apps/api/migrations/013_force_rls.sql`. Summary:

1. [ ] Create a least-privilege login role (NON-superuser, NON-BYPASSRLS, NOT the table owner):
   ```sql
   CREATE ROLE app_authenticated LOGIN PASSWORD '<secret>'
     NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
   GRANT USAGE ON SCHEMA public TO app_authenticated;
   GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_authenticated;
   GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_authenticated;
   ALTER DEFAULT PRIVILEGES IN SCHEMA public
     GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_authenticated;
   ```
   Ensure `auth.uid()` is resolvable for this role (Supabase ships it; it reads
   `request.jwt.claims ->> 'sub'`, which `set_tenant_context` sets per transaction).
2. [ ] Apply migration `013_force_rls.sql` to prod.
3. [ ] Repoint the api `DATABASE_URL` user to `app_authenticated` (env change).
4. [ ] Set `DB_RLS_CONTEXT_ENABLED=true` in the api env; redeploy.
5. [ ] **Decisive test** (run AS the new role, with a tenant bound, as the app does per request):
   ```sql
   BEGIN;
     SET LOCAL request.jwt.claims = '{"sub":"<a real users.supabase_uid>"}';
     SELECT count(*) AS visible, count(distinct workspace_id) AS workspaces FROM contacts; -- expect workspaces = 1
     SELECT count(*) FROM call_summaries; -- now policy-bound (was 0 policies)
   COMMIT;
   ```
   Pre-cutover the same probe spans 2 workspaces (audit `phase2/evidence-rls.md §5`); post-cutover it
   must be scoped to one — that proves the DB-level backstop is live.
- **Rollback:** set `DB_RLS_CONTEXT_ENABLED=false` and/or repoint `DATABASE_URL` back to the
  privileged role. `013` (FORCE RLS + policies) is harmless to a BYPASSRLS role, so leaving it
  applied does not break the old connection.

---

_After each step lands, advance the corresponding row in
`audit/2026-06-03-vetting/REMEDIATION_REGISTER.md` (OPEN → … → DEPLOYED → VERIFIED). `crm-pm` is the
authoritative maintainer of that register._
