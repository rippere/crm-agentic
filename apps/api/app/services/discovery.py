"""
Discovery dispatch seam for the Autonomous Lead Engine (Inc 1).

The ONE dispatch path (resolution R2) for a market-discovery run, called by BOTH
``POST /workspaces/{ws}/discovery/runs`` (routers/discovery.py) AND the
action_bus ``discover_market`` action (services/actions/discovery.py). There is
no ``run_discovery(ws, locality, criteria)`` variant — every caller goes through
:func:`dispatch_discovery_run`.

Contract (R2 / spec §2.1.7):
  1. Validate the request (provider vs PLACES_PROVIDERS; rubric via
     ``validate_rubric`` -> HTTP 422 on bad weights).
  2. Snapshot the effective rubric; create the ``discovery_runs`` row
     (status='queued'); flush for its id; **COMMIT the run row BEFORE dispatch**
     so a fast worker is guaranteed to find it (closes the dispatch-before-commit
     race).
  3. Guarded dispatch: enqueue ``run_market_discovery.delay(ws, run_id)`` and
     mark the job (mirrors agents.py ``_mark_job_dispatched``). Missing worker
     deps -> ``job_id='pending'``.
  4. Write a ``discovery_run_started`` ActivityEvent (``meta=json.dumps(...)``);
     commit; return the run.
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import TYPE_CHECKING

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.activity_event import ActivityEvent
from app.models.discovery_run import DiscoveryRun
from app.services.discovery_rubric import DEFAULT_RUBRIC, validate_rubric

if TYPE_CHECKING:  # avoid a router<->service import cycle at module load
    from app.routers.discovery import DiscoveryRunRequest

logger = logging.getLogger(__name__)


async def dispatch_discovery_run(
    workspace_id: uuid.UUID,
    request: "DiscoveryRunRequest",
    db: AsyncSession,
) -> DiscoveryRun:
    """Create + enqueue one market-discovery run. The shared seam (R2).

    See the module docstring for the four-step contract. Raises
    ``HTTPException(422)`` on an invalid provider or rubric; otherwise always
    returns the committed ``DiscoveryRun`` (``job_id`` is the Celery task id, or
    ``'pending'`` when the worker module is unavailable — e.g. a web-only deploy).
    The caller supplies ``workspace_id`` from the URL + 403 guard; the model /
    request body never supplies it.
    """
    # ── 1. validate ────────────────────────────────────────────────────────────
    # PLACES_PROVIDERS is the single-source tuple in the router; import it lazily
    # so this service and the router don't form an import cycle at module load.
    from app.routers.discovery import PLACES_PROVIDERS

    locality: str = request.locality
    provider = getattr(request, "provider", None)
    if provider is not None and provider not in PLACES_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown provider '{provider}'. Valid: {', '.join(PLACES_PROVIDERS)}",
        )

    override_rubric = getattr(request, "rubric", None)
    if override_rubric is not None:
        try:
            validate_rubric(override_rubric)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid rubric: {exc}",
            ) from exc
    effective_rubric = override_rubric if override_rubric is not None else DEFAULT_RUBRIC

    # ── 2. create the run row + COMMIT before dispatch ─────────────────────────
    max_venues = getattr(request, "max_venues", None) or settings.DISCOVERY_MAX_VENUES
    params = {
        "categories": getattr(request, "categories", None),
        "radius_m": getattr(request, "radius_m", None),
        "max_venues": max_venues,
        "provider": provider,
    }
    run = DiscoveryRun(
        workspace_id=workspace_id,
        locality=locality,
        provider=provider,
        status="queued",
        params=params,
        rubric=effective_rubric,
        stats={},
    )
    db.add(run)
    await db.flush()          # assign run.id
    run_id = run.id
    await db.commit()         # a fast worker must find the row (R2 race fix)

    # ── 3. guarded dispatch ────────────────────────────────────────────────────
    job_id = "pending"
    try:
        from app.workers.discovery import run_market_discovery
        from app.routers.agents import _mark_job_dispatched

        task = run_market_discovery.delay(str(workspace_id), str(run_id))
        _mark_job_dispatched(task.id, str(workspace_id))
        job_id = task.id
    except ImportError as exc:
        logger.warning("discovery dispatch_unavailable run_id=%s exc=%s", run_id, exc)
    run.job_id = job_id

    # ── 4. audit + commit ──────────────────────────────────────────────────────
    event = ActivityEvent(
        workspace_id=workspace_id,
        type="discovery_run_started",
        agent_name="System",
        description=f"Discovery run queued for {locality}",
        meta=json.dumps(
            {
                "run_id": str(run_id),
                "locality": locality,
                "provider": provider,
                "job_id": job_id,
                "max_venues": max_venues,
            }
        ),
        severity="info",
    )
    db.add(event)
    await db.commit()
    await db.refresh(run)
    return run
