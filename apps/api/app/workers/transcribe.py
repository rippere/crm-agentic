"""
Celery task: transcribe_call(call_summary_id: str, audio_path: str)

1. Load Whisper base model (cached after first load)
2. Transcribe audio file
3. Send transcript to Claude Sonnet for summary + action items
4. Persist results to call_summaries row
5. Clean up temp audio file
"""
from __future__ import annotations

import asyncio
import os
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.workers.celery_app import celery_app

WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL", "base")

_EXTRACT_PROMPT = """\
You are a CRM assistant. Given a call transcript, produce:
1. A 2-3 sentence executive summary of the call.
2. A JSON list of action items with fields: "owner" (string), "task" (string), "due" (string or null).

Respond ONLY in this exact JSON format:
{
  "summary": "...",
  "action_items": [{"owner": "...", "task": "...", "due": "..."}]
}"""


@lru_cache(maxsize=1)
def _whisper_model():
    import whisper
    return whisper.load_model(WHISPER_MODEL_SIZE)


def _transcribe_audio(path: str) -> tuple[str, float]:
    """Returns (transcript_text, duration_seconds)."""
    model = _whisper_model()
    result = model.transcribe(path, fp16=False)
    text: str = result.get("text", "").strip()
    segments: list[dict] = result.get("segments", [])
    duration = segments[-1]["end"] if segments else 0.0
    return text, duration


def _extract_with_claude(transcript: str) -> dict[str, Any]:
    import anthropic
    import json

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[
            {"role": "user", "content": f"{_EXTRACT_PROMPT}\n\nTranscript:\n{transcript}"},
        ],
    )
    raw = msg.content[0].text.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        import re
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            return json.loads(m.group(0))
        return {"summary": raw, "action_items": []}


def _make_session() -> async_sessionmaker[AsyncSession]:
    url = os.getenv("DATABASE_URL", "")
    if not url:
        url = os.getenv("SUPABASE_URL", "").replace("postgres://", "postgresql+asyncpg://", 1)
    return async_sessionmaker(
        create_async_engine(url, echo=False),
        class_=AsyncSession,
        expire_on_commit=False,
    )


async def _persist(call_id: str, transcript: str, duration: float, extracted: dict[str, Any]) -> None:
    from sqlalchemy import select
    from app.models.call_summary import CallSummary

    factory = _make_session()
    async with factory() as db:
        result = await db.execute(
            select(CallSummary).where(CallSummary.id == uuid.UUID(call_id))
        )
        call = result.scalar_one_or_none()
        if call is None:
            return
        call.transcript = transcript
        call.duration_seconds = int(duration)
        call.summary = extracted.get("summary", "")
        call.action_items = extracted.get("action_items", [])
        call.model_used = f"whisper-{WHISPER_MODEL_SIZE}"
        db.add(call)
        await db.commit()


@celery_app.task(name="app.workers.transcribe.transcribe_call", bind=True)
def transcribe_call(self: Any, call_summary_id: str, audio_path: str) -> dict[str, Any]:
    """Transcribe audio, extract summary + action items, persist to DB, clean up file."""
    try:
        transcript, duration = _transcribe_audio(audio_path)
        extracted = _extract_with_claude(transcript)
        asyncio.get_event_loop().run_until_complete(
            _persist(call_summary_id, transcript, duration, extracted)
        )
        return {
            "call_summary_id": call_summary_id,
            "duration_seconds": int(duration),
            "action_items_count": len(extracted.get("action_items", [])),
        }
    finally:
        try:
            Path(audio_path).unlink(missing_ok=True)
        except Exception:
            pass
