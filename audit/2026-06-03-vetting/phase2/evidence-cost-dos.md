# NovaCRM Phase 2 — Cost-DoS Pairing (Rate Limiter ⊕ Shared ANTHROPIC_API_KEY ⊕ 2-slot worker)

**Scope:** CODE-READ ONLY. No live load test against prod was run (per authorization).
**Verdict:** PROVEN (mechanism demonstrated empirically on the real limiter code + config).
**Date:** 2026-06-03
**Code under test:** `/tmp/crm-signup-fix/apps/api`

---

## Thesis

One authenticated tenant can drive **unbounded spend** on the single shared
`ANTHROPIC_API_KEY` and **starve the 2-slot Celery worker queue** for every other
tenant, because:

1. The per-route rate limiter is effectively a **single global bucket shared by ALL
   tenants** (it keys on `request.client.host`, which behind Railway's proxy is one
   fixed edge-proxy IP — and the intended per-user key is dead code).
2. There is **no per-tenant cost/budget/quota** anywhere in the codebase on the one
   shared Anthropic key.
3. A single inbound message triggers **up to 4 model calls** (3× Haiku + 1× Sonnet);
   the heaviest endpoints fan out N× that through a worker pool hard-pinned to
   **`--concurrency=2`** with no queue isolation.

---

## (a) Does the rate limiter actually gate the expensive AI endpoints, and is it keyed correctly behind Railway's proxy?

### Finding A1 — The limiter key is broken two ways: dead per-user branch + XFF-blind IP

`/tmp/crm-signup-fix/apps/api/app/limiter.py`:
```python
def _rate_key(request) -> str:
    user = getattr(request.state, "user", None)   # ← request.state.user is NEVER set
    if user is not None:
        return str(getattr(user, "id", get_remote_address(request)))
    return get_remote_address(request)            # ← always taken

limiter = Limiter(key_func=_rate_key)
```

**`request.state.user` is never assigned anywhere in the app.** Authentication is a
FastAPI *dependency* (`get_current_user`) that returns a `User`; it does not write to
`request.state`. Proof:
```
$ grep -rn "request.state" apps/api/        # only the READ in limiter.py
apps/api/app/limiter.py:7:    user = getattr(request.state, "user", None)
$ grep -rn "state.user" apps/api/           # assignments:
(none)
```
There is no `@app.middleware` and no dependency that sets `request.state.user`
(`main.py` registers only `SlowAPIMiddleware`, `CORSMiddleware`, and a logging
middleware). So `_rate_key` **always** falls through to `get_remote_address`.

### Finding A2 — `get_remote_address` ignores X-Forwarded-For; uvicorn is launched WITHOUT `--proxy-headers`

slowapi `get_remote_address` (installed 0.1.9, project pins `slowapi>=0.1.9` in
`apps/api/requirements.txt`) reads **only** `request.client.host` — it does NOT parse
`X-Forwarded-For` (only the unused `get_ipaddr` helper does, and even that checks the
wrong header name `X_FORWARDED_FOR`):
```python
def get_remote_address(request):
    if not request.client or not request.client.host:
        return "127.0.0.1"
    return request.client.host
```

For `request.client.host` to be the *real* client IP behind a proxy, uvicorn must be
started with `--proxy-headers` (+ `--forwarded-allow-ips`). It is **not**:

- `apps/api/start.sh`: `exec .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000`
- `apps/api/Dockerfile` CMD (the actual prod entrypoint on Railway):
  `CMD ["/bin/sh","-c","exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]`
```
$ grep -rn "proxy-headers\|forwarded-allow\|ProxyHeaders" apps/api/
(no matches)
```
Therefore on Railway, `request.client.host` is the **Railway edge/proxy IP**, which is
the same for every tenant's request. The rate limiter becomes **one global bucket**.

### Empirical proof (ran the real `_rate_key` from the codebase)

Throwaway venv with the project's pinned slowapi (0.1.9), feeding the verbatim
`app/limiter.py` two different tenants arriving via the same proxy IP:

