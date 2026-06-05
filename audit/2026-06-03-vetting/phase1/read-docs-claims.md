# Phase 1 — Docs & Marketing-Copy Claims Register (NovaCRM audit)

**Auditor:** docs/claims subagent
**Repo:** `/tmp/crm-signup-fix` — git worktree, branch `fix/signup-confirm-redirect` (tracks `origin/master`; this is the deployed production code).
**Scope read:** README.md, PROGRESS.md, DEPLOY.md, DEMO_SCRIPT.md, AGENTS.md (the real file at root), HANDOFF.md (recovered from git history — see note), and `apps/web/src/app/page.tsx` (marketing landing page). AUDIT_ROADMAP.md does NOT exist (see note).

---

## 0. Scope-file availability notes

- **AUDIT_ROADMAP.md — DOES NOT EXIST.** Not in the working tree, and not in ANY commit on ANY ref (verified via `git rev-list --all | git ls-tree`). The task scope named it but it is absent. Treat as "not produced."
- **HANDOFF.md — NOT in working tree; recovered from git history.** Two relevant commits:
  - `0e74552 docs: session handoff — testing complete, deployment ready` (the content I quote; dated 2026-04-29, references git `a07c2a4` on master).
  - `893a7ba security: remove leaked Supabase anon key and test credentials from HANDOFF.md` — i.e. HANDOFF.md **previously contained a real Supabase anon key + a test-user password in plaintext**, later scrubbed. The recovered copy I read still shows the structure with `***REDACTED***` placeholders where secrets were. **This is a historical credential-leak event** — the anon key + test creds were committed to git and are in history.
- **AGENTS.md** at root is NOT an agent-roster doc — it's a 6-line Next.js agent-rules banner ("This is NOT the Next.js you know… read node_modules/next/dist/docs"). No factual product claims.
- The repo also contains `audit.js` (10.8 KB) and a prior `DEPLOY.md` "audit" dated 2026-05-25. These are self-audit artifacts, not third-party.

---

## 1. THE HEADLINE FINDING — Marketing AI/ML claims are largely fabricated

`apps/web/src/app/page.tsx` advertises a sophisticated ML stack. The actual backend (`apps/api`) uses **Claude (Haiku/Sonnet) for generative tasks + simple Python heuristics for scoring**. `requirements.txt` contains NO xgboost, NO lightgbm, NO openai, NO torch, NO transformers/RoBERTa, NO RL library. Full deps: fastapi, uvicorn, sqlalchemy, asyncpg, PyJWT, cryptography, celery, httpx, **anthropic==0.34.2**, python-dotenv, pydantic, pgvector, **sentence-transformers** (the only real ML model, all-MiniLM-L6-v2 for embeddings), **openai-whisper** (transcription only), python-multipart, slowapi, flower.

