import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.agent import Agent
from app.models.activity_event import ActivityEvent

logger = logging.getLogger(__name__)

router = APIRouter()

# How long a dispatched job id is remembered in Redis. Long enough to outlive any
# realistic run + the frontend's bounded polling window, short enough to self-clean.
_JOB_MARKER_TTL_SECONDS = 24 * 60 * 60
_JOB_MARKER_PREFIX = "crm:job:"

# Agent types that have a real backing Celery task dispatched from this endpoint.
# Everything else runs via its own flow (upload / message ingest / compose endpoint)
# and has no "run me now" task, so /run returns 501 for them.
_DISPATCHABLE_TYPES = {"pipeline_optimizer", "pm_agent"}
_NO_BACKING_TASK_DETAIL = {
    "email_composer": "Email Composer runs per-contact via the compose endpoint, not as a batch job.",
    "call_summarizer": "Call Summarizer runs automatically when a call recording is uploaded.",
    "sentiment_analyzer": "Sentiment Analyzer runs automatically as messages are ingested.",
    "semantic_sorter": "Semantic Sorter runs automatically as messages are ingested.",
}


def _mark_job_dispatched(task_id: str, workspace_id: str) -> None:
    """Record that we dispatched this Celery task id AND which workspace owns it.

    The marker VALUE is the owning workspace id (string). GET /jobs/{id} reads it
    back to enforce tenant isolation — a job's result is only visible to the
    workspace that dispatched it — and still uses presence/absence to tell a
    never-dispatched id from a real-but-pending one. Best-effort; never fail the
    request.
    """
    from app.config import settings

    try:
        import redis as _redis

        client = _redis.Redis.from_url(settings.REDIS_URL, socket_connect_timeout=2, socket_timeout=2)
        try:
            client.set(f"{_JOB_MARKER_PREFIX}{task_id}", str(workspace_id), ex=_JOB_MARKER_TTL_SECONDS)
        finally:
            client.close()
    except Exception as exc:  # noqa: BLE001 — marker is best-effort, never fail the request
        logger.warning("event=job_marker_write_failed task_id=%s error=%s", task_id, exc)


def _job_was_dispatched(task_id: str) -> bool | None:
    """True/False if we have a dispatched marker; None if Redis is unreachable.

    None means 'can't tell' — callers should NOT treat a missing marker as unknown
    in that case, to avoid masking a real-but-pending job during a Redis blip.
    """
    from app.config import settings

    try:
        import redis as _redis

        client = _redis.Redis.from_url(settings.REDIS_URL, socket_connect_timeout=2, socket_timeout=2)
        try:
            return client.exists(f"{_JOB_MARKER_PREFIX}{task_id}") > 0
        finally:
            client.close()
    except Exception as exc:  # noqa: BLE001
        logger.warning("event=job_marker_read_failed task_id=%s error=%s", task_id, exc)
        return None


def _job_owner_workspace(task_id: str) -> str | None:
    """Return the owning workspace id stored in the dispatch marker, else None.

    None means 'can't tell' — marker missing/expired OR Redis unreachable. Callers
    must NOT deny access on None alone (that would 404 a legitimate job whose marker
    expired, or during a Redis blip); they deny only on a DEFINITE foreign owner.
    Legacy markers written before tenant-scoping hold the literal "1" and carry no
    owner — treated as None so they neither leak cross-tenant nor 404 the owner
    (they self-heal within the 24h TTL).
    """
    from app.config import settings

    try:
        import redis as _redis

        client = _redis.Redis.from_url(settings.REDIS_URL, socket_connect_timeout=2, socket_timeout=2)
        try:
            raw = client.get(f"{_JOB_MARKER_PREFIX}{task_id}")
        finally:
            client.close()
    except Exception as exc:  # noqa: BLE001
        logger.warning("event=job_marker_owner_read_failed task_id=%s error=%s", task_id, exc)
        return None

    if raw is None:
        return None
    owner = raw.decode() if isinstance(raw, (bytes, bytearray)) else str(raw)
    if owner == "1":  # legacy marker, no tenant identity
        return None
    return owner


class AgentResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str | None
    type: str | None
    description: str | None
    model: str | None
    status: str
    accuracy: float
    tasks_today: int
    last_run: str
    workflow: list = []
    metrics: list = []

    model_config = {"from_attributes": True}


class RunResponse(BaseModel):
    job_id: str
    agent_id: uuid.UUID
    status: str


