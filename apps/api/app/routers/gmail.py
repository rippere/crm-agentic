"""
Gmail OAuth router.

Endpoints:
  GET  /workspaces/{id}/connectors/gmail/auth       — build OAuth URL
  GET  /auth/gmail/callback                          — exchange code, store tokens
  POST /workspaces/{id}/connectors/gmail/sync        — trigger Celery ingest
  POST /workspaces/{id}/connectors/gmail/subscribe   — set up Gmail push notifications
  POST /webhooks/gmail/push                          — receive Pub/Sub push notifications
  DELETE /workspaces/{id}/connectors/{connector_id}  — remove connector
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import uuid as uuid_mod
from urllib.parse import urlencode

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import httpx

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.connector import Connector
from app.models.user import User
from app.services.crypto import decrypt_token, encrypt_token
from app.services.oauth_state import build_state, verify_state

logger = logging.getLogger(__name__)

router = APIRouter()


async def _derive_connector_status(db: AsyncSession, connector: Connector) -> str:
    """Derive a connector's status from real state instead of hardcoding 'active'.

    - "error"  if a recent connector_auth_error ActivityEvent exists for the
               workspace+connector (e.g. Slack token revoked — persisted by the
               ingest worker), or the connector has no token.
    - "pending" if it has never synced.
    - "stale"  if the last sync is older than 24h.
    - "active" otherwise.
    """
    from datetime import datetime, timedelta, timezone

    from app.models.activity_event import ActivityEvent

    if not getattr(connector, "encrypted_token", None):
        return "error"

    try:
        recent = await db.execute(
            select(ActivityEvent)
            .where(
                ActivityEvent.workspace_id == connector.workspace_id,
                ActivityEvent.type == "connector_auth_error",
                ActivityEvent.meta.like(f"%connector_id={connector.id}%"),
            )
            .order_by(ActivityEvent.created_at.desc())
            .limit(1)
        )
        evt = recent.scalar_one_or_none()
    except Exception:  # noqa: BLE001 — status derivation must never 500 the endpoint
        evt = None

    if evt is not None:
        # An auth error supersedes a later successful sync only if it post-dates it.
        if connector.last_sync is None or (
            evt.created_at is not None and evt.created_at >= connector.last_sync
        ):
            return "error"

    if connector.last_sync is None:
        return "pending"

    if connector.last_sync < datetime.now(tz=timezone.utc) - timedelta(hours=24):
        return "stale"

    return "active"


GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "openid",
    "email",
]


def _build_redirect_uri() -> str:
    return f"{settings.API_URL.rstrip('/')}/auth/gmail/callback"


# ── 1. Initiate OAuth ────────────────────────────────────────────


@router.get("/workspaces/{workspace_id}/connectors/gmail/auth")
async def gmail_auth_url(
    workspace_id: uuid_mod.UUID,
    current_user: User = Depends(get_current_user),
) -> dict:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    state = build_state(workspace_id)

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
    # Verify the signed state and derive workspace_id from the verified payload.
    try:
        workspace_id = verify_state(state)
    except ValueError:
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
            "status": await _derive_connector_status(db, c),
            "last_sync": c.last_sync.isoformat() if c.last_sync else None,
            "message_count": c.message_count,
        }
        for c in rows
    ]


@router.get("/workspaces/{workspace_id}/connectors/{connector_id}/status")
async def connector_status(
    workspace_id: uuid_mod.UUID,
    connector_id: uuid_mod.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
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

    return {
        "id": str(connector.id),
        "service": connector.service,
        "status": await _derive_connector_status(db, connector),
        "external_email": connector.external_email,
        "message_count": connector.message_count,
        "task_count": connector.task_count,
        "last_sync": connector.last_sync.isoformat() if connector.last_sync else None,
        "created_at": connector.created_at.isoformat(),
    }


_GMAIL_WATCH_URL = "https://gmail.googleapis.com/gmail/v1/users/me/watch"
_GMAIL_STOP_URL = "https://gmail.googleapis.com/gmail/v1/users/me/stop"


@router.post("/workspaces/{workspace_id}/connectors/gmail/subscribe")
async def gmail_subscribe(
    workspace_id: uuid_mod.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Register a Gmail push subscription via users.watch().

    Calls the Gmail API to set up Pub/Sub push notifications for the workspace's
    Gmail connector. Requires GMAIL_PUBSUB_TOPIC to be configured.

    Returns the watch response (historyId, expiration).
    """
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if not settings.GMAIL_PUBSUB_TOPIC:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GMAIL_PUBSUB_TOPIC not configured",
        )

    result = await db.execute(
        select(Connector).where(
            Connector.workspace_id == workspace_id,
            Connector.service == "gmail",
        )
    )
    connector = result.scalar_one_or_none()
    if connector is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gmail connector not found")

    try:
        access_token = decrypt_token(connector.encrypted_token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not decrypt connector token",
        )

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            _GMAIL_WATCH_URL,
            json={
                "topicName": settings.GMAIL_PUBSUB_TOPIC,
                "labelIds": ["INBOX"],
            },
            headers={"Authorization": f"Bearer {access_token}"},
        )

    if resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Gmail watch failed: {resp.text}",
        )

    watch_data = resp.json()
    logger.info(
        "gmail_watch_registered connector=%s expiration=%s",
        connector.id,
        watch_data.get("expiration"),
    )
    return {
        "connector_id": str(connector.id),
        "history_id": watch_data.get("historyId"),
        "expiration": watch_data.get("expiration"),
    }


