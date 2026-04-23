import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.services.auth import verify_supabase_jwt, extract_supabase_uid

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/verify", auto_error=True)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Validate Bearer JWT, look up the User row, and return it.
    Raises 401 if the token is invalid or the user does not exist.
    """
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = verify_supabase_jwt(token)
        supabase_uid = extract_supabase_uid(payload)
    except (ValueError, Exception):
        raise credentials_exc

    result = await db.execute(select(User).where(User.supabase_uid == supabase_uid))
    user = result.scalar_one_or_none()
    if user is None:
        raise credentials_exc
    return user


async def get_workspace_id(
    current_user: User = Depends(get_current_user),
) -> uuid.UUID:
    """Return the workspace_id for the authenticated user."""
    if current_user.workspace_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User has no workspace assigned",
        )
    return current_user.workspace_id
