import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.dependencies import get_current_user
from app.limiter import limiter
from app.models.user import User
from app.models.message import Message
from app.models.clarity_score import ClarityScore
from app.models.connector import Connector

router = APIRouter()


class ClarityScoreNested(BaseModel):
    score: int | None
    rationale: str | None

    model_config = {"from_attributes": True}


class TaskNested(BaseModel):
    id: uuid.UUID
    title: str
    status: str

    model_config = {"from_attributes": True}


class MessageResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    external_id: str
    subject: str | None
    body_plain: str | None = None
    sender_email: str | None
    received_at: datetime | None
    contact_id: uuid.UUID | None
    processed: bool
    relevant: bool | None = None
    clarity_score: ClarityScoreNested | None = None
    tasks: list[TaskNested] = []

    model_config = {"from_attributes": True}


class ScoreClarityResponse(BaseModel):
    message_id: uuid.UUID
    score: int
    rationale: str
    model_used: str

    model_config = {"from_attributes": True}


@router.post(
    "/workspaces/{workspace_id}/messages/{message_id}/score-clarity",
    response_model=ScoreClarityResponse,
    status_code=status.HTTP_200_OK,
)
@limiter.limit("10/minute")
async def score_message_clarity(
    request: Request,
    workspace_id: uuid.UUID,
    message_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ScoreClarityResponse:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    result = await db.execute(
        select(Message)
        .where(Message.id == message_id, Message.workspace_id == workspace_id)
        .options(selectinload(Message.clarity_score))
    )
    message = result.scalar_one_or_none()
    if message is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")

    from app.services.clarity import score_clarity
    scored = await score_clarity(message.body_plain)

    existing = message.clarity_score
    if existing is not None:
        existing.score = scored["score"]
        existing.rationale = scored["rationale"]
        cs = existing
    else:
        cs = ClarityScore(
            workspace_id=workspace_id,
            message_id=message_id,
            score=scored["score"],
            rationale=scored["rationale"],
            model_used="claude-sonnet-4-6",
        )
        db.add(cs)

    await db.commit()
    await db.refresh(cs)

    return ScoreClarityResponse(
        message_id=message_id,
        score=cs.score,
        rationale=cs.rationale or "",
        model_used=cs.model_used,
    )


@router.get("/workspaces/{workspace_id}/messages", response_model=list[MessageResponse])
async def list_messages(
    workspace_id: uuid.UUID,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[MessageResponse]:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    result = await db.execute(
        select(Message)
        .where(Message.workspace_id == workspace_id)
        .options(
            selectinload(Message.clarity_score),
            selectinload(Message.tasks),
        )
        .order_by(Message.received_at.desc().nulls_last())
        .limit(limit)
        .offset(offset)
    )
    messages = result.scalars().all()
    return [MessageResponse.model_validate(m) for m in messages]


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/messages/volume-trends
# ---------------------------------------------------------------------------


@router.get("/workspaces/{workspace_id}/messages/volume-trends")
async def get_message_volume_trends(
    workspace_id: uuid.UUID,
    weeks: int = Query(default=12, ge=4, le=52),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """Return weekly message counts broken down by connector source (gmail/slack/teams/unknown).

    Each row covers one Mon–Sun calendar week for the last `weeks` weeks.
    """
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    now = datetime.now(tz=timezone.utc)
    # Start of the oldest week (Monday at 00:00 UTC)
    today_mon = now - timedelta(days=now.weekday())
    cutoff = (today_mon - timedelta(weeks=weeks - 1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    # Fetch messages with their connector (for service field)
    msgs_result = await db.execute(
        select(Message, Connector.service)
        .outerjoin(Connector, Connector.id == Message.connector_id)
        .where(
            Message.workspace_id == workspace_id,
            Message.received_at >= cutoff,
        )
        .order_by(Message.received_at.asc())
    )
    rows = msgs_result.all()

    # Build {week_start → {service → count}}
    SERVICES = ("gmail", "slack", "teams")
    week_data: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for msg, service in rows:
        if msg.received_at is None:
            continue
        ts = msg.received_at if msg.received_at.tzinfo else msg.received_at.replace(tzinfo=timezone.utc)
        week_mon = ts - timedelta(days=ts.weekday())
        week_key = week_mon.strftime("%Y-%m-%d")
        bucket = service if service in SERVICES else "unknown"
        week_data[week_key][bucket] += 1

    # Emit all weeks in the window (even zero-count weeks)
    result = []
    for i in range(weeks):
        d = cutoff + timedelta(weeks=i)
        wk = d.strftime("%Y-%m-%d")
        counts = week_data.get(wk, {})
        row: dict = {"week_start": wk}
        total = 0
        for svc in SERVICES:
            v = counts.get(svc, 0)
            row[svc] = v
            total += v
        unknown = counts.get("unknown", 0)
        row["unknown"] = unknown
        total += unknown
        row["total"] = total
        result.append(row)

    return result


class ReprocessResponse(BaseModel):
    job_id: str


@router.post(
    "/workspaces/{workspace_id}/messages/reprocess",
    response_model=ReprocessResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def reprocess_messages(
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
) -> ReprocessResponse:
    """Enqueue a non-destructive re-enrichment + relevance-flagging pass over all
    existing messages in the workspace. Returns the Celery task id as job_id so the
    frontend can poll /jobs/{id}."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    from app.workers.ingest import reprocess_workspace_messages
    from app.routers.agents import _mark_job_dispatched

    task = reprocess_workspace_messages.delay(str(workspace_id))
    _mark_job_dispatched(task.id, str(workspace_id))
    return ReprocessResponse(job_id=task.id)
