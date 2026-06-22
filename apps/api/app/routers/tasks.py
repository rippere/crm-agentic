import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
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
    external_id: str | None = None
    message_id: uuid.UUID | None
    contact_id: uuid.UUID | None
    deal_id: uuid.UUID | None = None
    project_id: uuid.UUID | None
    title: str
    description: str
    status: str
    due_date: date | None
    updated_at: str | None = None

    model_config = {"from_attributes": True}


class TaskCreate(BaseModel):
    title: str
    description: str = ""
    status: str = "open"
    due_date: date | None = None
    message_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    status: str | None = None
    due_date: date | None = None
    project_id: uuid.UUID | None = None


def _to_response(t: Task) -> TaskResponse:
    return TaskResponse(
        id=t.id,
        workspace_id=t.workspace_id,
        external_id=t.external_id,
        message_id=t.message_id,
        contact_id=t.contact_id,
        deal_id=t.deal_id,
        project_id=t.project_id,
        title=t.title,
        description=t.description,
        status=t.status,
        due_date=t.due_date,
        updated_at=t.updated_at.isoformat() if t.updated_at else None,
    )


@router.get("/workspaces/{workspace_id}/tasks", response_model=list[TaskResponse])
async def list_tasks(
    workspace_id: uuid.UUID,
    project_id: uuid.UUID | None = Query(default=None),
    contact_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[TaskResponse]:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    q = select(Task).where(Task.workspace_id == workspace_id)
    if project_id is not None:
        q = q.where(Task.project_id == project_id)
    if contact_id is not None:
        q = q.where(Task.contact_id == contact_id)
    q = q.order_by(Task.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(q)
    return [_to_response(t) for t in result.scalars().all()]


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
        project_id=body.project_id,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return _to_response(task)


class TaskUpsert(BaseModel):
    title: str
    description: str = ""
    status: str = "open"
    due_date: date | None = None
    project_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    deal_id: uuid.UUID | None = None


async def upsert_task_record(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    external_id: str,
    *,
    title: str,
    description: str = "",
    status: str = "open",
    due_date: date | None = None,
    project_id: uuid.UUID | None = None,
    contact_id: uuid.UUID | None = None,
    deal_id: uuid.UUID | None = None,
) -> Task:
    """Idempotent create-or-update of a task keyed on (workspace_id, external_id).

    Shared by the REST by-external endpoint and the MCP ``upsert_task`` tool so the
    two stay in lock-step. Caller is responsible for workspace authorization.
    """
    result = await db.execute(
        select(Task).where(Task.workspace_id == workspace_id, Task.external_id == external_id)
    )
    task = result.scalar_one_or_none()
    if task is None:
        task = Task(
            workspace_id=workspace_id,
            external_id=external_id,
            title=title,
            description=description,
            status=status,
            due_date=due_date,
            project_id=project_id,
            contact_id=contact_id,
            deal_id=deal_id,
        )
        db.add(task)
    else:
        task.title = title  # type: ignore[assignment]
        task.description = description  # type: ignore[assignment]
        task.status = status  # type: ignore[assignment]
        task.due_date = due_date  # type: ignore[assignment]
        task.project_id = project_id  # type: ignore[assignment]
        task.contact_id = contact_id  # type: ignore[assignment]
        task.deal_id = deal_id  # type: ignore[assignment]

    await db.commit()
    await db.refresh(task)
    return task


@router.put("/workspaces/{workspace_id}/tasks/by-external/{external_id}", response_model=TaskResponse)
async def upsert_task_by_external(
    workspace_id: uuid.UUID,
    external_id: str,
    body: TaskUpsert,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TaskResponse:
    """Idempotent create-or-update keyed on (workspace_id, external_id).

    Entry point for the vault->NovaCRM task sync bridge: re-running the sync with
    the same vault uid updates the existing task instead of creating a duplicate.
    """
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    task = await upsert_task_record(
        db,
        workspace_id,
        external_id,
        title=body.title,
        description=body.description,
        status=body.status,
        due_date=body.due_date,
        project_id=body.project_id,
        contact_id=body.contact_id,
        deal_id=body.deal_id,
    )
    return _to_response(task)


@router.delete("/workspaces/{workspace_id}/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    workspace_id: uuid.UUID,
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    result = await db.execute(
        select(Task).where(Task.id == task_id, Task.workspace_id == workspace_id)
    )
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    await db.delete(task)
    await db.commit()


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
    if body.project_id is not None:
        task.project_id = body.project_id  # type: ignore[assignment]

    await db.commit()
    await db.refresh(task)
    return _to_response(task)
