"""
Celery task: compute_deal_health(workspace_id: str)

For every active deal in the workspace:
  1. Determine days_in_stage from stage_changed_at
  2. Find the most recent message for the linked contact
  3. Call services.deal_health.compute_health
  4. Persist health_score back to DB
"""
from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.workers.celery_app import celery_app


def _make_session() -> async_sessionmaker[AsyncSession]:
    url = os.getenv("DATABASE_URL", "")
    if not url:
        url = os.getenv("SUPABASE_URL", "").replace("postgres://", "postgresql+asyncpg://", 1)
    return async_sessionmaker(
        create_async_engine(url, echo=False),
        class_=AsyncSession,
        expire_on_commit=False,
    )


_NEXT_BEST_ACTION: dict[str, str] = {
    "discovery": "Schedule a discovery call to qualify the opportunity",
    "qualified": "Send a tailored proposal or case study",
    "proposal": "Follow up on proposal — ask for feedback and objections",
    "negotiation": "Re-engage with a concession or alternative pricing",
}


async def _run(workspace_id: str) -> dict[str, Any]:
    from app.models.deal import Deal
    from app.models.message import Message
    from app.models.activity_event import ActivityEvent
    from app.services.deal_health import compute_health

    factory = _make_session()
    updated = 0
    alerts_fired = 0
    ws_uuid = uuid.UUID(workspace_id)

    async with factory() as db:
        result = await db.execute(
            select(Deal).where(
                Deal.workspace_id == ws_uuid,
                Deal.stage.not_in(["closed_won", "closed_lost"]),
            )
        )
        deals = result.scalars().all()

        for deal in deals:
            # Most recent message from linked contact (if any)
            last_msg_at: datetime | None = None
            if deal.contact_id:
                msg_result = await db.execute(
                    select(Message.received_at)
                    .where(Message.contact_id == deal.contact_id)
                    .order_by(Message.received_at.desc())
                    .limit(1)
                )
                last_msg_at = msg_result.scalar_one_or_none()

            stage_changed_at = getattr(deal, "stage_changed_at", None) or deal.created_at
            if stage_changed_at is None:
                stage_changed_at = datetime.now(tz=timezone.utc)

            score, signals = compute_health(
                stage=deal.stage,
                stage_changed_at=stage_changed_at,
                last_message_at=last_msg_at,
            )
            deal.health_score = score
            db.add(deal)
            updated += 1

            # Fire a proactive alert for critical deals (score ≤ 25)
            if score <= 25:
                nba = _NEXT_BEST_ACTION.get(deal.stage, "Review deal and re-engage the contact")
                signal_text = signals[0] if signals else "Health score critical"
                alert = ActivityEvent(
                    workspace_id=ws_uuid,
                    type="deal_alert",
                    agent_name="DealHealthAgent",
                    description=f'⚠ {deal.title or "Deal"} at {deal.company or ""}: {signal_text}. Suggested action: {nba}',
                    meta=f"deal:{deal.id}",
                    severity="warning",
                )
                db.add(alert)
                alerts_fired += 1

        await db.commit()

    return {"workspace_id": workspace_id, "deals_scored": updated, "alerts_fired": alerts_fired}


@celery_app.task(name="app.workers.deal_health_worker.compute_deal_health", bind=True)
def compute_deal_health(self: Any, workspace_id: str) -> dict[str, Any]:
    """Compute and persist health scores for all active deals in a workspace."""
    return asyncio.get_event_loop().run_until_complete(_run(workspace_id))
