# Betson on NovaCRM — Readiness Assessment

**Scope:** Putting the Betson userbase on NovaCRM (crm-agentic) — multi-tenant FastAPI + Next.js + Supabase(Postgres) + Celery on Railway, with the new lead-gen module (leads / segments / sequences / campaigns / outreach + 4 Celery workers).
**Two tiers assessed:**
- **T1 — Zach's photo-booth division, near-term.** A few users, up to ~10k leads as *data* volume, low concurrency, email-only. Demonstrable September, solid October.
- **T2 — Wider Betson.** Dozens of users, multiple workspaces, higher volume, real cold-outreach at scale.

Synthesized from four dimension assessments: Data & Scale, Multi-Tenancy & Security, Infrastructure & Ops, App & Product.

---

## 1. Bottom line — two-tier verdict

### T1 (Zach's photo-booth division, Sept/Oct) — **READY WITH CAVEATS**

The lead-gen module is genuinely well-built and the demo click-path holds together: real Supabase auth, server-side workspace binding, RLS present on all 8 new tables, 733 passing API tests, a clean web build, and every UI method has both a demo branch and a live api-client path. At Zach's scale the database is comfortably fast — migration 023's indexes cover the hot read paths, and 10k rows makes OFFSET pagination, in-memory CSV export, and ILIKE search all trivially cheap. **But three things gate "Zach uses it for real" versus "the demo works":** (1) migration 023 must be hand-applied to Supabase prod or every lead-gen endpoint 500s on real data (there is no migration runner); (2) the "funnel of engagement" is non-functional on real Gmail sends — opened/clicked/replied/bounced events only arrive via an inbound webhook no provider is wired to, so scores never move and stop-on-reply never fires; and (3) SMS is a stub that falsely records `type='sent'`. None of these are hard blockers for a *scoped* rollout — keep it email-only, apply the migration, and be honest that engagement auto-scoring needs a tracking provider before multi-step drips run against real recipients. With those handled, Zach's division can run for real in October.

### T2 (wider Betson adoption) — **NOT READY**

Multiple independent structural gaps compound at scale, and one of them — tenant isolation — is a correctness/security concern, not just performance. **DB-layer RLS is inert in production:** the API connects with a privileged role that bypasses RLS, `get_db()` propagates no per-request identity, and the 8 new lead-gen tables were never `FORCE`d, so a second Betson tenant's data is **not provably isolated** — isolation rests entirely on every current and future query carrying the right `workspace_id` filter, with no DB backstop to catch a miss. On top of that: there is **no migration runner** (all 24 migrations hand-applied, with a drift-prone `init_docker.sql` copy); **every Celery worker builds and leaks a fresh SQLAlchemy engine per task** (the exact pooler-exhaustion class already fought once, and a plausible contributor to the known sjc1 502s); the **email path is a single-account Gmail connector** with no ESP, rate limiting, retry, bounce/unsubscribe or domain auth (physically can't send a multi-step campaign over thousands of leads, and is a CAN-SPAM gap); Celery has **no time limits, acks_late, or per-workspace locking** so overlapping ticks can double-send; and the **10k CSV import ships all rows inline through one browser→HTTP JSON body**, never exercised above ~40 rows. Close the DB-isolation, migration-runner, worker-engine, email-ESP and per-tenant-webhook items before onboarding a second division.

---

## 2. Go / no-go table

