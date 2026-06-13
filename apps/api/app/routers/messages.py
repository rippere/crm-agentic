import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.limiter import limiter
from app.models.user import User
from app.models.message import Message
from app.models.clarity_score import ClarityScore
from app.services.llm_budget import check_and_reserve, estimate_reprocess_tokens

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


class ReprocessResponse(BaseModel):
    job_id: str


@router.post(
    "/workspaces/{workspace_id}/messages/reprocess",
    response_model=ReprocessResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
@limiter.limit(settings.REPROCESS_RATE_LIMIT)
async def reprocess_messages(
    request: Request,
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ReprocessResponse:
    """Enqueue a non-destructive re-enrichment + relevance-flagging pass over all
    existing messages in the workspace. Returns the Celery task id as job_id so the
    frontend can poll /jobs/{id}.

    F5 cost/DoS hardening: this endpoint is the heaviest model-call amplifier
    (~4 model calls per message, previously un-rate-limited and unbounded). It is
    now (1) per-principal rate-limited, (2) capped/charged against the workspace's
    LLM token budget *before* enqueue based on the message count, and (3) routed
    to the dedicated low-concurrency `long` Celery queue so it cannot pin the pool
    that serves short enrich/scoring jobs.
    """
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    # Bound the per-call fan-out: count the workspace's messages and reserve the
    # estimated token spend against the per-workspace budget (HTTP 429 if over).
    # The count is also clamped to REPROCESS_MAX_MESSAGES so an enormous mailbox
    # cannot translate into an unbounded single-task fan-out.
    count_result = await db.execute(
        select(func.count()).select_from(Message).where(Message.workspace_id == workspace_id)
    )
    message_count = int(count_result.scalar_one() or 0)
    effective_count = min(message_count, settings.REPROCESS_MAX_MESSAGES)
    estimated_tokens = await estimate_reprocess_tokens(effective_count)
    await check_and_reserve(workspace_id, estimated_tokens)

    from app.workers.ingest import reprocess_workspace_messages
    from app.routers.agents import _mark_job_dispatched

    # Route to the isolated long-jobs queue (see workers/celery_app.py task_routes).
    task = reprocess_workspace_messages.apply_async(args=[str(workspace_id)], queue="long")
    _mark_job_dispatched(task.id, str(workspace_id))
    return ReprocessResponse(job_id=task.id)
