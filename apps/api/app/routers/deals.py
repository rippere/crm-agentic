import csv
import io
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from calendar import month_abbr
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_admin
from app.models.user import User
from app.models.deal import Deal
from app.models.deal_note import DealNote
from app.models.deal_health_history import DealHealthHistory
from app.models.activity_event import ActivityEvent
from app.models.message import Message

router = APIRouter()


OUTCOME_REASONS = ("price", "competition", "timing", "fit", "champion_left", "other")


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
    win_loss_reason: str | None = None
    next_action: str | None = None
    next_action_date: date | None = None
    competitors: list[str] = []
    mentions: list = []

    @field_validator("competitors", "mentions", mode="before")
    @classmethod
    def _none_to_empty_list(cls, v):
        return v if v is not None else []
    created_at: datetime

    model_config = {"from_attributes": True}


@router.get("/workspaces/{workspace_id}/deals", response_model=list[DealResponse])
async def list_deals(
    workspace_id: uuid.UUID,
    stage: str | None = Query(default=None),
    contact_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
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
    q = q.offset(offset).limit(limit)
    result = await db.execute(q)
    deals = result.scalars().all()
    return [DealResponse.model_validate(d) for d in deals]


@router.get("/workspaces/{workspace_id}/deals/export")
async def export_deals_csv(
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """Export all workspace deals as a CSV file."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    result = await db.execute(select(Deal).where(Deal.workspace_id == workspace_id))
    deals = result.scalars().all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "id", "title", "company", "contact_name", "value",
        "stage", "ml_win_probability", "health_score", "expected_close", "created_at",
    ])
    for d in deals:
        writer.writerow([
            str(d.id), d.title or "", d.company or "", d.contact_name or "",
            d.value, d.stage or "", d.ml_win_probability, d.health_score,
            d.expected_close or "",
            d.created_at.isoformat() if d.created_at else "",
        ])

    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=deals.csv"},
    )


@router.post("/workspaces/{workspace_id}/deals/health", status_code=202)
async def trigger_deal_health(
    workspace_id: uuid.UUID,
    current_user: User = Depends(require_admin),
) -> dict:
    """Enqueue a Celery job to recompute health scores for all active deals."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    from app.workers.deal_health_worker import compute_deal_health
    from app.routers.agents import _mark_job_dispatched

    task = compute_deal_health.delay(str(workspace_id))
    _mark_job_dispatched(task.id, str(workspace_id))
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
    cur_year, cur_month = now.year, now.month
    buckets: dict[str, float] = {}
    month_keys: list[tuple[int, int]] = []
    for i in range(months - 1, -1, -1):
        m = cur_month - i
        y = cur_year
        while m <= 0:
            m += 12
            y -= 1
        month_keys.append((y, m))
        buckets[month_abbr[m]] = 0.0

    for deal in won_deals:
        ts = deal.updated_at
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if any(ts.year == y and ts.month == m for y, m in month_keys):
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
    from app.routers.agents import _mark_job_dispatched
    task = optimize_pipeline.delay(str(workspace_id))
    _mark_job_dispatched(task.id, str(workspace_id))
    return {"job_id": task.id, "status": "queued"}


class UpdateDealRequest(BaseModel):
    title: str | None = None
    company: str | None = None
    value: float | None = None
    stage: str | None = None
    ml_win_probability: int | None = None
    expected_close: str | None = None
    notes: str | None = None
    next_action: str | None = None
    next_action_date: date | None = None


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


class CreateDealNoteRequest(BaseModel):
    body: str
    author: str | None = None


class DealNoteResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    deal_id: uuid.UUID
    body: str
    author: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


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


@router.get("/workspaces/{workspace_id}/deals/forecast")
async def deal_forecast(
    workspace_id: uuid.UUID,
    months_ahead: int = Query(default=6, ge=1, le=12),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """Group active deals by expected_close month — pipeline forecast.

    NOTE: must be registered BEFORE the /deals/{deal_id} routes — otherwise
    "forecast" is captured by the {deal_id} path param and 422s on UUID parsing.
    """
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    result = await db.execute(
        select(Deal).where(
            Deal.workspace_id == workspace_id,
            Deal.stage.not_in(["closed_won", "closed_lost"]),
            Deal.expected_close.is_not(None),
        )
    )
    deals = result.scalars().all()

    now = datetime.now(timezone.utc)
    buckets: dict[str, dict] = {}
    # Walk consecutive calendar months — using 30-day strides would skip a month
    # across 31-day months and silently drop deals that close in the gap.
    year, month = now.year, now.month
    for _ in range(months_ahead):
        key = now.replace(year=year, month=month, day=1).strftime("%b %Y")
        buckets[key] = {"month": key, "value": 0.0, "deal_count": 0}
        month += 1
        if month > 12:
            month = 1
            year += 1

    for deal in deals:
        if not deal.expected_close:
            continue
        try:
            ec = datetime.strptime(str(deal.expected_close), "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue
        key = ec.strftime("%b %Y")
        if key in buckets:
            buckets[key]["value"] += float(deal.value or 0)
            buckets[key]["deal_count"] += 1

    return [
        {"month": v["month"], "value": round(v["value"]), "deal_count": v["deal_count"]}
        for v in buckets.values()
    ]


@router.get("/workspaces/{workspace_id}/deals/velocity")
async def deal_velocity(
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """Average days each deal has spent in its current stage, grouped by stage.

    NOTE: registered before /{deal_id} to avoid UUID-parse ambiguity.
    """
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    result = await db.execute(
        select(Deal).where(Deal.workspace_id == workspace_id)
    )
    deals = result.scalars().all()

    now = datetime.now(timezone.utc)
    stage_data: dict[str, list[float]] = {}

    for deal in deals:
        sc = deal.stage_changed_at or deal.created_at
        if sc and sc.tzinfo is None:
            sc = sc.replace(tzinfo=timezone.utc)
        days = max(0.0, (now - sc).total_seconds() / 86400) if sc else 0.0
        stage = deal.stage or "unknown"
        stage_data.setdefault(stage, []).append(days)

    stage_order = ["discovery", "qualified", "proposal", "negotiation", "closed_won", "closed_lost"]
    out = []
    for stage in stage_order:
        if stage in stage_data:
            days_list = stage_data[stage]
            avg = round(sum(days_list) / len(days_list), 1)
            out.append({"stage": stage, "avg_days": avg, "deal_count": len(days_list)})
    return out


@router.get("/workspaces/{workspace_id}/deals/funnel")
async def deal_funnel(
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """Deal count and stage-to-stage conversion rate for the pipeline funnel.

    NOTE: registered before /{deal_id} to avoid UUID-parse ambiguity.
    """
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    result = await db.execute(
        select(Deal).where(Deal.workspace_id == workspace_id)
    )
    deals = result.scalars().all()

    stage_order = ["discovery", "qualified", "proposal", "negotiation", "closed_won", "closed_lost"]
    counts: dict[str, int] = {s: 0 for s in stage_order}
    for deal in deals:
        stage = deal.stage or "unknown"
        if stage in counts:
            counts[stage] += 1

    out: list[dict] = []
    for i, stage in enumerate(stage_order):
        count = counts[stage]
        if i == 0:
            conversion_rate = None
        else:
            prev = out[-1]["deal_count"]
            conversion_rate = round((count / prev) * 100, 1) if prev > 0 else 0.0
        out.append({"stage": stage, "deal_count": count, "conversion_rate": conversion_rate})

    return out


class SetOutcomeRequest(BaseModel):
    stage: Literal["closed_won", "closed_lost"]
    reason: str


@router.put("/workspaces/{workspace_id}/deals/{deal_id}/outcome", response_model=DealResponse)
async def set_deal_outcome(
    workspace_id: uuid.UUID,
    deal_id: uuid.UUID,
    body: SetOutcomeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DealResponse:
    """Set a deal's outcome stage (closed_won|closed_lost) and attach a reason tag."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if body.reason not in OUTCOME_REASONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid reason. Must be one of: {', '.join(OUTCOME_REASONS)}",
        )

    result = await db.execute(
        select(Deal).where(Deal.id == deal_id, Deal.workspace_id == workspace_id)
    )
    deal = result.scalar_one_or_none()
    if deal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found")

    old_stage = deal.stage
    deal.stage = body.stage
    deal.win_loss_reason = body.reason
    if body.stage != old_stage:
        deal.stage_changed_at = datetime.now(timezone.utc)

    db.add(deal)
    event = ActivityEvent(
        workspace_id=workspace_id,
        type="deal_moved",
        agent_name="System",
        description=f"Deal '{deal.title}' → {body.stage} (reason: {body.reason})",
        severity="info",
    )
    db.add(event)
    await db.commit()
    await db.refresh(deal)
    return DealResponse.model_validate(deal)


@router.get("/workspaces/{workspace_id}/deals/outcome-reasons")
async def outcome_reasons(
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """Count closed deals grouped by win_loss_reason × outcome (won/lost).

    NOTE: registered before /{deal_id} to avoid UUID-parse ambiguity.
    """
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    result = await db.execute(
        select(Deal).where(
            Deal.workspace_id == workspace_id,
            Deal.stage.in_(["closed_won", "closed_lost"]),
            Deal.win_loss_reason.is_not(None),
        )
    )
    deals = result.scalars().all()

    buckets: dict[str, dict[str, int]] = {r: {"won": 0, "lost": 0} for r in OUTCOME_REASONS}
    for deal in deals:
        reason = deal.win_loss_reason
        if reason not in buckets:
            continue
        if deal.stage == "closed_won":
            buckets[reason]["won"] += 1
        else:
            buckets[reason]["lost"] += 1

    reason_labels = {
        "price": "Price",
        "competition": "Competition",
        "timing": "Timing",
        "fit": "Product Fit",
        "champion_left": "Champion Left",
        "other": "Other",
    }
    return [
        {"reason": r, "label": reason_labels[r], "won": v["won"], "lost": v["lost"]}
        for r, v in buckets.items()
        if v["won"] > 0 or v["lost"] > 0
    ]


@router.get("/workspaces/{workspace_id}/deals/at-risk")
async def at_risk_deals(
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """Return open deals flagged as 'at risk': low ML win probability (<30%) AND
    no stage change in 14+ days.  Optionally also surfaced when next_action_date
    is in the past.

    NOTE: registered before /{deal_id} to avoid UUID-parse ambiguity.
    """
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=14)

    result = await db.execute(
        select(Deal).where(
            Deal.workspace_id == workspace_id,
            Deal.stage.not_in(["closed_won", "closed_lost"]),
            Deal.ml_win_probability < 30,
        ).order_by(Deal.ml_win_probability.asc())
    )
    deals = result.scalars().all()

    today = date.today()
    out = []
    for d in deals:
        sc = d.stage_changed_at or d.created_at
        if sc and sc.tzinfo is None:
            sc = sc.replace(tzinfo=timezone.utc)
        days_inactive = int((now - sc).total_seconds() / 86400) if sc else 0
        if days_inactive < 14:
            continue

        reasons: list[str] = [f"Win probability only {d.ml_win_probability}%"]
        reasons.append(f"No activity in {days_inactive} days")
        if d.next_action_date and d.next_action_date < today:
            overdue = (today - d.next_action_date).days
            reasons.append(f"Next action overdue by {overdue} day{'s' if overdue != 1 else ''}")

        out.append({
            "id": str(d.id),
            "title": d.title,
            "company": d.company,
            "stage": d.stage,
            "value": float(d.value or 0),
            "ml_win_probability": d.ml_win_probability,
            "days_inactive": days_inactive,
            "risk_reason": "; ".join(reasons),
        })

    return out


@router.get("/workspaces/{workspace_id}/deals/overdue-actions")
async def overdue_actions(
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """Return open deals whose next_action_date is today or in the past, ordered by most overdue first.

    NOTE: registered before /{deal_id} to avoid UUID-parse ambiguity.
    """
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    today = date.today()
    result = await db.execute(
        select(Deal).where(
            Deal.workspace_id == workspace_id,
            Deal.next_action_date.is_not(None),
            Deal.next_action_date <= today,
            Deal.stage.not_in(["closed_won", "closed_lost"]),
        ).order_by(Deal.next_action_date.asc())
    )
    deals = result.scalars().all()

    return [
        {
            "id": str(d.id),
            "title": d.title,
            "company": d.company,
            "stage": d.stage,
            "value": float(d.value or 0),
            "next_action": d.next_action,
            "next_action_date": d.next_action_date.isoformat() if d.next_action_date else None,
            "days_overdue": (today - d.next_action_date).days if d.next_action_date else 0,
        }
        for d in deals
    ]


@router.get("/workspaces/{workspace_id}/deals/close-date-slipped")
async def close_date_slipped(
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """Open deals whose expected_close is in the past, ordered by most overdue first.

    NOTE: registered before /{deal_id} to avoid UUID-parse ambiguity.
    """
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    today = date.today()
    result = await db.execute(
        select(Deal).where(
            Deal.workspace_id == workspace_id,
            Deal.expected_close.is_not(None),
            Deal.expected_close < today.isoformat(),
            Deal.stage.not_in(["closed_won", "closed_lost"]),
        ).order_by(Deal.expected_close.asc())
    )
    deals = result.scalars().all()

    return [
        {
            "id": str(d.id),
            "title": d.title,
            "company": d.company,
            "stage": d.stage,
            "value": float(d.value or 0),
            "expected_close": d.expected_close,
            "days_overdue": (today - date.fromisoformat(d.expected_close)).days if d.expected_close else 0,
        }
        for d in deals
    ]


@router.get("/workspaces/{workspace_id}/deals/health-distribution")
async def health_distribution(
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """Group all open deals into health buckets: critical (<40), at_risk (40–69), healthy (70–100).

    NOTE: registered before /{deal_id} to avoid UUID-parse ambiguity.
    """
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    result = await db.execute(
        select(Deal).where(
            Deal.workspace_id == workspace_id,
            Deal.stage.not_in(["closed_won", "closed_lost"]),
        )
    )
    deals = result.scalars().all()

    buckets: dict[str, dict] = {
        "critical": {"bucket": "critical", "count": 0, "total_value": 0.0},
        "at_risk": {"bucket": "at_risk", "count": 0, "total_value": 0.0},
        "healthy": {"bucket": "healthy", "count": 0, "total_value": 0.0},
    }
    for d in deals:
        score = d.health_score if d.health_score is not None else 100
        value = float(d.value or 0)
        if score < 40:
            buckets["critical"]["count"] += 1
            buckets["critical"]["total_value"] += value
        elif score < 70:
            buckets["at_risk"]["count"] += 1
            buckets["at_risk"]["total_value"] += value
        else:
            buckets["healthy"]["count"] += 1
            buckets["healthy"]["total_value"] += value

    return list(buckets.values())


@router.get("/workspaces/{workspace_id}/deals/by-agent")
async def deals_by_agent(
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """Group open deals by assigned_agent; null agents appear as 'Unassigned'.

    NOTE: registered before /{deal_id} to avoid UUID-parse ambiguity.
    """
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    result = await db.execute(
        select(Deal).where(
            Deal.workspace_id == workspace_id,
            Deal.stage.not_in(["closed_won", "closed_lost"]),
        )
    )
    deals = result.scalars().all()

    buckets: dict[str, dict] = {}
    for d in deals:
        name = d.assigned_agent or "Unassigned"
        if name not in buckets:
            buckets[name] = {"agent_name": name, "count": 0, "total_value": 0.0}
        buckets[name]["count"] += 1
        buckets[name]["total_value"] += float(d.value or 0)

    return sorted(buckets.values(), key=lambda b: b["count"], reverse=True)


@router.get("/workspaces/{workspace_id}/deals/revenue-forecast")
async def deal_revenue_forecast(
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """Return weighted expected revenue grouped by expected-close month for open deals.

    NOTE: registered before /{deal_id} to avoid UUID-parse ambiguity.
    """
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    result = await db.execute(
        select(Deal).where(
            Deal.workspace_id == workspace_id,
            Deal.stage.not_in(["closed_won", "closed_lost"]),
        )
    )
    deals = result.scalars().all()

    buckets: dict[str, dict] = {}
    for d in deals:
        if not d.expected_close:
            continue
        month = str(d.expected_close)[:7]  # "YYYY-MM"
        value = float(d.value or 0)
        prob = float(d.ml_win_probability or 0) / 100.0
        expected = round(value * prob, 2)
        if month not in buckets:
            buckets[month] = {"month": month, "expected_revenue": 0.0, "deal_count": 0, "total_value": 0.0}
        buckets[month]["expected_revenue"] = round(buckets[month]["expected_revenue"] + expected, 2)
        buckets[month]["deal_count"] += 1
        buckets[month]["total_value"] = round(buckets[month]["total_value"] + value, 2)

    return sorted(buckets.values(), key=lambda b: b["month"])


_OPEN_STAGE_ORDER = ["discovery", "qualified", "proposal", "negotiation"]
_OPEN_STAGES_SET = set(_OPEN_STAGE_ORDER)


@router.get("/workspaces/{workspace_id}/deals/stage-aging")
async def deal_stage_aging(
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """Open deals with days in current stage, sorted by stage order then oldest-first.

    NOTE: registered before /{deal_id} to avoid UUID-parse ambiguity.
    """
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    result = await db.execute(
        select(Deal).where(
            Deal.workspace_id == workspace_id,
            Deal.stage.in_(_OPEN_STAGES_SET),
        )
    )
    deals = result.scalars().all()
    now = datetime.now(timezone.utc)

    rows = []
    for d in deals:
        ref = d.stage_changed_at or d.created_at
        if ref is None:
            days = 0
        else:
            ref = ref if ref.tzinfo else ref.replace(tzinfo=timezone.utc)
            days = max(0, int((now - ref).total_seconds() / 86400))
        rows.append({
            "id": str(d.id),
            "title": d.title,
            "company": d.company,
            "stage": d.stage or "discovery",
            "value": float(d.value or 0),
            "days_in_stage": days,
        })

    stage_index = {s: i for i, s in enumerate(_OPEN_STAGE_ORDER)}
    rows.sort(key=lambda r: (stage_index.get(r["stage"], 99), -r["days_in_stage"]))
    return rows


@router.get("/workspaces/{workspace_id}/deals/win-probability-by-stage")
async def deal_win_probability_by_stage(
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """Average win probability per open stage.

    NOTE: registered before /{deal_id} to avoid UUID-parse ambiguity.
    """
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    result = await db.execute(
        select(Deal).where(
            Deal.workspace_id == workspace_id,
            Deal.stage.in_(_OPEN_STAGES_SET),
        )
    )
    deals = result.scalars().all()

    buckets: dict[str, dict] = {s: {"stage": s, "probabilities": [], "total_value": 0.0} for s in _OPEN_STAGE_ORDER}
    for d in deals:
        stage = d.stage or "discovery"
        if stage not in buckets:
            continue
        buckets[stage]["probabilities"].append(d.ml_win_probability or 0)
        buckets[stage]["total_value"] += float(d.value or 0)

    out = []
    for s in _OPEN_STAGE_ORDER:
        probs = buckets[s]["probabilities"]
        out.append({
            "stage": s,
            "avg_probability": round(sum(probs) / len(probs), 1) if probs else 0.0,
            "deal_count": len(probs),
            "total_value": round(buckets[s]["total_value"], 2),
        })
    return out


@router.get("/workspaces/{workspace_id}/deals/concentration-risk")
async def deal_concentration_risk(
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Pipeline concentration risk: how much of the pipeline is in the top 3 deals.

    NOTE: registered before /{deal_id} to avoid UUID-parse ambiguity.
    """
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    result = await db.execute(
        select(Deal).where(
            Deal.workspace_id == workspace_id,
            Deal.stage.in_(_OPEN_STAGES_SET),
        )
    )
    deals = result.scalars().all()

    sorted_deals = sorted(deals, key=lambda d: float(d.value or 0), reverse=True)
    total_pipeline = sum(float(d.value or 0) for d in sorted_deals)

    top3_value = sum(float(d.value or 0) for d in sorted_deals[:3])
    top3_pct = round((top3_value / total_pipeline * 100), 1) if total_pipeline > 0 else 0.0

    risk_level = "low"
    if top3_pct >= 60:
        risk_level = "high"
    elif top3_pct >= 40:
        risk_level = "medium"

    top_deals = [
        {
            "id": str(d.id),
            "title": d.title,
            "company": d.company,
            "stage": d.stage or "discovery",
            "value": float(d.value or 0),
            "pct_of_pipeline": round(float(d.value or 0) / total_pipeline * 100, 1) if total_pipeline > 0 else 0.0,
        }
        for d in sorted_deals[:5]
    ]

    return {
        "total_pipeline": round(total_pipeline, 2),
        "top_deals": top_deals,
        "top3_pct": top3_pct,
        "risk_level": risk_level,
    }


@router.get("/workspaces/{workspace_id}/deals/close-date-accuracy")
async def deal_close_date_accuracy(
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """For closed_won deals: compare expected vs actual close date.

    NOTE: registered before /{deal_id} to avoid UUID-parse ambiguity.
    """
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    from datetime import date as date_cls

    result = await db.execute(
        select(Deal).where(
            Deal.workspace_id == workspace_id,
            Deal.stage == "closed_won",
        )
    )
    deals = result.scalars().all()

    rows = []
    for d in deals:
        if not d.expected_close or not d.stage_changed_at:
            continue
        try:
            exp = date_cls.fromisoformat(str(d.expected_close)[:10])
        except ValueError:
            continue
        actual_dt = d.stage_changed_at if d.stage_changed_at.tzinfo else d.stage_changed_at.replace(tzinfo=timezone.utc)
        actual_date = actual_dt.date()
        days_delta = (actual_date - exp).days
        if days_delta < 0:
            outcome = "early"
        elif days_delta == 0:
            outcome = "on_time"
        else:
            outcome = "late"
        rows.append({
            "id": str(d.id),
            "title": d.title,
            "company": d.company,
            "value": float(d.value or 0),
            "expected_close": exp.isoformat(),
            "actual_close": actual_date.isoformat(),
            "days_delta": days_delta,
            "outcome": outcome,
        })

    rows.sort(key=lambda r: r["days_delta"], reverse=True)
    return rows


@router.get("/workspaces/{workspace_id}/deals/revenue-cohort")
async def deal_revenue_cohort(
    workspace_id: uuid.UUID,
    cohort_months: int = Query(default=6, ge=1, le=24),
    lookforward_months: int = Query(default=6, ge=1, le=12),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """Revenue cohort analysis: closed-won revenue grouped by contact acquisition cohort.

    Each cohort is defined by the month a contact's FIRST closed-won deal was recorded.
    Subsequent deals from the same contact contribute to that cohort's later months,
    enabling expansion-revenue tracking (LTV curve by acquisition cohort).

    NOTE: registered before /{deal_id} to avoid UUID-parse ambiguity.
    """
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    now = datetime.now(timezone.utc)

    # Build ordered list of cohort month (year, month) tuples — oldest first
    cohort_month_keys: list[tuple[int, int]] = []
    for i in range(cohort_months - 1, -1, -1):
        m = now.month - i
        y = now.year
        while m <= 0:
            m += 12
            y -= 1
        cohort_month_keys.append((y, m))
    cohort_set = set(cohort_month_keys)

    result = await db.execute(
        select(Deal).where(
            Deal.workspace_id == workspace_id,
            Deal.stage == "closed_won",
            Deal.stage_changed_at.isnot(None),
        )
    )
    all_deals = list(result.scalars().all())

    # For each contact, find the month of their FIRST closed-won deal (cohort month)
    contact_cohort: dict[str, tuple[int, int]] = {}
    for deal in all_deals:
        if deal.contact_id is None:
            continue
        cid = str(deal.contact_id)
        dt = deal.stage_changed_at
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        ym = (dt.year, dt.month)
        if cid not in contact_cohort or ym < contact_cohort[cid]:
            contact_cohort[cid] = ym

    # Accumulate revenue and deal counts by (cohort_month, deal_month)
    cohort_revenue: dict[tuple[int, int], dict[tuple[int, int], float]] = {}
    cohort_count: dict[tuple[int, int], dict[tuple[int, int], int]] = {}

    for deal in all_deals:
        dt = deal.stage_changed_at
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        deal_ym = (dt.year, dt.month)

        cohort = contact_cohort.get(str(deal.contact_id)) if deal.contact_id else deal_ym
        if cohort is None:
            cohort = deal_ym
        if cohort not in cohort_set:
            continue

        rev = float(deal.value or 0)
        cohort_revenue.setdefault(cohort, {})
        cohort_count.setdefault(cohort, {})
        cohort_revenue[cohort][deal_ym] = cohort_revenue[cohort].get(deal_ym, 0.0) + rev
        cohort_count[cohort][deal_ym] = cohort_count[cohort].get(deal_ym, 0) + 1

    rows: list[dict] = []
    for cy, cm in cohort_month_keys:
        cohort = (cy, cm)
        initial = cohort_revenue.get(cohort, {}).get(cohort, 0.0)

        months: list[dict] = []
        for offset in range(lookforward_months):
            mm, yy = cm + offset, cy
            while mm > 12:
                mm -= 12
                yy += 1
            month_ym = (yy, mm)
            rev = cohort_revenue.get(cohort, {}).get(month_ym, 0.0)
            cnt = cohort_count.get(cohort, {}).get(month_ym, 0)
            months.append({
                "month_offset": offset,
                "revenue": round(rev, 2),
                "deal_count": cnt,
                "pct_of_initial": round(rev / initial * 100, 1) if initial > 0 else None,
            })

        rows.append({
            "cohort_month": f"{cy}-{cm:02d}",
            "initial_revenue": round(initial, 2),
            "months": months,
        })

    return rows


@router.get("/workspaces/{workspace_id}/deals/velocity-trends")
async def deal_velocity_trends(
    workspace_id: uuid.UUID,
    months: int = Query(default=6, ge=1, le=24),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """Month-over-month average deal cycle time (creation → close) for the last N months.

    Returns one row per calendar month with avg_cycle_days, deal_count, closed_won,
    closed_lost. Only closed deals (closed_won or closed_lost) with a valid
    stage_changed_at are counted.

    NOTE: registered before /{deal_id} to avoid UUID-parse ambiguity.
    """
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    now = datetime.now(timezone.utc)

    # Build ordered list of (year, month) tuples — oldest-first
    month_keys: list[tuple[int, int]] = []
    for i in range(months - 1, -1, -1):
        m = now.month - i
        y = now.year
        while m <= 0:
            m += 12
            y -= 1
        month_keys.append((y, m))
    month_set = set(month_keys)

    result = await db.execute(
        select(Deal).where(
            Deal.workspace_id == workspace_id,
            Deal.stage.in_(["closed_won", "closed_lost"]),
            Deal.stage_changed_at.isnot(None),
        )
    )
    closed_deals = list(result.scalars().all())

    # Accumulate per-month cycle days and won/lost counts
    month_data: dict[tuple[int, int], dict] = {
        ym: {"cycle_days": [], "closed_won": 0, "closed_lost": 0}
        for ym in month_keys
    }

    for deal in closed_deals:
        closed_at = deal.stage_changed_at
        if closed_at.tzinfo is None:
            closed_at = closed_at.replace(tzinfo=timezone.utc)
        ym = (closed_at.year, closed_at.month)
        if ym not in month_set:
            continue

        created = deal.created_at
        if created and created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)

        if created:
            cycle = max(0.0, (closed_at - created).total_seconds() / 86400)
            month_data[ym]["cycle_days"].append(cycle)

        if deal.stage == "closed_won":
            month_data[ym]["closed_won"] += 1
        else:
            month_data[ym]["closed_lost"] += 1

    rows: list[dict] = []
    for ym in month_keys:
        y, m = ym
        data = month_data[ym]
        days_list = data["cycle_days"]
        avg = round(sum(days_list) / len(days_list), 1) if days_list else None
        rows.append({
            "month": f"{y}-{m:02d}",
            "avg_cycle_days": avg,
            "deal_count": len(days_list),
            "closed_won": data["closed_won"],
            "closed_lost": data["closed_lost"],
        })

    return rows


_STAGE_DEFAULT_CYCLE_DAYS: dict[str, int] = {
    "discovery": 90,
    "qualified": 60,
    "proposal": 40,
    "negotiation": 20,
}


@router.get("/workspaces/{workspace_id}/deals/{deal_id}/predicted-close")
async def deal_predicted_close(
    workspace_id: uuid.UUID,
    deal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Predict close date using historical cycle-time distribution from closed deals.

    Algorithm:
    1. Fetch all closed (won/lost) deals in the workspace with both created_at and
       stage_changed_at (which serves as close date).
    2. Compute cycle time = stage_changed_at − created_at in days.
    3. Derive mean (μ) and population std-dev (σ).
    4. predicted_date = deal.created_at + μ days
    5. lower_bound = deal.created_at + max(0, μ − σ)
    6. upper_bound = deal.created_at + (μ + σ)
    7. Confidence: high ≥10 data points, medium ≥3, low ≥1, none → stage defaults.

    NOTE: registered before /{deal_id} to avoid UUID-parse ambiguity.
    """
    import math

    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    deal_result = await db.execute(
        select(Deal).where(Deal.id == deal_id, Deal.workspace_id == workspace_id)
    )
    deal = deal_result.scalar_one_or_none()
    if deal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found")

    # Short-circuit: if already closed, return actual close date
    if deal.stage in ("closed_won", "closed_lost") and deal.stage_changed_at:
        close_dt = deal.stage_changed_at if deal.stage_changed_at.tzinfo else deal.stage_changed_at.replace(tzinfo=timezone.utc)
        return {
            "predicted_date": close_dt.date().isoformat(),
            "lower_bound": close_dt.date().isoformat(),
            "upper_bound": close_dt.date().isoformat(),
            "confidence_level": "actual",
            "confidence_pct": 100,
            "data_points": 0,
            "avg_cycle_days": None,
        }

    hist_result = await db.execute(
        select(Deal).where(
            Deal.workspace_id == workspace_id,
            Deal.stage.in_(["closed_won", "closed_lost"]),
            Deal.stage_changed_at.isnot(None),
            Deal.created_at.isnot(None),
        )
    )
    closed_deals = hist_result.scalars().all()

    cycle_days: list[float] = []
    for d in closed_deals:
        created = d.created_at if d.created_at.tzinfo else d.created_at.replace(tzinfo=timezone.utc)
        closed = d.stage_changed_at if d.stage_changed_at.tzinfo else d.stage_changed_at.replace(tzinfo=timezone.utc)
        days = max(0.0, (closed - created).total_seconds() / 86400)
        if days <= 730:  # exclude >2-year outliers
            cycle_days.append(days)

    n = len(cycle_days)
    now = datetime.now(timezone.utc)
    deal_created = deal.created_at if deal.created_at.tzinfo else deal.created_at.replace(tzinfo=timezone.utc)

    if n == 0:
        default_days = _STAGE_DEFAULT_CYCLE_DAYS.get(deal.stage or "discovery", 60)
        predicted = deal_created + timedelta(days=default_days)
        lower = deal_created + timedelta(days=max(0, default_days - 14))
        upper = deal_created + timedelta(days=default_days + 14)
        confidence_level = "none"
        confidence_pct = 30
    else:
        mean = sum(cycle_days) / n
        variance = sum((x - mean) ** 2 for x in cycle_days) / n
        std = math.sqrt(variance)

        predicted = deal_created + timedelta(days=mean)
        lower = deal_created + timedelta(days=max(0.0, mean - std))
        upper = deal_created + timedelta(days=mean + std)

        if n >= 10:
            confidence_level = "high"
            confidence_pct = 85
        elif n >= 3:
            confidence_level = "medium"
            confidence_pct = 65
        else:
            confidence_level = "low"
            confidence_pct = 40

    # Ensure predicted is always in the future relative to today; shift bounds with it
    if predicted.date() < now.date():
        shift = (now + timedelta(days=7)) - predicted
        predicted = now + timedelta(days=7)
        lower = lower + shift
        upper = upper + shift

    return {
        "predicted_date": predicted.date().isoformat(),
        "lower_bound": lower.date().isoformat(),
        "upper_bound": upper.date().isoformat(),
        "confidence_level": confidence_level,
        "confidence_pct": confidence_pct,
        "data_points": n,
        "avg_cycle_days": round(sum(cycle_days) / n, 1) if n > 0 else None,
    }


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
    for field in ("title", "company", "value", "stage", "ml_win_probability", "expected_close", "notes", "next_action", "next_action_date"):
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


@router.get("/workspaces/{workspace_id}/deals/{deal_id}/timeline")
async def get_deal_timeline(
    workspace_id: uuid.UUID,
    deal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """Return activity events related to this deal, ordered newest-first."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    deal_result = await db.execute(
        select(Deal).where(Deal.id == deal_id, Deal.workspace_id == workspace_id)
    )
    deal = deal_result.scalar_one_or_none()
    if deal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found")

    q = select(ActivityEvent).where(ActivityEvent.workspace_id == workspace_id)
    if deal.title:
        from sqlalchemy import or_
        q = q.where(
            or_(
                ActivityEvent.description.ilike(f"%{deal.title}%"),
                ActivityEvent.type == "deal_moved",
            )
        )
    q = q.order_by(ActivityEvent.created_at.desc()).limit(20)

    result = await db.execute(q)
    events = result.scalars().all()
    return [
        {
            "id": str(e.id),
            "type": e.type or "activity",
            "title": e.agent_name or e.type or "activity",
            "body": e.description or "",
            "ts": e.created_at.isoformat() if e.created_at else None,
            "meta": {"severity": e.severity},
        }
        for e in events
    ]


@router.get(
    "/workspaces/{workspace_id}/deals/{deal_id}/notes",
    response_model=list[DealNoteResponse],
)
async def list_deal_notes(
    workspace_id: uuid.UUID,
    deal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[DealNoteResponse]:
    """Return all notes for a deal, oldest-first (chronological thread)."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    deal_result = await db.execute(
        select(Deal).where(Deal.id == deal_id, Deal.workspace_id == workspace_id)
    )
    deal = deal_result.scalar_one_or_none()
    if deal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found")

    result = await db.execute(
        select(DealNote)
        .where(
            DealNote.workspace_id == workspace_id,
            DealNote.deal_id == deal_id,
        )
        .order_by(DealNote.created_at.asc())
    )
    notes = result.scalars().all()
    return [DealNoteResponse.model_validate(n) for n in notes]


@router.post(
    "/workspaces/{workspace_id}/deals/{deal_id}/notes",
    response_model=DealNoteResponse,
    status_code=201,
)
async def create_deal_note(
    workspace_id: uuid.UUID,
    deal_id: uuid.UUID,
    body: CreateDealNoteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DealNoteResponse:
    """Append a note to a deal. Notes are immutable once created."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    text = (body.body or "").strip()
    if not text:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Note body must not be empty",
        )

    deal_result = await db.execute(
        select(Deal).where(Deal.id == deal_id, Deal.workspace_id == workspace_id)
    )
    deal = deal_result.scalar_one_or_none()
    if deal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found")

    note = DealNote(
        workspace_id=workspace_id,
        deal_id=deal_id,
        body=text,
        author=body.author or getattr(current_user, "email", None),
    )
    db.add(note)
    await db.commit()
    await db.refresh(note)
    return DealNoteResponse.model_validate(note)


class CompetitorUpdateRequest(BaseModel):
    competitors: list[str]


@router.get("/workspaces/{workspace_id}/deals/{deal_id}/competitors")
async def get_deal_competitors(
    workspace_id: uuid.UUID,
    deal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Return the competitor tags for a deal."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    result = await db.execute(
        select(Deal).where(Deal.id == deal_id, Deal.workspace_id == workspace_id)
    )
    deal = result.scalar_one_or_none()
    if deal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found")

    return {"competitors": deal.competitors or []}


@router.put("/workspaces/{workspace_id}/deals/{deal_id}/competitors")
async def update_deal_competitors(
    workspace_id: uuid.UUID,
    deal_id: uuid.UUID,
    body: CompetitorUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Replace the competitor tag list for a deal (full replace, max 20 entries)."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    cleaned = [c.strip() for c in body.competitors if c.strip()][:20]

    result = await db.execute(
        select(Deal).where(Deal.id == deal_id, Deal.workspace_id == workspace_id)
    )
    deal = result.scalar_one_or_none()
    if deal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found")

    deal.competitors = cleaned
    db.add(deal)
    await db.commit()
    await db.refresh(deal)
    return {"competitors": deal.competitors or []}


class MentionEntry(BaseModel):
    name: str
    type: str = "teammate"  # "teammate" | "contact"


class MentionUpdateRequest(BaseModel):
    mentions: list[MentionEntry]


@router.get("/workspaces/{workspace_id}/deals/{deal_id}/mentions")
async def get_deal_mentions(
    workspace_id: uuid.UUID,
    deal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Return the mention list for a deal."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    result = await db.execute(
        select(Deal).where(Deal.id == deal_id, Deal.workspace_id == workspace_id)
    )
    deal = result.scalar_one_or_none()
    if deal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found")

    return {"mentions": deal.mentions or []}


@router.post("/workspaces/{workspace_id}/deals/{deal_id}/mentions")
async def update_deal_mentions(
    workspace_id: uuid.UUID,
    deal_id: uuid.UUID,
    body: MentionUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Replace the mention list for a deal (full replace, max 30 entries)."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    cleaned = [
        {"name": m.name.strip(), "type": m.type}
        for m in body.mentions
        if m.name.strip()
    ][:30]

    result = await db.execute(
        select(Deal).where(Deal.id == deal_id, Deal.workspace_id == workspace_id)
    )
    deal = result.scalar_one_or_none()
    if deal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found")

    deal.mentions = cleaned
    db.add(deal)
    await db.commit()
    await db.refresh(deal)
    return {"mentions": deal.mentions or []}


@router.get("/workspaces/{workspace_id}/deals/{deal_id}/health-score-history")
async def get_deal_health_score_history(
    workspace_id: uuid.UUID,
    deal_id: uuid.UUID,
    limit: int = Query(default=30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """Return the recorded health-score snapshots for a deal, oldest first.

    Snapshots are written by a periodic Celery beat task. Returns an empty
    list when no snapshots have been recorded yet.
    """
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    deal_result = await db.execute(
        select(Deal).where(Deal.id == deal_id, Deal.workspace_id == workspace_id)
    )
    deal = deal_result.scalar_one_or_none()
    if deal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found")

    history_result = await db.execute(
        select(DealHealthHistory)
        .where(
            DealHealthHistory.deal_id == deal_id,
            DealHealthHistory.workspace_id == workspace_id,
        )
        .order_by(DealHealthHistory.recorded_at.asc())
        .limit(limit)
    )
    rows = history_result.scalars().all()

    return [
        {
            "recorded_at": row.recorded_at.isoformat() if row.recorded_at else None,
            "score": row.score,
        }
        for row in rows
    ]


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


_VALID_STAGES = {"discovery", "qualified", "proposal", "negotiation", "closed_won", "closed_lost"}


class BulkDealRequest(BaseModel):
    action: Literal["move_stage", "delete"]
    deal_ids: list[uuid.UUID]
    stage: str | None = None


class BulkDealResponse(BaseModel):
    action: str
    updated: int
    deal_ids: list[str]


@router.post("/workspaces/{workspace_id}/deals/bulk", response_model=BulkDealResponse)
async def bulk_deal_action(
    workspace_id: uuid.UUID,
    body: BulkDealRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BulkDealResponse:
    """Bulk move deals to a new stage or bulk delete deals."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if not body.deal_ids:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="deal_ids must not be empty")

    if len(body.deal_ids) > 100:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Maximum 100 deals per bulk operation")

    if body.action == "move_stage":
        if not body.stage or body.stage not in _VALID_STAGES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"stage must be one of {sorted(_VALID_STAGES)}",
            )

    result = await db.execute(
        select(Deal).where(
            Deal.workspace_id == workspace_id,
            Deal.id.in_(body.deal_ids),
        )
    )
    deals = result.scalars().all()

    if not deals:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No matching deals found")

    updated_ids = [str(d.id) for d in deals]

    if body.action == "move_stage":
        now = datetime.now(timezone.utc)
        for deal in deals:
            if deal.stage != body.stage:
                deal.stage = body.stage  # type: ignore[assignment]
                deal.stage_changed_at = now
                db.add(deal)
        event = ActivityEvent(
            workspace_id=workspace_id,
            type="deal_moved",
            agent_name="System",
            description=f"Bulk moved {len(deals)} deal(s) → {body.stage}",
            severity="info",
        )
        db.add(event)
    else:
        titles = [d.title or str(d.id) for d in deals]
        for deal in deals:
            await db.delete(deal)
        event = ActivityEvent(
            workspace_id=workspace_id,
            type="deal_deleted",
            agent_name="System",
            description=f"Bulk deleted {len(deals)} deal(s): {', '.join(titles[:3])}" + ("…" if len(titles) > 3 else ""),
            severity="warning",
        )
        db.add(event)

    await db.commit()
    return BulkDealResponse(action=body.action, updated=len(deals), deal_ids=updated_ids)


@router.get("/workspaces/{workspace_id}/deals/{deal_id}/probability-trend")
async def deal_probability_trend(
    workspace_id: uuid.UUID,
    deal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """Win probability trend for the last 30 days (synthetic from current score + deal age)."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    result = await db.execute(
        select(Deal).where(Deal.id == deal_id, Deal.workspace_id == workspace_id)
    )
    deal = result.scalar_one_or_none()
    if deal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found")

    now = datetime.now(timezone.utc)
    created = deal.created_at if deal.created_at and deal.created_at.tzinfo else now
    age_days = max(1, (now - created).days)
    points = min(age_days + 1, 30)
    final_prob = int(deal.ml_win_probability)

    trend = []
    for i in range(points):
        frac = i / max(1, points - 1)
        # Deterministic jitter seeded by deal id + index so it's stable across requests
        jitter = (hash(str(deal_id) + str(i)) % 11) - 5
        prob = max(5, min(95, int(max(15, final_prob - 25) + (final_prob - max(15, final_prob - 25)) * frac + jitter)))
        dt = now - timedelta(days=points - 1 - i)
        trend.append({"date": dt.strftime("%b %d"), "probability": prob})

    return trend


@router.get("/workspaces/{workspace_id}/deals/{deal_id}/timeline-summary")
async def deal_timeline_summary(
    workspace_id: uuid.UUID,
    deal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """Weekly activity event counts for the last 12 weeks (oldest-first, for sparkline)."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    deal_result = await db.execute(
        select(Deal).where(Deal.id == deal_id, Deal.workspace_id == workspace_id)
    )
    deal = deal_result.scalar_one_or_none()
    if deal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found")

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(weeks=12)

    q = select(ActivityEvent).where(
        ActivityEvent.workspace_id == workspace_id,
        ActivityEvent.created_at >= cutoff,
    )
    if deal.title:
        from sqlalchemy import or_
        q = q.where(
            or_(
                ActivityEvent.description.ilike(f"%{deal.title}%"),
                ActivityEvent.type == "deal_moved",
            )
        )
    result = await db.execute(q)
    events = result.scalars().all()

    # Build 12 weekly buckets oldest→newest
    buckets: list[dict] = []
    for week_i in range(12):
        week_start = cutoff + timedelta(weeks=week_i)
        week_end = week_start + timedelta(weeks=1)
        label = week_start.strftime("%b %d")
        count = 0
        for e in events:
            if e.created_at is None:
                continue
            ts = e.created_at if e.created_at.tzinfo else e.created_at.replace(tzinfo=timezone.utc)
            if week_start <= ts < week_end:
                count += 1
        buckets.append({"week": label, "events": count})

    return buckets


@router.get("/workspaces/{workspace_id}/deals/{deal_id}/activity-heatmap")
async def deal_activity_heatmap(
    workspace_id: uuid.UUID,
    deal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """Weekly activity_events + messages + deal_notes counts for the last 12 weeks."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    deal_result = await db.execute(
        select(Deal).where(Deal.id == deal_id, Deal.workspace_id == workspace_id)
    )
    deal = deal_result.scalar_one_or_none()
    if deal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found")

    from app.models.message import Message

    today = datetime.now(timezone.utc).date()
    this_monday = today - timedelta(days=today.weekday())
    week_starts = [this_monday - timedelta(weeks=i) for i in range(11, -1, -1)]
    cutoff = datetime.combine(week_starts[0], datetime.min.time()).replace(tzinfo=timezone.utc)

    # Activity events referencing this deal
    event_q = select(ActivityEvent).where(
        ActivityEvent.workspace_id == workspace_id,
        ActivityEvent.created_at >= cutoff,
    )
    if deal.title:
        from sqlalchemy import or_
        event_q = event_q.where(
            or_(
                ActivityEvent.description.ilike(f"%{deal.title}%"),
                ActivityEvent.type == "deal_moved",
            )
        )
    events_result = await db.execute(event_q)
    events = events_result.scalars().all()

    # Messages linked to the deal's contact
    messages: list = []
    if deal.contact_id:
        msg_result = await db.execute(
            select(Message).where(
                Message.workspace_id == workspace_id,
                Message.contact_id == deal.contact_id,
                Message.received_at >= cutoff,
            )
        )
        messages = msg_result.scalars().all()

    # Deal notes
    notes_result = await db.execute(
        select(DealNote).where(
            DealNote.workspace_id == workspace_id,
            DealNote.deal_id == deal_id,
            DealNote.created_at >= cutoff,
        )
    )
    deal_notes = notes_result.scalars().all()

    def _tz(t):
        if t is None:
            return None
        return t if t.tzinfo else t.replace(tzinfo=timezone.utc)

    output = []
    for ws in week_starts:
        we = ws + timedelta(weeks=1)
        ws_dt = datetime.combine(ws, datetime.min.time()).replace(tzinfo=timezone.utc)
        we_dt = datetime.combine(we, datetime.min.time()).replace(tzinfo=timezone.utc)

        evts = sum(1 for e in events if (t := _tz(e.created_at)) and ws_dt <= t < we_dt)
        msgs = sum(1 for m in messages if (t := _tz(m.received_at)) and ws_dt <= t < we_dt)
        nts = sum(1 for n in deal_notes if (t := _tz(n.created_at)) and ws_dt <= t < we_dt)
        output.append({
            "week_start": ws.isoformat(),
            "events": evts,
            "messages": msgs,
            "notes": nts,
            "total": evts + msgs + nts,
        })

    return output


_STAGE_ORDER = ["discovery", "qualified", "proposal", "negotiation", "closed_won", "closed_lost"]
_STAGE_LABELS = {
    "discovery": "Discovery", "qualified": "Qualified", "proposal": "Proposal",
    "negotiation": "Negotiation", "closed_won": "Closed Won", "closed_lost": "Closed Lost",
}
_VALID_STAGE_NAMES = set(_STAGE_ORDER)
_STAGE_RE = re.compile(r"→\s*([a-z_]+)")


@router.get("/workspaces/{workspace_id}/deals/{deal_id}/stage-history")
async def deal_stage_history(
    workspace_id: uuid.UUID,
    deal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """Stage progression history — each stage with entry date and days spent."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    deal_result = await db.execute(
        select(Deal).where(Deal.id == deal_id, Deal.workspace_id == workspace_id)
    )
    deal = deal_result.scalar_one_or_none()
    if deal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found")

    now = datetime.now(timezone.utc)

    # Query deal_moved events for this deal (oldest-first) to reconstruct stage transitions
    events_q = select(ActivityEvent).where(
        ActivityEvent.workspace_id == workspace_id,
        ActivityEvent.type == "deal_moved",
    )
    if deal.title:
        events_q = events_q.where(ActivityEvent.description.ilike(f"%{deal.title}%"))
    events_q = events_q.order_by(ActivityEvent.created_at.asc())
    events_result = await db.execute(events_q)
    events = events_result.scalars().all()

    def _tz(t: datetime | None) -> datetime:
        if t is None:
            return now
        return t if t.tzinfo else t.replace(tzinfo=timezone.utc)

    # Parse destination stage from each event description (e.g., "Deal 'X' → proposal")
    transitions: list[tuple[str, datetime]] = []
    for evt in events:
        m = _STAGE_RE.search(evt.description or "")
        if m and m.group(1) in _VALID_STAGE_NAMES:
            ts = _tz(evt.created_at)
            transitions.append((m.group(1), ts))

    deal_created = _tz(deal.created_at)
    current_stage = deal.stage or "discovery"

    # No transitions recorded — return single entry for current stage
    if not transitions:
        entered = _tz(deal.stage_changed_at or deal.created_at)
        return [{
            "stage": current_stage,
            "label": _STAGE_LABELS.get(current_stage, current_stage),
            "entered_at": entered.isoformat(),
            "days_in_stage": max(0, (now - entered).days),
            "is_current": True,
        }]

    history: list[dict] = []

    # Prepend stage before first known transition (inferred from stage order)
    first_stage, first_ts = transitions[0]
    idx = _STAGE_ORDER.index(first_stage) if first_stage in _STAGE_ORDER else 0
    if idx > 0:
        initial_stage = _STAGE_ORDER[idx - 1]
        history.append({
            "stage": initial_stage,
            "label": _STAGE_LABELS.get(initial_stage, initial_stage),
            "entered_at": deal_created.isoformat(),
            "days_in_stage": max(0, int((first_ts - deal_created).total_seconds() / 86400)),
            "is_current": False,
        })

    for i, (stage, ts) in enumerate(transitions):
        is_last = i == len(transitions) - 1
        end_ts = transitions[i + 1][1] if not is_last else now
        history.append({
            "stage": stage,
            "label": _STAGE_LABELS.get(stage, stage),
            "entered_at": ts.isoformat(),
            "days_in_stage": max(0, int((end_ts - ts).total_seconds() / 86400)),
            "is_current": is_last,
        })

    return history


@router.get("/workspaces/{workspace_id}/deals/{deal_id}/response-lag")
async def deal_response_lag_heatmap(
    workspace_id: uuid.UUID,
    deal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """7×24 avg-response-lag heatmap for messages linked to the deal's contact."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    deal_result = await db.execute(
        select(Deal).where(Deal.id == deal_id, Deal.workspace_id == workspace_id)
    )
    deal = deal_result.scalar_one_or_none()
    if deal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found")

    if deal.contact_id is None:
        return {"cells": [], "max_lag_hours": 0.0}

    msgs_result = await db.execute(
        select(Message)
        .where(
            Message.workspace_id == workspace_id,
            Message.contact_id == deal.contact_id,
        )
        .order_by(Message.received_at.asc())
    )
    msgs = msgs_result.scalars().all()

    if len(msgs) < 2:
        return {"cells": [], "max_lag_hours": 0.0}

    def _tz(t: datetime | None) -> datetime | None:
        if t is None:
            return None
        return t if t.tzinfo else t.replace(tzinfo=timezone.utc)

    from collections import defaultdict
    bucket: dict[tuple[int, int], list[float]] = defaultdict(list)

    for i in range(len(msgs) - 1):
        t0 = _tz(msgs[i].received_at)
        t1 = _tz(msgs[i + 1].received_at)
        if t0 is None or t1 is None:
            continue
        lag_hours = (t1 - t0).total_seconds() / 3600
        # Skip negative or outlier lags (> 1 week)
        if lag_hours <= 0 or lag_hours > 168:
            continue
        bucket[(t0.weekday(), t0.hour)].append(lag_hours)

    if not bucket:
        return {"cells": [], "max_lag_hours": 0.0}

    cells = [
        {
            "dow": dow,
            "hour": hour,
            "avg_lag_hours": round(sum(lags) / len(lags), 2),
            "count": len(lags),
        }
        for (dow, hour), lags in bucket.items()
    ]
    max_lag = max(c["avg_lag_hours"] for c in cells)
    return {"cells": cells, "max_lag_hours": round(max_lag, 2)}


@router.get("/workspaces/{workspace_id}/deals/{deal_id}/engagement-score")
async def deal_engagement_score(
    workspace_id: uuid.UUID,
    deal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Compute a 0–100 engagement score from contact messages, deal notes, and task completion (last 90 days)."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    deal_result = await db.execute(
        select(Deal).where(Deal.id == deal_id, Deal.workspace_id == workspace_id)
    )
    deal = deal_result.scalar_one_or_none()
    if deal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found")

    from app.models.task import Task

    cutoff = datetime.now(timezone.utc) - timedelta(days=90)

    # Messages from the linked contact
    message_count = 0
    if deal.contact_id:
        msg_result = await db.execute(
            select(Message).where(
                Message.workspace_id == workspace_id,
                Message.contact_id == deal.contact_id,
                Message.received_at >= cutoff,
            )
        )
        message_count = len(msg_result.scalars().all())

    # Notes on this deal
    note_result = await db.execute(
        select(DealNote).where(
            DealNote.workspace_id == workspace_id,
            DealNote.deal_id == deal_id,
            DealNote.created_at >= cutoff,
        )
    )
    note_count = len(note_result.scalars().all())

    # Tasks linked to the deal's contact
    tasks_total = 0
    tasks_done = 0
    if deal.contact_id:
        task_result = await db.execute(
            select(Task).where(
                Task.workspace_id == workspace_id,
                Task.contact_id == deal.contact_id,
                Task.created_at >= cutoff,
            )
        )
        tasks = task_result.scalars().all()
        tasks_total = len(tasks)
        tasks_done = sum(1 for t in tasks if t.status == "done")

    messages_score = min(40, message_count * 8)
    notes_score = min(30, note_count * 10)
    tasks_score = round(30 * tasks_done / tasks_total) if tasks_total > 0 else 0
    total_score = messages_score + notes_score + tasks_score

    return {
        "score": total_score,
        "message_count": message_count,
        "note_count": note_count,
        "tasks_total": tasks_total,
        "tasks_done": tasks_done,
        "components": {
            "messages": messages_score,
            "notes": notes_score,
            "tasks": tasks_score,
        },
    }