| # | Item | Dimension | Sev | **Must-do before Zach (T1)** | **Before wider rollout (T2)** |
|---|------|-----------|-----|:---:|:---:|
| A | Apply migration 023 to prod + verify a live `GET /workspaces/{ws}/leads` returns 200 | Ops / App | blocker | ✅ **YES** | ✅ (subsumed by runner) |
| B | Keep sequences email-only; hide/disable SMS channel (stub reports false "sent") | Ops / App | high | ✅ **YES** | ✅ or wire Twilio |
| C | Point onboarding invite at the real `inviteTeammate` call (currently a no-op) | App | medium | ⚠️ recommended | ✅ **YES** |
| D | Run one real 10k CSV against deployed prod (or switch to multipart upload) | App | high | ⚠️ recommended | ✅ **YES** |
| E | Be explicit that engagement scoring / stop-on-reply need a tracking provider before drips run on real people | App | high | ✅ **YES (honesty gate)** | ✅ wire ESP webhooks |
| F | Real migration runner (Alembic / release-phase SQL) + kill init_docker.sql drift | Ops / Data | high | — | ✅ **YES** |
| G | DB-layer tenant isolation: app role + `SET LOCAL` identity + `FORCE RLS` on all leadgen tables | Security | high | — | ✅ **YES** |
| H | Module-level (reused) worker engine; stop per-task `create_async_engine` leak | Data / Ops | high/blocker | — | ✅ **YES** |
| I | Move bulk outbound to a dedicated ESP (throttle, retry, bounce/unsub, domain auth) | Ops / App | high | — | ✅ **YES** |
| J | Celery safety: `task_time_limit`, `acks_late`, `prefetch=1`, per-workspace lock / `SKIP LOCKED` | Ops | high | — | ✅ **YES** |
| K | Per-workspace webhook secret (replace single global HMAC) | Security | medium | — | ✅ **YES** |
| L | Bulk / select-all HITL approve + fix `list_pending_outreach` N+1 | App | high | — | ✅ **YES** |
| M | Chunk `tick_sequences` due-enrollments; batch re-scoring | Ops | high | — | ✅ **YES** |
| N | FK-leading indexes on engagement_events / enrollments; keyset pagination; streamed export; trigram search | Data | med/low | — | ✅ **YES** |
| O | Fix divergent 021 policy; restore missing 020/021 files; reconcile call_summaries policy | Security | medium | — | ✅ **YES** |
| P | Explicit API pool sizing for multi-replica; Sentry; `/health` reports real status; RLS initplan one-liner; pgvector schema; leaked-password check | Data / Ops / Security | low | — | ✅ nice-to-have |

---

## 3. Prioritized gap list (de-duplicated across dimensions)

### BLOCKER

- **[B1 · T1+T2 · Deploy/schema] No migration runner; 023 must be hand-applied or the whole module 500s.**
  *Evidence:* `start.sh` is just `exec uvicorn app.main:app`; `023_outbound_engagement.sql` header "USER-applied to prod … NOT executed automatically"; `022` header "ORDERING IS LOAD-BEARING"; DEPLOY.md stale (lists only 001–012). Railway auto-deploys code on push, so code can land before tables exist.
  *Fix (T1):* apply 023 to prod Supabase now; verify a live 200 before the Sept demo. *(T2):* add a real runner (Alembic or release-phase `psql -f`) recording applied files; make/kill `init_docker.sql` to end drift. Flagged by Data, Ops, and App — same root cause.

- **[B2 · T2 · db-connections] Every worker leaks a fresh engine per task.**
  *Evidence:* `_get_async_session()` calls `create_async_engine()` inline in `engagement_score.py:84-92`, `sequence_sender.py:57-65`, `campaign_enroll.py`, `import_leads.py`, `pm_agent.py`, `embed_contacts.py`, `enrich_contact.py`, `slack_ingest.py`; no `dispose()` anywhere. `database.py:8-23` documents a prior EMAXCONNSESSION pooler exhaustion. `tick_sequences_all` fans out one engine per workspace every 5 min.
  *Fix:* hoist a single module-level (or `lru_cache`d) engine per worker process, reuse across tasks, size pools explicitly. Harmless at T1's task volume; most likely infra root cause to check against the open sjc1-502 task. Flagged identically by Data and Ops.

### HIGH

