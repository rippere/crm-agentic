# Refutation attempt — "Rate limiter degrades to a single global IP bucket" (NovaCRM)

VERDICT: UPHELD (could not refute). All three legs re-verified by file:line re-read + empirical reproduction under the pinned slowapi. Authorization respected: code-read + one isolated local repro of the verbatim limiter; no prod load, no writes, no test data created.

## Environment confirmation (prod IS behind Railway proxy)
`railway variables --service api --json` (sensitive values redacted):
- PORT = 8000
- RAILWAY_ENVIRONMENT = production
- RAILWAY_PUBLIC_DOMAIN = api-production-c080.up.railway.app
- RAILWAY_SERVICE_NAME = api
=> The api service runs in production behind Railway's edge proxy. Precondition (request.client.host == proxy IP) holds.

## Leg (a) — global bucket / dead per-user key / XFF-blind / no --proxy-headers

apps/api/app/limiter.py (verbatim):
```
def _rate_key(request) -> str:
    user = getattr(request.state, "user", None)
    if user is not None:
        return str(getattr(user, "id", get_remote_address(request)))
    return get_remote_address(request)
limiter = Limiter(key_func=_rate_key)
```

- `grep -rn "state.user" apps/api/` => only limiter.py:7 (a READ) + main.py:72 (`app.state.limiter`, which is APP state, not request.state). Zero assignments to `request.state.user`.
- `grep -rn "request.state" apps/api/ --include=*.py` => only the READ at limiter.py:7.
- `get_current_user` (apps/api/app/dependencies.py:18) does NOT take a `request` param and NEVER sets `request.state.user`. It just returns a User. So the per-user branch is dead code.
- Architectural reinforcement: main.py registers `SlowAPIMiddleware`. The limit key is computed at the ASGI middleware layer, which runs BEFORE FastAPI resolves route dependencies (get_current_user). So even hypothetically nothing could populate request.state.user in time. Key always falls through to get_remote_address.
- No proxy-header handling anywhere: `grep -rn "proxy-headers|forwarded-allow|ProxyHeaders" apps/api/` => RC=1 (no matches). The only uvicorn start lines are:
  - apps/api/start.sh:3  `exec .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000`
  - apps/api/Dockerfile:21 `CMD ... exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}`
  Neither passes `--proxy-headers`. railway.toml uses builder=DOCKERFILE with NO `startCommand`, so the Dockerfile CMD is what runs in prod. No TrustedHostMiddleware / forwarded-allow-ips / ProxyHeadersMiddleware exists.

EMPIRICAL REPRO — isolated venv, slowapi 0.1.9 / starlette 1.2.1 / limits 5.8.0, loading the VERBATIM production limiter.py:
```
[1] get_remote_address: A -> 100.64.0.7 | B -> 100.64.0.7 | collapse to proxy IP: True
[2] hasattr(A.state,'user') = False; _rate_key(A)=100.64.0.7; _rate_key(B)=100.64.0.7
    => ALL tenants share ONE bucket: True
[3] control: when state.user IS set, _rate_key(A) = user-123 (nothing in the app ever sets it)
[4] XFF-blindness: A carried X-Forwarded-For=203.0.113.10, B=198.51.100.22; keys still equal: True
```
This reproduces the prior agent's [1]/[2]/[3] exactly and adds [4] (differing XFF still collapses).

No global ceiling either: production builds `Limiter(key_func=_rate_key)` with NO default_limits and NO application_limits (both default to []). Verified empirically: `default_limits = []`, `application_limits = []`. So there is no app-wide cap; only per-route decorators exist.

Un-decorated heavy endpoint confirmed: `@limiter.limit` appears on 9 routes (auth 30/min, messages 10/min, contacts, calls, ai 20/min, mcp 20/min, search 2/min) but POST /workspaces/{id}/messages/reprocess (messages.py:141-159) is a bare `@router.post` with NO limiter.

## Leg (b) — no per-tenant budget; single shared key; ~4 model calls/message; reprocess re-runs all 4 per message

- `grep -rin "budget|quota|usage_limit|cost_cap|token_budget|billing|credits|monthly_limit|tier_limit|spend" apps/api/ --include=*.py` => RC=1 (zero matches).
- Single key: apps/web/.env.local has exactly ONE `ANTHROPIC_API_KEY` (count=1). All clients read `os.getenv("ANTHROPIC_API_KEY")` or `settings.ANTHROPIC_API_KEY`. config.py:16 declares one `ANTHROPIC_API_KEY: str`.
- Per inbound message the enrich path makes 4 calls: _is_deal_relevant_async Haiku (ingest.py:115, model=claude-haiku-4-5) + extract_tasks Haiku (extraction.py:47) + analyze_sentiment Haiku (sentiment.py:58) + score_clarity SONNET (clarity.py:48, model=claude-sonnet-4-6).
- reprocess worker `_run_reprocess` (ingest.py:442-551) loops over ALL workspace messages and per message calls `_is_deal_relevant` (Haiku) + `extract_tasks` (Haiku) + `analyze_sentiment` (Haiku) + `score_clarity` (Sonnet) — 4 calls/message in ONE synchronous task. Endpoint is un-rate-limited and repeatable at will. Confirmed.

## Leg (c) — 2-slot queue, no isolation

- apps/api/railway-worker.toml deploy.startCommand: `celery -A app.workers.celery_app.celery_app worker --loglevel=info --concurrency=2`.
- apps/api/app/workers/celery_app.py: defines `task_serializer/result_serializer/beat_schedule` etc. but NO `task_routes`, NO `task_default_queue`, NO `worker_prefetch_multiplier`. All task modules (ingest, transcribe, pipeline, score_contact, pm_agent, ...) share the default queue and the same 2 slots. Two long tasks pin the pool. Confirmed.

## Exploit precondition — self-serve signup yields admin + workspace

- POST /auth/verify (auth.py:57, the login/signup verify) auto-provisions on first login: creates a Workspace, a User with `role="admin"`, default agents, syncs workspace_id into Supabase metadata, returns workspace_id.
- dependencies.py:76 also auto-provisions `role="admin"` on first authenticated hit.
=> A single self-serve signup yields an authenticated admin tenant with a workspace and a valid Supabase JWT. Exploit precondition holds.

## Conclusion
Every leg re-verified at file:line and the load-bearing limiter behavior reproduced empirically under the exact pinned slowapi. The per-route limiter collapses to one global proxy-IP bucket (so it throttles tenants collectively, never isolating an abuser), the primary cost amplifier (reprocess: 4 calls/message incl. Sonnet) is not rate-limited at all, there is no per-tenant budget and a single shared Anthropic key, and the 2-slot worker has no queue isolation. Finding UPHELD.
