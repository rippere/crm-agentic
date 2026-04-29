"""
POST /slack/interactions — handles Slack Block Kit button clicks for HITL approval.

Slack sends a form-encoded `payload` parameter containing a JSON string.
We verify the request signature, parse the action, and either:
  - approve: send the email via Gmail and mark the event resolved
  - dismiss: mark the event dismissed
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid

from fastapi import APIRouter, Form, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from app.config import settings
from app.database import get_db
from app.models.activity_event import ActivityEvent

router = APIRouter()


def _verify_slack_signature(body: bytes, timestamp: str, signature: str) -> bool:
    if not settings.SLACK_SIGNING_SECRET:
        return True  # Skip verification if not configured
    if abs(time.time() - float(timestamp)) > 300:
        return False
    base = f"v0:{timestamp}:{body.decode()}"
    expected = "v0=" + hmac.new(
        key=settings.SLACK_SIGNING_SECRET.encode(),
        msg=base.encode(),
        digestmod=hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.post("/slack/interactions")
async def slack_interactions(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_slack_request_timestamp: str = Header(default="0"),
    x_slack_signature: str = Header(default=""),
) -> dict:
    body = await request.body()
    if not _verify_slack_signature(body, x_slack_request_timestamp, x_slack_signature):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid Slack signature")

    form = await request.form()
    payload_raw = form.get("payload", "")
    if not payload_raw:
        return {"ok": True}

    payload = json.loads(str(payload_raw))
    actions = payload.get("actions", [])
    if not actions:
        return {"ok": True}

    action = actions[0]
    action_id: str = action.get("action_id", "")
    hitl_id: str = action.get("value", "")

    if action_id not in ("hitl_approve", "hitl_dismiss"):
        return {"ok": True}

    # Look up the pending HITL event
    result = await db.execute(
        select(ActivityEvent).where(
            ActivityEvent.type == "hitl_pending",
            ActivityEvent.meta.like(f'%"hitl_id": "{hitl_id}"%'),
        ).limit(1)
    )
    event = result.scalar_one_or_none()
    if event is None:
        return {"ok": True}

    meta = json.loads(event.meta or "{}")

    if action_id == "hitl_dismiss":
        event.type = "hitl_dismissed"
        event.severity = "warning"
        db.add(event)
        await db.commit()
        return {"ok": True}

    # Approve: send the email via Gmail
    workspace_id = uuid.UUID(meta["workspace_id"])
    from app.models.connector import Connector
    from app.services.gmail_client import GmailClient

    gmail_result = await db.execute(
        select(Connector).where(
            Connector.workspace_id == workspace_id,
            Connector.service == "gmail",
        )
    )
    connector = gmail_result.scalar_one_or_none()
    if connector is None:
        return {"ok": True, "error": "no_gmail_connector"}

    gmail = GmailClient(
        connector=connector,
        db=db,
        google_client_id=settings.GOOGLE_CLIENT_ID,
        google_client_secret=settings.GOOGLE_CLIENT_SECRET,
    )
    try:
        await gmail.send_message(
            to=meta["to"],
            subject=meta["subject"],
            body=meta["body"],
        )
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

    event.type = "hitl_approved"
    event.severity = "success"
    event.description = f"HITL approved & sent to {meta['to']}"
    db.add(event)

    sent_event = ActivityEvent(
        workspace_id=workspace_id,
        type="email_sent",
        agent_name="FollowupAgent",
        description=f"HITL follow-up sent to {meta['to']}: {meta['subject']}",
        meta=f"contact:{meta.get('contact_id', '')}",
        severity="success",
    )
    db.add(sent_event)
    await db.commit()

    return {"ok": True}
