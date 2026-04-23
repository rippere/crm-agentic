import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.agent import Agent
from app.models.activity_event import ActivityEvent

router = APIRouter()


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
    """Stub: set agent status=processing, log activity, return job_id."""
    result = await db.execute(
        select(Agent).where(Agent.id == agent_id, Agent.workspace_id == current_user.workspace_id)
    )
    agent = result.scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

    agent.status = "processing"  # type: ignore[assignment]
    db.add(agent)

    job_id = str(uuid.uuid4())
    event = ActivityEvent(
        workspace_id=current_user.workspace_id,
        type="agent_run",
        agent_name=agent.name,
        description=f"Agent {agent.name} triggered (job {job_id})",
        severity="info",
    )
    db.add(event)
    await db.commit()

    return RunResponse(job_id=job_id, agent_id=agent_id, status="processing")
