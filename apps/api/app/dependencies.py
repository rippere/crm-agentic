import logging
import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.services.auth import verify_supabase_jwt, extract_supabase_uid

logger = logging.getLogger(__name__)

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
        logger.warning("event=jwt_verify_failed error=%s", e)
        raise credentials_exc

    result = await db.execute(select(User).where(User.supabase_uid == supabase_uid))
    user = result.scalar_one_or_none()

    if user is None:
        # Auto-provision. The ONLY trusted workspace binding is server-only app_metadata
        # (not writable via supabase.auth.updateUser). We never bind a new user to a
        # workspace_id taken from user-writable metadata — that was the cross-tenant IDOR.
        from app.routers.auth import (
            _DEFAULT_AGENTS,
            _read_bound_workspace_id,
            _sync_workspace_metadata,
        )
        from app.models.agent import Agent

        email: str | None = payload.get("email") or (payload.get("user_metadata") or {}).get("email")
        trusted_ws_str: str | None = _read_bound_workspace_id(payload)

        trusted_ws_id: uuid.UUID | None = None
        if trusted_ws_str:
            try:
                trusted_ws_id = uuid.UUID(trusted_ws_str)
            except ValueError:
                trusted_ws_id = None

        synced_workspace_id: uuid.UUID | None = None

        if trusted_ws_id is not None:
            # Server-bound (e.g. invited teammate). Join the existing workspace; create the
            # row only if the trusted id has no workspace yet (server-issued id, safe).
            ws_result = await db.execute(select(Workspace).where(Workspace.id == trusted_ws_id))
            existing_ws = ws_result.scalar_one_or_none()
            if existing_ws is None:
                slug = email.split("@")[0].lower().replace(".", "-") if email else str(trusted_ws_id)[:8]
                db.add(Workspace(id=trusted_ws_id, name=slug, slug=slug, mode="sales"))
                await db.flush()
                role = "admin"
            else:
                role = "member"
            workspace_id = trusted_ws_id
        else:
            # No trusted binding → provision a FRESH workspace with a server-generated id
            # (never the user-supplied one) + the default agent roster. This is the safe
            # fallback for a user who hits the API before completing onboarding.
            workspace_id = uuid.uuid4()
            slug = email.split("@")[0].lower().replace(".", "-") if email else str(workspace_id)[:8]
            db.add(Workspace(id=workspace_id, name=slug, slug=slug, mode="sales"))
            await db.flush()
            for spec in _DEFAULT_AGENTS:
                db.add(Agent(workspace_id=workspace_id, **spec))
            role = "admin"
            synced_workspace_id = workspace_id

        user = User(
            supabase_uid=supabase_uid,
            workspace_id=workspace_id,
            email=email,
            role=role,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

        # Bind the freshly-created workspace into server-only app_metadata so the next JWT
        # carries it (best-effort; never blocks the request).
        if synced_workspace_id is not None:
            await _sync_workspace_metadata(str(supabase_uid), str(synced_workspace_id))

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
