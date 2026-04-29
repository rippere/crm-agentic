import json
import uuid
from datetime import datetime

import anthropic as _anthropic
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.contact import Contact
from app.models.activity_event import ActivityEvent

router = APIRouter()


class ContactResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str | None
    email: str | None
    company: str | None
    role: str | None
    status: str
    ml_score: dict
    revenue: float
    deal_count: int
    last_activity: str

    model_config = {"from_attributes": True}


class CreateContactRequest(BaseModel):
    name: str
    email: str | None = None
    company: str | None = None
    role: str | None = None
    status: str = "lead"


@router.post("/workspaces/{workspace_id}/contacts", response_model=ContactResponse, status_code=201)
async def create_contact(
    workspace_id: uuid.UUID,
    body: CreateContactRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ContactResponse:
    """Create a new contact in the workspace."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    allowed_statuses = {"lead", "prospect", "customer", "churned"}
    if body.status not in allowed_statuses:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"status must be one of {allowed_statuses}",
        )

    contact = Contact(
        workspace_id=workspace_id,
        name=body.name,
        email=body.email,
        company=body.company,
        role=body.role,
        status=body.status,
    )
    db.add(contact)
    await db.flush()

    event = ActivityEvent(
        workspace_id=workspace_id,
        type="contact_created",
        agent_name="System",
        description=f"New contact added: {body.name}",
        severity="info",
    )
    db.add(event)
    await db.commit()
    await db.refresh(contact)

    return ContactResponse.model_validate(contact)


@router.get("/workspaces/{workspace_id}/contacts", response_model=list[ContactResponse])
async def list_contacts(
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ContactResponse]:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    result = await db.execute(select(Contact).where(Contact.workspace_id == workspace_id))
    contacts = result.scalars().all()
    return [ContactResponse.model_validate(c) for c in contacts]


@router.post("/workspaces/{workspace_id}/contacts/{contact_id}/score", status_code=status.HTTP_200_OK)
async def score_contact(
    workspace_id: uuid.UUID,
    contact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Enqueue heuristic lead scoring for a contact via Celery."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.workspace_id == workspace_id)
    )
    contact = result.scalar_one_or_none()
    if contact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    # Import here to avoid circular-import at module load time
    from app.workers.score_contact import score_lead  # noqa: PLC0415
    task = score_lead.delay(str(contact_id), str(workspace_id))

    return {"status": "queued", "contact_id": str(contact_id), "job_id": task.id}


class EmailDraftResponse(BaseModel):
    subject: str
    body: str


@router.post("/workspaces/{workspace_id}/contacts/{contact_id}/compose", response_model=EmailDraftResponse)
async def compose_email(
    workspace_id: uuid.UUID,
    contact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EmailDraftResponse:
    """
    Generate a personalised outreach email draft for a contact using Claude Sonnet.
    # TODO: needs ANTHROPIC_API_KEY in env
    """
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.workspace_id == workspace_id)
    )
    contact = result.scalar_one_or_none()
    if contact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    system_prompt = (
        "You are a sales professional. Write a personalized outreach email for the following contact. "
        'Return JSON only: {"subject": "<subject line>", "body": "<email body>"}'
    )
    user_content = (
        f"Contact name: {contact.name or 'Unknown'}\n"
        f"Company: {contact.company or 'Unknown'}\n"
        f"Role: {contact.role or 'Unknown'}\n"
        f"Status: {contact.status}\n"
        f"Semantic tags: {json.dumps(contact.semantic_tags or [])}\n"
        f"Revenue: {contact.revenue}\n"
    )

    client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        system=system_prompt,
        messages=[{"role": "user", "content": user_content}],
    )

    raw = message.content[0].text if message.content else "{}"

    # Strip markdown code fence if present
    if raw.strip().startswith("```"):
        lines = raw.strip().splitlines()
        raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    try:
        data = json.loads(raw)
        return EmailDraftResponse(subject=data.get("subject", ""), body=data.get("body", ""))
    except (json.JSONDecodeError, KeyError):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to parse email draft from Claude response",
        )


@router.post("/workspaces/{workspace_id}/contacts/{contact_id}/enrich", status_code=202)
async def enrich_contact_endpoint(
    workspace_id: uuid.UUID,
    contact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Enqueue contact enrichment: Hunter.io email lookup + Claude Haiku inference from messages."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.workspace_id == workspace_id)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    from app.workers.enrich_contact import enrich_contact
    task = enrich_contact.delay(str(contact_id))
    return {"status": "queued", "contact_id": str(contact_id), "job_id": task.id}


class ContactStatusUpdate(BaseModel):
    status: str


@router.patch("/workspaces/{workspace_id}/contacts/{contact_id}/status")
async def update_contact_status(
    workspace_id: uuid.UUID,
    contact_id: uuid.UUID,
    body: ContactStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Update a contact's status (lead/prospect/customer/churned)."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    allowed = {"lead", "prospect", "customer", "churned"}
    if body.status not in allowed:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"status must be one of {allowed}")

    result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.workspace_id == workspace_id)
    )
    contact = result.scalar_one_or_none()
    if contact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    contact.status = body.status  # type: ignore[assignment]
    db.add(contact)

    event = ActivityEvent(
        workspace_id=workspace_id,
        type="deal_moved",
        agent_name="System",
        description=f"{contact.name} flagged as {body.status}",
        severity="warning",
    )
    db.add(event)
    await db.commit()

    return {"id": str(contact_id), "status": body.status}


class SendEmailRequest(BaseModel):
    to: str
    subject: str
    body: str


@router.post("/workspaces/{workspace_id}/contacts/{contact_id}/send-email")
async def send_email(
    workspace_id: uuid.UUID,
    contact_id: uuid.UUID,
    body: SendEmailRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Send an email via the workspace's connected Gmail account."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    from app.models.connector import Connector
    from app.services.gmail_client import GmailClient
    from app.config import settings

    result = await db.execute(
        select(Connector).where(
            Connector.workspace_id == workspace_id,
            Connector.service == "gmail",
        )
    )
    connector = result.scalar_one_or_none()
    if connector is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No Gmail connector found")

    client = GmailClient(
        connector=connector,
        db=db,
        google_client_id=settings.GOOGLE_CLIENT_ID,
        google_client_secret=settings.GOOGLE_CLIENT_SECRET,
    )

    try:
        sent = await client.send_message(to=body.to, subject=body.subject, body=body.body)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Gmail error: {exc}") from exc

    event = ActivityEvent(
        workspace_id=workspace_id,
        type="email_sent",
        agent_name="Gmail",
        description=f"Email sent to {body.to}: {body.subject}",
        severity="success",
    )
    db.add(event)
    await db.commit()

    return {"message_id": sent.get("id"), "status": "sent", "to": body.to}


@router.get("/workspaces/{workspace_id}/contacts/{contact_id}/timeline")
async def contact_timeline(
    workspace_id: uuid.UUID,
    contact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """Return a chronological timeline of all activity for a contact."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    from app.models.message import Message
    from app.models.call_summary import CallSummary
    from app.models.deal import Deal
    from app.models.activity_event import ActivityEvent

    timeline: list[dict] = []

    # Messages
    msg_result = await db.execute(
        select(Message).where(
            Message.workspace_id == workspace_id,
            Message.contact_id == contact_id,
        )
    )
    for m in msg_result.scalars().all():
        ts = m.received_at or m.created_at
        timeline.append({
            "id": str(m.id),
            "type": "message",
            "title": m.subject or "(No subject)",
            "body": (m.body_plain or "")[:200],
            "ts": ts.isoformat() if ts else None,
            "meta": {"sender": m.sender_email},
        })

    # Call summaries
    call_result = await db.execute(
        select(CallSummary).where(
            CallSummary.workspace_id == workspace_id,
            CallSummary.contact_id == contact_id,
        )
    )
    for c in call_result.scalars().all():
        timeline.append({
            "id": str(c.id),
            "type": "call",
            "title": c.title,
            "body": c.summary[:200] if c.summary else "",
            "ts": c.call_date.isoformat() if c.call_date else None,
            "meta": {"duration_seconds": c.duration_seconds, "participants": c.participants},
        })

    # Deal stage events
    deal_result = await db.execute(
        select(Deal).where(
            Deal.workspace_id == workspace_id,
            Deal.contact_id == contact_id,
        )
    )
    for d in deal_result.scalars().all():
        timeline.append({
            "id": str(d.id),
            "type": "deal_stage",
            "title": f"Deal: {d.title or 'Untitled'}",
            "body": f"Stage: {d.stage} · Value: ${d.value:,.0f}",
            "ts": d.stage_changed_at.isoformat() if d.stage_changed_at else d.created_at.isoformat(),
            "meta": {"stage": d.stage, "value": float(d.value or 0)},
        })

    # Activity events linked to this contact via meta
    contact_meta = f"contact:{contact_id}"
    evt_result = await db.execute(
        select(ActivityEvent).where(
            ActivityEvent.workspace_id == workspace_id,
            ActivityEvent.meta.like(f"%{contact_meta}%"),
        )
    )
    for e in evt_result.scalars().all():
        timeline.append({
            "id": str(e.id),
            "type": "activity",
            "title": e.type or "Activity",
            "body": e.description or "",
            "ts": e.created_at.isoformat() if e.created_at else None,
            "meta": {"agent_name": e.agent_name, "severity": e.severity},
        })

    # Sort newest first
    timeline.sort(key=lambda x: x["ts"] or "", reverse=True)
    return timeline


@router.post("/workspaces/{workspace_id}/contacts/{contact_id}/brief")
async def pre_meeting_brief(
    workspace_id: uuid.UUID,
    contact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Generate a pre-meeting intelligence brief for a contact using Claude."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    from app.models.contact import Contact
    from app.models.message import Message
    from app.models.call_summary import CallSummary
    from app.models.deal import Deal
    from app.config import settings
    import anthropic

    contact_result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.workspace_id == workspace_id)
    )
    contact = contact_result.scalar_one_or_none()
    if contact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    # Gather context: recent messages (3), calls (2), active deals (3)
    msg_result = await db.execute(
        select(Message).where(
            Message.workspace_id == workspace_id,
            Message.contact_id == contact_id,
        ).order_by(Message.received_at.desc()).limit(3)
    )
    messages = msg_result.scalars().all()

    call_result = await db.execute(
        select(CallSummary).where(
            CallSummary.workspace_id == workspace_id,
            CallSummary.contact_id == contact_id,
        ).order_by(CallSummary.call_date.desc()).limit(2)
    )
    calls = call_result.scalars().all()

    deal_result = await db.execute(
        select(Deal).where(
            Deal.workspace_id == workspace_id,
            Deal.contact_id == contact_id,
            Deal.stage.not_in(["closed_lost"]),
        ).limit(3)
    )
    deals = deal_result.scalars().all()

    context_parts = [
        f"Contact: {contact.name} ({contact.email}), {contact.role} at {contact.company}",
        f"Status: {contact.status}",
    ]
    if messages:
        context_parts.append("Recent emails:")
        for m in messages:
            context_parts.append(f"  - Subject: {m.subject or '(none)'}")
    if calls:
        context_parts.append("Recent calls:")
        for c in calls:
            context_parts.append(f"  - {c.title}: {c.summary[:300] if c.summary else '(no summary)'}")
    if deals:
        context_parts.append("Active deals:")
        for d in deals:
            context_parts.append(f"  - {d.title} | Stage: {d.stage} | Value: ${d.value:,.0f} | Win prob: {d.ml_win_probability}%")

    context = "\n".join(context_parts)
    prompt = (
        f"You are a senior sales strategist. Generate a concise pre-meeting intelligence brief for the contact below.\n\n"
        f"{context}\n\n"
        f"The brief should include: 1) Who they are (2 sentences), 2) Current deal status & risks, "
        f"3) Conversation highlights (key themes from emails/calls), 4) Recommended talking points (3 bullets), "
        f"5) Watch-out signals. Keep it scannable and under 300 words."
    )

    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    message = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
    )
    brief_text = message.content[0].text

    return {
        "contact_id": str(contact_id),
        "contact_name": contact.name,
        "brief": brief_text,
    }
