"""
Sentiment analyzer service.

analyze_sentiment(message_body: str) -> dict
  - Calls Claude Haiku with a structured prompt
  - Returns: {sentiment: positive|neutral|negative|urgent, confidence: 0.0-1.0, signals: [str]}
  - On any error returns a safe default dict
"""
from __future__ import annotations

import json
import os
from typing import Any

import anthropic

_client: anthropic.Anthropic | None = None

SYSTEM_PROMPT = (
    "You are a sentiment analysis engine. Analyze the sentiment of the message provided. "
    "Return JSON only — no markdown, no prose:\n"
    '{"sentiment": "<positive|neutral|negative|urgent>", "confidence": <0.0-1.0>, "signals": ["<phrase1>", ...]}'
)

_DEFAULT_RESULT: dict[str, Any] = {
    "sentiment": "neutral",
    "confidence": 0.0,
    "signals": [],
}


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        _client = anthropic.Anthropic(api_key=api_key)
    return _client


def analyze_sentiment(message_body: str) -> dict[str, Any]:
    """
    Analyze sentiment of a message body synchronously using Claude Haiku.

    Args:
        message_body: Plain-text message content to analyze.

    Returns:
        Dict with keys: sentiment (str), confidence (float), signals (list[str]).
        Returns neutral defaults if API call fails or API key is missing.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return _DEFAULT_RESULT.copy()

    try:
        client = _get_client()
        message = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=256,
            system=SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": message_body[:4000]},
            ],
        )
        raw = message.content[0].text if message.content else "{}"

        # Strip markdown code fence if present
        stripped = raw.strip()
        if stripped.startswith("```"):
            lines = stripped.splitlines()
            stripped = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        data: dict[str, Any] = json.loads(stripped)

        return {
            "sentiment": str(data.get("sentiment", "neutral")),
            "confidence": float(data.get("confidence", 0.0)),
            "signals": list(data.get("signals", [])),
        }
    except Exception:
        # Sentiment failure must never block the ingest pipeline
        return _DEFAULT_RESULT.copy()