| Marketing claim (page.tsx) | Line | Reality (verified in code) | Verdict |
|---|---|---|---|
| Email Composer = **"GPT-4o Fine-tuned"** | page.tsx:260-261 | `contacts.py:310` uses `model="claude-haiku-4-5-20251001"`. No OpenAI SDK in deps at all. Not GPT, not GPT-4o, not fine-tuned. | **FALSE** |
| Email Composer **"48% Open Rate", "22% Reply Rate"** | page.tsx:261 | No email open/reply tracking exists anywhere in the codebase. Fabricated metrics. | **FALSE / unverifiable** |
| ML Lead Scoring = **"XGBoost v2", "Feature Store", "F1: 0.947"** | page.tsx:246-248 | `workers/score_contact.py` docstring literally says "heuristic lead scorer"; `_compute_score` = base 50 ± status/revenue/deal-count adjustments. No XGBoost, no feature store, no F1 computation. Agent seed lists Lead Scorer `"model": "heuristic"`. | **FALSE** |
| Pipeline Intelligence = **"RL Policy", "LightGBM", "Win Prediction"** | page.tsx:252-254 | `workers/pipeline.py` docstring says "heuristic pipeline optimizer"; win prob = STAGE_BONUS lookup table. No RL, no LightGBM. | **FALSE** |
| Churn Prediction = **"RoBERTa Fine-tuned"**, "flags at-risk accounts" | page.tsx:272-275 | No churn product and no RoBERTa. Only `services/sentiment.py` → `claude-haiku-4-5` per-message tone. No churn agent in the seed list. | **FALSE** (feature largely doesn't exist as described) |
| Call Summarization = **"Whisper Large v3", "Claude 3.5"**, "in 23 seconds" | page.tsx:267-268 | `workers/transcribe.py` loads Whisper **base** (`WHISPER_MODEL` default "base"), not Large v3. Summary model is `claude-sonnet-4-6` (not "Claude 3.5"). "23 seconds" is invented — no timing guarantee. | **FALSE (model size + version) / unverifiable (timing)** |
| Semantic Sorting = **"all-MiniLM-L6-v2", "Cosine Similarity"** | page.tsx:239-240 | `services/embedding.py` genuinely uses all-MiniLM-L6-v2 (384-dim). pgvector cosine. | **TRUE** (only feature whose tags match reality) |
| Hero badge **"6 AI Agents Running · 94.7% Accuracy"** | page.tsx:143-144 | Agent seed (`auth.py`) defines **7** agents with hardcoded accuracy fields (94.2/87.1/91.8/89.5/85.3/92.0/100.0). "94.7%" matches no agent and isn't computed from any eval — it's a vanity constant (also reused as F1 0.947 and the dashboard "Accuracy" tile). | **FALSE / fabricated** |
| Dashboard preview tiles: **"$2.4M" Revenue, "148" Deals, "94.7%" Accuracy, "6 / 8" Agents** | page.tsx:191-204 | Hardcoded mock UI props on the public landing page. Not live data. "6/8 agents" contradicts the 7-agent seed and the "6 running" badge directly above it. | **Mock presented as product reality** |
| Agents log shows live events ("model_retrain complete · f1:0.947→0.951", "streaming") | page.tsx:343-361 | Entirely hardcoded array animated to look live. No model retraining exists (heuristics don't retrain). The `cursor-blink` "processing batch:49" is decorative. | **Fabricated "live" feed** |

---

## 2. Security / compliance posture claims — UNSUBSTANTIATED

| Claim | Location | Reality | Verdict |
|---|---|---|---|
| **"SOC 2 Type II"** | page.tsx:179 (hero) AND page.tsx:462 (CTA trust badges) | The strings "SOC 2 Type II" appear ONLY as marketing copy. Zero evidence of a SOC 2 audit, controls, policy docs, or anything in code/docs/sql. | **Unsubstantiated — likely false advertising** |
| **"GDPR Compliant"** | page.tsx:462 | No data-processing agreement, no deletion/export-for-GDPR machinery beyond a generic CSV export, no consent handling, no privacy controls. (App does have a workspace delete + contact CSV export, but that's not GDPR compliance.) | **Unsubstantiated** |
| **"99.9% uptime" / "99.99% SLA" (Enterprise)** | page.tsx:179, 386 | No SLA infrastructure, no uptime monitoring shipped (DEPLOY.md §Observability explicitly says NO Sentry, NO alerting, manual setup required). PROGRESS.md says no live Railway URL is even configured. | **Unsubstantiated** |
| DEMO_SCRIPT data-privacy pitch: "we never train on it … only external calls are to Anthropic's API … stateless" | DEMO_SCRIPT.md:106-107 | Plausible architecturally (Claude API + own Postgres), but unverified and stated as a guarantee. Also ignores Hunter.io, Google, Slack external calls. | **Partially supportable, overstated** |

**Note (security, doc-vs-code, IN THE SAFE DIRECTION):** DEPLOY.md:55 and the recovered HANDOFF.md both claim Slack signature verification is **"skipped (dev-only behavior)"** when `SLACK_SIGNING_SECRET` is unset. The **actual deployed code** in `slack_interactions.py:40-45` **fails closed** (`if not settings.SLACK_SIGNING_SECRET: return False`) with a comment explaining the forged-POST→send-email-via-victim's-Gmail risk. So the code is safer than the docs claim. This is a doc inaccuracy, not a live vuln — but it means operators reading DEPLOY.md have a WRONG mental model of the auth behavior. Flag for homogenization.

---

## 3. Test-count claims — inconsistent across surfaces

| Source | Claim | Reality |
|---|---|---|
| PROGRESS.md:40 | "324 tests pass (up from 318)" | `grep -rh "def test_" apps/api` = **325** backend test functions. Web (`it(`/`test(`) = **9** (Playwright smoke). So "324" is approximately right for backend but the exact integer drifts per commit and excludes the 9 web E2E. |
| PROGRESS.md history | 288 → 295 → 304 → 305 → 308 → 312 → 318 → 324 (a per-phase running tally) | Internally consistent narrative; final number ~matches actual. |
| HANDOFF.md (recovered) | **"29/29 endpoints passing"** and **"12 pages compiled"** | A different, older metric (endpoint smoke tests, not unit tests). Dated 2026-04-29 vs PROGRESS.md up to 2026-06-03. Reflects an earlier snapshot — stale. |
| README.md | No explicit test count | — |

Bottom line: test claims are roughly truthful for the backend unit suite (~324–325) but the docs use **three different testing metrics** (unit count, endpoint count, page count) without reconciling them. The HANDOFF "29/29" is stale.

---

## 4. Cross-surface NUMERIC inconsistencies (homogenization targets)

The same product reports wildly different headline numbers depending on which surface you read. All are mock/demo values, but they are presented as if real and they don't even agree with each other:

| Metric | Marketing page.tsx | DEMO_SCRIPT.md | Code seed (auth.py) / README |
|---|---|---|---|
| Revenue | **$2.4M** (preview tile, L192) | **$485K** (L17) | n/a (demo-data.ts drives real demo) |
| Accuracy | **94.7%** (badge L144 + tile L194) | **91%** lead accuracy (L17, L88) | per-agent: 94.2/87.1/91.8/89.5/85.3/92.0/100.0 (L18-24) |
| Agents | **"6 Running"** (L144) and **"6 / 8"** (L195) — internally contradictory | "6 agents" (L87) / "3 agents running right now" (L17) | **7** agents in seed list |
| Deals | 148 (L193) | — | — |
| Churn/Sentiment agent | "Churn Prediction / RoBERTa" feature card | not shown as agent | seed has "Sentiment Analyzer" (claude-haiku), NO churn agent |
| "PM Agent" (accuracy 100.0, model heuristic) | NOT advertised anywhere on marketing | not in demo script | present in seed (L24) — undocumented externally |

**README vs DEMO vs marketing on agent set:** README §Agents lists only **2** ("Nightly pipeline optimizer" 02:00 UTC + "Nightly deal health scorer" 02:15 UTC). DEMO_SCRIPT lists **6** by name (Semantic Sorter, Lead Scorer, Email Composer, Call Summarizer, Pipeline Optimizer, Sentiment Analyzer). Marketing implies 6 running / 8 total. Code defines **7** (the 6 + PM Agent). **Four different agent inventories.** DEPLOY.md Beat schedule lists **3** scheduled tasks (pipeline.optimize 02:00, deal_health 02:15, followup_sequences 09:00) — a fifth count.

---

## 5. Pricing & business claims (DEMO_SCRIPT + page.tsx) — assertions, mostly unverifiable

| Claim | Source | Note |
|---|---|---|
| Starter **$49/mo** (3 agents, 1,000 contacts), Pro **$149/mo** (all 6 agents, unlimited), Enterprise Custom | page.tsx:370-388 | DEMO_SCRIPT.md:112 says "$49/user/month core, $149/user AI tier" — phrasing "per-user" vs page "/mo" plan tiers differs slightly. No billing/Stripe code exists in repo, so NONE of these tiers are enforced. Pricing is aspirational. |
| Enterprise: **"SSO + SCIM", "On-premise deployment", "Dedicated ML engineer", "99.99% SLA"** | page.tsx:386 | No SSO/SCIM code, no on-prem packaging beyond docker-compose, no ML engineer (no ML models), no SLA. All aspirational. |
| **"currently in beta with 3 teams"** / "looking for the right seed partner" | DEMO_SCRIPT.md:96 | Unverifiable from repo. Investor-facing traction claim. |
| Target ACV **$15K–$80K**, per-seat SaaS | DEMO_SCRIPT.md:112 | Business projection, not a code claim. |
| Plan feature gating ("3 AI Agents" on Starter) | page.tsx:374 | No entitlement/feature-flag enforcement in code — all features available regardless of "plan". |

**Auth bypass note (UX/trust):** Every marketing CTA ("Start Free", "Launch App", "Launch NovaCRM", "Log in") links to `/dashboard` (page.tsx:79,84,121,164,453). There is no signup form on the landing page despite "Start Free Trial" / "No credit card required". `/dashboard` is auth-guarded server-side (`(app)/layout.tsx`: redirects to `/login` if no user, `/onboarding` if no workspace) — UNLESS `NEXT_PUBLIC_DEMO_MODE=true`, which **bypasses all auth** (layout.tsx:10-16). If the production web service is deployed with DEMO_MODE on (DEPLOY.md repeatedly suggests demo mode as the safe default to "enable while backend is being set up"), the entire app is unauthenticated and serving mock data. **This is the single biggest deploy-posture risk.**

---

## 6. Functional / architecture claims in README & docs — mostly TRUE, some caveats

| Claim | Source | Verdict |
|---|---|---|
| Next.js 16, FastAPI async SQLAlchemy Py3.11, Celery+Redis, Postgres16+pgvector, Supabase ES256 JWT, Claude Sonnet/Haiku + Whisper | README:7-14 | **TRUE** — matches requirements.txt + code (anthropic, sentence-transformers, whisper, asyncpg, celery[redis], PyJWT[crypto]). |
| Audio upload mp3/m4a/wav/ogg/webm/flac, 50 MB max | README:96 | Plausible (calls.py handles multipart). 50 MB limit to be re-verified in calls.py by audit team. |
| Hunter.io "free tier: 25 req/month" | README:119 | Hunter integration real (`enrich_contact.py` calls api.hunter.io email-finder/verifier). The "25/month" figure is Hunter's plan detail, not enforced in code. |
| Demo mode "All 44 API client methods have demo stubs" (DEPLOY.md:256) vs HANDOFF "44 API client methods" | DEPLOY/HANDOFF | Consistent internally at 44. Not independently counted here — flag for audit team to confirm api-client.ts method count. |
| Celery Beat: pipeline 02:00, deal_health 02:15, followup_sequences 09:00 UTC | DEPLOY.md:184-190 | Matches worker module names seen in grep. README only mentions the first two. |
| `/health` returns 200 always, body status ok/degraded, pings DB with SELECT 1 | DEPLOY.md:14,177 | Asserted by the self-audit; to be verified in main.py by audit team. |
| Migration 005 adds 'error' to severity CHECK; without it HITL errors cause constraint violations | DEPLOY.md:19,220-222 | Self-audit claim; `slack_interactions.py` does write `severity="warning"`/`"error"` (saw "warning" at L69). Plausible. Flag: is 005 actually applied in prod? PROGRESS/DEPLOY list it as a REMAINING manual step. |
| "Realtime removed (activity via FastAPI SSE)" [Phase 1e] THEN "Supabase Realtime activity feed — replaced EventSource/SSE" [Phase 7c] | PROGRESS.md:9 vs :33 | **Self-contradicting history**: SSE replaced Realtime, then Realtime replaced SSE. Whatever ships now, the docs disagree about the mechanism. Homogenization target. |

---

## 7. PROGRESS.md "Blockers" that are also implicit claims

- "Supabase production credentials ARE present in apps/api/.env and apps/web/.env.local" (L50) — confirms **real prod secrets live in gitignored local files**; DEPLOY.md §Critical says rotate them if ever shared, and git history (commit 893a7ba) shows an anon key + test creds WERE committed once. **Credential-hygiene risk, partially realized.**
- "Local DATABASE_URL points to localhost:5433 … /health returns degraded locally" (L50) — consistent with DEPLOY health design.
- GMAIL_PUBSUB_TOPIC/SECRET, SLACK_SIGNING_SECRET not set → push/webhooks won't work in prod (L51-52). Honest blocker disclosure. NOTE this contradicts marketing's "agents running 24/7" framing — the webhook-driven ingestion is NOT live without these.

---

## 8. Summary of "false advertising" exposure (for synthesizer / homogenization)

**Tier 1 — outright false (model/tech claims contradicted by code):**
1. "GPT-4o Fine-tuned" email composer → actually Claude Haiku, no OpenAI dep.
2. "XGBoost v2 / F1 0.947" lead scoring → heuristic, no XGBoost.
3. "RL Policy / LightGBM" pipeline → heuristic lookup table.
4. "RoBERTa Fine-tuned" churn prediction → Claude Haiku sentiment; no churn feature.
5. "Whisper Large v3" → Whisper **base**. "Claude 3.5" → claude-sonnet-4-6.
6. "94.7% Accuracy" / "F1 0.947" / "48% open / 22% reply" → fabricated constants; nothing computes them.
7. Animated "live" agent log with "model_retrain … f1→0.951" → fully hardcoded; heuristics never retrain.

**Tier 2 — unsubstantiated trust/compliance claims:**
8. "SOC 2 Type II", "GDPR Compliant", "99.9% / 99.99% uptime/SLA" — no evidence anywhere; observability explicitly NOT shipped.

**Tier 3 — internal inconsistency (homogenization):**
9. Revenue ($2.4M vs $485K), accuracy (94.7% vs 91% vs per-agent), agent count (2 vs 3 vs 6 vs 6/8 vs 7), test metric (324 unit vs 29 endpoint), activity mechanism (SSE vs Realtime, flip-flopped). Pricing tiers unenforced (no billing code).

**Tier 4 — deploy-posture / security:**
10. DEMO_MODE bypasses ALL auth (layout.tsx:10) and docs recommend enabling it on the web service — risk of shipping an unauthenticated, all-mock app to prod.
11. Historical credential leak in git history (HANDOFF.md anon key + test password, later scrubbed but still in history → must rotate).
12. DEPLOY.md/HANDOFF claim Slack sig verification is "skipped when unset" but code fails closed — doc is wrong (safe direction), still a fix-the-docs item.

**Missing scope artifacts:** AUDIT_ROADMAP.md never existed; HANDOFF.md only in git history (and was the source of the leaked-credential commit).
