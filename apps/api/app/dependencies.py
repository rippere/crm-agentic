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
    Auto-provisions the user (and workspace if needed) on first hit.
    """
    from app.models.workspace import Workspace

    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = verify_supabase_jwt(token)
        supabase_uid = extract_supabase_uid(payload)
    except (ValueError, Exception) as e:
        import sys
        print(f"[auth] JWT verify failed: {e}", file=sys.stderr)
        raise credentials_exc

    result = await db.execute(select(User).where(User.supabase_uid == supabase_uid))
    user = result.scalar_one_or_none()

    if user is None:
        # Auto-provision: pull workspace_id + email from JWT user_metadata
        user_meta: dict = payload.get("user_metadata", {})
        email: str | None = payload.get("email") or user_meta.get("email")
        workspace_id_str: str | None = user_meta.get("workspace_id")

        workspace_id: uuid.UUID | None = None
        if workspace_id_str:
            try:
                workspace_id = uuid.UUID(workspace_id_str)
            except ValueError:
                pass

        # Ensure workspace row exists
        if workspace_id:
            ws_result = await db.execute(
                select(Workspace).where(Workspace.id == workspace_id)
            )
            if ws_result.scalar_one_or_none() is None:
                slug = email.split("@")[0].lower().replace(".", "-") if email else str(workspace_id)[:8]
                workspace = Workspace(
                    id=workspace_id,
                    name=slug,
                    slug=slug,
                    mode="sales",
                )
                db.add(workspace)
                await db.flush()

        user = User(
            supabase_uid=supabase_uid,
            workspace_id=workspace_id,
            email=email,
            role="admin",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    return user


async def require_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """Raise 403 if the user's role is not 'admin'."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )
    return current_user


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