```
$ /tmp/_pocvenv/bin/python  (loads /tmp/crm-signup-fix/apps/api/app/limiter.py verbatim)

[1] get_remote_address ignores X-Forwarded-For:
    A -> 100.64.0.7 | B -> 100.64.0.7
    collapse to proxy IP: True
[2] request.state.user is NEVER set -> _rate_key falls back to IP:
    hasattr(state,'user') = False
    _rate_key(A) = 100.64.0.7
    _rate_key(B) = 100.64.0.7
    => ALL tenants share ONE bucket: True
[3] control: when .user IS present, key becomes user id:
    _rate_key(C) = user-123 (but nothing in the app ever does this)
```

Interpretation:
- `[1]` proves XFF is ignored → all tenants collapse to the proxy IP.
- `[2]` proves the per-user branch is dead → key = that one proxy IP for everyone.
- `[3]` is the control: the limiter *logic* would key per-user **if** anything set
  `request.state.user`, confirming the defect is the missing assignment, not slowapi.

### Consequence of A1+A2 (two-sided, both bad)

- **Cross-tenant DoS of the limit itself:** because the bucket is global, any one
  tenant's traffic consumes the shared per-route allowance (e.g. `20/minute` on
  `/ai/query`), throttling/locking out *all other tenants* on that route. The limiter
  meant to protect each tenant instead lets one tenant deny the route to everyone.
- **It is NOT a meaningful per-attacker cap either:** the limits are tiny and per-route,
  but the truly expensive amplifiers are reached through paths that bypass them
  (see A3 + section (b)).

### Finding A3 — The biggest cost amplifier has NO rate limit at all

`POST /workspaces/{id}/messages/reprocess` (`apps/api/app/routers/messages.py:141-159`)
has **no `@limiter.limit`** decorator. It enqueues `reprocess_workspace_messages`, which
(`apps/api/app/workers/ingest.py:_run_reprocess`, lines 444-540) loops over **every
message in the workspace** and per message calls:
`_is_deal_relevant` (Haiku) + `extract_tasks` (Haiku) + `analyze_sentiment` (Haiku) +
`score_clarity` (**Sonnet**) = **4 model calls × N messages**, all inside **one**
synchronous Celery task occupying **one of the two** worker slots for its full duration.

Rate-limit inventory (the only gated endpoints; note all share the broken global key):
```
auth.py:57            30/minute
search.py:128          2/minute
calls.py:42           10/minute   upload_call -> Whisper + Sonnet (worker)
messages.py:66        10/minute   score-clarity -> Sonnet (inline)
contacts.py:256       10/minute   compose -> Haiku (inline)
contacts.py:334        5/minute   enrich -> worker (Hunter + Haiku)
contacts.py:660       10/minute   (AI endpoint) -> Haiku
ai.py:43              20/minute   ai/query -> Haiku (inline)
mcp_server.py:218     20/minute
--- NOT rate limited: messages.py reprocess (full-workspace AI fan-out) ---
```

---

## (b) Per-tenant quota on the shared key? Model calls per inbound message?

### Finding B1 — Single shared ANTHROPIC_API_KEY, zero per-tenant accounting

Every Anthropic client in the codebase is constructed from the **same** process-wide key
(`os.getenv("ANTHROPIC_API_KEY")` / `settings.ANTHROPIC_API_KEY`) — routers, services,
and workers alike (20 references across `routers/ai.py`, `routers/contacts.py`,
`services/{clarity,extraction,sentiment}.py`, `workers/{ingest,transcribe,enrich_contact,followup_sequences}.py`).
There is **no** per-workspace key, no token metering, no spend cap:
```
$ grep -rin "budget\|quota\|usage_limit\|cost_cap\|token_budget\|billing\|credits\|monthly_limit\|tier_limit\|spend" apps/api/ --include=*.py
RC=1            # ← zero matches: no budget/quota/billing/credits/spend mechanism exists
```
`apps/web/.env.local` confirms a single `ANTHROPIC_API_KEY=...` is the project's only key.

### Finding B2 — Model calls per inbound message: up to 4 (and they include Sonnet)

Live ingest path (`workers/ingest.py`):
- `_is_deal_relevant_async` → 1× **Haiku** relevance check per candidate (ingest.py:114).
- For each relevant message, `enrich_message` → `_run_enrich_message`
  (ingest.py:338-428) calls, per message:
  - `extract_tasks` → 1× **Haiku** (services/extraction.py:46, `model=claude-haiku-4-5`)
  - `analyze_sentiment` → 1× **Haiku** (services/sentiment.py:57)
  - `score_clarity` → 1× **Sonnet** (services/clarity.py:47, `model=claude-sonnet-4-6`)

