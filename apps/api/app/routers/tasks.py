import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.task import Task

router = APIRouter()


class TaskResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    message_id: uuid.UUID | None
    contact_id: uuid.UUID | None
    title: str
    description: str
    status: str
    due_date: date | None

    model_config = {"from_attributes": True}


class TaskCreate(BaseModel):
    title: str
    description: str = ""
    status: str = "open"
    due_date: date | None = None
    message_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    status: str | None = None
    due_date: date | None = None


@router.get("/workspaces/{workspace_id}/tasks", response_model=list[TaskResponse])
async def list_tasks(
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[TaskResponse]:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    result = await db.execute(select(Task).where(Task.workspace_id == workspace_id))
    tasks = result.scalars().all()
    return [TaskResponse.model_validate(t) for t in tasks]


@router.post("/workspaces/{workspace_id}/tasks", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    workspace_id: uuid.UUID,
    body: TaskCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TaskResponse:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    task = Task(
        workspace_id=workspace_id,
        title=body.title,
        description=body.description,
        status=body.status,
        due_date=body.due_date,
        message_id=body.message_id,
        contact_id=body.contact_id,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return TaskResponse.model_validate(task)


@router.put("/workspaces/{workspace_id}/tasks/{task_id}", response_model=TaskResponse)
async def update_task(
    workspace_id: uuid.UUID,
    task_id: uuid.UUID,
    body: TaskUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TaskResponse:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    result = await db.execute(
        select(Task).where(Task.id == task_id, Task.workspace_id == workspace_id)
    )
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    if body.title is not None:
        task.title = body.title  # type: ignore[assignment]
    if body.description is not None:
        task.description = body.description  # type: ignore[assignment]
    if body.status is not None:
        task.status = body.status  # type: ignore[assignment]
    if body.due_date is not None:
        task.due_date = body.due_date  # type: ignore[assignment]

    await db.commit()
    await db.refresh(task)
    return TaskResponse.model_validate(task)
