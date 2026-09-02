import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.sequence import Sequence
from app.models.sequence_step import SequenceStep
from app.models.activity_event import ActivityEvent
from app.services.supabase_rest import get_row

router = APIRouter()


# Literal sets mirror the SQL CHECK constraints in
# migrations/023_outbound_engagement.sql. Kept in sync by hand — a bad value
# must raise HTTPException(422), never reach the DB and 500 on a check violation.
SEQUENCE_CHANNELS = ("email", "sms", "mixed")
SEQUENCE_STATUSES = ("draft", "active", "archived")
STEP_CHANNELS = ("email", "sms")


class SequenceStepResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    sequence_id: uuid.UUID
    step_order: int
    channel: str
    delay_hours: int
    subject: str | None
    body_template: str
    requires_approval: bool
    ai_generate: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SequenceResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    description: str | None = None
    channel: str
    status: str
    step_count: int
    settings: dict = {}
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SequenceDetailResponse(SequenceResponse):
    steps: list[SequenceStepResponse] = []


class CreateSequenceRequest(BaseModel):
    name: str
    description: str | None = None
    channel: str = "email"
    status: str = "draft"
    settings: dict = {}


class UpdateSequenceRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    channel: str | None = None
    status: str | None = None
    settings: dict | None = None


class StepInput(BaseModel):
    step_order: int | None = None
    channel: str = "email"
    delay_hours: int = 0
    subject: str | None = None
    body_template: str = ""
    requires_approval: bool = True
    ai_generate: bool = False


class ReplaceStepsRequest(BaseModel):
    steps: list[StepInput]


class AppendStepRequest(BaseModel):
    step_order: int | None = None
    channel: str = "email"
    delay_hours: int = 0
    subject: str | None = None
    body_template: str = ""
    requires_approval: bool = True
    ai_generate: bool = False


class UpdateStepRequest(BaseModel):
    step_order: int | None = None
    channel: str | None = None
    delay_hours: int | None = None
    subject: str | None = None
    body_template: str | None = None
    requires_approval: bool | None = None
    ai_generate: bool | None = None


def _validate_sequence_channel(channel: str) -> None:
    if channel not in SEQUENCE_CHANNELS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"channel must be one of {list(SEQUENCE_CHANNELS)}",
        )


def _validate_sequence_status(value: str) -> None:
    if value not in SEQUENCE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"status must be one of {list(SEQUENCE_STATUSES)}",
        )


def _validate_step_channel(channel: str) -> None:
    if channel not in STEP_CHANNELS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"step channel must be one of {list(STEP_CHANNELS)}",
        )


# ─── Collection ─────────────────────────────────────────────────────────────


