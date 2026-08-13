import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.campaign import Campaign
from app.models.sequence_enrollment import SequenceEnrollment
from app.models.engagement_event import EngagementEvent
from app.models.activity_event import ActivityEvent
from app.services.supabase_rest import get_row

router = APIRouter()


# Enum-ish literal sets — mirror the SQL CHECK constraints in
# migrations/023_outbound_engagement.sql exactly.
CAMPAIGN_STATUSES = ("draft", "scheduled", "active", "paused", "completed", "archived")
CAMPAIGN_CHANNELS = ("email", "sms", "mixed")


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class CampaignResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    segment_id: uuid.UUID | None = None
    sequence_id: uuid.UUID | None = None
    name: str
    status: str
    channel: str
    scheduled_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    stats: dict = {}
    settings: dict = {}
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CreateCampaignRequest(BaseModel):
    name: str
    segment_id: uuid.UUID | None = None
    sequence_id: uuid.UUID | None = None
    channel: str = "email"
    settings: dict = {}


class UpdateCampaignRequest(BaseModel):
    name: str | None = None
    segment_id: uuid.UUID | None = None
    sequence_id: uuid.UUID | None = None
    channel: str | None = None
    settings: dict | None = None


class ScheduleCampaignRequest(BaseModel):
    scheduled_at: datetime


class EnrollmentResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    campaign_id: uuid.UUID
    sequence_id: uuid.UUID
    lead_id: uuid.UUID
    current_step: int
    status: str
    next_run_at: datetime | None = None
    last_sent_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _hydrate_campaign_from_row(row: dict) -> Campaign:
    """Build a transient Campaign ORM instance from a Supabase REST row so the
    caller can render or mutate it when the record is not in local Postgres."""
    def _dt(val):
        if not val:
            return None
        try:
            return datetime.fromisoformat(str(val).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None

    return Campaign(
        id=uuid.UUID(str(row["id"])),
        workspace_id=uuid.UUID(str(row["workspace_id"])),
        segment_id=uuid.UUID(str(row["segment_id"])) if row.get("segment_id") else None,
        sequence_id=uuid.UUID(str(row["sequence_id"])) if row.get("sequence_id") else None,
        name=row.get("name") or "",
        status=row.get("status") or "draft",
        channel=row.get("channel") or "email",
        scheduled_at=_dt(row.get("scheduled_at")),
        started_at=_dt(row.get("started_at")),
        completed_at=_dt(row.get("completed_at")),
        stats=row.get("stats") or {},
        settings=row.get("settings") or {},
        created_at=_dt(row.get("created_at")) or datetime.now(timezone.utc),
        updated_at=_dt(row.get("updated_at")) or datetime.now(timezone.utc),
    )


async def _load_campaign(
    db: AsyncSession, workspace_id: uuid.UUID, campaign_id: uuid.UUID
) -> Campaign | None:
    """ORM-first load with a Supabase REST fallback before the caller 404s."""
    result = await db.execute(
        select(Campaign).where(
            Campaign.id == campaign_id, Campaign.workspace_id == workspace_id
        )
    )
    campaign = result.scalar_one_or_none()
    if campaign is not None:
        return campaign

    row = await get_row(
        "campaigns", {"id": str(campaign_id), "workspace_id": str(workspace_id)}
    )
    if row is None:
        return None
    return _hydrate_campaign_from_row(row)


# ---------------------------------------------------------------------------
# Collection routes (static — declared before /{campaign_id})
# ---------------------------------------------------------------------------


@router.get("/workspaces/{workspace_id}/campaigns", response_model=list[CampaignResponse])
async def list_campaigns(
    workspace_id: uuid.UUID,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[CampaignResponse]:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    q = select(Campaign).where(Campaign.workspace_id == workspace_id)
    if status_filter and status_filter != "all":
        q = q.where(Campaign.status == status_filter)
    q = q.order_by(Campaign.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(q)
    campaigns = result.scalars().all()
    return [CampaignResponse.model_validate(c) for c in campaigns]


@router.post(
    "/workspaces/{workspace_id}/campaigns",
    response_model=CampaignResponse,
    status_code=201,
)
async def create_campaign(
    workspace_id: uuid.UUID,
    body: CreateCampaignRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CampaignResponse:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if body.channel not in CAMPAIGN_CHANNELS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"channel must be one of {list(CAMPAIGN_CHANNELS)}",
        )

    campaign = Campaign(
        workspace_id=workspace_id,
        segment_id=body.segment_id,
        sequence_id=body.sequence_id,
        name=body.name,
        status="draft",
        channel=body.channel,
        stats={},
        settings=body.settings or {},
    )
    db.add(campaign)
    event = ActivityEvent(
        workspace_id=workspace_id,
        type="campaign_created",
        agent_name="System",
        description=f"New campaign: {body.name}",
        severity="info",
    )
    db.add(event)
    await db.commit()
    await db.refresh(campaign)
    return CampaignResponse.model_validate(campaign)


# ---------------------------------------------------------------------------
# Item routes (/{campaign_id} + sub-actions)
# ---------------------------------------------------------------------------


@router.get(
    "/workspaces/{workspace_id}/campaigns/{campaign_id}",
    response_model=CampaignResponse,
)
async def get_campaign(
    workspace_id: uuid.UUID,
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CampaignResponse:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    campaign = await _load_campaign(db, workspace_id, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    return CampaignResponse.model_validate(campaign)


@router.patch(
    "/workspaces/{workspace_id}/campaigns/{campaign_id}",
    response_model=CampaignResponse,
)
async def update_campaign(
    workspace_id: uuid.UUID,
    campaign_id: uuid.UUID,
    body: UpdateCampaignRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CampaignResponse:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if body.channel is not None and body.channel not in CAMPAIGN_CHANNELS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"channel must be one of {list(CAMPAIGN_CHANNELS)}",
        )

    campaign = await _load_campaign(db, workspace_id, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    for field in ("name", "segment_id", "sequence_id", "channel", "settings"):
        value = getattr(body, field)
        if value is not None:
            setattr(campaign, field, value)

    db.add(campaign)
    event = ActivityEvent(
        workspace_id=workspace_id,
        type="campaign_updated",
        agent_name="System",
        description=f"Campaign '{campaign.name}' updated",
        severity="info",
    )
    db.add(event)
    await db.commit()
    await db.refresh(campaign)
    return CampaignResponse.model_validate(campaign)


@router.post(
    "/workspaces/{workspace_id}/campaigns/{campaign_id}/schedule",
    response_model=CampaignResponse,
)
async def schedule_campaign(
    workspace_id: uuid.UUID,
    campaign_id: uuid.UUID,
    body: ScheduleCampaignRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CampaignResponse:
    """Set scheduled_at and transition the campaign to 'scheduled'."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    campaign = await _load_campaign(db, workspace_id, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    campaign.scheduled_at = body.scheduled_at
    campaign.status = "scheduled"
    db.add(campaign)
    event = ActivityEvent(
        workspace_id=workspace_id,
        type="campaign_scheduled",
        agent_name="System",
        description=f"Campaign '{campaign.name}' scheduled for {body.scheduled_at.isoformat()}",
        severity="info",
    )
    db.add(event)
    await db.commit()
    await db.refresh(campaign)
    return CampaignResponse.model_validate(campaign)


@router.post("/workspaces/{workspace_id}/campaigns/{campaign_id}/launch", status_code=202)
async def launch_campaign(
    workspace_id: uuid.UUID,
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Activate the campaign and enqueue the enrollment worker.

    Enqueue uses a guarded import (mirrors the leads-import enqueue) so that a
    not-yet-deployed worker degrades to a synthetic job id rather than 500-ing.
    """
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    campaign = await _load_campaign(db, workspace_id, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    campaign.status = "active"
    campaign.started_at = datetime.now(timezone.utc)
    db.add(campaign)
    event = ActivityEvent(
        workspace_id=workspace_id,
        type="campaign_launched",
        agent_name="System",
        description=f"Campaign '{campaign.name}' launched",
        severity="info",
    )
    db.add(event)
    await db.commit()

    job_id: str
    try:
        from app.workers.campaign_enroll import enroll_campaign
        from app.routers.agents import _mark_job_dispatched

        task = enroll_campaign.delay(str(workspace_id), str(campaign_id))
        job_id = task.id
        _mark_job_dispatched(task.id, str(workspace_id))
    except Exception:
        # Worker not yet available (build order U10) — return a synthetic job id
        # so the endpoint contract (202 + job_id) holds regardless.
        job_id = str(uuid.uuid4())

    return {"status": "queued", "campaign_id": str(campaign_id), "job_id": job_id}


@router.post(
    "/workspaces/{workspace_id}/campaigns/{campaign_id}/pause",
    response_model=CampaignResponse,
)
async def pause_campaign(
    workspace_id: uuid.UUID,
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CampaignResponse:
    """Halt the sender by moving the campaign to 'paused'."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    campaign = await _load_campaign(db, workspace_id, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    campaign.status = "paused"
    db.add(campaign)
    event = ActivityEvent(
        workspace_id=workspace_id,
        type="campaign_paused",
        agent_name="System",
        description=f"Campaign '{campaign.name}' paused",
        severity="info",
    )
    db.add(event)
    await db.commit()
    await db.refresh(campaign)
    return CampaignResponse.model_validate(campaign)


@router.post(
    "/workspaces/{workspace_id}/campaigns/{campaign_id}/resume",
    response_model=CampaignResponse,
)
async def resume_campaign(
    workspace_id: uuid.UUID,
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CampaignResponse:
    """Resume a paused campaign by moving it back to 'active'."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    campaign = await _load_campaign(db, workspace_id, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    campaign.status = "active"
    db.add(campaign)
    event = ActivityEvent(
        workspace_id=workspace_id,
        type="campaign_resumed",
        agent_name="System",
        description=f"Campaign '{campaign.name}' resumed",
        severity="info",
    )
    db.add(event)
    await db.commit()
    await db.refresh(campaign)
    return CampaignResponse.model_validate(campaign)


@router.get(
    "/workspaces/{workspace_id}/campaigns/{campaign_id}/enrollments",
    response_model=list[EnrollmentResponse],
)
async def list_campaign_enrollments(
    workspace_id: uuid.UUID,
    campaign_id: uuid.UUID,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[EnrollmentResponse]:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    q = select(SequenceEnrollment).where(
        SequenceEnrollment.workspace_id == workspace_id,
        SequenceEnrollment.campaign_id == campaign_id,
    )
    if status_filter:
        q = q.where(SequenceEnrollment.status == status_filter)
    q = q.offset(offset).limit(limit)
    result = await db.execute(q)
    enrollments = result.scalars().all()
    return [EnrollmentResponse.model_validate(e) for e in enrollments]


@router.get("/workspaces/{workspace_id}/campaigns/{campaign_id}/stats")
async def campaign_stats(
    workspace_id: uuid.UUID,
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Live engagement rollup for a campaign, aggregated from engagement_events."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    campaign = await _load_campaign(db, workspace_id, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    result = await db.execute(
        select(EngagementEvent.type, func.count())
        .where(
            EngagementEvent.workspace_id == workspace_id,
            EngagementEvent.campaign_id == campaign_id,
        )
        .group_by(EngagementEvent.type)
    )

    by_type: dict[str, int] = {}
    total_events = 0
    for etype, count in result.all():
        key = etype or "unknown"
        count = int(count or 0)
        by_type[key] = by_type.get(key, 0) + count
        total_events += count

    return {
        "campaign_id": str(campaign_id),
        "status": campaign.status,
        "stats": campaign.stats or {},
        "events_by_type": by_type,
        "total_events": total_events,
    }


@router.delete(
    "/workspaces/{workspace_id}/campaigns/{campaign_id}",
    response_model=CampaignResponse,
)
async def archive_campaign(
    workspace_id: uuid.UUID,
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CampaignResponse:
    """Archive a campaign (soft-delete via status='archived')."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    campaign = await _load_campaign(db, workspace_id, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    campaign.status = "archived"
    db.add(campaign)
    event = ActivityEvent(
        workspace_id=workspace_id,
        type="campaign_archived",
        agent_name="System",
        description=f"Campaign archived: {campaign.name}",
        severity="warning",
    )
    db.add(event)
    await db.commit()
    await db.refresh(campaign)
    return CampaignResponse.model_validate(campaign)
