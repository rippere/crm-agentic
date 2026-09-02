# NovaCRM — Pilot Backlog Delivery Funnel

_Generated 2026-08-31 by the `pilot-backlog-funnel` workflow (run wf_5706ecf4-c08): 8 adversarial reviewers over 22 open PRs; every GREEN adversarially verified before it stayed green._

## TL;DR

- **2 merge-now** — verified safe, ship behind the gate.
- **7 fix-then-merge** — real features blocked on rebase/scope untangling.
- **11 close** — DUPLICATE/superseded work the daily AI-card automation rebuilt after the feature already merged. The treadmill tax.
- **2 needs-human** — scope/title mismatch or a security PR needing judgment.

**Headline:** half the open backlog (11/22) is dead duplicate work. The generator must sit behind this gate and dedup against `master` before opening a PR.

## Merge now (2)

_Verified merge-ready. Route to pr-gatekeeper._

### #77 — docs: list all 4 Celery Beat agent schedules in README
**GREEN · merge-now**

Docs-only. Verified the two added README lines against master's celery_app.py beat_schedule: daily-hitl-followup at crontab(hour=9,minute=0) and pm-health-check at crontab(minute='*/30') both exist and the README text (09:00 UTC, every 30 min) matches exactly. All 3 CI checks pass, branch is MERGEABLE (state BLOCKED is just the required-review gate, not a conflict). Zero blast radius. The gate:hold label means a human parked it, but content is correct and current. Traced all 4 beat_schedule jobs; times match master; CI green.

**Evidence:**
- `README.md:102-103 — adds daily-hitl-followup (09:00 UTC) + pm-health-check (every 30 min)`
- `apps/api/app/workers/celery_app.py beat_schedule (master) confirms both jobs with matching schedules`

### #98 — test(api): cover verify_state rejection branches in oauth_state
**GREEN · merge-now**

Additive test-only file, no production change. Traced every assertion against master's oauth_state.py: the four ValueError messages (malformed state, invalid state signature, invalid state payload, expired state) match verbatim, and the tests use real helpers (_b64encode, _sign, build_state(ttl_seconds=-1)) that exist. Assertions are non-performative — pytest.raises(match=...) exercises each real branch; the tampered-signature test substitutes 43 'A' chars which cannot collide with the HMAC-SHA256 digest, so it genuinely fails on unsigned input. CI green. Genuine security-behavior coverage for the OAuth callback verifier. state BLOCKED is only the review gate.

**Evidence:**
- `apps/api/tests/test_oauth_state.py:1-61 — 5 tests, one per branch + round-trip`
- `apps/api/app/services/oauth_state.py (master) verify_state raises the 4 matching ValueErrors`

## Fix then merge (7)

_Genuine unmerged features; queue as dev tasks._

### #73 — feat(leadgen): lead-generation/marketing module for Betson/Zach + CRM task coverage
**YELLOW · fix-then-merge**

The named feature (commit fbcd812, ~15.5k lines) is genuinely well-built and CI-green (733 API tests pass, E2E + tsc green; the 1 failure is a pre-existing date-bomb in test_deals unrelated to this diff). Security posture is strong: migration 023 enables RLS on all 8 new tables keyed on users.supabase_uid = auth.uid(), FK CASCADE ordering is documented and FK-safe, migration is idempotent (IF NOT EXISTS / DROP POLICY IF EXISTS); every REST endpoint enforces current_user.workspace_id != workspace_id; the inbound engagement webhook is fail-closed HMAC (returns False when no secret, uses hmac.compare_digest) and carries a real cross-tenant guard that rejects lead/campaign/enrollment IDs not owned by the URL workspace_id. I could not break the auth/tenancy/RLS story. The one blocking defect is scope/blast-radius, not correctness: the PR is stacked on 5 unrelated, unreviewed, unpushed commits (~2,695 lines of warm-context enrichment/ingest/compose spine) that the PR body itself says belong to a separate pending PR. None of the 5 are in origin/master, so merging #73 as-is silently lands all of them. Combined with the gate:hold label and the manual-prod-migration requirement (no migration runner exists), this must not merge as a single bundle. Fix is mechanical: isolate fbcd812.

**Blockers:**
- PR merges 5 unrelated, unreviewed commits (warm-context spine) into master alongside the feature — scope violation a solo founder cannot cleanly untangle post-merge.
- gate:hold label present; migration 023 requires manual application to Supabase prod (deploy step outside the PR).

