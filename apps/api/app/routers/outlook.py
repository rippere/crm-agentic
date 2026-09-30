"""
Outlook / Microsoft 365 OAuth router — the Outlook counterpart of gmail.py.

Endpoints:
  GET  /workspaces/{id}/connectors/outlook/auth   — build Microsoft OAuth URL
  GET  /auth/outlook/callback                     — exchange code, store tokens
  POST /workspaces/{id}/connectors/outlook/sync   — trigger Celery ingest

Listing, status and delete are service-agnostic and live in gmail.py
(GET/DELETE /workspaces/{id}/connectors[/{connector_id}]).
"""

import logging
from uuid import UUID
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import httpx

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.connector import Connector
from app.models.user import User
from app.services.crypto import encrypt_token
from app.services.oauth_state import build_state, verify_state
from app.services.outlook_client import GRAPH_API_BASE, MS_AUTH_URL, MS_TOKEN_URL, OUTLOOK_SCOPES

logger = logging.getLogger(__name__)

router = APIRouter()


def _build_redirect_uri() -> str:
    return f"{settings.API_URL.rstrip('/')}/auth/outlook/callback"


def _require_configured() -> None:
    # A confidential web app can't redeem an auth code without its secret, so
    # both halves of the credential must be present.
    if not settings.MICROSOFT_CLIENT_ID or not settings.MICROSOFT_CLIENT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Outlook connector not configured",
        )


# ── 1. Initiate OAuth ────────────────────────────────────────────


@router.get("/workspaces/{workspace_id}/connectors/outlook/auth")
async def outlook_auth_url(
    workspace_id: UUID,
    current_user: User = Depends(get_current_user),
) -> dict:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    _require_configured()

    state = build_state(workspace_id)

    params = {
        "client_id": settings.MICROSOFT_CLIENT_ID,
        "redirect_uri": _build_redirect_uri(),
        "response_type": "code",
        "response_mode": "query",
        "scope": " ".join(OUTLOOK_SCOPES),
        # Let users with several Microsoft accounts (work + personal) pick the
        # mailbox to connect instead of silently reusing the signed-in one.
        "prompt": "select_account",
        "state": state,
    }
    auth_url = f"{MS_AUTH_URL}?{urlencode(params)}"
    return {"auth_url": auth_url}


# ── 2. OAuth Callback ────────────────────────────────────────────


@router.get("/auth/outlook/callback")
async def outlook_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    # Microsoft redirects back with ?error=...&error_description=... (and no code)
    # when the user cancels or an admin-consent policy blocks the app. Send them
    # back to the connectors page rather than a bare 422.
    if error:
        logger.warning("outlook_oauth_error error=%s", error)
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL.rstrip('/')}/connectors?error=outlook_oauth_denied"
        )

    if not code or not state:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing code or state")

    # Verify the signed state and derive workspace_id from the verified payload.
    try:
        workspace_id = verify_state(state)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid state parameter")

    _require_configured()

    # Exchange code for tokens
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            MS_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.MICROSOFT_CLIENT_ID,
                "client_secret": settings.MICROSOFT_CLIENT_SECRET,
                "redirect_uri": _build_redirect_uri(),
                "grant_type": "authorization_code",
                "scope": " ".join(OUTLOOK_SCOPES),
            },
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Token exchange failed")
        token_data = resp.json()

    access_token: str = token_data["access_token"]
    refresh_token: str | None = token_data.get("refresh_token")

    # Fetch the Graph profile to get the mailbox address. `mail` is the primary
    # SMTP address; it is null for some personal accounts and unlicensed users,
    # where userPrincipalName is the sign-in address.
    async with httpx.AsyncClient() as client:
        profile_resp = await client.get(
            f"{GRAPH_API_BASE}/me",
            params={"$select": "mail,userPrincipalName"},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        profile_resp.raise_for_status()
        profile = profile_resp.json()

    external_email: str | None = profile.get("mail") or profile.get("userPrincipalName")

    # Encrypt tokens
    encrypted_access = encrypt_token(access_token)
    encrypted_refresh = encrypt_token(refresh_token) if refresh_token else None

    # Upsert connectors row
    result = await db.execute(
        select(Connector).where(
            Connector.workspace_id == workspace_id,
            Connector.service == "outlook",
            Connector.external_email == external_email,
        )
    )
    connector = result.scalar_one_or_none()

    if connector is None:
        connector = Connector(
            workspace_id=workspace_id,
            service="outlook",
            encrypted_token=encrypted_access,
            refresh_token=encrypted_refresh,
            external_email=external_email,
        )
        db.add(connector)
    else:
        connector.encrypted_token = encrypted_access
        if encrypted_refresh:
            connector.refresh_token = encrypted_refresh
        db.add(connector)

    await db.commit()

    redirect_url = f"{settings.FRONTEND_URL.rstrip('/')}/connectors?connected=outlook"
    return RedirectResponse(url=redirect_url)


# ── 3. Trigger sync ──────────────────────────────────────────────


@router.post("/workspaces/{workspace_id}/connectors/outlook/sync")
async def outlook_sync(
    workspace_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    # A workspace can hold several Outlook connectors (one per mailbox address);
    # sync the most recently connected rather than letting scalar_one_or_none
    # raise MultipleResultsFound.
    result = await db.execute(
        select(Connector)
        .where(
            Connector.workspace_id == workspace_id,
            Connector.service == "outlook",
        )
        .order_by(Connector.created_at.desc())
        .limit(1)
    )
    connector = result.scalar_one_or_none()
    if connector is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Outlook connector not found")

    # Import here to avoid circular imports at module load
    from app.workers.ingest import process_outlook_sync
    from app.routers.agents import _mark_job_dispatched

    task = process_outlook_sync.delay(str(connector.id))
    _mark_job_dispatched(task.id, str(workspace_id))
    return {"job_id": task.id}
