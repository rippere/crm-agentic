"""
Celery task: campaign enrollment builder.

enroll_campaign(workspace_id: str, campaign_id: str)
  1. Load the campaign (workspace-scoped)
  2. Resolve its segment's leads — static join (lead_segment_members) OR
     dynamic filter eval over the leads table
  3. Create one sequence_enrollment per lead
     (ON CONFLICT (campaign_id, lead_id) DO NOTHING), current_step=0,
     next_run_at = campaign.scheduled_at or NOW()
  4. Bump campaign.stats.enrolled by the number newly inserted
  5. Log an activity_event

Triggered from POST /campaigns/{id}/launch.
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.database import PGBOUNCER_CONNECT_ARGS

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def _get_async_session() -> async_sessionmaker[AsyncSession]:
    # Prefer DATABASE_URL (already asyncpg-formatted) over SUPABASE_URL
    url = os.getenv("DATABASE_URL", "") or os.getenv("SUPABASE_URL", "")
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://") and "+asyncpg" not in url:
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    engine = create_async_engine(url, echo=False, connect_args=PGBOUNCER_CONNECT_ARGS)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def _dynamic_filter_conditions(workspace_id: uuid.UUID, seg_filter: dict[str, Any]) -> list[Any]:
    """Translate a dynamic segment's stored filter JSON into workspace-scoped
    leads-table conditions.

    Supported keys: stage, source (scalar or list), min_score, tags
    (matched against leads.custom_fields->'tags'). Unknown keys are ignored so
    a filter authored against a newer schema never crashes an enrollment run.
    """
    from app.models.lead import Lead

    conditions: list[Any] = [Lead.workspace_id == workspace_id]
    if not isinstance(seg_filter, dict):
        return conditions

    stage = seg_filter.get("stage")
    if stage:
        if isinstance(stage, (list, tuple, set)):
            conditions.append(Lead.stage.in_(list(stage)))
        else:
            conditions.append(Lead.stage == stage)

    source = seg_filter.get("source")
    if source:
        if isinstance(source, (list, tuple, set)):
            conditions.append(Lead.source.in_(list(source)))
        else:
            conditions.append(Lead.source == source)

    min_score = seg_filter.get("min_score")
    if min_score is not None:
        conditions.append(Lead.score >= int(min_score))

    tags = seg_filter.get("tags")
    if tags:
        tag_list = list(tags) if isinstance(tags, (list, tuple, set)) else [tags]
        conditions.append(Lead.custom_fields["tags"].astext.in_(tag_list))

    return conditions


async def _resolve_segment_lead_ids(
    db: AsyncSession, workspace_id: uuid.UUID, segment: Any
) -> list[uuid.UUID]:
    """Return the lead ids that a segment currently resolves to.

    static  -> the lead_segment_members join, workspace-scoped
    dynamic -> the stored filter evaluated live over the leads table
    """
    from app.models.lead import Lead
    from app.models.lead_segment_member import LeadSegmentMember

    kind = getattr(segment, "kind", "static")
    if kind == "dynamic":
        conditions = _dynamic_filter_conditions(workspace_id, getattr(segment, "filter", {}) or {})
        result = await db.execute(select(Lead.id).where(and_(*conditions)))
    else:
        result = await db.execute(
            select(LeadSegmentMember.lead_id).where(
                LeadSegmentMember.workspace_id == workspace_id,
                LeadSegmentMember.segment_id == segment.id,
            )
        )
    return [row[0] for row in result.all()]


async def _run_enroll(workspace_id: str, campaign_id: str) -> dict[str, Any]:
    from app.models.campaign import Campaign
    from app.models.lead_segment import LeadSegment
    from app.models.sequence_enrollment import SequenceEnrollment
    from app.models.activity_event import ActivityEvent

    ws_uuid = uuid.UUID(workspace_id)
    camp_uuid = uuid.UUID(campaign_id)

    SessionFactory = _get_async_session()

    async with SessionFactory() as db:
        camp_result = await db.execute(
            select(Campaign).where(
                Campaign.id == camp_uuid,
                Campaign.workspace_id == ws_uuid,
            )
        )
        campaign = camp_result.scalar_one_or_none()
        if campaign is None:
            return {"error": "Campaign not found", "campaign_id": campaign_id}

        if campaign.segment_id is None or campaign.sequence_id is None:
            return {
                "campaign_id": campaign_id,
                "enrolled": 0,
                "resolved": 0,
                "reason": "campaign missing segment_id or sequence_id",
            }

        seg_result = await db.execute(
            select(LeadSegment).where(
                LeadSegment.id == campaign.segment_id,
                LeadSegment.workspace_id == ws_uuid,
            )
        )
        segment = seg_result.scalar_one_or_none()
        if segment is None:
            return {"error": "Segment not found", "campaign_id": campaign_id}

        lead_ids = await _resolve_segment_lead_ids(db, ws_uuid, segment)

        inserted = 0
        if lead_ids:
            next_run_at = campaign.scheduled_at or datetime.now(timezone.utc)
            rows = [
                {
                    "workspace_id": ws_uuid,
                    "campaign_id": camp_uuid,
                    "sequence_id": campaign.sequence_id,
                    "lead_id": lead_id,
                    "current_step": 0,
                    "status": "active",
                    "next_run_at": next_run_at,
                }
                for lead_id in lead_ids
            ]
            stmt = (
                pg_insert(SequenceEnrollment)
                .values(rows)
                .on_conflict_do_nothing(index_elements=["campaign_id", "lead_id"])
                .returning(SequenceEnrollment.id)
            )
            ins_result = await db.execute(stmt)
            inserted = len(ins_result.scalars().all())

        # Bump the denormalized enrolled counter (JSONB reassigned so SA flags it dirty).
        stats = dict(campaign.stats or {})
        stats["enrolled"] = int(stats.get("enrolled", 0) or 0) + inserted
        campaign.stats = stats  # type: ignore[assignment]
        db.add(campaign)

        event = ActivityEvent(
            workspace_id=ws_uuid,
            type="campaign_enrolled",
            agent_name="Campaign Enroller",
            description=(
                f"Enrolled {inserted} lead(s) into campaign "
                f"{campaign.name or campaign_id} "
                f"({len(lead_ids)} resolved from segment {segment.name or segment.id})"
            ),
            severity="info",
        )
        db.add(event)
        await db.commit()

    return {
        "campaign_id": campaign_id,
        "resolved": len(lead_ids),
        "enrolled": inserted,
    }


@celery_app.task(name="app.workers.campaign_enroll.enroll_campaign", bind=True)
def enroll_campaign(self: Any, workspace_id: str, campaign_id: str) -> dict[str, Any]:
    """Celery task: enroll a campaign's segment leads into its sequence."""
    return asyncio.run(_run_enroll(workspace_id, campaign_id))
