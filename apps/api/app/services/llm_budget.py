"""F5 — per-workspace LLM token/cost budget (Redis counter).

Implements a check-and-reserve guard over the single shared ANTHROPIC_API_KEY so
one tenant cannot drive unbounded spend (evidence-cost-dos.md B1). A per-workspace
rolling-window token counter is incremented atomically; if the reservation would
push the workspace over its window budget the reservation is rolled back and an
HTTP 429 is raised.

Design notes:
  * INERT by default. ``settings.LLM_BUDGET_ENABLED`` is False, so
    ``check_and_reserve`` returns immediately and prod is NOT throttled by merely
    shipping this code. Defaults are also generous (50M tokens / 24h / workspace).
  * Atomic. INCRBY returns the post-increment total in one round-trip; on the
    first write of a window we set the TTL so the budget rolls over. Over-budget
    reservations are compensated with a matching DECRBY (best-effort) so a
    rejected request does not permanently consume headroom.
  * Fail-open on Redis errors. The budget is a cost guard, not an auth control;
    if Redis is unreachable we log and allow the call rather than hard-DoSing the
    product on an infra blip. (RLS / app-layer filters remain the security
    controls; this is purely spend/DoS mitigation.)
  * Uses redis.asyncio. A module-level lazy client is reused across requests; a
    custom client can be injected (tests pass a mock).
"""

from __future__ import annotations

import logging

from fastapi import HTTPException, status

from app.config import settings

logger = logging.getLogger(__name__)

_redis_client = None  # lazy singleton (redis.asyncio.Redis)


def _key(workspace_id: str) -> str:
    return f"llm_budget:{workspace_id}"


async def _get_redis():
    """Lazily build (and cache) a redis.asyncio client from REDIS_URL."""
    global _redis_client
    if _redis_client is None:
        import redis.asyncio as aioredis

        _redis_client = aioredis.from_url(
            settings.REDIS_URL,
            socket_connect_timeout=2,
            socket_timeout=2,
            decode_responses=True,
        )
    return _redis_client


async def check_and_reserve(
    workspace_id,
    estimated_tokens: int,
    *,
    redis_client=None,
) -> int:
    """Reserve ``estimated_tokens`` against the workspace's rolling budget.

    Returns the workspace's running total for the current window on success.
    Raises ``HTTPException(429)`` when the reservation would exceed the budget.

    No-op (returns 0) when ``LLM_BUDGET_ENABLED`` is False. ``redis_client`` lets
    callers/tests inject a client; otherwise the shared lazy client is used.
    """
    if not settings.LLM_BUDGET_ENABLED:
        return 0

    tokens = max(int(estimated_tokens), 0)
    budget = settings.LLM_BUDGET_TOKENS_PER_WINDOW
    ws = str(workspace_id)
    key = _key(ws)

    client = redis_client if redis_client is not None else await _get_redis()

    try:
        new_total = await client.incrby(key, tokens)
        # Set the window TTL only on the first increment of a fresh window so the
        # budget actually rolls over (INCRBY on a missing key starts at `tokens`).
        if new_total == tokens:
            await client.expire(key, settings.LLM_BUDGET_WINDOW_SECONDS)
    except HTTPException:
        raise
    except Exception:  # noqa: BLE001 — fail OPEN on infra error (cost guard, not auth)
        logger.warning(
            "event=llm_budget_check_unavailable workspace_id=%s detail=allowing_call", ws
        )
        return 0

    if new_total > budget:
        # Roll back our reservation so a rejected call doesn't burn headroom.
        try:
            await client.decrby(key, tokens)
        except Exception:  # noqa: BLE001
            logger.warning("event=llm_budget_rollback_failed workspace_id=%s", ws)
        logger.info(
            "event=llm_budget_exceeded workspace_id=%s requested=%d budget=%d window_s=%d",
            ws, tokens, budget, settings.LLM_BUDGET_WINDOW_SECONDS,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                "Workspace AI usage budget exceeded for the current window. "
                "Try again later or contact your administrator."
            ),
            headers={"Retry-After": str(settings.LLM_BUDGET_WINDOW_SECONDS)},
        )

    return new_total


async def estimate_reprocess_tokens(message_count: int) -> int:
    """Heuristic token estimate for a full-workspace reprocess of N messages.

    reprocess runs ~4 model calls per message (3 Haiku + 1 Sonnet); we price the
    pass at ``LLM_BUDGET_TOKENS_PER_MESSAGE`` per message so the reserve-before-
    enqueue check bounds the otherwise-unbounded fan-out.
    """
    return max(int(message_count), 0) * settings.LLM_BUDGET_TOKENS_PER_MESSAGE