⇒ **~4 model calls per relevant inbound message** (3 Haiku + 1 Sonnet), the Sonnet call
being the costly one. `reprocess` re-runs the same 4 calls for *every existing message*
on demand with no rate limit. Call transcription (`workers/transcribe.py`) adds Whisper
(CPU/GPU-heavy, in-worker) + 1× **Sonnet** summary per upload.

### Finding B3 — Worker queue is hard-pinned to 2 slots, single undifferentiated queue

`apps/api/railway-worker.toml`:
```
startCommand = "celery -A app.workers.celery_app.celery_app worker --loglevel=info --concurrency=2"
```
`workers/celery_app.py` defines **no** `task_routes` / `task_default_queue` /
`worker_prefetch_multiplier`. So all task types — Whisper transcription, ingest, enrich,
scoring, deal-health, embeds, the unmetered `reprocess` — contend for the **same 2
slots**. A single long task (full-mailbox ingest up to `INGEST_MAX_PAGES=10`×100=1000
messages, or a full-workspace `reprocess`, or a long-audio Whisper job) **pins one slot**;
two such concurrent tasks **pin the entire pool**, blocking every other tenant's async
jobs (enrichment, call summaries, scoring) until they finish.

---

## Conclusion

**One tenant CAN drive unbounded spend AND starve the 2-slot worker queue.** Confirmed
mechanism:

- **Unbounded spend:** No per-tenant budget on the single shared `ANTHROPIC_API_KEY`
  (B1). A tenant uploads N messages then hammers `POST /messages/reprocess`
  (un-rate-limited, A3) → 4 model calls/message including Sonnet (B2), repeatable at
  will. Even the rate-limited inline endpoints (`/ai/query` 20/min, compose 10/min) put
  zero ceiling on *token volume* per call and are individually uncapped in cost.
- **Worker starvation:** Whisper uploads + full-workspace reprocess run synchronously in
  a pool fixed at `--concurrency=2` with no queue isolation (B3). Two long jobs from one
  tenant block all other tenants' async work.
- **Rate limiter does not save you:** behind Railway's proxy with no `--proxy-headers`,
  the limiter degrades to a *single global IP bucket* (A1+A2, proven empirically) — it
  cannot isolate tenants and the heaviest amplifier isn't even decorated (A3).

### Caveats / why not "fully" load-proven
Per authorization, **no live load/spend test was run against production**. The IP-collapse
and dead-user-key behaviors are proven by executing the real `limiter.py` against the
project's pinned slowapi version; the proxy-IP claim rests on the documented fact that
`request.client.host` reflects the immediate peer (the Railway proxy) unless uvicorn is
run with `--proxy-headers`, which the Dockerfile/`start.sh` do not do. The spend/starvation
*magnitudes* are derived from static call-count + concurrency analysis, not a live meter.

### Remediation
1. Set `request.state.user` in auth (middleware or dependency) so `_rate_key` actually
   keys per-user — OR change the limiter to require an authenticated principal and reject
   if absent (never silently fall back to a shared proxy IP).
2. Run uvicorn with `--proxy-headers --forwarded-allow-ips=<railway proxy CIDR>` so
   `request.client.host` is the real client (defense-in-depth; per-user keying is primary).
3. Add a **per-workspace token/cost budget** (Redis counter or DB ledger) checked before
   every Anthropic call; hard-fail or queue-defer when exceeded.
4. Rate-limit `POST /messages/reprocess` and cap/queue-bound the per-call fan-out
   (chunk + throttle reprocess; cap messages per reprocess).
5. Isolate worker queues (dedicated low-concurrency queue for Whisper/long jobs; separate
   queue for short enrich/scoring) and/or raise concurrency with prefetch=1 so one long
   job can't pin the pool.
6. Cap inbound `max_tokens`/input size per tenant tier; consider per-workspace Anthropic
   keys or usage attribution.

### Cleanup
No prod resources touched. Throwaway artifacts created locally only:
`/tmp/_pocvenv`, `/tmp/_limiter_under_test.py` (copy of the read-only source). No test
users/workspaces created; nothing left in any prod/dev DB.