- **[H1 · T2 · Tenant isolation] DB-layer RLS is inert in production — app-layer filter is the *only* backstop.**
  *Evidence:* `get_db()` (`database.py:44-46`) opens a plain session with no `SET LOCAL request.jwt.claim.sub` / `SET ROLE`, so `auth.uid()` → NULL; per `013_force_rls.sql:19-51` the API's `DATABASE_URL` was never repointed to an unprivileged non-owner role, so the privileged connection bypasses all RLS. A single future query missing `.where(workspace_id==…)` = silent cross-tenant leak with nothing to catch it.
  *Fix:* create the dedicated `app_authenticated` role, repoint `DATABASE_URL`, add per-transaction `SET LOCAL` so `auth.uid()` resolves; verify a cross-workspace SELECT returns zero rows. Moot at T1 (one tenant); do **not** ship T2 without it.

- **[H2 · T2 · RLS coverage] The 8 leadgen tables get `ENABLE` but never `FORCE ROW LEVEL SECURITY`.**
  *Evidence:* `023` lines 62/83/100/123/147/175/199/227 all `ENABLE`, no `FORCE`; `013`'s hardcoded FORCE array (lines 67-81) predates and excludes all 023 (and 020/021) tables. On the single-DSN setup where the API role owns the tables, `ENABLE`-only is bypassed for the owner on exactly the new surface.
  *Fix:* migration to `FORCE` all 8 leadgen tables (+ deal_mentions, deal_health_score_history); refactor 013's list into a query over `pg_tables` with a `workspace_id` column so new tables can't be forgotten.

- **[H3 · T1(honesty)+T2 · Core product] The "funnel of engagement" is non-functional on real Gmail sends.**
  *Evidence:* `sequence_sender.py:163-223` raw Gmail send, no tracking pixel / link-wrap / unsubscribe; `outreach.py:484-573` webhook is the *sole* ingress for opened/clicked/replied/bounced/unsub; no provider wired to POST it; no reply-detection job. So scores never move, stage auto-advance never fires, `stop_on_reply` never triggers against real people. Demo only "works" via fixtures + manual HITL events.
  *Fix (T1):* acceptable for a demo, but gate `stop_on_reply` behind a real reply source before turning on multi-step drips against real recipients — and say so plainly. *(T2):* wire an ESP with open/click/bounce webhooks (or tracking-pixel + link-rewrite) and a reply job posting `replied` events.

- **[H4 · both · SMS stub reports false success.**]
  *Evidence:* `sequence_sender.py` sms branch returns `{delivered: bool(phone), stub:True}` (log-only), yet the caller unconditionally writes `EngagementEvent(type='sent')` and advances the enrollment. No Twilio wired.
  *Fix:* keep sequences email-only for Zach and hide "sms" in the sequence builder; make the sms branch record `skipped/blocked`, not `sent`. Wire Twilio only if Zach needs SMS.

- **[H5 · T2 · Email throughput/deliverability] Single-account Gmail connector, no ESP.**
  *Evidence:* `sequence_sender.py::_deliver` sends inline via `GmailClient.send_message`; `gmail_client.py` has no rate/sleep/quota/429/batch/retry/backoff and no List-Unsubscribe/SPF/DKIM/domain story. Gmail caps ~500/day consumer, ~2000 Workspace — a 10k-lead multi-step campaign physically exceeds one account; cold-blasting from a personal mailbox invites spam-filtering and ToS trouble; no unsubscribe = CAN-SPAM gap.
  *Fix:* route bulk outbound through SendGrid/Postmark/SES with per-workspace throttle, retry/backoff, suppression lists, bounce/complaint webhooks, domain auth, injected List-Unsubscribe. Keep Gmail for low-volume 1:1. Tolerable at T1 only if daily sends stay under Gmail caps.

