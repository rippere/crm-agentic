import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.message import Message

router = APIRouter()


class MessageResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    external_id: str
    subject: str | None
    sender_email: str | None
    received_at: datetime | None
    contact_id: uuid.UUID | None
    processed: bool

    model_config = {"from_attributes": True}


@router.get("/workspaces/{workspace_id}/messages", response_model=list[MessageResponse])
async def list_messages(
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[MessageResponse]:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    result = await db.execute(select(Message).where(Message.workspace_id == workspace_id))
    messages = result.scalars().all()
    return [MessageResponse.model_validate(m) for m in messages]
