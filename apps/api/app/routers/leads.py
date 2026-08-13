"""Leads router — the funnel-engine surface for the lead-gen module.

Follows the house conventions verbatim (see routers/deals.py, routers/contacts.py):
module-level ``router = APIRouter()`` with no prefix/tags, full paths including
``/workspaces/{workspace_id}/...``, a first-line workspace-auth guard on every
handler, every query scoped by ``workspace_id``, inline Pydantic schemas, enum-ish
validation against the same literal sets as the SQL CHECK constraints, ActivityEvent
audit rows on writes, and ORM-first + supabase_rest fallback before 404.

STATIC sub-paths (``/funnel``, ``/import``, ``/export``) are declared BEFORE the
``/{lead_id}`` routes so they are not captured by the UUID path param.
"""

import csv
import io
import json
import os
import tempfile
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.lead import Lead
from app.models.lead_segment_member import LeadSegmentMember
from app.models.engagement_event import EngagementEvent
from app.models.contact import Contact
from app.models.deal import Deal
from app.models.activity_event import ActivityEvent
from app.services.supabase_rest import get_row

router = APIRouter()


# ─── Literal sets — mirror the SQL CHECK constraints in 023_outbound_engagement ──
LEAD_SOURCES = ("import", "manual", "web", "api", "referral", "event")
LEAD_STAGES = ("new", "contacted", "engaged", "qualified", "converted", "lost")


