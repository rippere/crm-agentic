"""
Celery task: check_stale_deals_hitl

For each workspace with Slack + Gmail connectors:
  1. Find active deals with health_score <= 40 that haven't had a HITL request in 7 days
  2. Generate a follow-up email draft via Claude
  3. Post to Slack as an interactive Block Kit message for human approval
  4. Store a hitl_pending ActivityEvent so the interactions endpoint can resolve it
"""
from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.workers.celery_app import celery_app


def _make_session() -> async_sessionmaker[AsyncSession]:
    url = os.getenv("DATABASE_URL", "")
    if not url:
        url = os.getenv("SUPABASE_URL", "").replace("postgres://", "postgresql+asyncpg://", 1)
    return async_sessionmaker(
        create_async_engine(url, echo=False),
        class_=AsyncSession,
        expire_on_commit=False,
    )


async def _draft_email(deal_title: str, company: str, contact_name: str, stage: str) -> dict[str, str]:
    import anthropic
    client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
    prompt = (
        f"You are a sales assistant. Write a brief, professional follow-up email for the deal "
        f'"{deal_title}" with {company}. The contact name is {contact_name or "there"} and '
        f"the deal is currently in the {stage} stage. The email should re-engage, reference "
        f"next steps, and invite a response. Keep it under 120 words. "
        f"Respond with JSON: {{\"subject\": \"...\", \"body\": \"...\"}}"
    )
    message = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = message.content[0].text.strip()
    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw)


async def _run_hitl() -> dict[str, Any]:
    from app.models.deal import Deal
    from app.models.connector import Connector
    from app.models.contact import Contact
    from app.models.activity_event import ActivityEvent
    from app.services.slack_client import SlackClient
    from app.config import settings

    factory = _make_session()
    processed = 0
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=7)

    async with factory() as db:
        # Get all workspaces that have both Slack and Gmail connectors
        slack_result = await db.execute(
            select(Connector).where(Connector.service == "slack")
        )
        slack_connectors = {c.workspace_id: c for c in slack_result.scalars().all()}

        gmail_result = await db.execute(
            select(Connector).where(Connector.service == "gmail")
        )
        gmail_connectors = {c.workspace_id: c for c in gmail_result.scalars().all()}

        eligible_workspaces = set(slack_connectors) & set(gmail_connectors)

        for ws_id in eligible_workspaces:
            # Find stale deals
            deal_result = await db.execute(
                select(Deal).where(
                    Deal.workspace_id == ws_id,
                    Deal.health_score <= 40,
                    Deal.stage.not_in(["closed_won", "closed_lost"]),
                ).limit(5)
            )
            stale_deals = deal_result.scalars().all()

            for deal in stale_deals:
                # Skip if we already sent a HITL for this deal recently
                recent_result = await db.execute(
                    select(ActivityEvent).where(
                        ActivityEvent.workspace_id == ws_id,
                        ActivityEvent.type == "hitl_pending",
                        ActivityEvent.meta.like(f'%"deal_id": "{deal.id}"%'),
                        ActivityEvent.created_at >= cutoff,
                    ).limit(1)
                )
                if recent_result.scalar_one_or_none():
                    continue

                # Resolve contact info
                contact_name = deal.contact_name or "there"
                contact_email: str | None = None
                if deal.contact_id:
                    contact_result = await db.execute(
                        select(Contact).where(Contact.id == deal.contact_id)
                    )
                    contact = contact_result.scalar_one_or_none()
                    if contact:
                        contact_name = contact.name or contact_name
                        contact_email = contact.email

                if not contact_email:
                    continue  # Can't send without an email

                # Generate draft via Claude
                try:
                    draft = await _draft_email(
                        deal_title=deal.title or "your deal",
                        company=deal.company or "your company",
                        contact_name=contact_name,
                        stage=deal.stage,
                    )
                except Exception:
                    continue

                # Persist HITL pending event
                hitl_id = str(uuid.uuid4())
                meta_payload = json.dumps({
                    "hitl_id": hitl_id,
                    "deal_id": str(deal.id),
                    "workspace_id": str(ws_id),
                    "contact_id": str(deal.contact_id) if deal.contact_id else None,
                    "to": contact_email,
                    "subject": draft["subject"],
                    "body": draft["body"],
                })
                event = ActivityEvent(
                    workspace_id=ws_id,
                    type="hitl_pending",
                    agent_name="FollowupAgent",
                    description=f"HITL follow-up draft for: {deal.title}",
                    meta=meta_payload,
                    severity="info",
                )
                db.add(event)
                await db.flush()

                # Post to Slack
                slack_conn = slack_connectors[ws_id]
                slack = SlackClient(slack_conn)
                channel = settings.SLACK_HITL_CHANNEL
                body_preview = (draft["body"][:200] + "…") if len(draft["body"]) > 200 else draft["body"]
                try:
                    await slack.post_hitl_block(
                        channel=channel,
                        deal_title=deal.title or "Deal",
                        company=deal.company or "",
                        subject=draft["subject"],
                        body_preview=body_preview,
                        approve_value=hitl_id,
                        dismiss_value=hitl_id,
                    )
                    processed += 1
                except Exception:
                    pass

        await db.commit()

    return {"hitl_sent": processed}


@celery_app.task(name="app.workers.followup_sequences.check_stale_deals_hitl", bind=True)
def check_stale_deals_hitl(self: Any) -> dict[str, Any]:
    """Find stale deals, draft follow-up emails via Claude, post to Slack for approval."""
    return asyncio.get_event_loop().run_until_complete(_run_hitl())
