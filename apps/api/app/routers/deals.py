import uuid
from datetime import datetime, timedelta, timezone
from calendar import month_abbr

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_admin
from app.models.user import User
from app.models.deal import Deal
from app.models.activity_event import ActivityEvent

router = APIRouter()


class DealResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    title: str | None
    company: str | None
    contact_name: str | None
    contact_id: uuid.UUID | None
    value: float
    stage: str
    ml_win_probability: int
    expected_close: str | None
    assigned_agent: str | None
    notes: str | None
    health_score: int = 100
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


@router.get("/workspaces/{workspace_id}/deals", response_model=list[DealResponse])
async def list_deals(
    workspace_id: uuid.UUID,
    stage: str | None = Query(default=None),
    contact_id: uuid.UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[DealResponse]:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    q = select(Deal).where(Deal.workspace_id == workspace_id)
    if stage and stage != "all":
        q = q.where(Deal.stage == stage)
    if contact_id is not None:
        q = q.where(Deal.contact_id == contact_id)
    result = await db.execute(q)
    deals = result.scalars().all()
    return [DealResponse.model_validate(d) for d in deals]


@router.post("/workspaces/{workspace_id}/deals/health", status_code=202)
async def trigger_deal_health(
    workspace_id: uuid.UUID,
    current_user: User = Depends(require_admin),
) -> dict:
    """Enqueue a Celery job to recompute health scores for all active deals."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    from app.workers.deal_health_worker import compute_deal_health

    task = compute_deal_health.delay(str(workspace_id))
    return {"job_id": task.id, "status": "queued"}


@router.get("/workspaces/{workspace_id}/deals/stale")
async def stale_deals(
    workspace_id: uuid.UUID,
    threshold: int = 40,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """Return deals with health_score below threshold, ordered worst-first."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    from sqlalchemy import asc

    result = await db.execute(
        select(Deal)
        .where(
            Deal.workspace_id == workspace_id,
            Deal.health_score <= threshold,
            Deal.stage.not_in(["closed_won", "closed_lost"]),
        )
        .order_by(asc(Deal.health_score))
        .limit(10)
    )
    deals = result.scalars().all()

    from app.services.deal_health import compute_health

    out = []
    for d in deals:
        _, signals = compute_health(
            stage=d.stage,
            stage_changed_at=d.stage_changed_at or d.created_at,
            last_message_at=None,
        )
        out.append({
            "id": str(d.id),
            "title": d.title,
            "company": d.company,
            "stage": d.stage,
            "value": float(d.value or 0),
            "health_score": d.health_score,
            "signals": signals,
        })
    return out


@router.get("/workspaces/{workspace_id}/deals/history")
async def deals_history(
    workspace_id: uuid.UUID,
    months: int = Query(default=6, ge=1, le=24),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """Monthly closed-won revenue for the last N months."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    result = await db.execute(
        select(Deal).where(
            Deal.workspace_id == workspace_id,
            Deal.stage == "closed_won",
        )
    )
    won_deals = result.scalars().all()

    now = datetime.now(timezone.utc)
    buckets: dict[str, float] = {}
    for i in range(months - 1, -1, -1):
        target = now - timedelta(days=30 * i)
        key = month_abbr[target.month]
        buckets[key] = 0.0

    for deal in won_deals:
        ts = deal.updated_at
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        age_months = (now - ts).days // 30
        if 0 <= age_months < months:
            key = month_abbr[ts.month]
            if key in buckets:
                buckets[key] += float(deal.value or 0)

    return [{"month": m, "revenue": round(v)} for m, v in buckets.items()]


@router.get("/workspaces/{workspace_id}/pipeline/suggestions")
async def pipeline_suggestions(
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """Return top actionable suggestions derived from active deal data."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(Deal).where(
            Deal.workspace_id == workspace_id,
            Deal.stage.not_in(["closed_won", "closed_lost"]),
        )
    )
    deals = result.scalars().all()

    suggestions = []
    for deal in deals:
        sc = deal.stage_changed_at
        if sc and sc.tzinfo is None:
            sc = sc.replace(tzinfo=timezone.utc)
        days_stale = (now - sc).days if sc else 0

        if days_stale >= 21:
            suggestions.append({
                "deal_id": str(deal.id),
                "title": deal.title,
                "company": deal.company,
                "stage": deal.stage,
                "value": float(deal.value or 0),
                "action": "follow_up",
                "reason": f"No stage change in {days_stale} days",
                "priority": "high" if days_stale >= 30 else "medium",
            })
        elif (deal.ml_win_probability or 50) < 35 and deal.stage in ("proposal", "negotiation"):
            suggestions.append({
                "deal_id": str(deal.id),
                "title": deal.title,
                "company": deal.company,
                "stage": deal.stage,
                "value": float(deal.value or 0),
                "action": "review",
                "reason": f"Win probability only {deal.ml_win_probability}% — consider re-qualifying",
                "priority": "medium",
            })

    suggestions.sort(key=lambda s: (s["priority"] == "high", s["value"]), reverse=True)
    return suggestions[:10]


