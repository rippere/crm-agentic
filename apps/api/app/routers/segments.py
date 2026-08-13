import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.lead import Lead
from app.models.lead_segment import LeadSegment
from app.models.lead_segment_member import LeadSegmentMember
from app.models.activity_event import ActivityEvent
from app.services.supabase_rest import get_row

router = APIRouter()


# Mirror the SQL CHECK constraint on lead_segments.kind exactly.
SEGMENT_KINDS = ("static", "dynamic")


# ─── Schemas ─────────────────────────────────────────────────────────────────

class SegmentResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    description: str | None = None
    kind: str
    filter: dict = {}
    member_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class CreateSegmentRequest(BaseModel):
    name: str
    description: str | None = None
    kind: str = "static"
    filter: dict = {}


class UpdateSegmentRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    kind: str | None = None
    filter: dict | None = None


class SegmentMemberLead(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    contact_id: uuid.UUID | None = None
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    company: str | None = None
    title: str | None = None
    source: str
    stage: str
    score: int
    owner_id: uuid.UUID | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class AddMembersRequest(BaseModel):
    lead_ids: list[uuid.UUID]


class AddMembersResponse(BaseModel):
    segment_id: str
    added: int
    member_count: int


# ─── Collection routes ───────────────────────────────────────────────────────

@router.get("/workspaces/{workspace_id}/segments", response_model=list[SegmentResponse])
async def list_segments(
    workspace_id: uuid.UUID,
    kind: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[SegmentResponse]:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    q = select(LeadSegment).where(LeadSegment.workspace_id == workspace_id)
    if kind and kind != "all":
        if kind not in SEGMENT_KINDS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"kind must be one of {list(SEGMENT_KINDS)}",
            )
        q = q.where(LeadSegment.kind == kind)
    q = q.order_by(LeadSegment.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(q)
    segments = result.scalars().all()
    return [SegmentResponse.model_validate(s) for s in segments]


@router.post("/workspaces/{workspace_id}/segments", response_model=SegmentResponse, status_code=201)
async def create_segment(
    workspace_id: uuid.UUID,
    body: CreateSegmentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SegmentResponse:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if body.kind not in SEGMENT_KINDS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"kind must be one of {list(SEGMENT_KINDS)}",
        )

    name = (body.name or "").strip()
    if not name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Segment name must not be empty",
        )

    segment = LeadSegment(
        workspace_id=workspace_id,
        name=name,
        description=body.description,
        kind=body.kind,
        filter=body.filter or {},
        member_count=0,
    )
    db.add(segment)
    event = ActivityEvent(
        workspace_id=workspace_id,
        type="segment_created",
        agent_name="System",
        description=f"New segment: {name} ({body.kind})",
        severity="info",
    )
    db.add(event)
    await db.commit()
    await db.refresh(segment)
    return SegmentResponse.model_validate(segment)


# ─── Member sub-routes (declared before /{segment_id} for path clarity) ──────

@router.get(
    "/workspaces/{workspace_id}/segments/{segment_id}/members",
    response_model=list[SegmentMemberLead],
)
async def list_segment_members(
    workspace_id: uuid.UUID,
    segment_id: uuid.UUID,
    limit: int = Query(default=500, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[SegmentMemberLead]:
    """List the resolved leads for a segment.

    Static segments read the explicit join table; dynamic segments evaluate the
    stored ``filter`` JSON against the workspace's leads at request time.
    """
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    seg_result = await db.execute(
        select(LeadSegment).where(
            LeadSegment.id == segment_id,
            LeadSegment.workspace_id == workspace_id,
        )
    )
    segment = seg_result.scalar_one_or_none()
    if segment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Segment not found")

    if segment.kind == "dynamic":
        q = select(Lead).where(Lead.workspace_id == workspace_id)
        q = _apply_lead_filter(q, segment.filter or {})
    else:
        q = (
            select(Lead)
            .join(LeadSegmentMember, LeadSegmentMember.lead_id == Lead.id)
            .where(
                LeadSegmentMember.segment_id == segment_id,
                LeadSegmentMember.workspace_id == workspace_id,
                Lead.workspace_id == workspace_id,
            )
        )

    q = q.offset(offset).limit(limit)
    result = await db.execute(q)
    leads = result.scalars().all()
    return [SegmentMemberLead.model_validate(lead) for lead in leads]


@router.post(
    "/workspaces/{workspace_id}/segments/{segment_id}/members",
    response_model=AddMembersResponse,
)
async def add_segment_members(
    workspace_id: uuid.UUID,
    segment_id: uuid.UUID,
    body: AddMembersRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AddMembersResponse:
    """Add leads to a static segment, then recompute the member_count cache."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if not body.lead_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="lead_ids must not be empty",
        )
    if len(body.lead_ids) > 5000:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Maximum 5000 leads per add operation",
        )

    seg_result = await db.execute(
        select(LeadSegment).where(
            LeadSegment.id == segment_id,
            LeadSegment.workspace_id == workspace_id,
        )
    )
    segment = seg_result.scalar_one_or_none()
    if segment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Segment not found")

    if segment.kind != "static":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Members can only be added to static segments",
        )

    # Only attach leads that actually belong to this workspace.
    lead_result = await db.execute(
        select(Lead.id).where(
            Lead.workspace_id == workspace_id,
            Lead.id.in_(body.lead_ids),
        )
    )
    valid_lead_ids = set(lead_result.scalars().all())

    # Skip leads already in the segment to respect the (segment_id, lead_id) unique index.
    existing_result = await db.execute(
        select(LeadSegmentMember.lead_id).where(
            LeadSegmentMember.segment_id == segment_id,
            LeadSegmentMember.workspace_id == workspace_id,
        )
    )
    existing_ids = set(existing_result.scalars().all())

    added = 0
    for lead_id in valid_lead_ids:
        if lead_id in existing_ids:
            continue
        db.add(
            LeadSegmentMember(
                workspace_id=workspace_id,
                segment_id=segment_id,
                lead_id=lead_id,
            )
        )
        added += 1

    new_count = len(existing_ids | valid_lead_ids)
    segment.member_count = new_count
    db.add(segment)

    event = ActivityEvent(
        workspace_id=workspace_id,
        type="segment_updated",
        agent_name="System",
        description=f"Added {added} lead(s) to segment '{segment.name}'",
        severity="info",
    )
    db.add(event)
    await db.commit()

    return AddMembersResponse(
        segment_id=str(segment_id), added=added, member_count=new_count
    )


@router.delete(
    "/workspaces/{workspace_id}/segments/{segment_id}/members/{lead_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_segment_member(
    workspace_id: uuid.UUID,
    segment_id: uuid.UUID,
    lead_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Remove one lead from a static segment and recompute member_count."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    seg_result = await db.execute(
        select(LeadSegment).where(
            LeadSegment.id == segment_id,
            LeadSegment.workspace_id == workspace_id,
        )
    )
    segment = seg_result.scalar_one_or_none()
    if segment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Segment not found")

    member_result = await db.execute(
        select(LeadSegmentMember).where(
            LeadSegmentMember.segment_id == segment_id,
            LeadSegmentMember.lead_id == lead_id,
            LeadSegmentMember.workspace_id == workspace_id,
        )
    )
    member = member_result.scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Segment member not found")

    await db.delete(member)

    count_result = await db.execute(
        select(func.count())
        .select_from(LeadSegmentMember)
        .where(
            LeadSegmentMember.segment_id == segment_id,
            LeadSegmentMember.workspace_id == workspace_id,
        )
    )
    # Post-delete count within the same transaction is not yet reflected, so
    # subtract the row we just removed from the pre-delete count.
    pre_count = count_result.scalar() or 0
    segment.member_count = max(0, pre_count - 1)
    db.add(segment)

    event = ActivityEvent(
        workspace_id=workspace_id,
        type="segment_updated",
        agent_name="System",
        description=f"Removed lead from segment '{segment.name}'",
        severity="info",
    )
    db.add(event)
    await db.commit()


# ─── Item routes (/{segment_id}) ─────────────────────────────────────────────

@router.get("/workspaces/{workspace_id}/segments/{segment_id}", response_model=SegmentResponse)
async def get_segment(
    workspace_id: uuid.UUID,
    segment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SegmentResponse:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    result = await db.execute(
        select(LeadSegment).where(
            LeadSegment.id == segment_id,
            LeadSegment.workspace_id == workspace_id,
        )
    )
    segment = result.scalar_one_or_none()
    if segment is None:
        # Fallback to Supabase REST before declaring the segment missing.
        row = await get_row(
            "lead_segments",
            {"id": str(segment_id), "workspace_id": str(workspace_id)},
        )
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Segment not found")
        return SegmentResponse(
            id=row["id"],
            workspace_id=row["workspace_id"],
            name=row.get("name") or "",
            description=row.get("description"),
            kind=row.get("kind") or "static",
            filter=row.get("filter") or {},
            member_count=row.get("member_count") or 0,
        )
    return SegmentResponse.model_validate(segment)


@router.patch("/workspaces/{workspace_id}/segments/{segment_id}", response_model=SegmentResponse)
async def update_segment(
    workspace_id: uuid.UUID,
    segment_id: uuid.UUID,
    body: UpdateSegmentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SegmentResponse:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if body.kind is not None and body.kind not in SEGMENT_KINDS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"kind must be one of {list(SEGMENT_KINDS)}",
        )

    result = await db.execute(
        select(LeadSegment).where(
            LeadSegment.id == segment_id,
            LeadSegment.workspace_id == workspace_id,
        )
    )
    segment = result.scalar_one_or_none()
    if segment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Segment not found")

    for field in ("name", "description", "kind", "filter"):
        value = getattr(body, field)
        if value is not None:
            setattr(segment, field, value)

    db.add(segment)
    event = ActivityEvent(
        workspace_id=workspace_id,
        type="segment_updated",
        agent_name="System",
        description=f"Segment updated: {segment.name}",
        severity="info",
    )
    db.add(event)
    await db.commit()
    await db.refresh(segment)
    return SegmentResponse.model_validate(segment)


@router.delete(
    "/workspaces/{workspace_id}/segments/{segment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_segment(
    workspace_id: uuid.UUID,
    segment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    result = await db.execute(
        select(LeadSegment).where(
            LeadSegment.id == segment_id,
            LeadSegment.workspace_id == workspace_id,
        )
    )
    segment = result.scalar_one_or_none()
    if segment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Segment not found")

    segment_name = segment.name or str(segment_id)
    await db.delete(segment)
    event = ActivityEvent(
        workspace_id=workspace_id,
        type="segment_deleted",
        agent_name="System",
        description=f"Segment removed: {segment_name}",
        severity="warning",
    )
    db.add(event)
    await db.commit()


# ─── Dynamic-filter evaluation ───────────────────────────────────────────────

def _apply_lead_filter(query, flt: dict):
    """Translate a stored dynamic-segment filter into Lead WHERE clauses.

    Recognized keys mirror the documented filter shape
    ``{stage, source, min_score, ...}``. ``stage``/``source`` accept a single
    value or a list; unknown keys are ignored so a filter is never a hard error.
    """
    stage = flt.get("stage")
    if isinstance(stage, list) and stage:
        query = query.where(Lead.stage.in_(stage))
    elif isinstance(stage, str) and stage:
        query = query.where(Lead.stage == stage)

    source = flt.get("source")
    if isinstance(source, list) and source:
        query = query.where(Lead.source.in_(source))
    elif isinstance(source, str) and source:
        query = query.where(Lead.source == source)

    min_score = flt.get("min_score")
    if isinstance(min_score, (int, float)):
        query = query.where(Lead.score >= int(min_score))

    return query
