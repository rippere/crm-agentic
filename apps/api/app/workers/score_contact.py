"""
Celery task: heuristic lead scorer.

score_lead(contact_id: str, workspace_id: str)
  1. Load contact from DB
  2. Compute heuristic score (0-100) based on status, deal_count, revenue
  3. Update contact.ml_score JSONB
  4. Log activity_event
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


def _get_async_session() -> async_sessionmaker[AsyncSession]:
    url = os.getenv("SUPABASE_URL", "")
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    engine = create_async_engine(url, echo=False)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def _compute_score(contact: Any) -> dict[str, Any]:
    """Heuristic scoring: base 50, adjustments based on status / revenue / deals."""
    score = 50
    signals: list[str] = []

    status = getattr(contact, "status", "lead")
    revenue = float(getattr(contact, "revenue", 0) or 0)
    deal_count = int(getattr(contact, "deal_count", 0) or 0)

    if status == "customer":
        score += 10
        signals.append("Active customer (+10)")
    elif status == "prospect":
        score += 5
        signals.append("Prospect status (+5)")
    elif status == "churned":
        score -= 10
        signals.append("Churned — at risk (-10)")

    if deal_count > 0:
        score += 10
        signals.append(f"{deal_count} associated deal(s) (+10)")

    if revenue > 50000:
        score += 5
        signals.append(f"High revenue ${revenue:,.0f} (+5)")
    elif revenue > 10000:
        score += 10
        signals.append(f"Revenue ${revenue:,.0f} (+10)")

    # Clamp
    score = max(0, min(100, score))

    if score >= 70:
        label = "hot"
    elif score >= 40:
        label = "warm"
    else:
        label = "cold"

    return {
        "value": score,
        "label": label,
        "trend": "stable",
        "signals": signals,
    }


async def _run_score(contact_id: str, workspace_id: str) -> dict[str, Any]:
    from app.models.contact import Contact
    from app.models.activity_event import ActivityEvent

    SessionFactory = _get_async_session()

    async with SessionFactory() as db:
        result = await db.execute(
            select(Contact).where(
                Contact.id == uuid.UUID(contact_id),
                Contact.workspace_id == uuid.UUID(workspace_id),
            )
        )
        contact = result.scalar_one_or_none()
        if contact is None:
            return {"error": "Contact not found", "contact_id": contact_id}

        ml_score = _compute_score(contact)
        contact.ml_score = ml_score  # type: ignore[assignment]
        db.add(contact)

        event = ActivityEvent(
            workspace_id=uuid.UUID(workspace_id),
            type="lead_score_updated",
            agent_name="Lead Scorer",
            description=f"Lead score updated to {ml_score['value']} ({ml_score['label']}) for contact {contact.name or contact_id}",
            severity="info",
        )
        db.add(event)
        await db.commit()

    return {"contact_id": contact_id, "ml_score": ml_score}


@celery_app.task(name="app.workers.score_contact.score_lead", bind=True)
def score_lead(self: Any, contact_id: str, workspace_id: str) -> dict[str, Any]:
    """Celery task: compute heuristic lead score and update contact.ml_score."""
    return asyncio.get_event_loop().run_until_complete(_run_score(contact_id, workspace_id))