**Evidence:**
- `PR bundles 6 commits; only fbcd812 is the feature. Stacked: e1d3f55c (enrichment), 04663e02 (contacts), e2afa7a0 (ingest), 77d8a580 (ingest fix), f06b4829 (compose) — all confirmed NOT ancestors of origin/master.`
- `PR totals +18174/-131; fbcd812 alone is +15479/-3 across 56 files. ~2695 unreviewed lines ride along from the 5 stacked commits.`
- `apps/api/migrations/023_outbound_engagement.sql: RLS + policy on every table (leads_policy, campaigns_policy, etc.), workspace FK ON DELETE CASCADE, idempotent DDL; header notes it must be applied to Supabase prod BY HAND (no migration runner).`
- `apps/api/app/routers/outreach.py:220-236 _verify_engagement_signature fail-closed with hmac.compare_digest; lines 519-541 cross-tenant guard rejects lead/campaign/enrollment not in URL workspace_id.`

### #42 — feat: contact relationship health AI summary (Phase 14g)
**YELLOW · fix-then-merge**

Genuinely unmerged feature: relationship-health / health_rating exists nowhere on master (ai.py still only exposes /ai/query; the entire 14g-15y AI-card PR series is parked and unmerged). The red CI is from stale-base failures NOT caused by this diff — test_predicted_close_uses_historical_cycle_times and reports/page.tsx TS2322 are pre-existing master-state failures at branch time, not in PR42's touched files. Core diff (new POST ai/contacts/{cid}/relationship-health + card + client stub + 2 tests) looks self-contained. But branch is 62 commits behind and CONFLICTING, so it cannot merge or be CI-verified as-is. Fix: rebase onto master, resolve PROGRESS.md/api-client.ts/page conflicts, re-run CI; confirm relationship-health card is still wanted given the parked AI series.

**Blockers:**
- branch CONFLICTING, 62 commits behind — needs rebase before merge/CI

**Evidence:**
- `apps/api/app/routers/ai.py:105 — only /ai/query on master; no relationship-health anywhere in apps/`
- `CI failures are test_deals.py::test_predicted_close and reports/page.tsx TS2322 — outside PR42's diff (ai.py/test_ai.py/contacts[id]/page.tsx/api-client.ts)`
- `mergeable=CONFLICTING, 62 commits behind`

### #66 — feat(phase-14y): AI deal discovery questions
**YELLOW · fix-then-merge**

The only net-new PR of the five: /deals/{id}/ai/discovery-questions does NOT exist on master (0 occurrences). Logic is sound — DealNote.workspace_id filter is valid (column exists in models/deal_note.py:21), closed-deal 400 guard, 403 workspace guard, category enum validation, and demo stubs are all correct; CI is green (API/E2E/TS all pass). The one blocker is staleness: the branch is CONFLICTING/DIRTY against master (ai.py append region, test_ai.py, and PROGRESS.md all drifted since many later phases merged). Rebase onto master to resolve conflicts, then it is mergeable. Minor non-blocking nit: server slices questions to [:7] while the PR/prompt promise exactly 6.

**Blockers:**
- Branch conflicts with master; needs rebase before merge
- Labeled gate:hold

**Evidence:**
- `discovery-questions: 0 occurrences on origin/master — genuinely new`
- `apps/api/app/models/deal_note.py:21 — workspace_id column exists, so DealNote.workspace_id filter is valid`
- `gh pr view: mergeable=CONFLICTING state=DIRTY base=master`
- `ai.py diff: `questions = [...][:7]` vs PR claim of exactly 6 questions (non-blocking)`

### #81 — feat(phase-15i): AI deal next-step planner
**YELLOW · fix-then-merge**

Sound, non-duplicated feature: master has no deal next-step endpoint (grep on master ai.py returns 0 for deals/{id}/ai/next-step) and the card lives on /pipeline/[id], a surface master's recent contact-focused phases have not touched. Code traces correctly (403 guard, closed-deal 400, days-in-stage tz-normalization, blockers clamped to 3, invalid time_horizon coerced), CI is green, tests assert real fields. Blocking issue is purely mechanical: branch is CONFLICTING/DIRTY against a master that advanced ~13 phases since creation (append-conflicts in ai.py/api-client.ts + heavy PROGRESS.md divergence). Minor latent edge: float(deal.value) runs outside the try block, so a null deal value would 500, but real deals carry a value.