@router.get("/agents", response_model=list[AgentResponse])
async def list_agents(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[AgentResponse]:
    result = await db.execute(select(Agent).where(Agent.workspace_id == current_user.workspace_id))
    agents = result.scalars().all()
    return [AgentResponse.model_validate(a) for a in agents]


@router.post("/agents/{agent_id}/run", response_model=RunResponse)
async def run_agent(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RunResponse:
    """Dispatch the real Celery task backing this agent and return its task id.

    Branches on agent.type. Only types with a real batch task (pipeline_optimizer,
    pm_agent) actually dispatch; the rest run via their own flows and return 501.
    Agent bookkeeping (last_run / tasks_today / activity_event) is written ONLY
    after a successful dispatch so a 501 never fabricates a "run".
    """
    result = await db.execute(
        select(Agent).where(Agent.id == agent_id, Agent.workspace_id == current_user.workspace_id)
    )
    agent = result.scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

    agent_type = agent.type
    if agent_type not in _DISPATCHABLE_TYPES:
        detail = _NO_BACKING_TASK_DETAIL.get(
            agent_type or "",
            f"Agent type '{agent_type}' has no on-demand task and cannot be run from here.",
        )
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=detail)

    # Dispatch the real task. task.id is the genuine Celery id the poller will track.
    workspace_id_str = str(current_user.workspace_id)
    if agent_type == "pipeline_optimizer":
        from app.workers.pipeline import optimize_pipeline

        task = optimize_pipeline.delay(workspace_id_str)
    else:  # pm_agent
        from app.workers.pm_agent import run_health_check

        task = run_health_check.delay()

    job_id = task.id
    _mark_job_dispatched(job_id, workspace_id_str)

    # Bookkeeping — only reached on a successful dispatch.
    agent.status = "processing"  # type: ignore[assignment]
    agent.last_run = datetime.now(timezone.utc).isoformat()  # type: ignore[assignment]
    agent.tasks_today = (agent.tasks_today or 0) + 1  # type: ignore[assignment]
    db.add(agent)

    event = ActivityEvent(
        workspace_id=current_user.workspace_id,
        type="agent_run",
        agent_name=agent.name,
        description=f"Agent {agent.name} triggered (job {job_id})",
        meta=str(current_user.workspace_id),
        severity="info",
    )
    db.add(event)
    await db.commit()

    return RunResponse(job_id=job_id, agent_id=agent_id, status="processing")


class JobStatusResponse(BaseModel):
    job_id: str
    state: str
    result: dict | None = None
    error: str | None = None


class UpdateAgentRequest(BaseModel):
    status: str | None = None


@router.patch("/agents/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: uuid.UUID,
    body: UpdateAgentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AgentResponse:
    result = await db.execute(
        select(Agent).where(Agent.id == agent_id, Agent.workspace_id == current_user.workspace_id)
    )
    agent = result.scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

    if body.status is not None:
        agent.status = body.status  # type: ignore[assignment]

    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    return AgentResponse.model_validate(agent)


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(
    job_id: str,
    current_user: User = Depends(get_current_user),
) -> JobStatusResponse:
    """Return the state of a Celery task by job_id.

    Celery reports PENDING both for jobs that are genuinely queued and for ids that
    were never dispatched (the result backend has no entry for either). To avoid the
    frontend polling a non-existent job forever, we cross-check a Redis dispatch
    marker: a PENDING state with NO marker is reported as the terminal state
    "unknown" instead. SUCCESS/FAILURE/STARTED/REVOKED come straight from the
    backend and are trusted as-is.

    Tenant isolation: a job's result is only visible to the workspace that
    dispatched it. We read the owning workspace from the dispatch marker and 404
    (not 403, to avoid confirming the id exists) when a different tenant asks.
    """
    owner = _job_owner_workspace(job_id)
    if owner is not None and owner != str(current_user.workspace_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    from app.workers.celery_app import celery_app

    task = celery_app.AsyncResult(job_id)
    state = task.state  # PENDING | STARTED | SUCCESS | FAILURE | REVOKED

    result = None
    error = None
    if state == "SUCCESS":
        raw = task.result
        result = raw if isinstance(raw, dict) else {"value": str(raw)}
    elif state == "FAILURE":
        error = str(task.result)
    elif state == "PENDING":
        # Distinguish "queued/running" from "never existed". Only override when the
        # marker is DEFINITIVELY absent (False); None = Redis unreachable, in which
        # case we keep PENDING rather than risk masking a real in-flight job.
        if _job_was_dispatched(job_id) is False:
            state = "unknown"
            error = "No such job — it was never dispatched or has expired."

    return JobStatusResponse(job_id=job_id, state=state, result=result, error=error)
