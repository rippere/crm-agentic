import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.message import Message
from app.models.clarity_score import ClarityScore

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
async def score_message_clarity(
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

    task = reprocess_workspace_messages.delay(str(workspace_id))
    return ReprocessResponse(job_id=task.id)
