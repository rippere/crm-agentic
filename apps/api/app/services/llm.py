"""Shared Anthropic async client (R7, BUILD-SPEC §3.1, build-order 0).

Single source of truth for the async Anthropic client and the two model-id
constants used across the codebase. Built **first**, before any LLM caller, to
kill the inline-``AsyncAnthropic()`` + hardcoded-model-literal anti-pattern
(collision C8 / resolution R7).

Every LLM caller imports the cached singleton from here rather than
constructing its own client, and every model id comes from config
(``settings.ANTHROPIC_MODEL_FAST`` / ``settings.ANTHROPIC_MODEL_SMART``) —
**never a literal in logic**. The four callers (per R7):

- ``app.services.discovery_research.score_venue``   (MODEL_SMART)
- ``app.services.playbook_distill._run_distill``    (MODEL_SMART)
- ``app.workers.reply_sentiment.classify_reply``    (MODEL_FAST)
- the future escalation ``decide_action_model``     (MODEL_SMART)

The client is created lazily and memoized in a module-level global so a single
``AsyncAnthropic`` (and its underlying httpx connection pool) is reused across
the process. Construction does not perform any network I/O, so importing this
module is safe even when ``ANTHROPIC_API_KEY`` is empty — callers guard the
actual ``messages.create`` call on a non-empty key.
"""

from __future__ import annotations

import anthropic

from app.config import settings

# Memoized singleton. Lazily populated by get_async_anthropic_client(); reused
# for the life of the process so the httpx connection pool is shared.
_async_client: anthropic.AsyncAnthropic | None = None


def get_async_anthropic_client() -> anthropic.AsyncAnthropic:
    """Return the process-wide cached ``AsyncAnthropic`` client (R7).

    Creates the client on first call and returns the same instance thereafter.
    Construction is I/O-free, so this is safe to call at import time and when
    ``settings.ANTHROPIC_API_KEY`` is empty; callers must still short-circuit
    the guarded ``messages.create`` call when no key is configured.
    """
    global _async_client
    if _async_client is None:
        _async_client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _async_client


# Model ids — sourced from config only (never a literal in logic).
MODEL_FAST = settings.ANTHROPIC_MODEL_FAST    # reply-sentiment, quick answers
MODEL_SMART = settings.ANTHROPIC_MODEL_SMART  # agentic tool loop, deep-research scoring, distillation