- **[H6 · T2 · Celery safety] No time limits, acks_late, prefetch tuning, or per-workspace lock → double-send + wedged workers.**
  *Evidence:* `celery_app.py` sets only serializers/timezone/track_started/beat; `tick_sequences_all` fires every 5 min (`*/5`); `_due_enrollments` has no `FOR UPDATE SKIP LOCKED`/advisory lock, so two concurrent ticks load the same due enrollment → double send. Worker `--concurrency=2`, so two hung Gmail calls block the whole fleet.
  *Fix:* set `task_soft_time_limit/task_time_limit` (~300/360s), Redis per-workspace lock (or `SKIP LOCKED`), `worker_prefetch_multiplier=1` + `acks_late` for sends; consider a dedicated send queue.

- **[H7 · T2 · Tick scaling] `tick_sequences` processes ALL due enrollments serially in one task with inline sends + one scoring task per send.**
  *Evidence:* `sequence_sender.py::_run_tick` loops every `_due_enrollments` row (no chunk/limit — contrast `import_leads.py` chunking at 500/10k) doing `_draft_body` (optional Claude call) + `_deliver` in-line; each send fires `score_lead_engagement.delay(...)`. A large campaign launch = thousands of sequential sends with no time limit on `--concurrency=2`.
  *Fix:* chunk N due enrollments per tick (leave the rest for the next tick via `next_run_at`), or fan out per-enrollment send tasks onto a rate-limited queue; batch/debounce re-scoring.

- **[H8 · T1 · 10k import path] Whole CSV parsed client-side and POSTed as one inline JSON body; never tested above ~40 rows.**
  *Evidence:* `api-client.ts:1775` posts all rows as `JSON.stringify({rows})`; `leads.py:205-245` Pydantic-parses the full `list[dict]` before staging (staging spares only the Celery broker, not the HTTP path); `import_leads.py:34` `MAX_ROWS=10_000`. Multi-MB body risks Railway/proxy body-size limits and timeouts.
  *Fix:* switch to multipart file upload streamed straight to the staging file (skip JSON body + Pydantic list parse), then actually run a real 10k CSV against deployed prod before the October bar.

- **[H9 · T2 · HITL throughput] Approval is strictly one-at-a-time; no bulk/select-all.**
  *Evidence:* `outreach/page.tsx` renders per-card approve; `useOutreach.approveOutreach(single enrollmentId)`; `list_pending_outreach` flagged N+1; `sequence_steps.requires_approval` DEFAULT TRUE. A funnel over hundreds/thousands of leads is not approvable by hand.
  *Fix:* add a batch approve endpoint + select-all UI; let a sequence drop `requires_approval` on later steps once step 1 is trusted; fix the N+1.

### MEDIUM

- **[M1 · both · Webhook secret] One global HMAC secret across all tenants.** `outreach.py:211-217` reads a single `ENGAGEMENT_WEBHOOK_SECRET`; the row-ownership guard (484-541) is sound, but HMAC only proves "someone holds the global secret". At T2 any secret-holder who knows a `(workspace_id, lead_id)` pair can forge engagement events into another tenant's workspace (weights up to +40/−30 move scores). *Fix:* per-workspace secret stored hashed on the workspace row. Defer OK for T1.

- **[M2 · T2 · FK cascade indexing] 20 unindexed-FK advisor items; composite indexes lead with `workspace_id` so they don't cover the FK columns.** Sharpest: `engagement_events(lead_id/campaign_id/enrollment_id/step_id)`, `sequence_enrollments(lead_id/sequence_id)`. `delete_lead` (`leads.py:605-633`) cascades into the append-only `engagement_events` fact table → seq scans at scale. *Fix:* add FK-column-leading indexes on high-churn paths. Negligible at T1.

- **[M3 · T2 · RLS policy consistency (021)] Divergent policy + repo/prod drift.** `021` uses `current_setting('app.current_workspace_id')` (never set by the app) instead of the house `auth.uid()` subquery; if RLS were enforced this table returns zero rows for everyone. Files 020/021 are absent from the working tree (dir jumps 019→022) though applied to prod. *Fix:* drop/recreate as `deal_health_score_history_policy` with the standard pattern + FORCE; restore 020/021 SQL into the repo.

