import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.kpi_snapshot import KpiSnapshot

router = APIRouter()


class KpiSnapshotResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    date: date
    domain: str
    metric: str
    value: float
    meta: dict
    updated_at: str | None = None

    model_config = {"from_attributes": True}


class KpiSnapshotIn(BaseModel):
    domain: str
    metric: str
    value: float
    meta: dict | None = None  # tolerate explicit null from collectors


class KpiSnapshotBatch(BaseModel):
    snapshots: list[KpiSnapshotIn]


def _to_response(s: KpiSnapshot) -> KpiSnapshotResponse:
    return KpiSnapshotResponse(
        id=s.id,
        workspace_id=s.workspace_id,
        date=s.date,
        domain=s.domain,
        metric=s.metric,
        value=float(s.value),
        meta=s.meta or {},
        updated_at=s.updated_at.isoformat() if s.updated_at else None,
    )


@router.put("/workspaces/{workspace_id}/kpi/{date}", response_model=dict)
async def upsert_kpi_snapshots(
    workspace_id: uuid.UUID,
    date: date,
    body: KpiSnapshotBatch,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Idempotent batch upsert of life-KPI snapshots keyed on (workspace_id, date, metric).

    Entry point for the daily collector: re-pushing the same day's metrics updates
    value/meta in place instead of creating duplicate rows, so the collector can run
    repeatedly (or backfill) without skewing the ledger.
    """
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    upserted = 0
    for snap in body.snapshots:
        result = await db.execute(
            select(KpiSnapshot).where(
                KpiSnapshot.workspace_id == workspace_id,
                KpiSnapshot.date == date,
                KpiSnapshot.metric == snap.metric,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            row = KpiSnapshot(
                workspace_id=workspace_id,
                date=date,
                domain=snap.domain,
                metric=snap.metric,
                value=snap.value,
                meta=snap.meta or {},
            )
            db.add(row)
        else:
            row.domain = snap.domain  # type: ignore[assignment]
            row.value = snap.value  # type: ignore[assignment]
            row.meta = snap.meta or {}  # type: ignore[assignment]
        upserted += 1

    await db.commit()
    return {"upserted": upserted, "date": date}


@router.get("/workspaces/{workspace_id}/kpi", response_model=list[KpiSnapshotResponse])
async def list_kpi_snapshots(
    workspace_id: uuid.UUID,
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    domain: str | None = Query(default=None),
    metric: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[KpiSnapshotResponse]:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    q = select(KpiSnapshot).where(KpiSnapshot.workspace_id == workspace_id)
    if from_date is not None:
        q = q.where(KpiSnapshot.date >= from_date)
    if to_date is not None:
        q = q.where(KpiSnapshot.date <= to_date)
    if domain is not None:
        q = q.where(KpiSnapshot.domain == domain)
    if metric is not None:
        q = q.where(KpiSnapshot.metric == metric)
    result = await db.execute(q.order_by(KpiSnapshot.date.asc(), KpiSnapshot.metric.asc()))
    return [_to_response(s) for s in result.scalars().all()]
