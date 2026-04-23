import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.models.workspace import Workspace
from app.services.auth import verify_supabase_jwt, extract_supabase_uid

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/verify", auto_error=True)


class VerifyResponse(BaseModel):
    user_id: uuid.UUID
    workspace_id: uuid.UUID | None


@router.post("/auth/verify", response_model=VerifyResponse)
async def verify(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> VerifyResponse:
    """
    Verify a Supabase JWT. Auto-provisions a users row on first login.
    Returns user_id and workspace_id.
    """
    try:
        payload = verify_supabase_jwt(token)
        supabase_uid = extract_supabase_uid(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))

    email: str | None = payload.get("email")

    # Look up existing user
    result = await db.execute(select(User).where(User.supabase_uid == supabase_uid))
    user = result.scalar_one_or_none()

    if user is None:
        # Auto-provision: create a default workspace + user row
        ws = Workspace(name=f"{email or 'My'} Workspace", slug=str(uuid.uuid4())[:8], mode="sales")
        db.add(ws)
        await db.flush()

        user = User(supabase_uid=supabase_uid, email=email, workspace_id=ws.id, role="admin")
        db.add(user)
        await db.commit()
        await db.refresh(user)

    return VerifyResponse(user_id=user.id, workspace_id=user.workspace_id)
