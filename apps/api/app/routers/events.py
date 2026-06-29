"""
Server-Sent Events endpoint for real-time activity feed.
Streams new activity_events rows as they arrive, polling every 3 seconds.
"""
import asyncio
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.activity_event import ActivityEvent

logger = logging.getLogger(__name__)

router = APIRouter()

# Tear the SSE stream down after this many *consecutive* poll failures so a wedged
# DB session (e.g. asyncpg connection killed by PgBouncer) can't loop forever
# emitting heartbeats while every query silently fails.
_MAX_CONSECUTIVE_ERRORS = 5


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
    event_type: str | None = Query(default=None),
    agent_id: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ActivityEventResponse]:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    q = (
        select(ActivityEvent)
        .where(ActivityEvent.workspace_id == workspace_id)
    )
    if event_type:
        q = q.where(ActivityEvent.type == event_type)
    if agent_id:
        q = q.where(ActivityEvent.meta.like(f"%{agent_id}%"))

    q = q.order_by(desc(ActivityEvent.created_at)).offset(offset).limit(limit)
    result = await db.execute(q)
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


_TREND_CATEGORIES: dict[str, list[str]] = {
    "deals": ["deal_moved", "deal_created", "deal_deleted"],
    "contacts": ["contact_created", "contact_merged"],
    "agents": ["agent_run", "agent_success", "agent_failure"],
    "messages": ["message_received", "note_created"],
}
_TYPE_TO_CATEGORY: dict[str, str] = {
    t: cat for cat, types in _TREND_CATEGORIES.items() for t in types
}


@router.get("/workspaces/{workspace_id}/activity/trends")
async def activity_trends(
    workspace_id: uuid.UUID,
    weeks: int = Query(default=12, ge=1, le=52),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """Weekly activity-event counts for the last N weeks, grouped into categories.

    NOTE: registered before /activity (path-param route) to avoid ambiguity.
    """
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    from datetime import date as date_cls
    today = datetime.now(timezone.utc).date()
    this_monday = today - timedelta(days=today.weekday())
    week_starts = [this_monday - timedelta(weeks=i) for i in range(weeks - 1, -1, -1)]
    cutoff = datetime.combine(week_starts[0], datetime.min.time()).replace(tzinfo=timezone.utc)

    result = await db.execute(
        select(ActivityEvent).where(
            ActivityEvent.workspace_id == workspace_id,
            ActivityEvent.created_at >= cutoff,
        )
    )
    events = result.scalars().all()

    categories = list(_TREND_CATEGORIES.keys())
    output = []
    for ws in week_starts:
        we = ws + timedelta(weeks=1)
        ws_dt = datetime.combine(ws, datetime.min.time()).replace(tzinfo=timezone.utc)
        we_dt = datetime.combine(we, datetime.min.time()).replace(tzinfo=timezone.utc)
        counts: dict[str, int] = {c: 0 for c in categories}
        total = 0
        for e in events:
            if e.created_at is None:
                continue
            ts = e.created_at if e.created_at.tzinfo else e.created_at.replace(tzinfo=timezone.utc)
            if not (ws_dt <= ts < we_dt):
                continue
            cat = _TYPE_TO_CATEGORY.get(e.type or "", "other")
            if cat in counts:
                counts[cat] += 1
            total += 1
        output.append({"week_start": ws.isoformat(), "total": total, **counts})

    return output


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
        consecutive_errors = 0
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
                consecutive_errors = 0
            except Exception as exc:  # noqa: BLE001
                # Roll back so a failed statement doesn't leave the session in a
                # broken "transaction aborted" state where every subsequent poll
                # also fails. Log it (was previously swallowed silently), and bail
                # out after N consecutive failures instead of heartbeating forever.
                consecutive_errors += 1
                try:
                    await db.rollback()
                except Exception:  # noqa: BLE001
                    pass
                logger.warning(
                    "event=sse_poll_failed workspace=%s consecutive_errors=%d error=%s",
                    workspace_id, consecutive_errors, exc,
                )
                if consecutive_errors >= _MAX_CONSECUTIVE_ERRORS:
                    logger.error(
                        "event=sse_stream_aborted workspace=%s consecutive_errors=%d "
                        "detail=closing_stream_after_repeated_poll_failures",
                        workspace_id, consecutive_errors,
                    )
                    yield ": stream-error\n\n"
                    break
                yield ": heartbeat\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
