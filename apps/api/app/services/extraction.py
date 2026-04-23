"""
Claude extraction service.
Extracts actionable tasks from email message bodies using claude-haiku-4-5.
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


SYSTEM_PROMPT = (
    "You are a task extractor. Given an email message body, identify every actionable task mentioned. "
    "Return a JSON array of objects. Each object must have exactly three keys: "
    '"title" (string, short imperative), '
    '"description" (string, additional context or empty string), '
    '"due_date" (ISO 8601 date string YYYY-MM-DD or null if not specified). '
    "Return only the JSON array — no markdown, no prose."
)


async def extract_tasks(message_body: str, workspace_id: str) -> list[dict[str, Any]]:
    """
    Send message_body to Claude and parse the returned JSON task list.

    Args:
        message_body: Plain-text body of the email.
        workspace_id: For logging / future attribution (not sent to Claude).

    Returns:
        List of dicts with keys: title, description, due_date (str or None).
    """
    client = _get_client()

    message = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": message_body[:8000]},  # trim to avoid token blowout
        ],
    )

    raw = message.content[0].text if message.content else "[]"

    try:
        tasks: list[dict[str, Any]] = json.loads(raw)
        if not isinstance(tasks, list):
            tasks = []
    except (json.JSONDecodeError, IndexError):
        tasks = []

    return tasks