- **[M4 · T2 · call_summaries policy gap] Advisor reports RLS enabled, no policy (default-DENY under enforcement).** Prod doesn't match `013` (which intends ENABLE+FORCE+policy). Moot today (RLS bypassed) but a landmine the moment DB isolation is turned on. *Fix:* re-apply 013 + FORCE migration; verify via `pg_policies`.

- **[M5 · T2 · Onboarding invite is fake.** `onboarding/page.tsx:136-140` `handleInvite` just `setInviteSent(true)` — shows "Invite sent", sends nothing. The real `apiClient.inviteTeammate` exists and is wired on Settings (`settings/page.tsx:193-200`, `auth.py:176-219`). *Fix:* point onboarding's form at the existing call. Cheap; recommended even for T1.

- **[M6 · T2 · Pagination / export / observability]** OFFSET pagination on lead/campaign lists (`leads.py:166`, `campaigns.py:162/450`); CSV export materializes the whole set into a StringIO (`leads.py:272-291`); no Sentry and `/health` always returns 200 so the 15-min self-healer can't see a DB-degraded API (per DEPLOY.md); no send-outcome metrics. All fine at T1; fix before T2 (keyset pagination, streamed export, Sentry + `/health` body status + delivered/failed counter).

### LOW

- **[L1 · both · RLS initplan]** 25 policies re-evaluate `auth.uid()` per row (`auth_rls_initplan`), incl. all 8 leadgen tables. Low impact (hot path is service-role + explicit filter); one-line `(select auth.uid())` rewrite.
- **[L2 · T2 · API pool sizing]** `database.py:25-30` no explicit `pool_size/max_overflow` (defaults 5+10). Fine at one replica; size against the Supabase pooler ceiling × replica count for T2; confirm `DATABASE_URL` targets the transaction pooler (6543).
- **[L3 · T2 · Search]** Unindexed `ILIKE '%q%'` (`leads.py:149-157`); add a pg_trgm GIN index for T2.
- **[L4 · T2 · Cross-ref validation]** Campaign create doesn't validate `segment_id/sequence_id` belong to the caller's workspace (`campaigns.py:188-197`); no leak (worker re-filters) but a weak existence oracle. Load-by-workspace + 404 on miss.
- **[L5 · T1 · Import counts]** `inserted = rowcount or len(chunk)` (`import_leads.py:155-160`) can over-report inserts under pgbouncer. Cosmetic.
- **[L6 · T2 · HA / capacity]** Single API + single worker `--concurrency=2`, no autoscaling, single region + known sjc1 502s. Scale/replicate + separate send queue before dozens of users.
- **[L7 · T2 · Hygiene]** pgvector in `public` schema; leaked-password protection disabled. Cheap hardening wins before T2.

---

## 4. What's already solid (production-ready today)

This is not just a problem list — real parts are genuinely well-built:

- **App-layer tenant isolation is airtight on the new surface.** Every leadgen endpoint (leads 11/11, segments 8/8, sequences 9/9, campaigns 11/11) opens with `current_user.workspace_id != workspace_id → 403` and filters every query by `workspace_id`; all 4 Celery workers scope by workspace and fan out per-workspace. The prior auto-provisioning IDOR is fixed (users bind only to server-only `app_metadata`).
- **RLS policies exist on all 8 new tables** (defense-in-depth is *written*, even though it needs the role/FORCE wiring to enforce).
- **Test suite + build are green:** 733 API tests passing, clean Next.js web build; every UI method has both a demo branch and a live api-client path.
- **The hot read paths are correctly indexed.** Migration 023 is confirmed applied to prod; `list_leads` filter/sort, the funnel group-by, segment membership, and the scheduler's due-poll (`sequence_sender.py:228-242`) all match dedicated indexes (`idx_leads_ws_*`, `idx_lsm_*`, `idx_enroll_due`). At 10k rows every read is trivially fast.
- **The cross-tenant webhook row-ownership guard is sound** (rejects payloads whose lead/campaign/enrollment don't belong to the URL workspace) — the remaining webhook gap is only the shared secret, not the guard.
- **The import worker itself chunks correctly** (BATCH_SIZE 500 / MAX_ROWS 10k) — the weakness is the HTTP ingress, not the worker.
- **The Sept demo click-path is real end-to-end:** Supabase auth/login, server-side workspace binding, demo mutation hooks fixed.

The module is a strong foundation. The gaps are integration/ops hardening, not a rotten core.

---

## 5. Recommended sequence

### Phase 0 — Get to "T1 ready" (before showing Zach real data — days, not weeks)

1. **Apply migration 023 to Supabase prod** and verify a live `GET /workspaces/{ws}/leads` returns **200, not 500**. *(Gap B1)*
2. **Scope the demo to email-only:** hide/disable the SMS channel in the sequence builder and make the sms branch record `skipped`, not `sent`. *(H4)*
3. **Point the onboarding invite form at `apiClient.inviteTeammate`** (the call Settings already uses). *(M5 — cheap, removes a false-positive)*
4. **Run one real 10k CSV against deployed prod** (or switch import to multipart upload first). Confirm it completes; fix if it hits body-size/timeout. *(H8/D)*
5. **Set expectations honestly with Zach:** engagement auto-scoring, stage auto-advance, and stop-on-reply do **not** work on real Gmail sends yet. Either keep to single-step / manually-reviewed sends for the pilot, or gate multi-step drips until a tracking provider is wired. *(H3/E)*

→ **After Phase 0, T1 is genuinely ready** for Zach's small division to run for real in October.

### Phase 1 — Foundations for T2 (before onboarding a second division)

6. **Real migration runner** (Alembic or release-phase SQL recording applied files); kill the `init_docker.sql` drift. *(B1/F)*
7. **Fix worker engine leak:** one reused module-level engine per worker process, explicit pool sizing, `pool_pre_ping`. Verify against the sjc1-502 task. *(B2/H)*
8. **Turn on DB-layer isolation:** create `app_authenticated` role, repoint `DATABASE_URL`, `SET LOCAL` identity in `get_db()`, and a migration to `FORCE RLS` on all 8 leadgen tables (+ deal tables). Verify a cross-workspace SELECT returns zero rows as the app role. *(H1/H2/G)*
9. **Reconcile policy drift:** fix the divergent 021 policy, restore 020/021 files, repair call_summaries policy. *(M3/M4/O)*

### Phase 2 — Volume & deliverability for T2

10. **Move bulk outbound to an ESP** (SendGrid/Postmark/SES): per-workspace throttle, retry/backoff, suppression lists, bounce/complaint webhooks, domain auth, List-Unsubscribe. Wire the ESP's open/click/bounce webhooks so the engagement funnel actually closes; add a reply-detection job. *(H5/H3/I)*
11. **Celery safety + tick scaling:** time limits, `acks_late`, `prefetch=1`, per-workspace lock / `SKIP LOCKED`, chunk `tick_sequences`, batch re-scoring, dedicated send queue. *(H6/H7/J/M)*
12. **Per-workspace webhook secret** (hashed on the workspace row). *(M1/K)*
13. **Bulk HITL approve** + fix `list_pending_outreach` N+1. *(H9/L)*

### Phase 3 — Scale hardening for T2

14. FK-leading indexes, keyset pagination, streamed export, pg_trgm search. *(M2/N/L3)*
15. Sentry, real `/health` status body, delivered/failed metrics; explicit API pool sizing; worker/API replica scaling. *(M6/P/L2/L6)*
16. Hygiene: RLS initplan one-liner, pgvector schema move, leaked-password protection. *(L1/L7)*

---

*Assessment gates a real client decision. T1 verdict: proceed with the Phase 0 punch-list. T2 verdict: not yet — Phases 1–2 are the price of a second workspace.*
