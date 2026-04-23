import json
import os
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.contact import Contact
from app.models.activity_event import ActivityEvent

# TODO: needs ANTHROPIC_API_KEY in env
try:
    import anthropic as _anthropic
    _anthropic_client = _anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
except Exception:
    _anthropic_client = None  # type: ignore[assignment]

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
    """Stub: trigger ML scoring for a contact. Logs activity and returns 200."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.workspace_id == workspace_id)
    )
    contact = result.scalar_one_or_none()
    if contact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    event = ActivityEvent(
        workspace_id=workspace_id,
        type="score_contact",
        agent_name="ScoringAgent",
        description=f"Scoring triggered for contact {contact_id}",
        severity="info",
    )
    db.add(event)
    await db.commit()

    return {"status": "queued", "contact_id": str(contact_id)}


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

    if _anthropic_client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email composer unavailable — ANTHROPIC_API_KEY not configured",
        )

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

    message = _anthropic_client.messages.create(
        model="claude-sonnet-4-6",
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
