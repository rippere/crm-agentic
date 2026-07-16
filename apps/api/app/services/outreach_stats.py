"""Outreach outcome derivation — reply rates computed from owned data.

This is the question the CRM could not answer before migration 022: *did that
email get a reply?* No vendor sells the answer; it falls out of data the
workspace already owns once sends are recorded and threads are captured.

A reply is defined structurally, not heuristically: an INBOUND message sharing an
OUTBOUND message's ``thread_id`` and arriving strictly after it. No LLM, no
vendor, no thresholds to tune.

Known limits, stated rather than buried:
* Reply detection is thread-scoped. A prospect who replies in a brand-new thread
  (or from a different address) is invisible here and undercounts the true rate.
* Both sides of the join need ingest to have run, so a reply that arrives before
  the next Gmail sync is not yet visible — treat the number as a lower bound.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message import Message


@dataclass
class OutreachStats:
    """Reply performance over a window. Counts, not estimates."""

    sent: int
    replied: int
    reply_rate: float  # 0.0-1.0; 0.0 when nothing was sent
    median_reply_hours: float | None  # None until at least one reply exists


async def compute_outreach_stats(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    *,
    since: datetime | None = None,
    days: int = 90,
) -> OutreachStats:
    """Reply rate for outbound mail sent in the window.

    Counts distinct THREADS rather than messages: three follow-ups on one thread
    are one outreach attempt, and counting each as its own "send" would dilute the
    reply rate exactly when someone is chasing hardest.
    """
    if since is None:
        since = datetime.now(timezone.utc) - timedelta(days=days)

    result = await db.execute(
        select(Message).where(
            Message.workspace_id == workspace_id,
            Message.thread_id.is_not(None),
        )
    )
    messages = list(result.scalars().all())

    # First outbound per thread inside the window = one outreach attempt.
    first_sent: dict[str, datetime] = {}
    for m in messages:
        if m.direction != "outbound" or m.received_at is None:
            continue
        if m.received_at < since:
            continue
        prior = first_sent.get(m.thread_id)
        if prior is None or m.received_at < prior:
            first_sent[m.thread_id] = m.received_at

    # Earliest inbound strictly after that send, in the same thread.
    first_reply: dict[str, datetime] = {}
    for m in messages:
        if m.direction != "inbound" or m.received_at is None:
            continue
        sent_at = first_sent.get(m.thread_id)
        if sent_at is None or m.received_at <= sent_at:
            continue
        prior = first_reply.get(m.thread_id)
        if prior is None or m.received_at < prior:
            first_reply[m.thread_id] = m.received_at

    sent = len(first_sent)
    replied = len(first_reply)

    latencies = sorted(
        (first_reply[t] - first_sent[t]).total_seconds() / 3600.0 for t in first_reply
    )
    median_reply_hours: float | None = None
    if latencies:
        mid = len(latencies) // 2
        median_reply_hours = (
            latencies[mid]
            if len(latencies) % 2
            else (latencies[mid - 1] + latencies[mid]) / 2
        )

    return OutreachStats(
        sent=sent,
        replied=replied,
        reply_rate=(replied / sent) if sent else 0.0,
        median_reply_hours=median_reply_hours,
    )