@router.get("/workspaces/{workspace_id}/sequences", response_model=list[SequenceResponse])
async def list_sequences(
    workspace_id: uuid.UUID,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[SequenceResponse]:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    q = select(Sequence).where(Sequence.workspace_id == workspace_id)
    if status_filter and status_filter != "all":
        q = q.where(Sequence.status == status_filter)
    q = q.order_by(Sequence.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(q)
    sequences = result.scalars().all()
    return [SequenceResponse.model_validate(s) for s in sequences]


@router.post("/workspaces/{workspace_id}/sequences", response_model=SequenceResponse, status_code=201)
async def create_sequence(
    workspace_id: uuid.UUID,
    body: CreateSequenceRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SequenceResponse:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    _validate_sequence_channel(body.channel)
    _validate_sequence_status(body.status)

    sequence = Sequence(
        workspace_id=workspace_id,
        name=body.name,
        description=body.description,
        channel=body.channel,
        status=body.status,
        step_count=0,
        settings=body.settings or {},
    )
    db.add(sequence)
    event = ActivityEvent(
        workspace_id=workspace_id,
        type="sequence_created",
        agent_name="System",
        description=f"New sequence: {body.name}",
        severity="info",
    )
    db.add(event)
    await db.commit()
    await db.refresh(sequence)
    return SequenceResponse.model_validate(sequence)


# ─── Item ───────────────────────────────────────────────────────────────────


async def _load_sequence(db: AsyncSession, workspace_id: uuid.UUID, sequence_id: uuid.UUID) -> Sequence:
    result = await db.execute(
        select(Sequence).where(
            Sequence.id == sequence_id, Sequence.workspace_id == workspace_id
        )
    )
    sequence = result.scalar_one_or_none()
    if sequence is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sequence not found")
    return sequence


async def _load_ordered_steps(
    db: AsyncSession, workspace_id: uuid.UUID, sequence_id: uuid.UUID
) -> list[SequenceStep]:
    result = await db.execute(
        select(SequenceStep)
        .where(
            SequenceStep.workspace_id == workspace_id,
            SequenceStep.sequence_id == sequence_id,
        )
        .order_by(SequenceStep.step_order.asc())
    )
    return list(result.scalars().all())


@router.get(
    "/workspaces/{workspace_id}/sequences/{sequence_id}",
    response_model=SequenceDetailResponse,
)
async def get_sequence(
    workspace_id: uuid.UUID,
    sequence_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SequenceDetailResponse:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    result = await db.execute(
        select(Sequence).where(
            Sequence.id == sequence_id, Sequence.workspace_id == workspace_id
        )
    )
    sequence = result.scalar_one_or_none()

    # ORM-first, then Supabase REST fallback before returning 404 — matches the
    # contacts/deals pattern for rows that live in Supabase but not local Postgres.
    if sequence is None:
        row = await get_row(
            "sequences", {"id": str(sequence_id), "workspace_id": str(workspace_id)}
        )
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sequence not found")
        return SequenceDetailResponse(
            id=uuid.UUID(str(row["id"])),
            workspace_id=uuid.UUID(str(row["workspace_id"])),
            name=row.get("name"),
            description=row.get("description"),
            channel=row.get("channel", "email"),
            status=row.get("status", "draft"),
            step_count=row.get("step_count", 0),
            settings=row.get("settings") or {},
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
            steps=[],
        )

    steps = await _load_ordered_steps(db, workspace_id, sequence_id)
    base = SequenceResponse.model_validate(sequence)
    return SequenceDetailResponse(
        **base.model_dump(),
        steps=[SequenceStepResponse.model_validate(s) for s in steps],
    )


@router.patch(
    "/workspaces/{workspace_id}/sequences/{sequence_id}",
    response_model=SequenceResponse,
)
async def update_sequence(
    workspace_id: uuid.UUID,
    sequence_id: uuid.UUID,
    body: UpdateSequenceRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SequenceResponse:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if body.channel is not None:
        _validate_sequence_channel(body.channel)
    if body.status is not None:
        _validate_sequence_status(body.status)

    sequence = await _load_sequence(db, workspace_id, sequence_id)

    for field in ("name", "description", "channel", "status", "settings"):
        value = getattr(body, field)
        if value is not None:
            setattr(sequence, field, value)

    db.add(sequence)
    event = ActivityEvent(
        workspace_id=workspace_id,
        type="sequence_updated",
        agent_name="System",
        description=f"Sequence updated: {sequence.name}",
        severity="info",
    )
    db.add(event)
    await db.commit()
    await db.refresh(sequence)
    return SequenceResponse.model_validate(sequence)


@router.delete(
    "/workspaces/{workspace_id}/sequences/{sequence_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_sequence(
    workspace_id: uuid.UUID,
    sequence_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Archive a sequence (soft delete). Campaigns reference sequences via
    ON DELETE SET NULL, so archiving preserves history rather than hard-deleting."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    sequence = await _load_sequence(db, workspace_id, sequence_id)
    seq_name = sequence.name
    sequence.status = "archived"
    db.add(sequence)
    event = ActivityEvent(
        workspace_id=workspace_id,
        type="sequence_archived",
        agent_name="System",
        description=f"Sequence archived: {seq_name}",
        severity="warning",
    )
    db.add(event)
    await db.commit()


# ─── Steps ──────────────────────────────────────────────────────────────────


@router.put(
    "/workspaces/{workspace_id}/sequences/{sequence_id}/steps",
    response_model=SequenceDetailResponse,
)
async def replace_sequence_steps(
    workspace_id: uuid.UUID,
    sequence_id: uuid.UUID,
    body: ReplaceStepsRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SequenceDetailResponse:
    """Replace the full ordered step list for a sequence (builder save) and
    recompute step_count. step_order is normalized to 0-based position unless
    explicitly supplied."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    for step in body.steps:
        _validate_step_channel(step.channel)

    sequence = await _load_sequence(db, workspace_id, sequence_id)

    # Drop the existing owned children, then re-insert the new ordered list.
    await db.execute(
        delete(SequenceStep).where(
            SequenceStep.workspace_id == workspace_id,
            SequenceStep.sequence_id == sequence_id,
        )
    )

    for idx, step in enumerate(body.steps):
        db.add(
            SequenceStep(
                workspace_id=workspace_id,
                sequence_id=sequence_id,
                step_order=step.step_order if step.step_order is not None else idx,
                channel=step.channel,
                delay_hours=step.delay_hours,
                subject=step.subject,
                body_template=step.body_template or "",
                requires_approval=step.requires_approval,
                ai_generate=step.ai_generate,
            )
        )

    sequence.step_count = len(body.steps)
    db.add(sequence)
    event = ActivityEvent(
        workspace_id=workspace_id,
        type="sequence_updated",
        agent_name="System",
        description=f"Sequence '{sequence.name}' steps replaced ({len(body.steps)} steps)",
        severity="info",
    )
    db.add(event)
    await db.commit()
    await db.refresh(sequence)

    steps = await _load_ordered_steps(db, workspace_id, sequence_id)
    base = SequenceResponse.model_validate(sequence)
    return SequenceDetailResponse(
        **base.model_dump(),
        steps=[SequenceStepResponse.model_validate(s) for s in steps],
    )


@router.post(
    "/workspaces/{workspace_id}/sequences/{sequence_id}/steps",
    response_model=SequenceStepResponse,
    status_code=201,
)
async def append_sequence_step(
    workspace_id: uuid.UUID,
    sequence_id: uuid.UUID,
    body: AppendStepRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SequenceStepResponse:
    """Append one step to a sequence and bump step_count."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    _validate_step_channel(body.channel)

    sequence = await _load_sequence(db, workspace_id, sequence_id)

    if body.step_order is not None:
        next_order = body.step_order
    else:
        max_result = await db.execute(
            select(func.max(SequenceStep.step_order)).where(
                SequenceStep.workspace_id == workspace_id,
                SequenceStep.sequence_id == sequence_id,
            )
        )
        current_max = max_result.scalar_one_or_none()
        next_order = 0 if current_max is None else current_max + 1

    step = SequenceStep(
        workspace_id=workspace_id,
        sequence_id=sequence_id,
        step_order=next_order,
        channel=body.channel,
        delay_hours=body.delay_hours,
        subject=body.subject,
        body_template=body.body_template or "",
        requires_approval=body.requires_approval,
        ai_generate=body.ai_generate,
    )
    db.add(step)
    sequence.step_count = (sequence.step_count or 0) + 1
    db.add(sequence)
    event = ActivityEvent(
        workspace_id=workspace_id,
        type="sequence_updated",
        agent_name="System",
        description=f"Step appended to sequence '{sequence.name}'",
        severity="info",
    )
    db.add(event)
    await db.commit()
    await db.refresh(step)
    return SequenceStepResponse.model_validate(step)


@router.patch(
    "/workspaces/{workspace_id}/sequences/{sequence_id}/steps/{step_id}",
    response_model=SequenceStepResponse,
)
async def update_sequence_step(
    workspace_id: uuid.UUID,
    sequence_id: uuid.UUID,
    step_id: uuid.UUID,
    body: UpdateStepRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SequenceStepResponse:
    """Edit one step in a sequence."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if body.channel is not None:
        _validate_step_channel(body.channel)

    result = await db.execute(
        select(SequenceStep).where(
            SequenceStep.id == step_id,
            SequenceStep.sequence_id == sequence_id,
            SequenceStep.workspace_id == workspace_id,
        )
    )
    step = result.scalar_one_or_none()
    if step is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Step not found")

    for field in (
        "step_order",
        "channel",
        "delay_hours",
        "subject",
        "body_template",
        "requires_approval",
        "ai_generate",
    ):
        value = getattr(body, field)
        if value is not None:
            setattr(step, field, value)

    db.add(step)
    await db.commit()
    await db.refresh(step)
    return SequenceStepResponse.model_validate(step)


@router.delete(
    "/workspaces/{workspace_id}/sequences/{sequence_id}/steps/{step_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_sequence_step(
    workspace_id: uuid.UUID,
    sequence_id: uuid.UUID,
    step_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Remove one step from a sequence and decrement step_count."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    result = await db.execute(
        select(SequenceStep).where(
            SequenceStep.id == step_id,
            SequenceStep.sequence_id == sequence_id,
            SequenceStep.workspace_id == workspace_id,
        )
    )
    step = result.scalar_one_or_none()
    if step is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Step not found")

    await db.delete(step)

    sequence = await _load_sequence(db, workspace_id, sequence_id)
    sequence.step_count = max(0, (sequence.step_count or 0) - 1)
    db.add(sequence)
    await db.commit()
