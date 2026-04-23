"""
Celery task: heuristic pipeline optimizer.

optimize_pipeline(workspace_id: str)
  1. Load all open/active deals (stage NOT IN ('closed_won', 'closed_lost'))
  2. Compute win probability heuristic for each deal
  3. Batch-update deals.ml_win_probability
  4. Log a summary activity_event
"""
from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.workers.celery_app import celery_app

CLOSED_STAGES = {"closed_won", "closed_lost"}

STAGE_BONUS: dict[str, int] = {
    "discovery": 0,
    "qualified": 15,
    "proposal": 25,
    "negotiation": 35,
}


def _get_async_session() -> async_sessionmaker[AsyncSession]:
    url = os.getenv("SUPABASE_URL", "")
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    engine = create_async_engine(url, echo=False)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def _compute_win_probability(deal: Any, now: datetime) -> int:
    prob = 30
    stage: str = getattr(deal, "stage", "discovery")
    value = float(getattr(deal, "value", 0) or 0)
    updated_at: datetime | None = getattr(deal, "updated_at", None)

    prob += STAGE_BONUS.get(stage, 0)

    if value > 50000:
        prob += 5

    if updated_at:
        days_stale = (now - updated_at.replace(tzinfo=None)).days
        if days_stale > 30:
            prob -= 10

    return max(0, min(95, prob))


async def _run_optimize(workspace_id: str) -> dict[str, Any]:
    from app.models.deal import Deal
    from app.models.activity_event import ActivityEvent

    SessionFactory = _get_async_session()
    ws_uuid = uuid.UUID(workspace_id)
    now = datetime.utcnow()

    async with SessionFactory() as db:
        result = await db.execute(
            select(Deal).where(
                Deal.workspace_id == ws_uuid,
                ~Deal.stage.in_(list(CLOSED_STAGES)),
            )
        )
        deals = result.scalars().all()

        updated_count = 0
        for deal in deals:
            prob = _compute_win_probability(deal, now)
            deal.ml_win_probability = prob  # type: ignore[assignment]
            db.add(deal)
            updated_count += 1

        event = ActivityEvent(
            workspace_id=ws_uuid,
            type="pipeline_optimized",
            agent_name="Pipeline Optimizer",
            description=f"Pipeline Optimizer updated {updated_count} deals with win probability estimates",
            severity="info",
        )
        db.add(event)
        await db.commit()

    return {"workspace_id": workspace_id, "deals_updated": updated_count}


@celery_app.task(name="app.workers.pipeline.optimize_pipeline", bind=True)
def optimize_pipeline(self: Any, workspace_id: str) -> dict[str, Any]:
    """Celery task: compute heuristic win probabilities for all open pipeline deals."""
    return asyncio.get_event_loop().run_until_complete(_run_optimize(workspace_id))
