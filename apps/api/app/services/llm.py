"""Central Anthropic client factory.

Every Anthropic client in the backend is built here so ``timeout`` and
``max_retries`` are bounded from a single place. Without a request timeout the
SDK's default behaviour on rate-limit / credit-exhaustion is exponential backoff
(``max_retries`` retries, no wall-clock ceiling), which makes any LLM call hang
indefinitely — the observed "enrichment times out" failure. Sourcing the bounds
from :data:`app.config.settings` keeps them env-tunable per deploy.

Usage::

    from app.services.llm import get_anthropic, get_async_anthropic

    client = get_anthropic()            # sync client, bounded
    aclient = get_async_anthropic()     # async client, bounded + loop-safe
"""
from __future__ import annotations

import anthropic

from app.config import settings


def get_anthropic() -> anthropic.Anthropic:
    """Return a sync client with bounded timeout + retries.

    Deliberately not cached at module level: the existing test suite patches
    ``anthropic.Anthropic`` per test, and a cached instance would leak the first
    test's client into later ones (and, in prod, would pin the very first key
    read). Constructing per call matches the pre-existing per-request/per-task
    behaviour; only the bounds are new, and client construction is cheap.
    """
    return anthropic.Anthropic(
        api_key=settings.ANTHROPIC_API_KEY,
        timeout=settings.ANTHROPIC_TIMEOUT,
        max_retries=settings.ANTHROPIC_MAX_RETRIES,
    )


def get_async_anthropic() -> anthropic.AsyncAnthropic:
    """Return a NEW async client with bounded timeout + retries.

    Deliberately not cached: the workers run each Celery task under a fresh
    ``asyncio.run()`` event loop, and an ``AsyncAnthropic`` instance binds its
    connection pool to the loop that first uses it — a cached instance would
    raise "Event loop is closed" on the next task. Constructing per call matches
    the pre-existing behaviour; only the bounds are new.
    """
    return anthropic.AsyncAnthropic(
        api_key=settings.ANTHROPIC_API_KEY,
        timeout=settings.ANTHROPIC_TIMEOUT,
        max_retries=settings.ANTHROPIC_MAX_RETRIES,
    )
