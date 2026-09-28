"""Parse JSON out of an LLM text reply.

Haiku/Sonnet frequently wrap a "return JSON only" answer in a markdown fence
(```json ... ```), which plain ``json.loads`` rejects at char 0.
"""

from __future__ import annotations

import json
from typing import Any


def loads_llm_json(raw: str) -> Any:
    """``json.loads`` that tolerates a surrounding ``` / ```json code fence.

    Raises ``json.JSONDecodeError`` exactly like ``json.loads`` when the
    unfenced text still isn't valid JSON, so existing ``except`` clauses keep
    working unchanged.
    """
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        body = lines[1:-1] if len(lines) > 1 and lines[-1].strip() == "```" else lines[1:]
        text = "\n".join(body).strip()
    return json.loads(text)