def _verify_pubsub_secret(request_secret: str | None) -> bool:
    """Verify the shared secret in the push URL matches our configured value.

    Returns True if GMAIL_WEBHOOK_SECRET is empty (dev mode) or if the
    provided secret matches.
    """
    if not settings.GMAIL_WEBHOOK_SECRET:
        return True  # no secret configured — accept all (dev/test only)
    if not request_secret:
        return False
    return hmac.compare_digest(settings.GMAIL_WEBHOOK_SECRET, request_secret)


async def _trigger_ingest_for_email(email: str, db: AsyncSession) -> str | None:
    """Find the Gmail connector matching the push email and enqueue a sync."""
    result = await db.execute(
        select(Connector).where(
            Connector.service == "gmail",
            Connector.external_email == email,
        )
    )
    connector = result.scalar_one_or_none()
    if connector is None:
        logger.warning("gmail_push_no_connector email=%s", email)
        return None

    from app.workers.ingest import process_gmail_sync

    task = process_gmail_sync.delay(str(connector.id))
    logger.info("gmail_push_ingest_queued connector=%s job=%s", connector.id, task.id)
    return task.id


@router.post("/webhooks/gmail/push", status_code=204)
async def gmail_push_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    secret: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Receive Google Pub/Sub push notifications from Gmail.

    Google delivers a POST request with a JSON body:
      {
        "message": {
          "data": "<base64-encoded JSON>",   # {"emailAddress": "...", "historyId": "..."}
          "messageId": "...",
          "publishTime": "..."
        },
        "subscription": "projects/.../subscriptions/..."
      }

    We verify the shared secret, decode the payload, and enqueue a Celery
    ingest task for the matching connector.  Always returns 204 so Pub/Sub
    does not retry — errors are logged rather than returned as HTTP errors.
    """
    if not _verify_pubsub_secret(secret):
        logger.warning("gmail_push_invalid_secret remote=%s", request.client)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid webhook secret")

    try:
        body = await request.json()
        message = body.get("message", {})
        raw_data = message.get("data", "")
        # Pub/Sub base64-encodes the payload; add padding if needed
        padding = "=" * (-len(raw_data) % 4)
        payload_bytes = base64.urlsafe_b64decode(raw_data + padding)
        payload = json.loads(payload_bytes.decode())
        email_address: str = payload.get("emailAddress", "")
    except Exception as exc:
        logger.warning("gmail_push_decode_error err=%s", exc)
        # Return 204 so Pub/Sub doesn't retry — the message is malformed
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    if not email_address:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    background_tasks.add_task(_trigger_ingest_for_email, email_address, db)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
