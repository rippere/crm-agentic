"""
Clarity scoring service.
Scores message communication clarity on 0–100 using claude-sonnet-4-6.
"""
from __future__ import annotations

import json
import os
from typing import Any

import anthropic

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
    return _client


_SYSTEM_PROMPT = (
    "You are a communication clarity evaluator. Given a message body, rate its "
    "clarity on a scale of 0–100 and explain why in one sentence.\n\n"
    "Scoring guide:\n"
    "90–100: Crystal clear — specific, actionable, no ambiguity\n"
    "70–89: Good — mostly clear with minor gaps\n"
    "40–69: Moderate — some ambiguity or missing context\n"
    "0–39: Poor — vague, confusing, or missing critical information\n\n"
    "Return a JSON object with exactly two keys:\n"
    '  "score": integer 0–100\n'
    '  "rationale": one sentence, max 150 chars\n'
    "Return only the JSON — no markdown, no prose."
)


async def score_clarity(message_body: str) -> dict[str, Any]:
    """
    Score message clarity using Claude Sonnet.

    Returns dict with keys: score (int 0-100), rationale (str).
    Follows the same sync-client-in-async-function pattern as extraction.py.
    """
    client = _get_client()

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=256,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": message_body[:4000]}],
    )

    raw = (
        message.content[0].text
        if message.content
        else '{"score":50,"rationale":"Unable to score"}'
    )

    try:
        result: dict[str, Any] = json.loads(raw)
        score = int(result.get("score", 50))
        score = max(0, min(100, score))
        rationale = str(result.get("rationale", ""))[:200]
        return {"score": score, "rationale": rationale}
    except (json.JSONDecodeError, TypeError, ValueError):
        return {"score": 50, "rationale": "Scoring failed"}
