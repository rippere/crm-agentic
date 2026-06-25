import uuid
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select, func, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.commitment import Commitment

router = APIRouter()


class CommitmentResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    external_id: str | None = None
    title: str
    kind: str
    source: str | None
    declared_at: str
    due_date: date | None
    status: str
    evidence: str | None
    scored_at: str | None
    created_at: str | None = None
    updated_at: str | None = None

    model_config = {"from_attributes": True}


class CommitmentUpsert(BaseModel):
    title: str
    kind: str = "auto"
    source: str | None = None
    declared_at: datetime
    due_date: date | None = None
    status: str | None = None
    evidence: str | None = None
    scored_at: datetime | None = None


class CommitmentUpdate(BaseModel):
    title: str | None = None
    status: str | None = None
    evidence: str | None = None
    scored_at: datetime | None = None
    due_date: date | None = None


class CommitmentUpsertResponse(BaseModel):
    commitment: CommitmentResponse
    created: bool


class CommitmentWeekStat(BaseModel):
    week_start: date
    declared: int
    kept: int
    broken: int
    dropped: int
    open: int
    kept_rate: float | None


def _to_response(c: Commitment) -> CommitmentResponse:
    return CommitmentResponse(
        id=c.id,
        workspace_id=c.workspace_id,
        external_id=c.external_id,
        title=c.title,
        kind=c.kind,
        source=c.source,
        declared_at=c.declared_at.isoformat() if c.declared_at else None,
        due_date=c.due_date,
        status=c.status,
        evidence=c.evidence,
        scored_at=c.scored_at.isoformat() if c.scored_at else None,
        created_at=c.created_at.isoformat() if c.created_at else None,
        updated_at=c.updated_at.isoformat() if c.updated_at else None,
    )


