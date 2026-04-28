"""
Gmail OAuth router.

Endpoints:
  GET  /workspaces/{id}/connectors/gmail/auth    — build OAuth URL
  GET  /auth/gmail/callback                       — exchange code, store tokens
  POST /workspaces/{id}/connectors/gmail/sync    — trigger Celery ingest
  DELETE /workspaces/{id}/connectors/{connector_id} — remove connector
"""
from __future__ import annotations

import base64
import json
import uuid as uuid_mod
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import httpx

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.connector import Connector
from app.models.user import User
from app.services.crypto import encrypt_token

router = APIRouter()

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "openid",
    "email",
]


def _build_redirect_uri() -> str:
    return f"{settings.FRONTEND_URL.rstrip('/')}/auth/gmail/callback"


# ── 1. Initiate OAuth ────────────────────────────────────────────


@router.get("/workspaces/{workspace_id}/connectors/gmail/auth")
async def gmail_auth_url(
    workspace_id: uuid_mod.UUID,
    current_user: User = Depends(get_current_user),
) -> dict:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    state_payload = json.dumps({"wid": str(workspace_id), "csrf": str(uuid_mod.uuid4())})
    state = base64.urlsafe_b64encode(state_payload.encode()).decode()

    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": _build_redirect_uri(),
        "response_type": "code",
        "scope": " ".join(GMAIL_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    auth_url = f"{GOOGLE_AUTH_URL}?{urlencode(params)}"
    return {"auth_url": auth_url}


# ── 2. OAuth Callback ────────────────────────────────────────────


@router.get("/auth/gmail/callback")
async def gmail_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    # Decode state
    try:
        state_data = json.loads(base64.urlsafe_b64decode(state).decode())
        workspace_id = uuid_mod.UUID(state_data["wid"])
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid state parameter")

    # Exchange code for tokens
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uri": _build_redirect_uri(),
                "grant_type": "authorization_code",
            },
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Token exchange failed")
        token_data = resp.json()

    access_token: str = token_data["access_token"]
    refresh_token: str | None = token_data.get("refresh_token")

    # Fetch Gmail profile to get the email
    async with httpx.AsyncClient() as client:
        profile_resp = await client.get(
            "https://gmail.googleapis.com/gmail/v1/users/me/profile",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        profile_resp.raise_for_status()
        profile = profile_resp.json()

    external_email: str | None = profile.get("emailAddress")

    # Encrypt tokens
    encrypted_access = encrypt_token(access_token)
    encrypted_refresh = encrypt_token(refresh_token) if refresh_token else None

    # Upsert connectors row
    result = await db.execute(
        select(Connector).where(
            Connector.workspace_id == workspace_id,
            Connector.service == "gmail",
            Connector.external_email == external_email,
        )
    )
    connector = result.scalar_one_or_none()

    if connector is None:
        connector = Connector(
            workspace_id=workspace_id,
            service="gmail",
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

    redirect_url = f"{settings.FRONTEND_URL.rstrip('/')}/connectors?connected=gmail"
    return RedirectResponse(url=redirect_url)


# ── 3. Trigger sync ──────────────────────────────────────────────


@router.post("/workspaces/{workspace_id}/connectors/gmail/sync")
async def gmail_sync(
    workspace_id: uuid_mod.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    result = await db.execute(
        select(Connector).where(
            Connector.workspace_id == workspace_id,
            Connector.service == "gmail",
        )
    )
    connector = result.scalar_one_or_none()
    if connector is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gmail connector not found")

    # Import here to avoid circular imports at module load
    from app.workers.ingest import process_gmail_sync

    task = process_gmail_sync.delay(str(connector.id))
    return {"job_id": task.id}


# ── 4. Delete connector ──────────────────────────────────────────


@router.get("/workspaces/{workspace_id}/connectors")
async def list_connectors(
    workspace_id: uuid_mod.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    result = await db.execute(
        select(Connector).where(Connector.workspace_id == workspace_id)
    )
    rows = result.scalars().all()
    return [
        {
            "id": str(c.id),
            "service": c.service,
            "status": "active",
            "last_sync": c.last_sync.isoformat() if c.last_sync else None,
            "message_count": c.message_count,
        }
        for c in rows
    ]


@router.delete("/workspaces/{workspace_id}/connectors/{connector_id}")
async def delete_connector(
    workspace_id: uuid_mod.UUID,
    connector_id: uuid_mod.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    result = await db.execute(
        select(Connector).where(
            Connector.id == connector_id,
            Connector.workspace_id == workspace_id,
        )
    )
    connector = result.scalar_one_or_none()
    if connector is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector not found")

    await db.delete(connector)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
