"""
Celery task: engagement scoring for lead-gen leads.

score_lead_engagement(workspace_id: str, lead_id: str)
  1. Load the lead + its engagement_events over a trailing window
  2. Compute a weighted engagement score (0-100) from event types
     (open +5, click +15, reply +30, converted +40, bounce -20, unsub -30)
  3. Write lead.score + lead.score_detail (mirrors contact.ml_score shape),
     update lead.last_engaged_at
  4. Auto-advance lead.stage on thresholds (reply -> engaged;
     score>=70 & replied -> qualified; converted -> converted)
  5. Log an ActivityEvent

score_leads_all()
  Beat dispatcher (hourly): fan out per workspace -> rescore_workspace_leads(ws).

rescore_workspace_leads(workspace_id: str)
  Enqueue per-lead score_lead_engagement for recently-active leads in the workspace.

Copies the score_contact.py / pipeline.py worker house shape: sync
@celery_app.task wrapper delegating to asyncio.run(_async(...)); own
_get_async_session() reusing PGBOUNCER_CONNECT_ARGS; primitive args cast to
UUID inside; results written to Postgres + an ActivityEvent; a *_all beat
dispatcher fanning out over workspaces.
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.database import PGBOUNCER_CONNECT_ARGS

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

# Trailing window (days) over which engagement events count toward the score.
SCORE_WINDOW_DAYS = 90

# Only leads engaged within this window get re-scored by the hourly dispatcher.
RESCORE_ACTIVE_DAYS = 30

# Weighted contribution per engagement_event.type. Types absent here (queued,
# sent, delivered, approved, rejected) contribute 0 — they are activity, not
# engagement signal.
EVENT_WEIGHTS: dict[str, int] = {
    "opened": 5,
    "clicked": 15,
    "replied": 30,
    "converted": 40,
    "bounced": -20,
    "unsubscribed": -30,
}

# Human-readable signal fragment per counted type.
_SIGNAL_LABEL: dict[str, str] = {
    "opened": "open",
    "clicked": "click",
    "replied": "reply",
    "converted": "conversion",
    "bounced": "bounce",
    "unsubscribed": "unsubscribe",
}

# Lead stage ordering — advancement only ever moves forward, never regresses,
# and never touches a terminal 'lost' lead.
_STAGE_RANK: dict[str, int] = {
    "new": 0,
    "contacted": 1,
    "engaged": 2,
    "qualified": 3,
    "converted": 4,
    "lost": 5,
}


def _get_async_session() -> async_sessionmaker[AsyncSession]:
    # Prefer DATABASE_URL (already asyncpg-formatted) over SUPABASE_URL
    url = os.getenv("DATABASE_URL", "") or os.getenv("SUPABASE_URL", "")
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://") and "+asyncpg" not in url:
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    engine = create_async_engine(url, echo=False, connect_args=PGBOUNCER_CONNECT_ARGS)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def _naive(dt: datetime | None) -> datetime | None:
    """Drop tzinfo so aware/naive timestamps compare cleanly (matches pipeline.py)."""
    if dt is None:
        return None
    return dt.replace(tzinfo=None)


def _compute_score(
    events: list[Any],
    *,
    now: datetime | None = None,
    window_days: int = SCORE_WINDOW_DAYS,
) -> dict[str, Any]:
    """Weighted-sum engagement score over a trailing window, clamped 0-100.

    Pure function (no DB) mirroring score_contact._compute_score's return shape:
    {value, label, trend, signals}. Also returns booleans (`replied`,
    `converted`) the stage-advance logic keys on, plus per-type `counts`.

    `events` are objects with `.type` (str) and `.occurred_at` (datetime|None).
    Events whose type carries no weight, or that fall outside the window, are
    ignored. An event with a None occurred_at is always counted (can't be
    excluded by the window).
    """
    now_naive = _naive(now) or datetime.utcnow()
    cutoff = now_naive - timedelta(days=window_days)

    score = 0
    counts: dict[str, int] = {}
    replied = False
    converted = False

    for ev in events:
        ev_type = getattr(ev, "type", None)
        weight = EVENT_WEIGHTS.get(ev_type or "")
        if weight is None:
            continue  # not an engagement signal
        occurred = _naive(getattr(ev, "occurred_at", None))
        if occurred is not None and occurred < cutoff:
            continue  # outside the trailing window
        score += weight
        counts[ev_type] = counts.get(ev_type, 0) + 1
        if ev_type == "replied":
            replied = True
        if ev_type == "converted":
            converted = True

    # Clamp 0-100
    score = max(0, min(100, score))

    if score >= 70:
        label = "hot"
    elif score >= 40:
        label = "warm"
    else:
        label = "cold"

    signals: list[str] = []
    for ev_type, count in counts.items():
        frag = _SIGNAL_LABEL.get(ev_type, ev_type)
        weight = EVENT_WEIGHTS[ev_type]
        sign = "+" if weight >= 0 else ""
        signals.append(f"{count} {frag}(s) ({sign}{weight * count})")

    return {
        "value": score,
        "label": label,
        "trend": "stable",
        "signals": signals,
        "replied": replied,
        "converted": converted,
        "counts": counts,
    }


def _next_stage(current_stage: str, detail: dict[str, Any]) -> str | None:
    """Return the stage a lead should auto-advance to, or None to leave it be.

    Thresholds (forward-only; never regress, never touch 'lost'):
      - a conversion signal            -> converted
      - score >= 70 AND replied        -> qualified
      - replied                        -> engaged
    """
    if current_stage == "lost":
        return None

    replied = bool(detail.get("replied"))
    converted = bool(detail.get("converted"))
    score = int(detail.get("value", 0))

    target: str | None = None
    if converted:
        target = "converted"
    elif score >= 70 and replied:
        target = "qualified"
    elif replied:
        target = "engaged"

    if target is None:
        return None

    current_rank = _STAGE_RANK.get(current_stage, 0)
    if _STAGE_RANK[target] > current_rank:
        return target
    return None


async def _run_score(workspace_id: str, lead_id: str) -> dict[str, Any]:
    from app.models.lead import Lead
    from app.models.engagement_event import EngagementEvent
    from app.models.activity_event import ActivityEvent

    ws_uuid = uuid.UUID(workspace_id)
    lead_uuid = uuid.UUID(lead_id)
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=SCORE_WINDOW_DAYS)

    SessionFactory = _get_async_session()

    async with SessionFactory() as db:
        result = await db.execute(
            select(Lead).where(
                Lead.id == lead_uuid,
                Lead.workspace_id == ws_uuid,
            )
        )
        lead = result.scalar_one_or_none()
        if lead is None:
            return {"error": "Lead not found", "lead_id": lead_id}

        ev_result = await db.execute(
            select(EngagementEvent).where(
                EngagementEvent.workspace_id == ws_uuid,
                EngagementEvent.lead_id == lead_uuid,
                EngagementEvent.occurred_at >= cutoff,
            )
        )
        events = list(ev_result.scalars().all())

        detail = _compute_score(events, now=now)

        lead.score = detail["value"]  # type: ignore[assignment]
        # score_detail mirrors contact.ml_score shape: {value,label,signals,...}
        lead.score_detail = {  # type: ignore[assignment]
            "value": detail["value"],
            "label": detail["label"],
            "trend": detail["trend"],
            "signals": detail["signals"],
        }
        if events:
            # newest engagement wins; occurred_at may be tz-aware
            last = max(
                (getattr(e, "occurred_at", None) for e in events),
                default=None,
                key=lambda d: d or datetime.min.replace(tzinfo=timezone.utc),
            )
            if last is not None:
                lead.last_engaged_at = last  # type: ignore[assignment]

        old_stage = lead.stage
        new_stage = _next_stage(old_stage, detail)
        if new_stage is not None:
            lead.stage = new_stage  # type: ignore[assignment]
        db.add(lead)

        desc = (
            f"Engagement score {detail['value']} ({detail['label']}) for lead "
            f"{lead.name or lead_id}"
        )
        if new_stage is not None:
            desc += f"; stage {old_stage} -> {new_stage}"
        event = ActivityEvent(
            workspace_id=ws_uuid,
            type="lead_engagement_scored",
            agent_name="Engagement Scorer",
            description=desc,
            severity="info",
        )
        db.add(event)
        await db.commit()

    return {
        "lead_id": lead_id,
        "score": detail["value"],
        "label": detail["label"],
        "stage": new_stage or old_stage,
        "stage_changed": new_stage is not None,
    }


async def _enumerate_workspace_ids() -> list[str]:
    """Return every workspace id in the DB as a string (sync-land safe)."""
    from app.models.workspace import Workspace

    SessionFactory = _get_async_session()
    async with SessionFactory() as db:
        result = await db.execute(select(Workspace.id))
        return [str(ws_id) for ws_id in result.scalars().all()]


async def _run_rescore_workspace(workspace_id: str) -> dict[str, Any]:
    """Enqueue per-lead scoring for leads engaged within RESCORE_ACTIVE_DAYS."""
    from app.models.lead import Lead

    ws_uuid = uuid.UUID(workspace_id)
    cutoff = datetime.now(timezone.utc) - timedelta(days=RESCORE_ACTIVE_DAYS)

    SessionFactory = _get_async_session()
    async with SessionFactory() as db:
        result = await db.execute(
            select(Lead.id).where(
                Lead.workspace_id == ws_uuid,
                Lead.last_engaged_at >= cutoff,
            )
        )
        lead_ids = [str(lead_id) for lead_id in result.scalars().all()]

    for lead_id in lead_ids:
        score_lead_engagement.delay(workspace_id, lead_id)

    return {"workspace_id": workspace_id, "enqueued": len(lead_ids)}


@celery_app.task(name="app.workers.engagement_score.score_lead_engagement", bind=True)
def score_lead_engagement(self: Any, workspace_id: str, lead_id: str) -> dict[str, Any]:
    """Celery task: recompute a lead's engagement score, detail, and stage."""
    return asyncio.run(_run_score(workspace_id, lead_id))


@celery_app.task(name="app.workers.engagement_score.rescore_workspace_leads", bind=True)
def rescore_workspace_leads(self: Any, workspace_id: str) -> dict[str, Any]:
    """Enqueue per-lead scoring for recently-active leads in one workspace."""
    return asyncio.run(_run_rescore_workspace(workspace_id))


@celery_app.task(name="app.workers.engagement_score.score_leads_all", bind=True)
def score_leads_all(self: Any) -> dict[str, Any]:
    """Beat dispatcher (hourly): fan rescore_workspace_leads out per workspace.

    score_lead_engagement / rescore_workspace_leads require a workspace_id,
    which celery beat cannot supply. This no-arg task enumerates all workspaces
    and enqueues one rescore child per workspace.
    """
    workspace_ids = asyncio.run(_enumerate_workspace_ids())
    for ws_id in workspace_ids:
        rescore_workspace_leads.delay(ws_id)
    return {"dispatched": len(workspace_ids), "workspace_ids": workspace_ids}
