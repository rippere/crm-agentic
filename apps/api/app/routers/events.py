"""
Server-Sent Events endpoint for real-time activity feed.
Streams new activity_events rows as they arrive, polling every 3 seconds.
"""
import asyncio
import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.activity_event import ActivityEvent

router = APIRouter()


class ActivityEventResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    type: str | None
    agent_name: str | None
    description: str | None
    meta: str | None
    severity: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ActivityEventCreate(BaseModel):
    type: str
    agent_name: str
    description: str
    meta: str = ""
    severity: str = "info"


@router.get("/workspaces/{workspace_id}/activity", response_model=list[ActivityEventResponse])
async def list_activity(
    workspace_id: uuid.UUID,
    limit: int = 50,
    offset: int = 0,
    type: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ActivityEventResponse]:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    limit = max(1, min(limit, 200))
    offset = max(0, offset)

    query = select(ActivityEvent).where(ActivityEvent.workspace_id == workspace_id)
    if type:
        query = query.where(ActivityEvent.type == type)

    result = await db.execute(
        query.order_by(desc(ActivityEvent.created_at)).limit(limit).offset(offset)
    )
    return [ActivityEventResponse.model_validate(e) for e in result.scalars().all()]


@router.post("/workspaces/{workspace_id}/activity", response_model=ActivityEventResponse, status_code=status.HTTP_201_CREATED)
async def create_activity(
    workspace_id: uuid.UUID,
    body: ActivityEventCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ActivityEventResponse:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    event = ActivityEvent(
        workspace_id=workspace_id,
        type=body.type,
        agent_name=body.agent_name,
        description=body.description,
        meta=body.meta,
        severity=body.severity,
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return ActivityEventResponse.model_validate(event)


def _serialize(event: ActivityEvent) -> str:
    payload = {
        "id": str(event.id),
        "type": event.type,
        "agent_name": event.agent_name,
        "description": event.description,
        "meta": event.meta,
        "severity": event.severity,
        "created_at": event.created_at.isoformat() if event.created_at else None,
    }
    return f"data: {json.dumps(payload)}\n\n"


@router.get("/workspaces/{workspace_id}/events")
async def stream_events(
    workspace_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.workspace_id != workspace_id:
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    # Seed cursor: last seen event id at connection time
    result = await db.execute(
        select(ActivityEvent)
        .where(ActivityEvent.workspace_id == workspace_id)
        .order_by(desc(ActivityEvent.created_at))
        .limit(1)
    )
    last = result.scalar_one_or_none()
    last_ts = last.created_at if last else datetime.fromtimestamp(0, tz=timezone.utc)

    async def generate():
        nonlocal last_ts
        yield ": connected\n\n"
        while not await request.is_disconnected():
            await asyncio.sleep(3)
            try:
                res = await db.execute(
                    select(ActivityEvent)
                    .where(
                        ActivityEvent.workspace_id == workspace_id,
                        ActivityEvent.created_at > last_ts,
                    )
                    .order_by(ActivityEvent.created_at)
                    .limit(20)
                )
                new_events = res.scalars().all()
                for ev in new_events:
                    yield _serialize(ev)
                    if ev.created_at > last_ts:
                        last_ts = ev.created_at
            except Exception:
                yield ": heartbeat\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
