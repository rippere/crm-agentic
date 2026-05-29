"""
POST /slack/interactions — handles Slack Block Kit button clicks for HITL approval.

Slack sends a form-encoded `payload` parameter containing a JSON string.
We verify the request signature, parse the action, and:
  - Return HTTP 200 immediately (Slack requires a response within 3 seconds)
  - Dispatch the real work as a FastAPI BackgroundTask so we never block the ack

The background task either:
  - approve: sends the email via Gmail, marks the event resolved, updates the
             contact's last_activity, then posts a confirmation back to Slack
             via the interaction's response_url to replace the buttons.
  - dismiss: marks the event dismissed and replaces the Slack message with a
             "dismissed" notice.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Form, Header, HTTPException, Request, status, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.activity_event import ActivityEvent
from app.models.connector import Connector
from app.models.contact import Contact
from app.services.gmail_client import GmailClient
from app.services.slack_client import SlackClient

router = APIRouter()


def _verify_slack_signature(body: bytes, timestamp: str, signature: str) -> bool:
    # Fail closed: without a configured signing secret we cannot authenticate the
    # request, so we must reject it. (A forged POST could otherwise send email via
    # the victim's Gmail connector.) Prod sets SLACK_SIGNING_SECRET.
    if not settings.SLACK_SIGNING_SECRET:
        return False
    if not signature or not timestamp:
        return False
    try:
        if abs(time.time() - float(timestamp)) > 300:
            return False
    except (TypeError, ValueError):
        return False
    base = f"v0:{timestamp}:{body.decode()}"
    expected = "v0=" + hmac.new(
        key=settings.SLACK_SIGNING_SECRET.encode(),
        msg=base.encode(),
        digestmod=hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


async def _handle_dismiss(
    event: ActivityEvent,
    response_url: str | None,
    db: AsyncSession,
) -> None:
    """Mark event dismissed and replace the Slack message with a notice."""
    event.type = "hitl_dismissed"
    event.severity = "warning"
    db.add(event)
    await db.commit()

    if response_url:
        try:
            await SlackClient.ack_response_url(
                response_url,
                text=":no_entry_sign: Follow-up dismissed.",
                replace_original=True,
            )
        except Exception:
            pass


async def _handle_approve(
    event: ActivityEvent,
    meta: dict,
    response_url: str | None,
    db: AsyncSession,
) -> None:
    """Send email via Gmail, update contact last_activity, emit sent event,
    and replace the Slack message with a success notice."""
    workspace_id = uuid.UUID(meta["workspace_id"])

    # Resolve Gmail connector
    gmail_result = await db.execute(
        select(Connector).where(
            Connector.workspace_id == workspace_id,
            Connector.service == "gmail",
        )
    )
    connector = gmail_result.scalar_one_or_none()

    if connector is None:
        # Log as error and notify Slack
        event.type = "hitl_error"
        event.severity = "error"
        event.description = "HITL approval failed: no Gmail connector configured"
        db.add(event)
        await db.commit()
        if response_url:
            try:
                await SlackClient.ack_response_url(
                    response_url,
                    text=":warning: Could not send — no Gmail connector found for this workspace.",
                    replace_original=True,
                )
            except Exception:
                pass
        return

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
        event.type = "hitl_error"
        event.severity = "error"
        event.description = f"HITL approval failed (Gmail error): {exc}"
        db.add(event)
        await db.commit()
        if response_url:
            try:
                await SlackClient.ack_response_url(
                    response_url,
                    text=f":warning: Email send failed: {exc}",
                    replace_original=True,
                )
            except Exception:
                pass
        return

    # Mark HITL event resolved
    event.type = "hitl_approved"
    event.severity = "success"
    event.description = f"HITL approved & sent to {meta['to']}"
    db.add(event)

    # Emit email_sent activity event
    sent_event = ActivityEvent(
        workspace_id=workspace_id,
        type="email_sent",
        agent_name="FollowupAgent",
        description=f"HITL follow-up sent to {meta['to']}: {meta['subject']}",
        meta=f"contact:{meta.get('contact_id', '')}",
        severity="success",
    )
    db.add(sent_event)

    # Update contact last_activity so the CRM reflects the outreach
    contact_id_str = meta.get("contact_id")
    if contact_id_str:
        try:
            contact_id = uuid.UUID(contact_id_str)
            contact_result = await db.execute(
                select(Contact).where(Contact.id == contact_id)
            )
            contact = contact_result.scalar_one_or_none()
            if contact is not None:
                now_label = datetime.now(timezone.utc).strftime("%b %d, %Y")
                contact.last_activity = f"Email sent {now_label}"
                db.add(contact)
        except Exception:
            pass  # Non-fatal: activity update failure must not block the send

    await db.commit()

    # Replace the Slack message with a confirmation
    if response_url:
        try:
            await SlackClient.ack_response_url(
                response_url,
                text=f":white_check_mark: Follow-up email sent to *{meta['to']}* — _{meta['subject']}_",
                replace_original=True,
            )
        except Exception:
            pass


@router.post("/slack/interactions")
async def slack_interactions(
    request: Request,
    background_tasks: BackgroundTasks,
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

    # hitl_id is server-minted as str(uuid.uuid4()) (canonical dashed form) and
    # stored verbatim in the event meta JSON. Re-parse it to the same canonical
    # form so a forged value can never smuggle LIKE wildcards ('%' / '_') into the
    # lookup below. Canonical UUID output contains only hex digits and dashes.
    try:
        hitl_id = str(uuid.UUID(hitl_id))
    except (ValueError, AttributeError, TypeError):
        return {"ok": True}

    # response_url lets us update the original Slack message after we ack
    response_url: str | None = payload.get("response_url")

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

    # Dispatch the real work in the background so Slack gets its 3-second ack.
    if action_id == "hitl_dismiss":
        background_tasks.add_task(_handle_dismiss, event, response_url, db)
    else:
        background_tasks.add_task(_handle_approve, event, meta, response_url, db)

    # Immediate 200 ack to Slack — no body needed, but {"ok": True} is safe.
    return {"ok": True}
