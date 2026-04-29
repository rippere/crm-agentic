import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.models.workspace import Workspace
from app.services.auth import verify_supabase_jwt, extract_supabase_uid
from app.dependencies import get_current_user

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/verify", auto_error=True)


async def _sync_workspace_metadata(supabase_uid: str, workspace_id: str) -> None:
    """Push workspace_id into Supabase user_metadata via admin API (non-fatal)."""
    from app.config import settings as _s

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.patch(
                f"{_s.SUPABASE_URL.rstrip('/')}/auth/v1/admin/users/{supabase_uid}",
                headers={
                    "apikey": _s.SUPABASE_SERVICE_ROLE_KEY,
                    "Authorization": f"Bearer {_s.SUPABASE_SERVICE_ROLE_KEY}",
                    "Content-Type": "application/json",
                },
                json={"user_metadata": {"workspace_id": workspace_id}},
            )
    except Exception:
        pass  # metadata sync is best-effort; never block the auth response


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
    Reconciles workspace_id if the user completed onboarding after first provision.
    Returns user_id and workspace_id.
    """
    try:
        payload = verify_supabase_jwt(token)
        supabase_uid = extract_supabase_uid(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))

    email: str | None = payload.get("email")
    user_meta: dict = payload.get("user_metadata", {})
    meta_ws_id_str: str | None = user_meta.get("workspace_id")

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

        # Push workspace_id back into Supabase user_metadata so the JWT stays in sync
        await _sync_workspace_metadata(supabase_uid, str(ws.id))
    else:
        # Reconcile: if the JWT now carries a different workspace_id (e.g. after onboarding
        # created a new workspace via direct Supabase insert + updateUser), update our DB row.
        if meta_ws_id_str and meta_ws_id_str != str(user.workspace_id):
            try:
                new_ws_id = uuid.UUID(meta_ws_id_str)
                user.workspace_id = new_ws_id  # type: ignore[assignment]
                await db.commit()
                await db.refresh(user)
            except ValueError:
                pass

    return VerifyResponse(user_id=user.id, workspace_id=user.workspace_id)


@router.get("/me")
async def me(
    current_user=Depends(get_current_user),
) -> dict:
    """Return the authenticated user's profile including role."""
    return {
        "id": str(current_user.id),
        "email": current_user.email,
        "workspace_id": str(current_user.workspace_id) if current_user.workspace_id else None,
        "role": current_user.role,
    }


class InviteRequest(BaseModel):
    email: str


@router.post("/workspaces/{workspace_id}/invite")
async def invite_teammate(
    workspace_id: uuid.UUID,
    body: InviteRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    """Invite a teammate to the workspace via Supabase admin invite email."""
    from app.dependencies import require_admin
    from app.config import settings as app_settings
    import httpx

    if current_user.workspace_id != workspace_id:
        from fastapi import HTTPException as _HTTPException, status as _status
        raise _HTTPException(status_code=_status.HTTP_403_FORBIDDEN, detail="Access denied")
    if current_user.role != "admin":
        from fastapi import HTTPException as _HTTPException, status as _status
        raise _HTTPException(status_code=_status.HTTP_403_FORBIDDEN, detail="Admin role required")

    supabase_url = app_settings.SUPABASE_URL.rstrip("/")
    service_key = app_settings.SUPABASE_SERVICE_ROLE_KEY
    redirect_url = f"{app_settings.FRONTEND_URL}/onboarding"

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{supabase_url}/auth/v1/admin/invite",
            headers={
                "apikey": service_key,
                "Authorization": f"Bearer {service_key}",
                "Content-Type": "application/json",
            },
            json={
                "email": body.email,
                "data": {"workspace_id": str(workspace_id)},
                "redirect_to": redirect_url,
            },
        )

    if not resp.is_success:
        from fastapi import HTTPException as _HTTPException, status as _status
        detail = resp.json().get("message", "Invite failed")
        raise _HTTPException(status_code=_status.HTTP_502_BAD_GATEWAY, detail=detail)

    return {"status": "invited", "email": body.email}