@router.post("/workspaces/{workspace_id}/pipeline/optimize", status_code=202)
async def trigger_pipeline_optimize(
    workspace_id: uuid.UUID,
    current_user: User = Depends(require_admin),
) -> dict:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    from app.workers.pipeline import optimize_pipeline
    task = optimize_pipeline.delay(str(workspace_id))
    return {"job_id": task.id, "status": "queued"}


class UpdateDealRequest(BaseModel):
    title: str | None = None
    company: str | None = None
    value: float | None = None
    stage: str | None = None
    ml_win_probability: int | None = None
    expected_close: str | None = None
    notes: str | None = None


class CreateDealRequest(BaseModel):
    title: str | None = None
    company: str | None = None
    contact_id: uuid.UUID | None = None
    contact_name: str | None = None
    value: float = 0.0
    stage: str = "lead"
    ml_win_probability: int = 50
    expected_close: str | None = None
    assigned_agent: str | None = None
    notes: str | None = None


@router.post("/workspaces/{workspace_id}/deals", response_model=DealResponse, status_code=201)
async def create_deal(
    workspace_id: uuid.UUID,
    body: CreateDealRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DealResponse:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    deal = Deal(
        workspace_id=workspace_id,
        title=body.title,
        company=body.company,
        contact_id=body.contact_id,
        contact_name=body.contact_name,
        value=body.value,
        stage=body.stage,
        ml_win_probability=body.ml_win_probability,
        expected_close=body.expected_close,
        assigned_agent=body.assigned_agent,
        notes=body.notes,
        stage_changed_at=datetime.now(timezone.utc),
    )
    db.add(deal)
    event = ActivityEvent(
        workspace_id=workspace_id,
        type="deal_created",
        agent_name="System",
        description=f"New deal: {body.title or 'Untitled'}" + (f" ({body.company})" if body.company else ""),
        severity="info",
    )
    db.add(event)
    await db.commit()
    await db.refresh(deal)
    return DealResponse.model_validate(deal)


@router.get("/workspaces/{workspace_id}/deals/{deal_id}", response_model=DealResponse)
async def get_deal(
    workspace_id: uuid.UUID,
    deal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DealResponse:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    result = await db.execute(
        select(Deal).where(Deal.id == deal_id, Deal.workspace_id == workspace_id)
    )
    deal = result.scalar_one_or_none()
    if deal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found")
    return DealResponse.model_validate(deal)


@router.patch("/workspaces/{workspace_id}/deals/{deal_id}", response_model=DealResponse)
async def update_deal(
    workspace_id: uuid.UUID,
    deal_id: uuid.UUID,
    body: UpdateDealRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DealResponse:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    result = await db.execute(
        select(Deal).where(Deal.id == deal_id, Deal.workspace_id == workspace_id)
    )
    deal = result.scalar_one_or_none()
    if deal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found")

    old_stage = deal.stage
    for field in ("title", "company", "value", "stage", "ml_win_probability", "expected_close", "notes"):
        value = getattr(body, field)
        if value is not None:
            setattr(deal, field, value)

    if body.stage is not None and body.stage != old_stage:
        deal.stage_changed_at = datetime.now(timezone.utc)

    db.add(deal)
    event = ActivityEvent(
        workspace_id=workspace_id,
        type="deal_moved",
        agent_name="System",
        description=f"Deal '{deal.title}' updated" + (f" → {deal.stage}" if body.stage else ""),
        severity="info",
    )
    db.add(event)
    await db.commit()
    await db.refresh(deal)
    return DealResponse.model_validate(deal)


@router.delete("/workspaces/{workspace_id}/deals/{deal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_deal(
    workspace_id: uuid.UUID,
    deal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    result = await db.execute(
        select(Deal).where(Deal.id == deal_id, Deal.workspace_id == workspace_id)
    )
    deal = result.scalar_one_or_none()
    if deal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found")

    deal_title = deal.title or str(deal_id)
    await db.delete(deal)
    event = ActivityEvent(
        workspace_id=workspace_id,
        type="deal_deleted",
        agent_name="System",
        description=f"Deal removed: {deal_title}",
        severity="warning",
    )
    db.add(event)
    await db.commit()