**Blockers:**
- CONFLICTING against master; requires rebase/conflict-resolution before merge

**Evidence:**
- `gh pr view 81: mergeable=CONFLICTING, mergeStateStatus=DIRTY, gate:hold, created 2026-08-16`
- `git show origin/master:apps/api/app/routers/ai.py | grep next-step -> 0 matches (feature absent on master)`
- `master is at Phase 15y/15z; this PR is Phase 15i (stale)`
- `ai.py diff: float(deal.value) at context-build is outside try/except -> uncaught 500 if value is None`

### #82 — feat(phase-15j): AI agent recommendations on /agents page
**YELLOW · fix-then-merge**

Non-duplicated: master has no agent-recommendations endpoint (grep returns 0) and the card targets /agents, a surface untouched by master's contact-card churn. CI green, 403 guard present, structured-response test asserts real fields. Only blocker is that the branch is CONFLICTING/DIRTY and stale (Phase 15j vs master 15y), with the usual append-conflicts plus a large PROGRESS.md divergence. Needs rebase; no correctness defect found in the reviewed portion.

**Blockers:**
- CONFLICTING against master; requires rebase before merge

**Evidence:**
- `gh pr view 82: mergeable=CONFLICTING, mergeStateStatus=DIRTY, gate:hold, created 2026-08-17`
- `git show origin/master ai.py | grep agent-recommendations -> 0 matches`
- `master dashboard/agents surfaces do not contain this endpoint (grep count 0)`

### #83 — feat(phase-15k): AI workspace next-best-actions on dashboard
**YELLOW · fix-then-merge**

Non-duplicated: master has no next-best-actions endpoint (grep returns 0); master's dashboard has a goal-tracker (Phase 15h) but not this ranked-actions card. CI green, 403 guard, enum coercion and no-risk fallback handled. Sole blocker is staleness: CONFLICTING/DIRTY, Phase 15k against master 15y, so append-conflicts + PROGRESS.md divergence must be resolved. No correctness defect found.

**Blockers:**
- CONFLICTING against master; requires rebase before merge

**Evidence:**
- `gh pr view 83: mergeable=CONFLICTING, mergeStateStatus=DIRTY, gate:hold, created 2026-08-18`
- `git show origin/master ai.py | grep next-best-actions -> 0 matches`
- `diff size +507/-2 across multiple files; master advanced ~14 phases since`

### #100 — fix(web): collapse duplicate engagementScoreConfig into leadScoreConfig alias
**YELLOW · fix-then-merge**

Change is correct: verified on the base branch feat/betson-leadgen-module that engagementScoreConfig duplicates leadScoreConfig byte-for-byte and both LeadScore and EngagementLabel are the hot|warm|cold union, so aliasing is type-safe and behavior-preserving. But it does NOT target master — it targets the still-open, unmerged feature branch of PR #73, and gh reports 'no checks reported' for this branch (the CI workflow doesn't run on this non-master base), so the tsc/next-build verification is author-asserted only and unverified by CI. It is a stacked change dependent on #73 landing. Fix to green: merge PR #73 first (or retarget/rebase #100 once #73 lands) so CI actually runs against master.

**Blockers:**
- No CI executed on this PR (base is an unmerged feature branch) — merge into/after PR #73 and confirm tsc+build there before landing

**Evidence:**
- `apps/web/src/lib/utils.ts:126-127 (feat/betson-leadgen-module) — dup confirmed identical to leadScoreConfig:23-42`
- `gh pr checks 100 — 'no checks reported on the branch' (base is feat/betson-leadgen-module, not master)`
- `gh pr view 73 — still OPEN; #100 cannot reach master until #73 merges`

## Close or supersede (11)

_Already shipped or hopelessly stale — close with a pointer to the merged work._

### #22 — feat: analytics phases 12o–13d (16 endpoints, 113 new tests, 10 chart widgets)
**RED · close-or-supersede**

