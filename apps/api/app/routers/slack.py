"""
Slack OAuth router.

Endpoints:
  GET  /workspaces/{id}/connectors/slack/auth    — build OAuth URL
  GET  /auth/slack/callback                       — exchange code, store tokens
  POST /workspaces/{id}/connectors/slack/sync    — trigger Celery ingest
"""
from __future__ import annotations

import uuid as uuid_mod
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

router = APIRouter()

SLACK_AUTH_URL = "https://slack.com/oauth/v2/authorize"
SLACK_TOKEN_URL = "https://slack.com/api/oauth.v2.access"

SLACK_USER_SCOPES = [
    "channels:read",
    "channels:history",
    "groups:read",
    "groups:history",
    "im:read",
    "im:history",
    "mpim:read",
    "mpim:history",
    "users:read",
    "users:read.email",
    "identity.basic",
    "identity.email",
]


def _build_redirect_uri() -> str:
    return f"{settings.FRONTEND_URL.rstrip('/')}/auth/slack/callback"


# ── 1. Initiate OAuth ────────────────────────────────────────────


@router.get("/workspaces/{workspace_id}/connectors/slack/auth")
async def slack_auth_url(
    workspace_id: uuid_mod.UUID,
    current_user: User = Depends(get_current_user),
) -> dict:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    params = {
        "client_id": settings.SLACK_CLIENT_ID,
        "user_scope": ",".join(SLACK_USER_SCOPES),
        "redirect_uri": _build_redirect_uri(),
        "state": str(workspace_id),
    }
    return {"auth_url": f"{SLACK_AUTH_URL}?{urlencode(params)}"}


# ── 2. OAuth Callback ────────────────────────────────────────────


@router.get("/auth/slack/callback")
async def slack_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    try:
        workspace_id = uuid_mod.UUID(state)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid state parameter")

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            SLACK_TOKEN_URL,
            data={"code": code, "redirect_uri": _build_redirect_uri()},
            auth=(settings.SLACK_CLIENT_ID, settings.SLACK_CLIENT_SECRET),
        )
        data = resp.json()

    if not data.get("ok"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Slack token exchange failed: {data.get('error', 'unknown')}",
        )

    authed_user: dict = data.get("authed_user", {})
    user_token: str = authed_user.get("access_token", "")
    slack_user_id: str = authed_user.get("id", "")
    team_id: str = data.get("team", {}).get("id", "")

    if not user_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No user token returned by Slack")

    # Resolve email via users.identity (requires identity.email scope)
    external_email: str | None = None
    async with httpx.AsyncClient() as client:
        identity_resp = await client.get(
            "https://slack.com/api/users.identity",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        identity = identity_resp.json()
        if identity.get("ok"):
            external_email = identity.get("user", {}).get("email")

    if not external_email:
        external_email = f"{team_id}:{slack_user_id}"

    encrypted_token = encrypt_token(user_token)

    result = await db.execute(
        select(Connector).where(
            Connector.workspace_id == workspace_id,
            Connector.service == "slack",
            Connector.external_email == external_email,
        )
    )
    connector = result.scalar_one_or_none()

    if connector is None:
        connector = Connector(
            workspace_id=workspace_id,
            service="slack",
            encrypted_token=encrypted_token,
            external_email=external_email,
        )
        db.add(connector)
    else:
        connector.encrypted_token = encrypted_token
        db.add(connector)

    await db.commit()

    return RedirectResponse(url=f"{settings.FRONTEND_URL.rstrip('/')}/connectors?connected=slack")


# ── 3. Trigger sync ──────────────────────────────────────────────


@router.post("/workspaces/{workspace_id}/connectors/slack/sync")
async def slack_sync(
    workspace_id: uuid_mod.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    result = await db.execute(
        select(Connector).where(
            Connector.workspace_id == workspace_id,
            Connector.service == "slack",
        )
    )
    connector = result.scalar_one_or_none()
    if connector is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Slack connector not found")

    from app.workers.slack_ingest import process_slack_sync

    task = process_slack_sync.delay(str(connector.id))
    return {"job_id": task.id}
