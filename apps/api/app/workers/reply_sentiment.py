"""Celery task: reply-sentiment classifier for inbound engagement replies (Inc 2, R9).

The missing piece the adversarial critique flagged (C9/R9): the escalation graph
reads ``engagement_event.metadata.sentiment`` but nothing wrote it. This worker
classifies an inbound ``replied`` engagement_event into the R8 TEXT vocab
(``positive`` / ``neutral`` / ``negative`` / ``objection`` / ``booking`` /
``unsubscribe``) and writes it back onto that event's ``metadata.sentiment``.

classify_reply(workspace_id, event_id)
  1. Load the ``replied`` engagement_event (workspace-scoped).
  2. Build the classification prompt from the active playbook's reader rubric
     (``playbook.render_reader_rubric()``, Inc 3). Before Inc 3 lands — or whenever
     no playbook is active — fall back to the baked :data:`DEFAULT_READER_RUBRIC`.
  3. Ask the shared Anthropic client (``MODEL_FAST``, R7) for ONE vocab value;
     parse defensively; write ``event.metadata_['sentiment']``; commit.
  On any failure (no key, model error, unparseable) it leaves sentiment UNSET —
  the escalation decider treats ``None`` as neutral-hold, so a classifier outage
  never forces a wrong autonomous action.

House shape copied from ``engagement_score.py``: sync ``@celery_app.task`` wrapper
delegating to ``asyncio.run(_classify(...))``; own ``_get_async_session()`` reusing
PGBOUNCER_CONNECT_ARGS; primitive ``str`` args cast to UUID inside. On-demand only
— NO ``*_all`` dispatcher and NO ``beat_schedule`` entry. Enqueued beside
``score_lead_engagement`` from the engagement webhook on an inbound ``replied``.
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.config import settings
from app.database import PGBOUNCER_CONNECT_ARGS
from app.services.escalation import SENTIMENTS
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

# Baked cold-start rubric used before an active playbook exists (Inc 3 supersedes
# this via ``playbook.render_reader_rubric()``). Kept terse — the classifier only
# needs the label semantics, not the whole playbook.
DEFAULT_READER_RUBRIC: str = (
    "Classify the prospect's reply into exactly ONE label:\n"
    "- positive: warm, interested, asks a friendly question, wants to keep talking\n"
    "- neutral: acknowledges without clear interest or objection\n"
    "- negative: not interested, annoyed, or dismissive\n"
    "- objection: interested-but-blocked (price, timing, authority, need)\n"
    "- booking: wants to schedule a call/meeting/demo, or is ready to buy\n"
    "- unsubscribe: asks to stop, opt out, remove, or says STOP"
)


def _get_async_session() -> async_sessionmaker[AsyncSession]:
    # Prefer DATABASE_URL (already asyncpg-formatted) over SUPABASE_URL.
    url = os.getenv("DATABASE_URL", "") or os.getenv("SUPABASE_URL", "")
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://") and "+asyncpg" not in url:
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    engine = create_async_engine(url, echo=False, connect_args=PGBOUNCER_CONNECT_ARGS)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def _extract_reply_text(event: Any) -> str:
    """Pull the reply body from the event metadata (best-effort, never raises)."""
    meta = getattr(event, "metadata_", None) or {}
    for key in ("body", "text", "reply", "message", "snippet"):
        val = meta.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def _parse_sentiment(raw: str | None) -> str | None:
    """Map a raw model answer to a valid R8 vocab value, or None.

    Accepts a bare label or a label embedded in a sentence; case-insensitive.
    Returns None when nothing in the R8 vocab is present (caller leaves it unset).
    """
    if not raw:
        return None
    low = raw.strip().lower()
    # exact first, then substring — 'unsubscribe' before 'subscribe'-style noise.
    for label in SENTIMENTS:
        if low == label:
            return label
    for label in SENTIMENTS:
        if label in low:
            return label
    return None


async def _reader_rubric(workspace_id: uuid.UUID, db: AsyncSession) -> str:
    """The active playbook's reader rubric (Inc 3), or the baked default.

    Imported lazily and guarded so this worker stands alone before Inc 3 ships the
    playbook service.
    """
    try:
        from app.services.playbook import get_active_playbook

        pb = await get_active_playbook(workspace_id, db)
        rubric = pb.render_reader_rubric()
        if rubric:
            return rubric
    except Exception:  # noqa: BLE001 — no playbook service yet, or no active playbook
        pass
    return DEFAULT_READER_RUBRIC


async def _classify_text(reply_text: str, rubric: str) -> str | None:
    """Guarded LLM classification. Returns a vocab value or None. Never raises.

    Short-circuits to None when no ANTHROPIC_API_KEY is configured, so tests and
    key-less environments never touch the network.
    """
    if not reply_text:
        return None
    api_key = getattr(settings, "ANTHROPIC_API_KEY", "") or ""
    if not api_key:
        return None
    try:
        from app.services.llm import get_async_anthropic_client, MODEL_FAST

        client = get_async_anthropic_client()
        prompt = (
            f"{rubric}\n\n"
            "Reply to classify:\n"
            f'"""{reply_text}"""\n\n'
            "Answer with ONLY the single lowercase label, nothing else."
        )
        message = await client.messages.create(
            model=MODEL_FAST,
            max_tokens=8,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text if message.content else None
        return _parse_sentiment(raw)
    except Exception as exc:  # noqa: BLE001 — a classifier outage leaves sentiment unset
        logger.warning("reply_sentiment classify_failed exc=%s", exc)
        return None


async def _classify(workspace_id: str, event_id: str) -> dict[str, Any]:
    from app.models.engagement_event import EngagementEvent

    ws_uuid = uuid.UUID(str(workspace_id))
    event_uuid = uuid.UUID(str(event_id))

    SessionFactory = _get_async_session()
    async with SessionFactory() as db:
        result = await db.execute(
            select(EngagementEvent).where(
                EngagementEvent.id == event_uuid,
                EngagementEvent.workspace_id == ws_uuid,
            )
        )
        event = result.scalar_one_or_none()
        if event is None:
            return {"event_id": event_id, "sentiment": None, "status": "not_found"}
        if event.type != "replied":
            return {"event_id": event_id, "sentiment": None, "status": "not_a_reply"}

        reply_text = _extract_reply_text(event)
        rubric = await _reader_rubric(ws_uuid, db)
        sentiment = await _classify_text(reply_text, rubric)

        if sentiment is None:
            return {"event_id": event_id, "sentiment": None, "status": "unclassified"}

        # Write sentiment into the event metadata (JSONB reassignment so SQLAlchemy
        # flags the column dirty — in-place mutation of a JSONB dict is not tracked).
        meta = dict(event.metadata_ or {})
        meta["sentiment"] = sentiment
        event.metadata_ = meta
        db.add(event)
        await db.commit()

    return {"event_id": event_id, "sentiment": sentiment, "status": "classified"}


@celery_app.task(name="app.workers.reply_sentiment.classify_reply", bind=True)
def classify_reply(self: Any, workspace_id: str, event_id: str) -> dict[str, Any]:
    """Celery task: classify one inbound reply's sentiment. On-demand (no beat)."""
    return asyncio.run(_classify(workspace_id, event_id))
