"""Discovery router — the market-discovery surface for the Autonomous Lead Engine.

Increment 1 (Discovery). Follows the shipped house conventions verbatim (see
routers/leads.py, routers/agents.py): a bare module-level ``router = APIRouter()``
with no prefix/tags (tags are attached at registration in ``main.py``); every path
namespaced under ``/workspaces/{workspace_id}/...``; a first-line workspace-auth
403 guard on every handler; every query scoped by ``workspace_id``; inline Pydantic
schemas (``from_attributes``); literal-tuple validation -> 422; ORM-first with a
``supabase_rest.get_row`` fallback before 404; and STATIC sub-paths declared BEFORE
the ``/{run_id}`` param routes so they are not captured by the UUID path param.

The POST route delegates to the ONE dispatch seam
``app/services/discovery.py::dispatch_discovery_run`` (R2) — the same seam the
chatbot ``discover_market`` action calls — which creates the ``discovery_runs`` row
and enqueues ``app.workers.discovery.run_market_discovery``. Progress is polled via
the EXISTING ``GET /jobs/{job_id}`` (agents.py) using the returned ``job_id``; there
is no new poller.

``DiscoveryRunRequest`` / ``DiscoveryRunResponse`` are defined here and imported by
``services/discovery.py`` and the ``actions/discovery.py`` handler (the ONE
definition of each — R2/§2.1.7).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import Float, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.discovery_run import DiscoveryRun
from app.models.lead import Lead
from app.models.user import User
from app.routers.leads import LeadResponse
from app.services.supabase_rest import get_row

router = APIRouter()


# ─── Literal sets — mirror the SQL CHECK constraint + provider abstraction ──────
DISCOVERY_STATUSES = ("queued", "running", "succeeded", "partial", "failed")
PLACES_PROVIDERS = ("google_places", "yelp", "foursquare")


# ─── Schemas ───────────────────────────────────────────────────────────────────
class DiscoveryRunRequest(BaseModel):
    """Request body for POST /discovery/runs (and the chatbot discover action).

    ``provider`` is validated against :data:`PLACES_PROVIDERS` (-> 422) and
    ``rubric`` against ``discovery_rubric.validate_rubric`` (-> 422 on bad
    weights); both validations happen in ``dispatch_discovery_run`` (which raises
    ``ValueError``) and are surfaced as 422 by the POST handler.
    """

    locality: str
    categories: list[str] | None = None
    radius_m: int | None = None
    provider: str | None = None
    rubric: dict | None = None
    max_venues: int = 60


class DiscoveryRunResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    locality: str
    provider: str | None = None
    status: str
    params: dict = {}
    rubric: dict = {}
    stats: dict = {}
    job_id: str | None = None
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


# ─── STATIC sub-paths (declare BEFORE /{run_id}) ───────────────────────────────
@router.post(
    "/workspaces/{workspace_id}/discovery/runs",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=DiscoveryRunResponse,
)
async def create_discovery_run(
    workspace_id: uuid.UUID,
    body: DiscoveryRunRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DiscoveryRunResponse:
    """Create + enqueue a market-discovery run; returns the queued run row (202).

    Delegates to the shared ``dispatch_discovery_run`` seam (R2), which snapshots
    the effective rubric, creates the ``discovery_runs`` row, COMMITs it before
    dispatch (so a fast worker finds the row), and enqueues the Celery task. Poll
    progress via the existing ``GET /jobs/{job_id}`` with the returned ``job_id``.
    """
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if not body.locality or not body.locality.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="locality is required",
        )
    if body.provider is not None and body.provider not in PLACES_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"provider must be one of {list(PLACES_PROVIDERS)}",
        )

    # Lazy import: the dispatch seam is owned by a sibling module. Import inside
    # the handler so this router imports clean before that seam lands, and so a
    # missing seam degrades to a clear 503 rather than an import-time failure.
    try:
        from app.services.discovery import dispatch_discovery_run
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Discovery service is not available.",
        ) from exc

    try:
        run = await dispatch_discovery_run(workspace_id, body, db)
    except ValueError as exc:
        # validate_rubric / provider validation raise ValueError -> 422.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    return DiscoveryRunResponse.model_validate(run)


@router.get(
    "/workspaces/{workspace_id}/discovery/runs",
    response_model=list[DiscoveryRunResponse],
)
async def list_discovery_runs(
    workspace_id: uuid.UUID,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[DiscoveryRunResponse]:
    """List discovery runs for the workspace, newest first (paginated)."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if status_filter is not None and status_filter not in DISCOVERY_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"status must be one of {list(DISCOVERY_STATUSES)}",
        )

    stmt = select(DiscoveryRun).where(DiscoveryRun.workspace_id == workspace_id)
    if status_filter is not None:
        stmt = stmt.where(DiscoveryRun.status == status_filter)
    stmt = stmt.order_by(DiscoveryRun.created_at.desc()).offset(offset).limit(limit)

    result = await db.execute(stmt)
    runs = result.scalars().all()
    return [DiscoveryRunResponse.model_validate(r) for r in runs]


# ─── /{run_id} routes (leads sub-path declared before the bare {run_id}) ────────
@router.get(
    "/workspaces/{workspace_id}/discovery/runs/{run_id}/leads",
    response_model=list[LeadResponse],
)
async def list_discovery_run_leads(
    workspace_id: uuid.UUID,
    run_id: uuid.UUID,
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[LeadResponse]:
    """Leads produced by a discovery run.

    Filters ``leads WHERE custom_fields->'discovery'->>'run_id' = :run_id`` — the
    durable discovery record discovery writes into ``custom_fields.discovery``
    (R6/R7). Ordered by fit score (``custom_fields->'discovery'->>'fit_score'``,
    numeric-cast) descending so the strongest venues surface first, newest as the
    tiebreak.
    """
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    run_id_str = str(run_id)
    fit_score = Lead.custom_fields["discovery"]["fit_score"].astext.cast(Float)
    stmt = (
        select(Lead)
        .where(
            Lead.workspace_id == workspace_id,
            Lead.custom_fields["discovery"]["run_id"].astext == run_id_str,
        )
        .order_by(fit_score.desc().nullslast(), Lead.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(stmt)
    leads = result.scalars().all()
    return [LeadResponse.model_validate(lead) for lead in leads]


@router.get(
    "/workspaces/{workspace_id}/discovery/runs/{run_id}",
    response_model=DiscoveryRunResponse,
)
async def get_discovery_run(
    workspace_id: uuid.UUID,
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DiscoveryRunResponse:
    """Return a single discovery run (ORM-first, Supabase-REST fallback before 404)."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    result = await db.execute(
        select(DiscoveryRun).where(
            DiscoveryRun.id == run_id, DiscoveryRun.workspace_id == workspace_id
        )
    )
    run = result.scalar_one_or_none()
    if run is None:
        row = await get_row(
            "discovery_runs", {"id": str(run_id), "workspace_id": str(workspace_id)}
        )
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Discovery run not found"
            )
        return DiscoveryRunResponse.model_validate(row)
    return DiscoveryRunResponse.model_validate(run)
