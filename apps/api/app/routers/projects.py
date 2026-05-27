from __future__ import annotations

import uuid as uuid_mod

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.project import Project
from app.models.user import User

router = APIRouter()


class ProjectCreate(BaseModel):
    name: str
    description: str | None = None
    status: str = "active"
    contact_id: uuid_mod.UUID | None = None


class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    status: str | None = None
    contact_id: uuid_mod.UUID | None = None


class ProjectResponse(BaseModel):
    id: uuid_mod.UUID
    workspace_id: uuid_mod.UUID
    name: str
    description: str | None
    status: str
    contact_id: uuid_mod.UUID | None
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


def _to_response(p: Project) -> ProjectResponse:
    return ProjectResponse(
        id=p.id,
        workspace_id=p.workspace_id,
        name=p.name,
        description=p.description,
        status=p.status,
        contact_id=p.contact_id,
        created_at=p.created_at.isoformat(),
        updated_at=p.updated_at.isoformat(),
    )


@router.get("/workspaces/{workspace_id}/projects", response_model=list[ProjectResponse])
async def list_projects(
    workspace_id: uuid_mod.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ProjectResponse]:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    result = await db.execute(
        select(Project).where(Project.workspace_id == workspace_id).order_by(Project.created_at.desc())
    )
    return [_to_response(p) for p in result.scalars().all()]


@router.post("/workspaces/{workspace_id}/projects", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    workspace_id: uuid_mod.UUID,
    body: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProjectResponse:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    project = Project(
        workspace_id=workspace_id,
        name=body.name,
        description=body.description,
        status=body.status,
        contact_id=body.contact_id,
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return _to_response(project)


@router.get("/workspaces/{workspace_id}/projects/{project_id}", response_model=ProjectResponse)
async def get_project(
    workspace_id: uuid_mod.UUID,
    project_id: uuid_mod.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProjectResponse:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.workspace_id == workspace_id)
    )
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return _to_response(project)


@router.patch("/workspaces/{workspace_id}/projects/{project_id}", response_model=ProjectResponse)
async def update_project(
    workspace_id: uuid_mod.UUID,
    project_id: uuid_mod.UUID,
    body: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProjectResponse:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.workspace_id == workspace_id)
    )
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    if body.name is not None:
        project.name = body.name  # type: ignore[assignment]
    if body.description is not None:
        project.description = body.description  # type: ignore[assignment]
    if body.status is not None:
        project.status = body.status  # type: ignore[assignment]
    if body.contact_id is not None:
        project.contact_id = body.contact_id  # type: ignore[assignment]
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return _to_response(project)


@router.delete("/workspaces/{workspace_id}/projects/{project_id}")
async def delete_project(
    workspace_id: uuid_mod.UUID,
    project_id: uuid_mod.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.workspace_id == workspace_id)
    )
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    await db.delete(project)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