Fully superseded. Every endpoint this PR adds already exists on master at the identical route paths — deals at-risk/close-date-slipped/health-distribution/by-agent/revenue-forecast/stage-aging/win-probability-by-stage/concentration-risk/close-date-accuracy/revenue-cohort/velocity-trends, contacts going-dark/pipeline-contribution/reengagement-summary/{id}/last-touch, and events activity/trends all resolve on origin/master (git grep confirmed). The branch (feat/phase-13d, created 2026-07-01, carrying gate:hold) is 134 commits behind and 5 ahead of master, and GitHub reports mergeStateStatus=DIRTY / mergeable=CONFLICTING with real <<<<<<< conflict markers across all 12 touched files. Master has since advanced to phase 15y; this phase-13d work already landed via later phases. The code itself is sound (consistent tenancy: path workspace_id + current_user.workspace_id!=workspace_id 403 check + Deal.workspace_id==workspace_id query filter on every route; no DB migrations; no secrets; non-null ml_win_probability/health_score in model so comparisons are safe), but merging would only recreate duplicate routes and conflicts. Close as superseded. The one endpoint not on master (deals/leaderboard) is not worth resurrecting a 134-commit-stale conflicting branch for; re-add it as a fresh 1-file PR off master if wanted.

**Blockers:**
- All 16 endpoints already exist on master under identical route paths (duplicate work)
- Branch is 134 commits behind master and in a CONFLICTING/DIRTY merge state — cannot merge without full rebase
- Carries gate:hold label — was intentionally parked

**Evidence:**
- `origin/master:apps/api/app/routers/deals.py:601 already defines @router.get("/workspaces/{workspace_id}/deals/at-risk") — plus close-date-slipped:697, health-distribution:735, by-agent:777, revenue-forecast:809, stage-aging:851, win-probability-by-stage:895, concentration-risk:936, close-date-accuracy:989, revenue-cohort:1044, velocity-trends:1150 all present on master`
- `origin/master:apps/api/app/routers/contacts.py:314/404/470/1747 already define going-dark, pipeline-contribution, reengagement-summary, {contact_id}/last-touch`
- `origin/master:apps/api/app/routers/events.py:115 already defines activity/trends`
- `git: origin/master...origin/feat/phase-13d = 134 behind / 5 ahead; gh mergeStateStatus=DIRTY, mergeable=CONFLICTING; git merge-tree shows <<<<<<< conflicts in all 12 files`

### #11 — feat(api): MCP task-tools + tasks router updates with tests
**RED · close-or-supersede**

Branch is 141 commits behind master and CONFLICTING/DIRTY; CI red on both API and Web. The MCP task-tools are not present on master (mcp_server.py tools are list_contacts/list_deals/stale_deals/pipeline_summary/ask_crm), so not name-superseded, but master's tasks.py has evolved substantially (added by-external PUT and other routes) in those 141 commits, so the PR's router edits will conflict heavily and its MCP tools cannot be trusted to match the current task contract. This is a rework-from-fresh task, not a rebase. Cannot verify it still applies or passes.

**Blockers:**
- 141 commits stale + merge conflicts
- red CI
- task-router changes collide with evolved master tasks.py

**Evidence:**
- `apps/api/app/routers/mcp_server.py:36-81 (master tool set has no task tools)`
- `apps/api/app/routers/tasks.py:128 by-external route added on master post-dating the branch`
- `mergeable=CONFLICTING/DIRTY, 141 commits behind master, ci fail API+Web`

### #13 — feat(12p): contact no-recent-activity nudge
**RED · close-or-supersede**

Superseded. Master already shipped the same Phase 12p deliverable as the 'going-dark' detector: GET /workspaces/{id}/contacts/going-dark (contacts with no messages or notes in last 30 days, 3-query approach, amber dismissible banner on /contacts, getGoingDarkContacts stub, 2 tests) per PROGRESS.md line 106 dated 2026-06-29. This PR's GET /contacts/inactive is a duplicate implementation under a different name. Branch is also 136 commits behind, CONFLICTING, CI red.

**Blockers:**
- duplicate of shipped Phase 12p going-dark detector
- 136 commits stale + conflicts
- red CI

**Evidence:**
- `PROGRESS.md:106 — Phase 12p 'going dark' detector /contacts/going-dark already merged 2026-06-29`
- `apps/api/app/routers/contacts.py has no 'inactive' route on master (feature lives as going-dark)`
- `mergeable=CONFLICTING, 136 behind, ci fail`

### #14 — feat(12o): deal at-risk early warning endpoint + pipeline banner
**RED · close-or-supersede**

Superseded. Master already merged Phase 12o at-risk deals as commit c2b0bf0 'feat(api): add /deals/at-risk endpoint (Phase 12o)' (PROGRESS.md line 105, 2026-06-29) with an evolved implementation (ml_win_probability < 30, singular risk_reason string, days_inactive). This PR is a competing/older build of the identical endpoint (< 35, risk_reasons list) — exactly the duplicate at-risk-deal work pattern flagged in CLAUDE.md. Branch is 136 commits behind, CONFLICTING, CI red.

