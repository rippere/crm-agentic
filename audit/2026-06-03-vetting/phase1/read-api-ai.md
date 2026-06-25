# NovaCRM AI Subsystem — Phase 1 Read Notes (apps/api routers/ai.py, agents.py, calls.py, mcp_server.py + services/{clarity,sentiment,extraction,embedding,deal_health}.py)

Repo: /tmp/crm-signup-fix (git worktree of production master — deployed code).

## TL;DR
- The AI is **substantially real**, not vaporware — but it is **NOT what the marketing describes**.
- Real: Claude (Haiku/Sonnet) calls for sentiment, clarity, task extraction, email compose, enrichment, call summary; local Whisper transcription; local MiniLM embeddings; deterministic heuristics for lead scoring and deal health.
- Stubbed / fake: the **"6 AI Agents / 94.7% accuracy"** marketing layer. The `agents` table is a cosmetic dashboard. `POST /agents/{id}/run` is an explicit stub that enqueues NOTHING. The fabricated model names (XGBoost v2, RoBERTa, GPT-4o, RL Policy + LightGBM, Whisper Large v3) exist ONLY in seed/demo data — no such code or models exist in the repo. `ml_win_probability` is a user-supplied/default-50 integer column, not an ML output.
- **Zero cost controls / token accounting anywhere.** No budget, no usage tracking, no per-workspace spend cap. API key is a single global shared key.

---

## FILE-BY-FILE

### routers/ai.py — "Nova" freeform assistant (REAL)
- `POST /workspaces/{workspace_id}/ai/query`, rate-limited 20/min. Tenant check L52 (`current_user.workspace_id != workspace_id → 403`). Good.
- Builds a live workspace snapshot (contact count, top 20 deals, open tasks, last 5 activity events) and feeds it to Claude.
- Model: `claude-haiku-4-5-20251001` (L108), max_tokens=512.
- System prompt (L21-31) is decent and product-aware ("Nova", names real features). Quality: good.
- Failure handling: bare `except Exception` → 503 with **the raw exception string echoed to the client** (L114-118: `detail=f"AI unavailable: {exc}"`). Minor info-leak; could surface key/internal errors to API consumers.
- `msg.content[0].text` accessed after an `if msg.content else` guard — safe-ish, but assumes block 0 is text.

### routers/agents.py — Agent dashboard CRUD + "run" STUB (COSMETIC)
- `GET /agents`: lists Agent rows for the caller's workspace. Tenant-scoped (L45). OK.
- `POST /agents/{agent_id}/run` — **docstring literally says "Stub"** (L56). Sets `agent.status="processing"`, writes an ActivityEvent, returns a random `job_id = str(uuid.uuid4())`. **It enqueues no Celery task.** Confirmed: no `.delay`/`apply_async`/task ref in the file.
  - The returned `job_id` is a fresh UUID with **no corresponding Celery task**, so `GET /jobs/{job_id}` will forever return state `PENDING` (Celery reports unknown IDs as PENDING). The UI will show "processing" indefinitely.
  - The ONLY thing that ever clears `status=processing` is `pm_agent.py`, which after 30 min flips stuck agents to **`error`** and logs a severity=error event (pm_agent.py L50-65). So every manual "Run agent" click degrades into an error alert ~30 min later. Self-inflicted failure signal.
- `PATCH /agents/{agent_id}` accepts arbitrary `status` string (no enum/validation) — caller can set any status, incl. fake "active".
- `GET /jobs/{job_id}` is real Celery `AsyncResult` lookup — but **not workspace-scoped**: any authenticated user can poll any job_id (cross-tenant job result read if they can guess/obtain an ID). Job IDs are random UUIDs so low practical risk, but it's an authz gap (no ownership check on the job).
- `accuracy` field is `Numeric` default 0; seeded to fixed marketing numbers (see auth.py). It is **never computed or updated by any code path**. Static vanity metric.