@router.put(
    "/workspaces/{workspace_id}/commitments/by-external/{external_id}",
    response_model=CommitmentUpsertResponse,
)
async def upsert_commitment_by_external(
    workspace_id: uuid.UUID,
    external_id: str,
    body: CommitmentUpsert,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CommitmentUpsertResponse:
    """Idempotent create-or-update keyed on (workspace_id, external_id).

    Entry point for the session-log -> NovaCRM commitment harvest: re-running the
    harvest over the same session record updates the existing commitment instead of
    creating a duplicate.

    Never-reopen rule: once a commitment has been scored (status != 'open'), a later
    re-harvest of the same source — which always re-declares it as 'open' — must NOT
    reset it. So when the existing row is already kept/broken/dropped and the incoming
    status is 'open' or omitted, we preserve the existing status/evidence/scored_at.
    An explicit non-'open' incoming status (e.g. a scorer marking it kept) still applies.
    """
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    result = await db.execute(
        select(Commitment).where(
            Commitment.workspace_id == workspace_id, Commitment.external_id == external_id
        )
    )
    commitment = result.scalar_one_or_none()
    created = commitment is None
    if commitment is None:
        commitment = Commitment(
            workspace_id=workspace_id,
            external_id=external_id,
            title=body.title,
            kind=body.kind,
            source=body.source,
            declared_at=body.declared_at,
            due_date=body.due_date,
            status=body.status or "open",
            evidence=body.evidence,
            scored_at=body.scored_at,
        )
        db.add(commitment)
    else:
        commitment.title = body.title  # type: ignore[assignment]
        commitment.kind = body.kind  # type: ignore[assignment]
        commitment.source = body.source  # type: ignore[assignment]
        commitment.declared_at = body.declared_at  # type: ignore[assignment]
        commitment.due_date = body.due_date  # type: ignore[assignment]
        # Preserve an already-scored commitment against a re-harvest that re-opens it.
        incoming_reopens = body.status is None or body.status == "open"
        if commitment.status != "open" and incoming_reopens:
            pass  # keep existing status/evidence/scored_at untouched
        else:
            commitment.status = body.status or "open"  # type: ignore[assignment]
            commitment.evidence = body.evidence  # type: ignore[assignment]
            commitment.scored_at = body.scored_at  # type: ignore[assignment]

    await db.commit()
    await db.refresh(commitment)
    return CommitmentUpsertResponse(commitment=_to_response(commitment), created=created)


@router.get("/workspaces/{workspace_id}/commitments", response_model=list[CommitmentResponse])
async def list_commitments(
    workspace_id: uuid.UUID,
    status_: str | None = Query(default=None, alias="status"),
    kind: str | None = Query(default=None),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[CommitmentResponse]:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    q = select(Commitment).where(Commitment.workspace_id == workspace_id)
    if status_ is not None:
        q = q.where(Commitment.status == status_)
    if kind is not None:
        q = q.where(Commitment.kind == kind)
    if since is not None:
        q = q.where(Commitment.declared_at >= since)
    if until is not None:
        q = q.where(Commitment.declared_at <= until)
    result = await db.execute(q.order_by(Commitment.declared_at.desc()))
    return [_to_response(c) for c in result.scalars().all()]


@router.get("/workspaces/{workspace_id}/commitments/stats", response_model=list[CommitmentWeekStat])
async def commitment_stats(
    workspace_id: uuid.UUID,
    weeks: int = Query(default=12, ge=1, le=104),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[CommitmentWeekStat]:
    """Per ISO-week buckets of declared_at over the last N weeks.

    kept_rate = kept / (kept + broken), null when the denominator is 0 (no scored
    outcomes that week yet). Bucketing is done in SQL via date_trunc('week', ...),
    which Postgres anchors to Monday (ISO week start); the row shaping + rate math
    happen here.
    """
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    # Anchor the window to the Monday of the ISO week `weeks - 1` weeks ago so the
    # current (partial) week is the last bucket.
    today = datetime.now(timezone.utc).date()
    this_monday = today - timedelta(days=today.weekday())
    window_start = this_monday - timedelta(weeks=weeks - 1)

    week = func.date_trunc("week", Commitment.declared_at).label("week")
    result = await db.execute(
        select(
            week,
            func.count().label("declared"),
            func.count(case((Commitment.status == "kept", 1))).label("kept"),
            func.count(case((Commitment.status == "broken", 1))).label("broken"),
            func.count(case((Commitment.status == "dropped", 1))).label("dropped"),
            func.count(case((Commitment.status == "open", 1))).label("open"),
        )
        .where(
            Commitment.workspace_id == workspace_id,
            Commitment.declared_at >= datetime(window_start.year, window_start.month, window_start.day, tzinfo=timezone.utc),
        )
        .group_by(week)
    )

    by_week: dict[date, CommitmentWeekStat] = {}
    for row in result.all():
        bucket = row.week.date() if isinstance(row.week, datetime) else row.week
        denom = row.kept + row.broken
        by_week[bucket] = CommitmentWeekStat(
            week_start=bucket,
            declared=row.declared,
            kept=row.kept,
            broken=row.broken,
            dropped=row.dropped,
            open=row.open,
            kept_rate=(row.kept / denom) if denom else None,
        )

    # Emit a contiguous run of weeks (oldest -> newest), zero-filling empty buckets so
    # the consumer gets one row per week regardless of activity.
    out: list[CommitmentWeekStat] = []
    for i in range(weeks):
        wk = window_start + timedelta(weeks=i)
        out.append(
            by_week.get(
                wk,
                CommitmentWeekStat(
                    week_start=wk, declared=0, kept=0, broken=0, dropped=0, open=0, kept_rate=None
                ),
            )
        )
    return out


@router.patch("/workspaces/{workspace_id}/commitments/{commitment_id}", response_model=CommitmentResponse)
async def update_commitment(
    workspace_id: uuid.UUID,
    commitment_id: uuid.UUID,
    body: CommitmentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CommitmentResponse:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    result = await db.execute(
        select(Commitment).where(
            Commitment.id == commitment_id, Commitment.workspace_id == workspace_id
        )
    )
    commitment = result.scalar_one_or_none()
    if commitment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Commitment not found")

    if body.title is not None:
        commitment.title = body.title  # type: ignore[assignment]
    if body.status is not None:
        commitment.status = body.status  # type: ignore[assignment]
    if body.evidence is not None:
        commitment.evidence = body.evidence  # type: ignore[assignment]
    if body.scored_at is not None:
        commitment.scored_at = body.scored_at  # type: ignore[assignment]
    if body.due_date is not None:
        commitment.due_date = body.due_date  # type: ignore[assignment]

    await db.commit()
    await db.refresh(commitment)
    return _to_response(commitment)