**Blockers:**
- duplicate of shipped Phase 12o /deals/at-risk endpoint
- 136 commits stale + conflicts
- red CI

**Evidence:**
- `apps/api/app/routers/deals.py:593 at_risk_deals already on master`
- `PROGRESS.md:105 Phase 12o /deals/at-risk merged 2026-06-29 via c2b0bf0`
- `mergeable=CONFLICTING, 136 behind, ci fail`

### #52 — feat(phase-14o): AI deal comparison card
**RED · close-or-supersede**

Superseded and stale. The endpoint POST /workspaces/{id}/ai/deals/compare that this PR adds ALREADY EXISTS on master (apps/api/app/routers/ai.py:2099), landed via the merged PR #53 (per PROGRESS.md '[2026-07-25] Phase 14o ... PR #53 merged'). The branch is CONFLICTING/DIRTY against master, is 38 days old, and is labeled gate:hold. It also serves as the base for #58, compounding the stale stack. Nothing here is worth merging; the work already shipped.

**Blockers:**
- Feature already merged to master via PR #53
- Branch conflicts with master

**Evidence:**
- `origin/master apps/api/app/routers/ai.py:2099 — @router.post("/workspaces/{workspace_id}/ai/deals/compare") already present`
- `gh pr view: mergeable=CONFLICTING state=DIRTY base=master`
- `PR #59 PROGRESS.md line: 'Phase 14o: AI deal comparison card ... PR #53 merged'`

### #58 — feat(phase-14p–14s): AI inbox triage, re-engagement planner, objection handler, stakeholder map
**RED · close-or-supersede**