### routers/calls.py — Call Summarizer upload (REAL pipeline)
- `POST /workspaces/{id}/calls/upload` (202), 10/min. Tenant check L53.
- Validates extension against ALLOWED_AUDIO and size vs `MAX_CALL_UPLOAD_MB` (default 50). Reads whole file into memory then writes to a NamedTemporaryFile (delete=False) and enqueues `transcribe_call.delay(call_id, tmp.name)`.
- **Validation-order bug:** extension/size are checked AFTER `await file.read()` of the entire upload into RAM (L63). A 5 GB `.txt` would still be fully buffered before the 413. The 50 MB cap is enforced post-read, so memory isn't truly bounded by it for a single huge request. (Also `file.read()` then length check, not streaming.)
- Magic-bytes/content sniffing: none — extension-only. A renamed non-audio file passes to Whisper and fails in the worker (temp file is cleaned up in `finally`, OK).
- list/get/delete all tenant-scoped (L108/143/178). `get_call` exposes `model_used` (real: `whisper-{size}`). `processing` flag derived from empty transcript.
- `contact_id` parse failure is silently swallowed (`except ValueError: pass`, L80-81) → bad contact_id just yields null link, no 400. Minor.

### routers/mcp_server.py — native MCP server (REAL for 4 tools; doc lies about a 5th)
- Streamable HTTP JSON-RPC at `POST /mcp`, Bearer JWT, 20/min. initialize/tools/list/tools/call implemented.
- 4 working tools: list_contacts, list_deals, stale_deals, pipeline_summary. All read `current_user.workspace_id` (L251) → tenant-scoped. Good.
- **Module docstring (L12) advertises `ask_crm` "free-text AI query over CRM data" as a supported tool — but it is NOT in `TOOLS` and NOT in `TOOL_HANDLERS`.** Calling it returns `-32601 Unknown tool`. Doc/impl mismatch (claim vs reality).
- `list_contacts` does the text `query` filter **in Python AFTER applying `.limit(limit)` in SQL** (L97 then L102-108). So search is applied only to the first N rows fetched by status — a query for a contact beyond the limit window silently returns nothing. Correctness bug masquerading as "semantic"/search. (Note: it's substring matching, not embeddings — the description claims "ML lead score" return, which is real-ish via ml_score JSONB, but the search itself is naive substring.)
- `_list_deals` surfaces `d.ml_win_probability` as "Win prob: X%" — see below, this is not ML.
- Errors from handlers are stringified back to the JSON-RPC client (`_err(req_id, -32603, str(exc))`, L258) — info leak of internal exceptions.

### services/clarity.py — message clarity 0-100 (REAL, Claude Sonnet)
- `score_clarity(message_body)` → `claude-sonnet-4-6`, max_tokens=256, truncates body to 4000 chars.
- Prompt is **good**: explicit 0-100 rubric + strict JSON contract. Quality: high.
- Robust parse: clamps 0-100, truncates rationale, returns `{score:50, rationale:"Scoring failed"}` on JSONDecodeError/Type/Value. Graceful.
- BUT: **uses a synchronous `anthropic.Anthropic` client inside an `async def`** (blocking call on the event loop). Called from FastAPI endpoint `score_message_clarity` (messages.py L87) AND from the async ingest worker (ingest.py L409). This blocks the async loop for the full Claude latency. Pattern is acknowledged in the docstring ("Follows the same sync-client-in-async-function pattern as extraction.py") — i.e. it's a known, propagated anti-pattern. Inconsistent with ingest.py/followup/contacts.compose which correctly use `AsyncAnthropic`.
- Module-global singleton client `_client`; api key read once via `os.getenv("ANTHROPIC_API_KEY","")` — empty string if unset → API call 401s at runtime (no startup guard here; clarity has NO empty-key short-circuit, unlike sentiment.py).

### services/sentiment.py — tone analysis (REAL, Claude Haiku)
- `analyze_sentiment(message_body)` → `claude-haiku-4-5`, max_tokens=256, body[:4000].
- Returns `{sentiment, confidence, signals}`; on missing key returns neutral default **without calling** (L51-53) — best-effort, never blocks ingest. Catches all exceptions → neutral default. Strips ``` code fences. Robust.
- This is the cleanest service: empty-key guard + blanket try/except + safe default. Good model for homogenization.
- SYNC client but called synchronously from the Celery worker thread (ingest.py L386 `sentiment_result = analyze_sentiment(...)` — not awaited), so no event-loop blocking issue here. Acceptable in Celery context.

### services/extraction.py — task extraction (REAL, Claude Haiku)
- `extract_tasks(message_body, workspace_id)` → `claude-haiku-4-5`, max_tokens=1024, body[:8000]. `workspace_id` param is **not used** (doc says "for logging / future attribution (not sent to Claude)") — dead/aspirational param.
- Prompt good: strict JSON array contract.
- Parse: `json.loads(raw)` guarded by `(JSONDecodeError, IndexError)` → `[]`. **No markdown-fence stripping here** (unlike sentiment.py / compose / enrich), so a fenced response (```json ... ```) silently yields `[]` and drops all tasks. Inconsistent fragility across services.
- Same SYNC-client-in-async-def anti-pattern; awaited from ingest.py L368 (async) → blocks loop.
- No per-item schema validation: whatever objects Claude returns are passed through (downstream may get malformed task dicts).

### services/embedding.py — local sentence embeddings (REAL, local model)
- `all-MiniLM-L6-v2`, 384-dim, normalize_embeddings=True, lazy `@lru_cache` model load. No API/key. Genuinely local & free.
- `embed_text` is **synchronous and CPU-heavy**; if ever called from an async path it blocks (here used by embed_contacts worker — Celery, fine).
- This backs the "semantic" search claim — real embeddings exist, but note mcp_server.list_contacts does NOT use them (naive substring). Need to confirm where vector search is actually wired (contacts router /search — out of this scope but flagged).

### services/deal_health.py — deal health 0-100 (REAL, but pure HEURISTIC)
- Deterministic: start 100, decay by stage-staleness (`_DECAY_PER_DAY=3` beyond per-stage threshold) + engagement gap penalties (−20 no msgs, −20 >14d, −30 >30d). Clamped 0-100. Returns (score, human signals).
- No ML, no model — **this is the "deal health monitoring" / "ML models to score deals" marketing claim, and it's a rules engine.** Honest in code, oversold in marketing.
- Consumed by deal_health_worker (nightly 02:15 + on-demand from deals.py L109). Worker fires `deal_alert` ActivityEvent for score ≤25 with a canned `_NEXT_BEST_ACTION[stage]` string. "Next best action" = static dict lookup, not RL/LightGBM as seed claims.

---

## CROSS-CUTTING: model strings actually used (grep, unique)
- `claude-haiku-4-5` (6×), `claude-haiku-4-5-20251001` (5×), `claude-sonnet-4-6` (8×). **Only 2 underlying models** (Haiku 4.5, Sonnet 4.6) + local Whisper + local MiniLM.
- **Model-name inconsistency:** some call sites use the dated alias `claude-haiku-4-5-20251001` (ai.py, contacts compose, enrich, followup), others the rolling `claude-haiku-4-5` (sentiment, extraction, ingest relevance). Mixing pinned and rolling aliases for the same logical model = drift risk. Homogenize.
- NOTE for verifier: these model IDs (`claude-haiku-4-5`, `claude-sonnet-4-6`) should be checked against the actual Anthropic model catalog — they may be hallucinated/aspirational IDs that 404 at runtime. The whole AI layer's "realness" hinges on whether these IDs resolve. (Could not verify against live API in scope.)

## CROSS-CUTTING: API key & cost
- Single global `ANTHROPIC_API_KEY` (config.py required field for the API; workers read `os.getenv` directly). Shared across ALL workspaces/tenants — no per-tenant key, no attribution.
- **No cost controls of ANY kind.** grep for input_tokens/output_tokens/usage/cost/budget/spend/token-count = nothing. Every ingested message triggers 3 Claude calls (extract_tasks + sentiment + clarity) with NO budget ceiling, NO dedupe on spend, NO per-workspace quota. A tenant syncing a large mailbox = unbounded spend on the shared key. This is the single biggest commercial risk.
- Inconsistent key handling: config.py declares `ANTHROPIC_API_KEY` as a **required** Settings field (app won't boot without it), yet `compose_email` carries `# TODO: needs ANTHROPIC_API_KEY in env` (contacts.py L266) — stale TODO contradicting config. And services read `os.getenv(...,"")` defaulting to empty (would 401) rather than `settings.ANTHROPIC_API_KEY`. Two different key-access patterns (settings vs os.getenv).

## CROSS-CUTTING: error/exception leakage
- ai.py, mcp_server.py both echo `str(exc)` to clients. Sentiment/extraction/clarity swallow to safe defaults (better). Inconsistent failure posture across the AI surface.

---

## CLAIMS-vs-REALITY (marketing → code)
| Marketing / UI / seed claim | Reality in code |
|---|---|
| "6 AI Agents Running" (page.tsx L143, L194 "6/8") | `agents` table is a cosmetic dashboard; 7 default agents seeded (auth.py `_DEFAULT_AGENTS`). `/agents/{id}/run` is a no-op stub. "Running" = a status string, not a process. |
| "94.7% Accuracy" (page.tsx L143/194; seed.ts Lead Scorer accuracy:94.7, F1 0.947) | `accuracy` is a static seeded Numeric, never computed. 94.7 maps to a fabricated "XGBoost v2" Lead Scorer that is actually a 50-base heuristic (score_contact.py). No accuracy measurement exists anywhere. |
| "Each agent is a specialized ML model" (page.tsx L296) | Mostly heuristics (lead scorer, deal health/pipeline, pm_agent) + Claude prompts (sentiment, clarity, extraction, compose, enrich, call summary) + local MiniLM + local Whisper. Only 2 ML-ish components (MiniLM, Whisper) are "models"; rest are rules or LLM prompts. |
| seed.ts models: "XGBoost v2 + Feature Store", "GPT-4o (fine-tuned)", "Whisper Large v3 + Claude 3.5", "RL Policy + LightGBM", "RoBERTa fine-tuned + GPT-4o-mini" | **None exist.** No XGBoost, LightGBM, RoBERTa, GPT-4o, RL, fine-tuning, or feature store anywhere in the repo. Real backend = Claude Haiku/Sonnet + Whisper base + MiniLM. demo-data.ts repeats the fabrication with different fake IDs (xgboost-v2.1-crm, twitter-roberta, gpt-4o-mini, whisper-large-v3). |
| auth.py `_DEFAULT_AGENTS` accuracies (94.2/87.1/91.8/89.5/85.3/92.0/100.0) | All hardcoded literals. PM Agent "accuracy 100.0" is meaningless (it's a monitor). |
| MCP doc: "ask_crm: free-text AI query over CRM data" | Not implemented as an MCP tool; returns Unknown tool. |
| "ML lead score" (MCP list_contacts desc) | Heuristic score in ml_score JSONB (base 50 ± status/revenue/deals). Not ML. |
| Deal "Win prob: X%" (mcp list_deals; deals.py uses `ml_win_probability`) | `ml_win_probability` is a plain int column, default 50, user-settable via POST/PATCH (deals.py L281/L363). No model produces it. "ml_" prefix is misleading. |
| Call Summarizer "Whisper Large v3 + Claude 3.5", accuracy 97.1 | Real = Whisper **base** (env default, transcribe.py) + **claude-sonnet-4-6**. model_used persisted as `whisper-base`. Marketing says Large v3 + Claude 3.5 — both wrong. |
| "SOC 2 Type II · 99.9% uptime · No credit card" (page.tsx L181) | Unverifiable compliance/uptime claims in hero. No evidence in repo. Flag for legal/marketing review. |
| Landing: "summarize calls ... without lifting a finger" / autonomous | Call summary requires manual audio upload (calls.py). Email compose returns a DRAFT (compose_email), not autonomously sent. "Autonomous agents to compose emails... move your pipeline" overstates. |

## INCONSISTENCIES (for homogenization)
1. **Sync vs async Anthropic client:** clarity.py + extraction.py use sync `Anthropic` inside `async def` (blocks event loop when called from FastAPI/async worker); ingest.py, followup_sequences.py, contacts.compose use `AsyncAnthropic`. Pick one. The docstring in clarity.py admits it copies extraction.py's anti-pattern.
2. **Key access:** `settings.ANTHROPIC_API_KEY` (ai.py, contacts.py) vs `os.getenv("ANTHROPIC_API_KEY","")` (all services + workers). Config marks it required; services default to "". Stale `# TODO: needs ANTHROPIC_API_KEY` in contacts.py L266.
3. **Model alias drift:** `claude-haiku-4-5` vs `claude-haiku-4-5-20251001` for the same model across files.
4. **JSON-from-LLM parsing is copy-pasted N times** with DIFFERENT robustness: sentiment strips ``` fences; compose strips fences; enrich uses regex `\{.*\}`; transcribe uses regex fallback; extraction.py does NEITHER (plain json.loads → drops data on fenced output); ai.py/clarity differ again. Should be one shared `parse_llm_json()` util.
5. **DB session factory for workers duplicated** in every worker (`_make_session`/`_get_async_session`/`_get_session`) with slightly different URL-normalization logic (some handle `postgres://`, some `postgresql://`, some neither). 5+ near-identical copies. Centralize.
6. **Error surfacing:** ai.py + mcp_server.py leak `str(exc)` to clients; services swallow to defaults. Inconsistent.
7. **`agents` table vs real workers:** the dashboard "agents" (Agent model) are entirely disconnected from the actual Celery workers that do the work. There is no link between `Agent.type` and the worker that implements it; "run" doesn't invoke the corresponding worker. Two parallel, unreconciled notions of "agent."
8. **`accuracy` / `ml_win_probability` / `tasks_today` / `last_run`** are vanity columns never updated by backend logic (seed/demo only). agents.page.tsx even fabricates a sparkline from `Math.sin(i)` (page.tsx L100) — synthetic trend over static number.
9. MCP `list_contacts` filters post-LIMIT in Python; everywhere else filtering is in SQL. Correctness + pattern divergence.

## RISKS (evidence)
- [HIGH/authz] `GET /jobs/{job_id}` (agents.py L115-134) has **no workspace/ownership check** — any authenticated user can read any Celery job result/error by ID. Cross-tenant data exposure if a job result contains tenant data (transcribe/enrich results do). Auto-high per multi-tenancy rule.
- [HIGH/cost] No cost controls / token accounting / per-tenant quota anywhere; shared global API key; ingest fires 3 LLM calls per message unbounded (ingest.py L368/386/409). Runaway-spend + noisy-neighbor on shared key. (config.py, all services.)
- [MEDIUM/correctness] `/agents/{id}/run` is a stub that returns a job_id with no task → UI shows "processing" forever, then pm_agent flips it to `error` at 30 min (agents.py L50-78; pm_agent.py L50-65). Every manual run produces a false error alert. User-visible broken feature.
- [MEDIUM/info-leak] Raw exception strings returned to clients (ai.py L117; mcp_server.py L249/258).
- [MEDIUM/correctness] MCP `list_contacts` applies text query AFTER SQL LIMIT (mcp_server.py L97-108) → search misses rows beyond the limit window; silent empty results.
- [MEDIUM/perf] Sync Anthropic client in `async def score_clarity`/`extract_tasks` blocks the event loop on every FastAPI clarity call + async ingest (clarity.py L47; extraction.py L46; called messages.py L87, ingest.py L368/409).
- [MEDIUM/DoS-ish] calls.py reads entire upload into memory before size check (calls.py L63-68); 50 MB cap not enforced during read; no content-type sniffing.
- [LOW/correctness] extraction.py drops all tasks if Claude wraps JSON in a code fence (no fence stripping) (extraction.py L55-62).
- [LOW/data-integrity] `ml_win_probability` / `accuracy` named as ML outputs but are static/user-set columns — misleads downstream logic (deals.py L235 gates a recommendation on a hand-set number) and customers.
- [LOW/info] PATCH /agents accepts arbitrary status string, no enum (agents.py L106-108).
- [LOW] `contact_id` ValueError silently swallowed on call upload (calls.py L80).

## OPEN QUESTIONS (for verifier/synth)
- Do model IDs `claude-haiku-4-5`, `claude-sonnet-4-6`, `claude-haiku-4-5-20251001` actually resolve against the live Anthropic API, or are they aspirational/hallucinated? Entire "real AI" verdict depends on this — verify with a live call.
- Where is the actual semantic/vector contact search wired (contacts router /search)? embedding.py exists but MCP doesn't use it; confirm a real pgvector/cosine path exists vs. the substring fallback.
- Is Celery beat actually running in prod (does nightly deal-health/pipeline + pm-health-check fire)? If not, deal_health/pipeline_optimizer "active" agents do nothing.
- Does any onboarding path seed the marketing-grade fake agents (seed.ts) into a real customer workspace, or only auth.py `_DEFAULT_AGENTS`? seed.ts is in apps/web/scripts — confirm it's dev-only.
