"""
Slack OAuth router.

Endpoints:
  GET  /workspaces/{id}/connectors/slack/auth    — build OAuth URL
  GET  /auth/slack/callback                       — exchange code, store tokens
  POST /workspaces/{id}/connectors/slack/sync    — trigger Celery ingest
  POST /workspaces/{id}/connectors/slack/subscribe — verify Events API URL
  POST /webhooks/slack/events                     — receive Slack Events API events
"""

import hashlib
import hmac
import logging
import time
import uuid
from uuid import UUID
from urllib.parse import urlencode

from fastapi import APIRouter, BackgroundTasks, Body, Depends, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse, RedirectResponse
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

logger = logging.getLogger(__name__)

router = APIRouter()

SLACK_AUTH_URL = "https://slack.com/oauth/v2/authorize"
SLACK_TOKEN_URL = "https://slack.com/api/oauth.v2.access"

SLACK_USER_SCOPES = [
    "channels:read",
    "channels:history",
    "chat:write",
    "groups:read",
    "groups:history",
    "im:read",
    "im:history",
    "mpim:read",
    "mpim:history",
    "users:read",
    "users:read.email",
]


def _build_redirect_uri() -> str:
    return f"{settings.API_URL.rstrip('/')}/auth/slack/callback"


# ── 1. Initiate OAuth ────────────────────────────────────────────


@router.get("/workspaces/{workspace_id}/connectors/slack/auth")
async def slack_auth_url(
    workspace_id: UUID,
    current_user: User = Depends(get_current_user),
) -> dict:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    params = {
        "client_id": settings.SLACK_CLIENT_ID,
        "user_scope": ",".join(SLACK_USER_SCOPES),
        "redirect_uri": _build_redirect_uri(),
        "state": build_state(workspace_id),
    }
    return {"auth_url": f"{SLACK_AUTH_URL}?{urlencode(params)}"}


# ── 2. OAuth Callback ────────────────────────────────────────────


@router.get("/auth/slack/callback")
async def slack_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    # Verify the signed state and derive workspace_id from the verified payload.
    try:
        workspace_id = verify_state(state)
    except ValueError:
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

    # Resolve email via users.info (requires users:read.email scope)
    external_email: str | None = None
    async with httpx.AsyncClient() as client:
        profile_resp = await client.get(
            f"https://slack.com/api/users.info?user={slack_user_id}",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        profile = profile_resp.json()
        if profile.get("ok"):
            external_email = profile.get("user", {}).get("profile", {}).get("email")

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
    workspace_id: UUID,
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
    from app.routers.agents import _mark_job_dispatched

    task = process_slack_sync.delay(str(connector.id))
    _mark_job_dispatched(task.id, str(workspace_id))
    return {"job_id": task.id}


# ---------------------------------------------------------------------------
# Slack Events API — push webhook
# ---------------------------------------------------------------------------


def _verify_slack_signature(
    body: bytes,
    timestamp: str | None,
    signature: str | None,
    signing_secret: str,
) -> bool:
    """Verify Slack request signature using HMAC-SHA256.

    Slack signs each request with HMAC-SHA256(signing_secret, "v0:{ts}:{body}").
    We also check that the timestamp is within 5 minutes to prevent replay attacks.

    Fails closed when SLACK_SIGNING_SECRET is empty: without it we cannot
    authenticate the request, so we reject it (an unauthenticated POST to
    /webhooks/slack/events would otherwise trigger a Slack sync for any team_id).
    """
    if not signing_secret:
        return False  # fail closed — no signing secret means we cannot verify
    if not timestamp or not signature:
        return False
    try:
        ts = int(timestamp)
    except ValueError:
        return False
    if abs(time.time() - ts) > 300:
        return False  # replay attack window
    base = f"v0:{timestamp}:{body.decode('utf-8', errors='replace')}"
    expected = "v0=" + hmac.new(  # type: ignore[attr-defined]
        signing_secret.encode(), base.encode(), hashlib.sha256
    ).hexdigest()
    try:
        return hmac.compare_digest(expected, signature)
    except TypeError:
        return False  # non-ASCII signature -> treat as mismatch, never surface a 500


async def _trigger_slack_ingest_for_team(team_id: str, db: AsyncSession) -> str | None:
    """Find the Slack connector matching the team, enqueue a sync, and log the event."""
    from app.models.webhook_log import WebhookLog

    result = await db.execute(
        select(Connector).where(
            Connector.service == "slack",
            Connector.external_email == team_id,
        )
    )
    connector = result.scalar_one_or_none()

    if connector is None:
        logger.warning("slack_push_no_connector team_id=%s", team_id)
        db.add(WebhookLog(
            source="slack",
            event_type="event_callback",
            status="received",
            payload_summary=f"team={team_id} connector=not_found",
        ))
        await db.commit()
        return None

    from app.workers.slack_ingest import process_slack_sync
    from app.routers.agents import _mark_job_dispatched

    task = process_slack_sync.delay(str(connector.id))
    _mark_job_dispatched(task.id, str(connector.workspace_id))
    db.add(WebhookLog(
        workspace_id=connector.workspace_id,
        source="slack",
        event_type="event_callback",
        status="queued",
        payload_summary=f"team={team_id}",
        job_id=task.id,
    ))
    await db.commit()
    logger.info("slack_push_ingest_queued connector=%s job=%s", connector.id, task.id)
    return task.id


@router.post("/webhooks/slack/events", status_code=200)
async def slack_events_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_slack_request_timestamp: str | None = Header(default=None),
    x_slack_signature: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Receive Slack Events API payloads.

    Handles:
    - url_verification challenge (Slack sends during app setup)
    - event_callback for message events (triggers Celery ingest)

    Slack signs each request; we verify with HMAC-SHA256 before processing.
    Configure SLACK_SIGNING_SECRET to enable signature verification.
    """
    raw_body = await request.body()

    if not _verify_slack_signature(
        raw_body,
        x_slack_request_timestamp,
        x_slack_signature,
        settings.SLACK_SIGNING_SECRET,
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Slack signature")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON")

    event_type = payload.get("type")

    # Slack sends a url_verification challenge when the endpoint is first registered
    if event_type == "url_verification":
        from app.models.webhook_log import WebhookLog
        db.add(WebhookLog(
            source="slack",
            event_type="url_verification",
            status="received",
            payload_summary="Slack URL verification challenge",
        ))
        await db.commit()
        return {"challenge": payload.get("challenge")}

    if event_type == "event_callback":
        team_id: str | None = payload.get("team_id")
        if team_id:
            background_tasks.add_task(_trigger_slack_ingest_for_team, team_id, db)
        logger.info("slack_event_received team=%s type=%s", team_id, payload.get("event", {}).get("type"))

    return {"ok": True}