# ─── Schemas ─────────────────────────────────────────────────────────────────
class LeadResponse(BaseModel):
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
    score_detail: dict = {}
    owner_id: uuid.UUID | None = None
    custom_fields: dict = {}
    external_id: str | None = None
    last_engaged_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class CreateLeadRequest(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    company: str | None = None
    title: str | None = None
    source: str = "import"
    stage: str = "new"
    score: int = 0
    owner_id: uuid.UUID | None = None
    custom_fields: dict = {}
    external_id: str | None = None


class UpdateLeadRequest(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    company: str | None = None
    title: str | None = None
    source: str | None = None
    stage: str | None = None
    score: int | None = None
    owner_id: uuid.UUID | None = None
    custom_fields: dict | None = None
    external_id: str | None = None


class StageTransitionRequest(BaseModel):
    stage: str


class ImportLeadsRequest(BaseModel):
    rows: list[dict] = []
    mapping: dict = {}
    dedupe_on: str = "email"


class PromoteLeadRequest(BaseModel):
    create_deal: bool = False
    owner_id: uuid.UUID | None = None


# ─── STATIC sub-paths (declare BEFORE /{lead_id}) ────────────────────────────
@router.get("/workspaces/{workspace_id}/leads", response_model=list[LeadResponse])
async def list_leads(
    workspace_id: uuid.UUID,
    stage: str | None = Query(default=None),
    source: str | None = Query(default=None),
    min_score: int | None = Query(default=None, ge=0, le=100),
    segment_id: uuid.UUID | None = Query(default=None),
    q: str | None = Query(default=None),
    sort: str = Query(default="created_at"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[LeadResponse]:
    """List leads with funnel filters. `segment_id` restricts to a static segment's members."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    stmt = select(Lead).where(Lead.workspace_id == workspace_id)
    if stage and stage != "all":
        stmt = stmt.where(Lead.stage == stage)
    if source and source != "all":
        stmt = stmt.where(Lead.source == source)
    if min_score is not None:
        stmt = stmt.where(Lead.score >= min_score)
    if segment_id is not None:
        member_ids = (
            select(LeadSegmentMember.lead_id)
            .where(
                LeadSegmentMember.workspace_id == workspace_id,
                LeadSegmentMember.segment_id == segment_id,
            )
        )
        stmt = stmt.where(Lead.id.in_(member_ids))
    if q:
        from sqlalchemy import or_

        pattern = f"%{q}%"
        stmt = stmt.where(or_(
            Lead.name.ilike(pattern),
            Lead.email.ilike(pattern),
            Lead.company.ilike(pattern),
        ))

    if sort == "score":
        stmt = stmt.order_by(Lead.score.desc())
    elif sort == "stage":
        stmt = stmt.order_by(Lead.stage.asc())
    else:
        stmt = stmt.order_by(Lead.created_at.desc())

    stmt = stmt.offset(offset).limit(limit)
    result = await db.execute(stmt)
    leads = result.scalars().all()
    return [LeadResponse.model_validate(lead) for lead in leads]


@router.get("/workspaces/{workspace_id}/leads/funnel")
async def lead_funnel(
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """Lead count per funnel stage.

    NOTE: registered before /{lead_id} to avoid UUID-parse ambiguity.
    """
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    result = await db.execute(
        select(
            Lead.stage,
            func.count(),
            func.coalesce(func.sum(Lead.score), 0),
        )
        .where(Lead.workspace_id == workspace_id)
        .group_by(Lead.stage)
    )

    counts: dict[str, int] = {s: 0 for s in LEAD_STAGES}
    values: dict[str, int] = {s: 0 for s in LEAD_STAGES}
    for stage, count, value in result.all():
        if stage in counts:
            counts[stage] += int(count or 0)
            values[stage] += int(value or 0)

    return [{"stage": s, "count": counts[s], "value": values[s]} for s in LEAD_STAGES]


@router.post("/workspaces/{workspace_id}/leads/import", status_code=202)
async def import_leads(
    workspace_id: uuid.UUID,
    body: ImportLeadsRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Enqueue a bulk CSV import (up to 10k rows) via Celery.

    The payload rows (up to 10k dicts) are NOT passed inline through the Celery
    broker. They are persisted to a staging JSON file (temp dir keyed by a
    generated staging id) and only the FILE PATH is handed to the worker, whose
    `_load_rows` already accepts a path. This keeps the broker message tiny.

    NOTE: static path — registered before /{lead_id}.
    """
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    # Persist rows to a staging file keyed by a generated job id; pass the path.
    staging_id = uuid.uuid4()
    staging_dir = os.path.join(tempfile.gettempdir(), "lead-import", str(workspace_id))
    os.makedirs(staging_dir, exist_ok=True)
    staging_path = os.path.join(staging_dir, f"{staging_id}.json")
    with open(staging_path, "w", encoding="utf-8") as fh:
        json.dump(body.rows, fh)

    try:
        from app.workers.import_leads import process_lead_import  # noqa: PLC0415
        from app.routers.agents import _mark_job_dispatched

        task = process_lead_import.delay(
            str(workspace_id), staging_path, body.mapping, body.dedupe_on
        )
        _mark_job_dispatched(task.id, str(workspace_id))
        job_id = task.id
    except ImportError:
        # Worker not yet implemented (Round 3). Enqueue is a no-op stub.
        job_id = "pending"

    return {"status": "queued", "job_id": job_id}


@router.post("/workspaces/{workspace_id}/leads/export")
async def export_leads_csv(
    workspace_id: uuid.UUID,
    stage: str | None = Query(default=None),
    source: str | None = Query(default=None),
    min_score: int | None = Query(default=None, ge=0, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """Export the filtered lead set as a CSV file.

    NOTE: static path — registered before /{lead_id}.
    """
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    stmt = select(Lead).where(Lead.workspace_id == workspace_id)
    if stage and stage != "all":
        stmt = stmt.where(Lead.stage == stage)
    if source and source != "all":
        stmt = stmt.where(Lead.source == source)
    if min_score is not None:
        stmt = stmt.where(Lead.score >= min_score)

    result = await db.execute(stmt)
    leads = result.scalars().all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "id", "name", "email", "phone", "company", "title",
        "source", "stage", "score", "external_id", "created_at",
    ])
    for lead in leads:
        writer.writerow([
            str(lead.id), lead.name or "", lead.email or "", lead.phone or "",
            lead.company or "", lead.title or "", lead.source or "", lead.stage or "",
            lead.score, lead.external_id or "",
            lead.created_at.isoformat() if lead.created_at else "",
        ])

    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=leads.csv"},
    )


@router.post("/workspaces/{workspace_id}/leads", response_model=LeadResponse, status_code=201)
async def create_lead(
    workspace_id: uuid.UUID,
    body: CreateLeadRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> LeadResponse:
    """Create a single lead."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if body.source not in LEAD_SOURCES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"source must be one of {list(LEAD_SOURCES)}",
        )
    if body.stage not in LEAD_STAGES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"stage must be one of {list(LEAD_STAGES)}",
        )

    lead = Lead(
        workspace_id=workspace_id,
        name=body.name,
        email=body.email,
        phone=body.phone,
        company=body.company,
        title=body.title,
        source=body.source,
        stage=body.stage,
        score=body.score,
        owner_id=body.owner_id,
        custom_fields=body.custom_fields or {},
        external_id=body.external_id,
    )
    db.add(lead)
    event = ActivityEvent(
        workspace_id=workspace_id,
        type="lead_created",
        agent_name="System",
        description=f"New lead: {body.name or body.email or 'Unnamed'}"
        + (f" ({body.company})" if body.company else ""),
        severity="info",
    )
    db.add(event)
    await db.commit()
    await db.refresh(lead)
    return LeadResponse.model_validate(lead)


# ─── /{lead_id} routes ───────────────────────────────────────────────────────
@router.get("/workspaces/{workspace_id}/leads/{lead_id}", response_model=LeadResponse)
async def get_lead(
    workspace_id: uuid.UUID,
    lead_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> LeadResponse:
    """Return a single lead by id (ORM-first, Supabase-REST fallback before 404)."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    result = await db.execute(
        select(Lead).where(Lead.id == lead_id, Lead.workspace_id == workspace_id)
    )
    lead = result.scalar_one_or_none()
    if lead is None:
        row = await get_row("leads", {"id": str(lead_id), "workspace_id": str(workspace_id)})
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
        return LeadResponse.model_validate(row)
    return LeadResponse.model_validate(lead)


@router.patch("/workspaces/{workspace_id}/leads/{lead_id}", response_model=LeadResponse)
async def update_lead(
    workspace_id: uuid.UUID,
    lead_id: uuid.UUID,
    body: UpdateLeadRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> LeadResponse:
    """Update editable fields on a lead."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if body.source is not None and body.source not in LEAD_SOURCES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"source must be one of {list(LEAD_SOURCES)}",
        )
    if body.stage is not None and body.stage not in LEAD_STAGES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"stage must be one of {list(LEAD_STAGES)}",
        )

    result = await db.execute(
        select(Lead).where(Lead.id == lead_id, Lead.workspace_id == workspace_id)
    )
    lead = result.scalar_one_or_none()
    if lead is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")

    for field in (
        "name", "email", "phone", "company", "title", "source",
        "stage", "score", "owner_id", "custom_fields", "external_id",
    ):
        value = getattr(body, field)
        if value is not None:
            setattr(lead, field, value)

    db.add(lead)
    event = ActivityEvent(
        workspace_id=workspace_id,
        type="lead_updated",
        agent_name="System",
        description=f"Lead updated: {lead.name or lead.email or lead_id}",
        severity="info",
    )
    db.add(event)
    await db.commit()
    await db.refresh(lead)
    return LeadResponse.model_validate(lead)


@router.post("/workspaces/{workspace_id}/leads/{lead_id}/stage", response_model=LeadResponse)
async def transition_lead_stage(
    workspace_id: uuid.UUID,
    lead_id: uuid.UUID,
    body: StageTransitionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> LeadResponse:
    """Transition a lead to a new funnel stage (422 on an invalid stage).

    Writes an ActivityEvent audit row, and — when advancing to `converted` —
    appends an `engagement_event(type='converted')` fact row for the scorer.
    """
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if body.stage not in LEAD_STAGES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"stage must be one of {list(LEAD_STAGES)}",
        )

    result = await db.execute(
        select(Lead).where(Lead.id == lead_id, Lead.workspace_id == workspace_id)
    )
    lead = result.scalar_one_or_none()
    if lead is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")

    old_stage = lead.stage
    lead.stage = body.stage
    db.add(lead)

    event = ActivityEvent(
        workspace_id=workspace_id,
        type="lead_moved",
        agent_name="System",
        description=f"Lead '{lead.name or lead.email or lead_id}' {old_stage} → {body.stage}",
        severity="info",
    )
    db.add(event)

    if body.stage == "converted":
        db.add(EngagementEvent(
            workspace_id=workspace_id,
            lead_id=lead_id,
            type="converted",
            weight=40,
            metadata_={"from_stage": old_stage},
        ))

    await db.commit()
    await db.refresh(lead)
    return LeadResponse.model_validate(lead)


@router.post("/workspaces/{workspace_id}/leads/{lead_id}/promote")
async def promote_lead(
    workspace_id: uuid.UUID,
    lead_id: uuid.UUID,
    body: PromoteLeadRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Bot→human close handoff: promote a lead to a curated contact (+ optional deal).

    Creates or links a `contacts` row, optionally opens a `deals` row, sets
    `lead.contact_id`, and advances the lead's stage (→ qualified, or → converted
    when a deal is opened).
    """
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    result = await db.execute(
        select(Lead).where(Lead.id == lead_id, Lead.workspace_id == workspace_id)
    )
    lead = result.scalar_one_or_none()
    if lead is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")

    # Link an existing contact by email if one exists, else create a new one.
    contact = None
    if lead.email:
        existing = await db.execute(
            select(Contact).where(
                Contact.workspace_id == workspace_id,
                Contact.email == lead.email,
            )
        )
        contact = existing.scalar_one_or_none()

    if contact is None:
        contact = Contact(
            workspace_id=workspace_id,
            name=lead.name or lead.email or "Unnamed",
            email=lead.email,
            company=lead.company,
            role=lead.title,
            status="prospect",
        )
        db.add(contact)
        await db.flush()

    lead.contact_id = contact.id

    deal_id = None
    if body.create_deal:
        deal = Deal(
            workspace_id=workspace_id,
            title=f"{lead.company or lead.name or 'New'} — opportunity",
            company=lead.company,
            contact_id=contact.id,
            contact_name=lead.name,
            stage="discovery",
            stage_changed_at=datetime.now(timezone.utc),
        )
        db.add(deal)
        await db.flush()
        deal_id = str(deal.id)
        lead.stage = "converted"
    else:
        lead.stage = "qualified"

    if body.owner_id is not None:
        lead.owner_id = body.owner_id

    db.add(lead)
    event = ActivityEvent(
        workspace_id=workspace_id,
        type="lead_promoted",
        agent_name="System",
        description=f"Lead '{lead.name or lead.email or lead_id}' promoted to contact"
        + (" + deal" if deal_id else ""),
        severity="info",
    )
    db.add(event)
    await db.commit()
    await db.refresh(lead)

    return {
        "lead": LeadResponse.model_validate(lead).model_dump(mode="json"),
        "contact_id": str(contact.id),
        "deal_id": deal_id,
    }


@router.post("/workspaces/{workspace_id}/leads/{lead_id}/score", status_code=202)
async def score_lead(
    workspace_id: uuid.UUID,
    lead_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Enqueue an engagement-score recompute for a lead via Celery.

    The scoring worker (`app.workers.engagement_score`) lands in a later round;
    the `.delay` dispatch is guarded so this returns 202 either way.
    """
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    result = await db.execute(
        select(Lead).where(Lead.id == lead_id, Lead.workspace_id == workspace_id)
    )
    lead = result.scalar_one_or_none()
    if lead is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")

    try:
        from app.workers.engagement_score import score_lead_engagement  # noqa: PLC0415
        from app.routers.agents import _mark_job_dispatched

        task = score_lead_engagement.delay(str(workspace_id), str(lead_id))
        _mark_job_dispatched(task.id, str(workspace_id))
        job_id = task.id
    except ImportError:
        job_id = "pending"

    return {"status": "queued", "lead_id": str(lead_id), "job_id": job_id}


@router.delete("/workspaces/{workspace_id}/leads/{lead_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_lead(
    workspace_id: uuid.UUID,
    lead_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Delete a lead and its cascade-linked children."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    result = await db.execute(
        select(Lead).where(Lead.id == lead_id, Lead.workspace_id == workspace_id)
    )
    lead = result.scalar_one_or_none()
    if lead is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")

    lead_label = lead.name or lead.email or str(lead_id)
    await db.delete(lead)
    event = ActivityEvent(
        workspace_id=workspace_id,
        type="lead_deleted",
        agent_name="System",
        description=f"Lead removed: {lead_label}",
        severity="warning",
    )
    db.add(event)
    await db.commit()