Entirely superseded. All four bundled features already exist on master under separately-merged PRs: /ai/messages/triage (14p, PR #55), /ai/contacts/reengagement-plan (14q, PR #56), /deals/{id}/ai/objection-handler (14r), and a stakeholder endpoint (master ships /deals/{id}/ai/stakeholder-map; this PR adds a parallel /stakeholder-analysis name — a duplicate under a divergent route). Worse, this PR's base is feat/phase-14o-deal-comparison (PR #52's branch), not master, so it stacks on an already-superseded branch. Merging would create duplicate/divergent endpoints for work already shipped.

**Blockers:**
- All four features already merged to master via other PRs
- Adds duplicate stakeholder endpoint under divergent name
- Based on superseded branch #52, not master

**Evidence:**
- `origin/master ai.py contains /ai/messages/triage, /ai/contacts/reengagement-plan, /deals/{deal_id}/ai/objection-handler, /deals/{deal_id}/ai/stakeholder-map`
- `This PR adds /stakeholder-analysis (0 occurrences on master) — a parallel route to the merged stakeholder-map`
- `gh pr view: base=feat/phase-14o-deal-comparison (stacked on superseded #52)`
- `PROGRESS.md: 14p=PR #55, 14q=PR #56, 14r merged`

### #59 — feat(phase-15a): AI team performance summary on /reports
**RED · close-or-supersede**

Superseded. The endpoint GET /workspaces/{id}/ai/team-performance this PR adds already exists on master (apps/api/app/routers/ai.py:3779). Although this PR's own CI is green, the branch is CONFLICTING/DIRTY against master and the feature has already shipped, so merging it would duplicate an existing route. Close as already-delivered.

**Blockers:**
- team-performance endpoint already on master
- Branch conflicts with master

**Evidence:**
- `origin/master apps/api/app/routers/ai.py:3779 — @router.get("/workspaces/{workspace_id}/ai/team-performance") already present`
- `gh pr view: mergeable=CONFLICTING state=DIRTY base=master`
- `CI: all three checks pass (but against an already-merged feature)`

### #61 — feat(phase-14t): AI deal negotiation script
**RED · close-or-supersede**

Superseded and stale. POST /workspaces/{id}/deals/{id}/ai/negotiation-script already exists on master (apps/api/app/routers/ai.py:2743). The branch is CONFLICTING/DIRTY against master and 29 days old. The feature has shipped via another PR; this one is redundant.

**Blockers:**
- negotiation-script endpoint already on master
- Branch conflicts with master

**Evidence:**
- `origin/master apps/api/app/routers/ai.py:2743 — @router.post("/workspaces/{workspace_id}/deals/{deal_id}/ai/negotiation-script") already present`
- `gh pr view: mergeable=CONFLICTING state=DIRTY base=master`

### #67 — feat(phase-14y): AI task prioritizer on /tasks page
**RED · close-or-supersede**

Superseded. Master already ships Phase 14y 'AI task prioritization' via merged PR #69 (2026-08-10): the endpoint POST /workspaces/{id}/ai/tasks/prioritize and async def prioritize_tasks already exist on master at ai.py:3512 with a richer response shape (priority_rank/reason/summary_note). This PR redefines the same route and same function name with a divergent shape (rationale/recommended_action), and is CONFLICTING against master. Merging would duplicate an already-shipped feature and collide on the route/symbol. Oldest of the set (~23 days) and gate:hold.

**Blockers:**
- Duplicate of merged PR #69 (same route + same function name already on master)
- CONFLICTING / cannot merge as-is

**Evidence:**
- `git show origin/master:apps/api/app/routers/ai.py -> line 3512 '@router.post("/workspaces/{workspace_id}/ai/tasks/prioritize")' with 'async def prioritize_tasks' already present`
- `master PROGRESS.md: '[2026-08-10] Phase 14y: AI task prioritization ... PR #69 merged'`
- `gh pr view 67: mergeable=CONFLICTING, mergeStateStatus=DIRTY, label gate:hold`
- `apps/api/app/routers/ai.py (PR diff): re-adds '@router.post(.../ai/tasks/prioritize)' and 'async def prioritize_tasks' -> duplicate route/symbol`

### #84 — feat(phase-15l): AI contact competitive intelligence
**RED · close-or-supersede**

Thematically superseded on the same page. Master already shipped Phase 15v 'competitive-positioning' as a 'Competitive Position' card on /contacts/[id] (contacts page master rev has it at page.tsx:2083-2087), plus an ai/competitive-landscape endpoint. This PR adds a SECOND competitive card ('Competitive Intel') to the very same /contacts/[id] page, drawing on the same competitors-from-deals data source. That is redundant surface/real-estate against already-merged work and is exactly the auto-dev drift a solo founder should not merge blindly. Also CONFLICTING/DIRTY and stale (Phase 15l vs master 15y). Needs a human decision on whether a third competitive feature is wanted; do not auto-merge.

**Blockers:**
- Redundant with already-merged Phase 15v competitive-positioning card on the same /contacts/[id] page
- CONFLICTING against master; needs human product decision before any merge

**Evidence:**
- `master contacts/[id]/page.tsx:2083 '/* Competitive Positioning Card */' + :2087 'Competitive Position' already present`
- `master ai.py:6217 POST .../ai/contacts/{contact_id}/competitive-positioning (Phase 15v, PR #99) and :4903 ai/competitive-landscape`
- `PR #84 diff: contacts/[id]/page.tsx:308-313 adds '/* Competitive Intelligence */' 'Competitive Intel' card to same page`
- `gh pr view 84: mergeable=CONFLICTING, mergeStateStatus=DIRTY, gate:hold, created 2026-08-18`

### #80 — chore: update PROGRESS.md after Phase 15h
**RED · close-or-supersede**

Superseded and conflicting. This PR records Phase 15h and sets 15i as next task, but master's PROGRESS.md already contains the Phase 15h entry (line 159, PR #79 already in master) and has advanced ~15 phases beyond it through Phase 15z (line 182, dated 2026-08-31). The branch is CONFLICTING/DIRTY against master. Merging would regress the progress log. Pure bookkeeping doc with no value now. Confirmed master is many phases ahead; this update is stale.

**Blockers:**
- Branch conflicts with master and content is entirely superseded by later phase entries already on master

**Evidence:**
- `PROGRESS.md master:159 already logs Phase 15h (PR #79 merged)`
- `PROGRESS.md master:182 Next Task is Phase 15z — PR #80 would set it back to 15i`
- `gh pr view: mergeable=CONFLICTING, mergeStateStatus=DIRTY`

## Needs human (2)

_Requires your judgment before any action._

### #4 — Security + claims hardening: CLAIM (landing), F7 (erasure), F3/F5 (inert) + audit reconcile
**RED · needs-human**

The engineering is careful and internally coherent — flag-gated F3/F5 paths are genuinely inert by default, new model imports (Project/ContactNote/CallSummary) all exist with the required workspace_id/contact_id columns, ContactNote's FK is confirmed ON DELETE CASCADE (validating the merge-reassign logic), the rate-principal middleware is provably registered outermost of SlowAPIMiddleware, and tests assert real emitted SQL rather than trivialities. But it is NOT merge-ready: the branch is CONFLICTING/DIRTY against master, it carries an explicit gate:hold label, it is 79 days stale, its own body promises further follow-up commits (the deal.notes PII scrub is confirmed absent — only a docstring 'known residual'), and there is NO CI on the branch so the claimed '447 passed / next build clean' cannot be verified. Blast radius is high for a solo-founder pilot: F7 PII erasure ships ACTIVE by default and irreversibly hard-deletes messages + call_summaries on contact delete; the Celery default-queue rename (celery→default) and worker_prefetch_multiplier=1 ship active regardless of flags; and the deploy is coupled to a worker start-command change (-Q default,long) that must land in the same deploy. A human must resolve the conflict, run the suite, and consciously accept the destructive/deploy-coupled changes before this merges.

**Blockers:**
- Merge conflict with master (DIRTY) must be resolved before merge
- gate:hold label indicates the PR is intentionally parked / incomplete
- No CI to confirm the 447-passed test claim; cannot verify build/tests independently
- F7 hard-delete of messages+call_summaries is active-by-default and irreversible — needs explicit human sign-off
- Deploy coupled to worker start-command change (-Q default,long); merging code without the ops change strands long-queue tasks once enabled

**Evidence:**
- `PR metadata: mergeable=CONFLICTING, mergeStateStatus=DIRTY — cannot merge as-is`
- `Label gate:hold present; branch created 2026-06-13 (~79 days stale)`
- `gh pr checks: 'no checks reported' — no CI; '447 passed' claim unverifiable`
- `apps/api/app/routers/contacts.py:596 delete_contact calls _erase_contact_pii which HARD-DELETEs messages+call_summaries — active by default, irreversible, not flag-gated`

### #107 — Provision demo login for walkthrough seed data
**RED · needs-human**

The PR is titled/described as a small seed-only change ('provision demo login') but actually ships an entire lead-gen module as its true payload: 8 new tables, 2 unapplied DB migrations, 5 new routers wired into the live app, 8 Celery workers, frontend pages, and docs — +17739/-135 across 80 files, with the demo-seed being only the last of 8 commits. The code itself is high quality (RLS on every new table, per-endpoint workspace tenancy guards on all 33 authenticated endpoints, a fail-closed HMAC webhook with explicit cross-tenant row-ownership checks, HITL send-gating so nothing auto-emails, and substantive tests), so it is neither broken nor superseded. But it is a HIGH-blast-radius change on a live-deploy repo with a self-documented deploy-ordering outage hazard (models map new columns; migrations are manually USER-applied; deploying code before applying migrations 500s every message/contact/deal read path, per the cited 020_deal_mentions incident), no CI, and it was never run against prod. A solo founder cannot safely autonomously merge a 17k-line mislabeled bundle with a manual-migration footgun — it needs a human-supervised staged rollout (apply 022+023 to prod first, then deploy) and should be re-titled/split.

**Blockers:**
- Title/body claim seed-only but PR ships an entire 17k-line lead-gen feature (8 commits) — reviewer merging on the description would be blindsided
- Manual migration/deploy ordering hazard on a live-deploy repo: code deployed before 022/023 applied to prod causes a full read-path outage
- No CI and never verified against prod — high blast radius cannot be confirmed safe autonomously

**Evidence:**
- `apps/api/app/main.py:17 — adds 5 new routers (leads, segments, sequences, campaigns, outreach) not present on origin/master, far beyond the claimed seed change`
- `apps/api/migrations/023_outbound_engagement.sql:1 — 8 new tables (leads, lead_segments, lead_segment_members, sequences, sequence_steps, campaigns, sequence_enrollments, engagement_events) all with RLS but manually USER-applied to prod`
- `apps/api/migrations/022_message_graph_capture.sql:25 — header itself warns deploying model ahead of migration 500s every message/contact/deal read path (cites 020_deal_mentions outage 2026-07-10 to 2026-07-15)`
- `apps/api/app/routers/outreach.py:220 — engagement webhook is fail-closed HMAC (returns False when no secret), with cross-tenant guard at outreach.py:519 rejecting rows not in the URL workspace (security sound)`
