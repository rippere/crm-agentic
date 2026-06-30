import csv
import difflib
import io
import json
import uuid
from datetime import datetime, timedelta

import anthropic as _anthropic
from typing import Literal

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import or_, select, insert, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.limiter import limiter
from app.models.user import User
from app.models.contact import Contact
from app.models.contact_note import ContactNote
from app.models.activity_event import ActivityEvent
from app.services.supabase_rest import get_row

router = APIRouter()


class ContactResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str | None
    email: str | None
    company: str | None
    role: str | None
    avatar: str | None = None
    status: str
    ml_score: dict
    semantic_tags: list = []
    revenue: float
    deal_count: int
    last_activity: str
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class CreateContactRequest(BaseModel):
    name: str
    email: str | None = None
    company: str | None = None
    role: str | None = None
    status: str = "lead"


class ContactNoteResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    contact_id: uuid.UUID
    body: str
    author: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class CreateContactNoteRequest(BaseModel):
    body: str
    author: str | None = None


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
    contact_status: str | None = Query(default=None, alias="status"),
    q: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ContactResponse]:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    stmt = select(Contact).where(Contact.workspace_id == workspace_id)
    if contact_status and contact_status != "all":
        stmt = stmt.where(Contact.status == contact_status)
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(or_(
            Contact.name.ilike(pattern),
            Contact.email.ilike(pattern),
            Contact.company.ilike(pattern),
        ))
    stmt = stmt.limit(limit).offset(offset)
    result = await db.execute(stmt)
    contacts = result.scalars().all()
    return [ContactResponse.model_validate(c) for c in contacts]


@router.get("/workspaces/{workspace_id}/contacts/export")
async def export_contacts_csv(
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """Export all workspace contacts as a CSV file."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    result = await db.execute(select(Contact).where(Contact.workspace_id == workspace_id))
    contacts = result.scalars().all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["id", "name", "email", "company", "role", "status", "ml_score", "revenue", "created_at"])
    for c in contacts:
        writer.writerow([
            str(c.id), c.name or "", c.email or "", c.company or "",
            c.role or "", c.status or "", c.ml_score or 0,
            c.revenue or 0,
            c.created_at.isoformat() if c.created_at else "",
        ])

    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=contacts.csv"},
    )


@router.post("/workspaces/{workspace_id}/contacts/import")
async def import_contacts_csv(
    workspace_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Import contacts from a CSV file. Expected columns: name, email, company, role, status."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    content = await file.read()
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))
    imported = 0
    skipped = 0
    errors: list[str] = []
    allowed_statuses = {"lead", "prospect", "customer", "churned"}

    for i, row in enumerate(reader, start=2):
        name = (row.get("name") or row.get("Name") or "").strip()
        if not name:
            errors.append(f"Row {i}: missing name — skipped")
            skipped += 1
            continue

        email = (row.get("email") or row.get("Email") or "").strip() or None
        company = (row.get("company") or row.get("Company") or "").strip() or None
        role = (row.get("role") or row.get("Role") or "").strip() or None
        raw_status = (row.get("status") or row.get("Status") or "lead").strip().lower()
        contact_status = raw_status if raw_status in allowed_statuses else "lead"

        # Upsert by email within workspace
        if email:
            result = await db.execute(
                select(Contact).where(
                    Contact.workspace_id == workspace_id,
                    Contact.email == email,
                )
            )
            existing = result.scalar_one_or_none()
            if existing is not None:
                existing.name = name
                if company:
                    existing.company = company
                if role:
                    existing.role = role
                existing.status = contact_status  # type: ignore[assignment]
                db.add(existing)
                imported += 1
                continue

        contact = Contact(
            workspace_id=workspace_id,
            name=name,
            email=email,
            company=company,
            role=role,
            status=contact_status,
        )
        db.add(contact)
        imported += 1

    await db.commit()
    return {"imported": imported, "skipped": skipped, "errors": errors}


# ─── Duplicate-candidate detection ─────────────────────────────────────────────

class DuplicateCandidatePair(BaseModel):
    contact_a: ContactResponse
    contact_b: ContactResponse
    similarity_score: float
    reason: str


@router.get("/workspaces/{workspace_id}/contacts/duplicate-candidates")
async def get_duplicate_candidates(
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Return pairs of contacts that are likely duplicates based on name similarity and email domain."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    result = await db.execute(
        select(Contact)
        .where(Contact.workspace_id == workspace_id)
        .limit(300)
    )
    contacts = result.scalars().all()

    pairs: list[dict] = []
    for i in range(len(contacts)):
        for j in range(i + 1, len(contacts)):
            a, b = contacts[i], contacts[j]
            name_a = (a.name or "").lower().strip()
            name_b = (b.name or "").lower().strip()
            if not name_a or not name_b:
                continue

            name_sim = difflib.SequenceMatcher(None, name_a, name_b).ratio()

            domain_a = a.email.split("@")[1].lower() if a.email and "@" in a.email else ""
            domain_b = b.email.split("@")[1].lower() if b.email and "@" in b.email else ""
            same_domain = bool(domain_a and domain_a == domain_b)

            score = round(name_sim * 0.7 + (0.3 if same_domain else 0.0), 3)
            if score < 0.65:
                continue

            reasons: list[str] = []
            if name_sim >= 0.8:
                reasons.append("similar name")
            if same_domain:
                reasons.append("same email domain")

            pairs.append({
                "contact_a": ContactResponse.model_validate(a),
                "contact_b": ContactResponse.model_validate(b),
                "similarity_score": score,
                "reason": " + ".join(reasons) if reasons else "similar profile",
            })

    pairs.sort(key=lambda x: x["similarity_score"], reverse=True)
    return {"pairs": pairs[:20]}


@router.get("/workspaces/{workspace_id}/contacts/going-dark")
async def going_dark_contacts(
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """Return customer/prospect contacts with no messages or notes in the last 30 days."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    from app.models.message import Message
    from datetime import timezone

    contact_result = await db.execute(
        select(Contact).where(
            Contact.workspace_id == workspace_id,
            Contact.status.in_(["customer", "prospect"]),
        )
    )
    contacts = contact_result.scalars().all()
    if not contacts:
        return []

    contact_ids = [c.id for c in contacts]
    now = datetime.now(timezone.utc)
    cutoff_90 = now - timedelta(days=90)

    msg_result = await db.execute(
        select(Message).where(
            Message.workspace_id == workspace_id,
            Message.contact_id.in_(contact_ids),
            Message.received_at >= cutoff_90,
        )
    )
    messages = msg_result.scalars().all()

    note_result = await db.execute(
        select(ContactNote).where(
            ContactNote.workspace_id == workspace_id,
            ContactNote.contact_id.in_(contact_ids),
            ContactNote.created_at >= cutoff_90,
        )
    )
    notes = note_result.scalars().all()

    last_msg: dict = {}
    for m in messages:
        if m.contact_id and m.received_at:
            ts = m.received_at
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if m.contact_id not in last_msg or ts > last_msg[m.contact_id]:
                last_msg[m.contact_id] = ts

    last_note: dict = {}
    for n in notes:
        ts = n.created_at
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if n.contact_id not in last_note or ts > last_note[n.contact_id]:
            last_note[n.contact_id] = ts

    cutoff_30 = now - timedelta(days=30)
    out = []
    for c in contacts:
        dates = [d for d in [last_msg.get(c.id), last_note.get(c.id)] if d is not None]
        if dates:
            last_contact = max(dates)
            if last_contact >= cutoff_30:
                continue
            days_since = int((now - last_contact).total_seconds() / 86400)
            last_contact_str = last_contact.date().isoformat()
        else:
            days_since = 90
            last_contact_str = None

        out.append({
            "id": str(c.id),
            "name": c.name,
            "email": c.email,
            "company": c.company,
            "status": c.status,
            "days_since_last_contact": days_since,
            "last_contact_date": last_contact_str,
        })

    out.sort(key=lambda x: x["days_since_last_contact"], reverse=True)
    return out


@router.get("/workspaces/{workspace_id}/contacts/pipeline-contribution")
async def contact_pipeline_contribution(
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """Return each contact's pipeline contribution: deal counts, pipeline value, won value.

    NOTE: registered before /{contact_id} to avoid UUID-parse ambiguity.
    """
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    from app.models.deal import Deal

    deal_result = await db.execute(
        select(Deal).where(
            Deal.workspace_id == workspace_id,
            Deal.contact_id.is_not(None),
        )
    )
    deals = deal_result.scalars().all()
    if not deals:
        return []

    contact_ids = list({d.contact_id for d in deals})
    contact_result = await db.execute(
        select(Contact).where(
            Contact.id.in_(contact_ids),
            Contact.workspace_id == workspace_id,
        )
    )
    contacts = {c.id: c for c in contact_result.scalars().all()}

    buckets: dict = {}
    for d in deals:
        cid = d.contact_id
        if cid not in buckets:
            buckets[cid] = {"contact_id": str(cid), "pipeline_value": 0.0, "closed_won_value": 0.0, "deal_count": 0, "won_count": 0}
        v = float(d.value or 0)
        buckets[cid]["deal_count"] += 1
        if d.stage == "closed_won":
            buckets[cid]["closed_won_value"] += v
            buckets[cid]["won_count"] += 1
        elif d.stage != "closed_lost":
            buckets[cid]["pipeline_value"] += v

    out = []
    for cid, b in buckets.items():
        c = contacts.get(cid)
        win_rate = round((b["won_count"] / b["deal_count"]) * 100, 1) if b["deal_count"] else 0.0
        out.append({
            "contact_id": b["contact_id"],
            "name": c.name if c else None,
            "email": c.email if c else None,
            "company": c.company if c else None,
            "pipeline_value": round(b["pipeline_value"], 2),
            "closed_won_value": round(b["closed_won_value"], 2),
            "deal_count": b["deal_count"],
            "win_rate": win_rate,
        })

    out.sort(key=lambda x: x["pipeline_value"], reverse=True)
    return out


@router.get("/workspaces/{workspace_id}/contacts/reengagement-summary")
async def contact_reengagement_summary(
    workspace_id: uuid.UUID,
    weeks: int = Query(default=12, ge=1, le=52),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """Weekly count of contacts re-engaged after a 30+ day dark period.

    A re-engagement is when a contact receives a message or note after their
    previous touch was more than 30 days earlier.

    NOTE: registered before /{contact_id} to avoid UUID-parse ambiguity.
    """
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    from datetime import timezone as _tz
    from app.models.message import Message as _Message

    today = datetime.now(_tz.utc).date()
    this_monday = today - timedelta(days=today.weekday())
    week_starts = [this_monday - timedelta(weeks=i) for i in range(weeks - 1, -1, -1)]
    cutoff = datetime.combine(week_starts[0], datetime.min.time()).replace(tzinfo=_tz.utc)
    lookback_start = cutoff - timedelta(days=60)

    msg_result = await db.execute(
        select(_Message).where(
            _Message.workspace_id == workspace_id,
            _Message.received_at >= lookback_start,
            _Message.contact_id.is_not(None),
        )
    )
    messages = msg_result.scalars().all()

    note_result = await db.execute(
        select(ContactNote).where(
            ContactNote.workspace_id == workspace_id,
            ContactNote.created_at >= lookback_start,
        )
    )
    notes = note_result.scalars().all()

    touches_by_contact: dict = {}
    for m in messages:
        cid = m.contact_id
        if cid is None:
            continue
        ts = m.received_at
        if ts is None:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=_tz.utc)
        touches_by_contact.setdefault(cid, []).append(ts)
    for n in notes:
        cid = n.contact_id
        ts = n.created_at
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=_tz.utc)
        touches_by_contact.setdefault(cid, []).append(ts)

    reengagement_events: list[datetime] = []
    for cid, dates in touches_by_contact.items():
        dates_sorted = sorted(dates)
        for i in range(1, len(dates_sorted)):
            gap_days = (dates_sorted[i] - dates_sorted[i - 1]).total_seconds() / 86400
            if gap_days > 30 and dates_sorted[i] >= cutoff:
                reengagement_events.append(dates_sorted[i])

    week_counts = {ws: 0 for ws in week_starts}
    for evt_ts in reengagement_events:
        for ws in reversed(week_starts):
            ws_dt = datetime.combine(ws, datetime.min.time()).replace(tzinfo=_tz.utc)
            we_dt = ws_dt + timedelta(weeks=1)
            if ws_dt <= evt_ts < we_dt:
                week_counts[ws] += 1
                break

    return [{"week_start": ws.isoformat(), "reengaged": week_counts[ws]} for ws in week_starts]


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
    from app.routers.agents import _mark_job_dispatched
    task = score_lead.delay(str(contact_id), str(workspace_id))
    _mark_job_dispatched(task.id, str(workspace_id))

    return {"status": "queued", "contact_id": str(contact_id), "job_id": task.id}


class EmailDraftResponse(BaseModel):
    subject: str
    body: str


class ComposeEmailRequest(BaseModel):
    tone: str | None = None
    deal_id: uuid.UUID | None = None


@router.post("/workspaces/{workspace_id}/contacts/{contact_id}/compose", response_model=EmailDraftResponse)
@limiter.limit("10/minute")
async def compose_email(
    request: Request,
    workspace_id: uuid.UUID,
    contact_id: uuid.UUID,
    body: ComposeEmailRequest = Body(default=ComposeEmailRequest()),
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
    contact_orm = result.scalar_one_or_none()

    # Fallback: read from Supabase REST if not in local Postgres
    if contact_orm is None:
        row = await get_row("contacts", {"id": str(contact_id), "workspace_id": str(workspace_id)})
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")
        contact_name = row.get("name") or "Unknown"
        contact_company = row.get("company") or "Unknown"
        contact_role = row.get("role") or "Unknown"
        contact_status = row.get("status") or "cold"
        contact_tags = row.get("semantic_tags") or []
        contact_revenue = row.get("revenue") or 0
    else:
        contact_name = contact_orm.name or "Unknown"
        contact_company = contact_orm.company or "Unknown"
        contact_role = contact_orm.role or "Unknown"
        contact_status = contact_orm.status
        contact_tags = contact_orm.semantic_tags or []
        contact_revenue = contact_orm.revenue

    # Optionally ground the draft in a specific deal
    deal_context = ""
    if body.deal_id is not None:
        from app.models.deal import Deal

        deal_result = await db.execute(
            select(Deal).where(Deal.id == body.deal_id, Deal.workspace_id == workspace_id)
        )
        deal = deal_result.scalar_one_or_none()
        if deal is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found")
        deal_context = (
            f"Related deal: {deal.title or 'Untitled'}\n"
            f"Deal stage: {deal.stage}\n"
            f"Deal value: ${float(deal.value or 0):,.0f}\n"
            f"Win probability: {deal.ml_win_probability}%\n"
        )

    system_prompt = (
        "You are a sales professional. Write a personalized outreach email for the following contact. "
        'Return JSON only: {"subject": "<subject line>", "body": "<email body>"}'
    )
    if body.tone:
        system_prompt += f" Write the email in a {body.tone} tone."
    user_content = (
        f"Contact name: {contact_name}\n"
        f"Company: {contact_company}\n"
        f"Role: {contact_role}\n"
        f"Status: {contact_status}\n"
        f"Semantic tags: {json.dumps(contact_tags)}\n"
        f"Revenue: {contact_revenue}\n"
        f"{deal_context}"
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
@limiter.limit("5/minute")
async def enrich_contact_endpoint(
    request: Request,
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
        # Check Supabase fallback before 404
        row = await get_row("contacts", {"id": str(contact_id), "workspace_id": str(workspace_id)})
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    from app.workers.enrich_contact import enrich_contact
    from app.routers.agents import _mark_job_dispatched
    task = enrich_contact.delay(str(contact_id))
    _mark_job_dispatched(task.id, str(workspace_id))
    return {"status": "queued", "contact_id": str(contact_id), "job_id": task.id}


@router.get("/workspaces/{workspace_id}/contacts/{contact_id}", response_model=ContactResponse)
async def get_contact(
    workspace_id: uuid.UUID,
    contact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ContactResponse:
    """Return a single contact by ID."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.workspace_id == workspace_id)
    )
    contact = result.scalar_one_or_none()
    if contact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    return ContactResponse.model_validate(contact)


class UpdateContactRequest(BaseModel):
    name: str | None = None
    email: str | None = None
    company: str | None = None
    role: str | None = None
    status: str | None = None


@router.patch("/workspaces/{workspace_id}/contacts/{contact_id}", response_model=ContactResponse)
async def update_contact(
    workspace_id: uuid.UUID,
    contact_id: uuid.UUID,
    body: UpdateContactRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ContactResponse:
    """Update editable fields on a contact."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.workspace_id == workspace_id)
    )
    contact = result.scalar_one_or_none()
    if contact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    allowed_statuses = {"lead", "prospect", "customer", "churned"}
    if body.status is not None and body.status not in allowed_statuses:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"status must be one of {allowed_statuses}",
        )

    for field in ("name", "email", "company", "role", "status"):
        value = getattr(body, field)
        if value is not None:
            setattr(contact, field, value)

    db.add(contact)
    event = ActivityEvent(
        workspace_id=workspace_id,
        type="contact_updated",
        agent_name="System",
        description=f"Contact updated: {contact.name}",
        severity="info",
    )
    db.add(event)
    await db.commit()
    await db.refresh(contact)

    return ContactResponse.model_validate(contact)


class UpdateTagsRequest(BaseModel):
    tags: list[dict]


@router.put("/workspaces/{workspace_id}/contacts/{contact_id}/tags", response_model=ContactResponse)
async def update_contact_tags(
    workspace_id: uuid.UUID,
    contact_id: uuid.UUID,
    body: UpdateTagsRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ContactResponse:
    """Replace the semantic_tags list on a contact."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.workspace_id == workspace_id)
    )
    contact = result.scalar_one_or_none()
    if contact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    for tag in body.tags:
        if "label" not in tag:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Each tag must have a 'label' field",
            )

    contact.semantic_tags = body.tags
    db.add(contact)
    event = ActivityEvent(
        workspace_id=workspace_id,
        type="contact_updated",
        agent_name="System",
        description=f"Tags updated for contact: {contact.name}",
        severity="info",
    )
    db.add(event)
    await db.commit()
    await db.refresh(contact)

    return ContactResponse.model_validate(contact)


@router.delete("/workspaces/{workspace_id}/contacts/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contact(
    workspace_id: uuid.UUID,
    contact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Delete a contact and all cascade-linked records."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.workspace_id == workspace_id)
    )
    contact = result.scalar_one_or_none()
    if contact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    contact_name = contact.name or str(contact_id)
    await db.delete(contact)
    event = ActivityEvent(
        workspace_id=workspace_id,
        type="contact_deleted",
        agent_name="System",
        description=f"Contact removed: {contact_name}",
        severity="warning",
    )
    db.add(event)
    await db.commit()


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
@limiter.limit("10/minute")
async def pre_meeting_brief(
    request: Request,
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


class BulkContactRequest(BaseModel):
    action: Literal["delete"]
    contact_ids: list[uuid.UUID]


class BulkContactResponse(BaseModel):
    action: str
    deleted: int
    contact_ids: list[str]


@router.post("/workspaces/{workspace_id}/contacts/bulk", response_model=BulkContactResponse)
async def bulk_contact_action(
    workspace_id: uuid.UUID,
    body: BulkContactRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BulkContactResponse:
    """Bulk delete contacts (max 100 at a time)."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if not body.contact_ids:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="contact_ids must not be empty")

    if len(body.contact_ids) > 100:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Maximum 100 contacts per bulk operation")

    result = await db.execute(
        select(Contact).where(
            Contact.workspace_id == workspace_id,
            Contact.id.in_(body.contact_ids),
        )
    )
    contacts = result.scalars().all()

    if not contacts:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No matching contacts found")

    deleted_ids = [str(c.id) for c in contacts]
    names = [c.name or str(c.id) for c in contacts]

    for contact in contacts:
        await db.delete(contact)

    event = ActivityEvent(
        workspace_id=workspace_id,
        type="contact_deleted",
        agent_name="System",
        description=f"Bulk deleted {len(contacts)} contact(s): {', '.join(names[:3])}" + ("…" if len(names) > 3 else ""),
        severity="warning",
    )
    db.add(event)
    await db.commit()

    return BulkContactResponse(action="delete", deleted=len(contacts), contact_ids=deleted_ids)


# ─── Contact merge ─────────────────────────────────────────────────────────────

class MergeContactRequest(BaseModel):
    primary_id: uuid.UUID
    duplicate_id: uuid.UUID


class MergeContactResponse(BaseModel):
    primary_id: str
    duplicate_id: str
    tasks_reassigned: int
    messages_reassigned: int
    deals_reassigned: int


@router.post("/workspaces/{workspace_id}/contacts/merge", response_model=MergeContactResponse)
async def merge_contacts(
    workspace_id: uuid.UUID,
    body: MergeContactRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MergeContactResponse:
    """Merge duplicate into primary: reassign tasks/messages/deals, then delete duplicate."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if body.primary_id == body.duplicate_id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="primary_id and duplicate_id must differ")

    # Verify both contacts exist in this workspace
    result = await db.execute(
        select(Contact).where(
            Contact.workspace_id == workspace_id,
            Contact.id.in_([body.primary_id, body.duplicate_id]),
        )
    )
    contacts = {c.id: c for c in result.scalars().all()}
    if body.primary_id not in contacts:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="primary contact not found")
    if body.duplicate_id not in contacts:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="duplicate contact not found")

    from app.models.task import Task
    from app.models.message import Message
    from app.models.deal import Deal

    # Reassign tasks
    task_result = await db.execute(
        update(Task)
        .where(Task.workspace_id == workspace_id, Task.contact_id == body.duplicate_id)
        .values(contact_id=body.primary_id)
    )
    tasks_updated: int = task_result.rowcount or 0

    # Reassign messages
    msg_result = await db.execute(
        update(Message)
        .where(Message.workspace_id == workspace_id, Message.contact_id == body.duplicate_id)
        .values(contact_id=body.primary_id)
    )
    messages_updated: int = msg_result.rowcount or 0

    # Reassign deals
    deal_result = await db.execute(
        update(Deal)
        .where(Deal.workspace_id == workspace_id, Deal.contact_id == body.duplicate_id)
        .values(contact_id=body.primary_id)
    )
    deals_updated: int = deal_result.rowcount or 0

    # Delete the duplicate
    duplicate = contacts[body.duplicate_id]
    duplicate_name = duplicate.name or str(body.duplicate_id)
    primary_name   = contacts[body.primary_id].name or str(body.primary_id)
    await db.delete(duplicate)

    event = ActivityEvent(
        workspace_id=workspace_id,
        type="contact_deleted",
        agent_name="System",
        description=(
            f"Merged '{duplicate_name}' into '{primary_name}' — "
            f"{tasks_updated} task(s), {messages_updated} message(s), "
            f"{deals_updated} deal(s) reassigned"
        ),
        severity="info",
    )
    db.add(event)
    await db.commit()

    return MergeContactResponse(
        primary_id=str(body.primary_id),
        duplicate_id=str(body.duplicate_id),
        tasks_reassigned=tasks_updated,
        messages_reassigned=messages_updated,
        deals_reassigned=deals_updated,
    )


@router.get(
    "/workspaces/{workspace_id}/contacts/{contact_id}/notes",
    response_model=list[ContactNoteResponse],
)
async def list_contact_notes(
    workspace_id: uuid.UUID,
    contact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ContactNoteResponse]:
    """Return all notes for a contact, oldest-first (chronological thread)."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    contact_result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.workspace_id == workspace_id)
    )
    contact = contact_result.scalar_one_or_none()
    if contact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    result = await db.execute(
        select(ContactNote)
        .where(
            ContactNote.workspace_id == workspace_id,
            ContactNote.contact_id == contact_id,
        )
        .order_by(ContactNote.created_at.asc())
    )
    notes = result.scalars().all()
    return [ContactNoteResponse.model_validate(n) for n in notes]


@router.post(
    "/workspaces/{workspace_id}/contacts/{contact_id}/notes",
    response_model=ContactNoteResponse,
    status_code=201,
)
async def create_contact_note(
    workspace_id: uuid.UUID,
    contact_id: uuid.UUID,
    body: CreateContactNoteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ContactNoteResponse:
    """Append a note to a contact. Notes are immutable once created."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    text = (body.body or "").strip()
    if not text:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Note body must not be empty",
        )

    contact_result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.workspace_id == workspace_id)
    )
    contact = contact_result.scalar_one_or_none()
    if contact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    note = ContactNote(
        workspace_id=workspace_id,
        contact_id=contact_id,
        body=text,
        author=body.author or getattr(current_user, "email", None),
    )
    db.add(note)
    await db.commit()
    await db.refresh(note)
    return ContactNoteResponse.model_validate(note)


@router.get("/workspaces/{workspace_id}/contacts/{contact_id}/activity-heatmap")
async def contact_activity_heatmap(
    workspace_id: uuid.UUID,
    contact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """Return weekly message + note counts for the last 12 weeks (Mon–Sun buckets)."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    contact_result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.workspace_id == workspace_id)
    )
    if contact_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    from app.models.message import Message

    today = datetime.utcnow().date()
    this_monday = today - timedelta(days=today.weekday())
    # Oldest-first list of 12 week-start dates
    week_starts = [this_monday - timedelta(weeks=i) for i in range(11, -1, -1)]
    cutoff = datetime.combine(week_starts[0], datetime.min.time())

    msg_result = await db.execute(
        select(Message).where(
            Message.workspace_id == workspace_id,
            Message.contact_id == contact_id,
            Message.received_at >= cutoff,
        )
    )
    messages = msg_result.scalars().all()

    note_result = await db.execute(
        select(ContactNote).where(
            ContactNote.workspace_id == workspace_id,
            ContactNote.contact_id == contact_id,
            ContactNote.created_at >= cutoff,
        )
    )
    notes = note_result.scalars().all()

    output = []
    for ws in week_starts:
        we = ws + timedelta(weeks=1)
        ws_dt = datetime.combine(ws, datetime.min.time())
        we_dt = datetime.combine(we, datetime.min.time())
        msgs = sum(1 for m in messages if m.received_at and ws_dt <= m.received_at < we_dt)
        nts = sum(1 for n in notes if n.created_at and ws_dt <= n.created_at < we_dt)
        output.append({
            "week_start": ws.isoformat(),
            "messages": msgs,
            "notes": nts,
            "total": msgs + nts,
        })

    return output


@router.get("/workspaces/{workspace_id}/contacts/{contact_id}/engagement-score")
async def contact_engagement_score(
    workspace_id: uuid.UUID,
    contact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Compute a 0–100 engagement score from messages, notes, and task completion (last 90 days)."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    contact_result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.workspace_id == workspace_id)
    )
    if contact_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    from app.models.message import Message
    from app.models.task import Task

    cutoff = datetime.utcnow() - timedelta(days=90)

    msg_result = await db.execute(
        select(Message).where(
            Message.workspace_id == workspace_id,
            Message.contact_id == contact_id,
            Message.received_at >= cutoff,
        )
    )
    message_count = len(msg_result.scalars().all())

    note_result = await db.execute(
        select(ContactNote).where(
            ContactNote.workspace_id == workspace_id,
            ContactNote.contact_id == contact_id,
            ContactNote.created_at >= cutoff,
        )
    )
    note_count = len(note_result.scalars().all())

    task_result = await db.execute(
        select(Task).where(
            Task.workspace_id == workspace_id,
            Task.contact_id == contact_id,
            Task.created_at >= cutoff,
        )
    )
    tasks = task_result.scalars().all()
    tasks_total = len(tasks)
    tasks_done = sum(1 for t in tasks if t.status == "done")

    messages_score = min(40, message_count * 8)
    notes_score = min(30, note_count * 10)
    tasks_score = round(30 * tasks_done / tasks_total) if tasks_total > 0 else 0
    total_score = messages_score + notes_score + tasks_score

    return {
        "score": total_score,
        "message_count": message_count,
        "note_count": note_count,
        "tasks_total": tasks_total,
        "tasks_done": tasks_done,
        "components": {
            "messages": messages_score,
            "notes": notes_score,
            "tasks": tasks_score,
        },
    }


@router.get("/workspaces/{workspace_id}/contacts/{contact_id}/deal-summary")
async def contact_deal_summary(
    workspace_id: uuid.UUID,
    contact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Aggregate deal value metrics for a contact: pipeline value, closed-won, win rate, avg size."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    from app.models.deal import Deal

    contact_result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.workspace_id == workspace_id)
    )
    if contact_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    deal_result = await db.execute(
        select(Deal).where(Deal.workspace_id == workspace_id, Deal.contact_id == contact_id)
    )
    deals = deal_result.scalars().all()

    CLOSED = {"closed_won", "closed_lost"}
    pipeline_value = sum(float(d.value or 0) for d in deals if d.stage not in CLOSED)
    closed_won_value = sum(float(d.value or 0) for d in deals if d.stage == "closed_won")
    open_deal_count = sum(1 for d in deals if d.stage not in CLOSED)
    won_count = sum(1 for d in deals if d.stage == "closed_won")
    lost_count = sum(1 for d in deals if d.stage == "closed_lost")
    total_closed = won_count + lost_count
    win_rate = round(won_count / total_closed * 100) if total_closed > 0 else None
    avg_deal_size = round(sum(float(d.value or 0) for d in deals) / len(deals)) if deals else None

    return {
        "total_pipeline_value": pipeline_value,
        "closed_won_value": closed_won_value,
        "open_deal_count": open_deal_count,
        "win_rate": win_rate,
        "avg_deal_size": avg_deal_size,
        "total_deals": len(deals),
    }


@router.get("/workspaces/{workspace_id}/contacts/{contact_id}/timeline/export")
async def export_contact_timeline(
    workspace_id: uuid.UUID,
    contact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """Export a contact's full timeline as a CSV file."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    contact_result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.workspace_id == workspace_id)
    )
    if contact_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    from app.models.message import Message
    from app.models.call_summary import CallSummary
    from app.models.deal import Deal

    rows: list[dict] = []

    msg_result = await db.execute(
        select(Message).where(
            Message.workspace_id == workspace_id,
            Message.contact_id == contact_id,
        )
    )
    for m in msg_result.scalars().all():
        ts = m.received_at or m.created_at
        rows.append({
            "date": ts.isoformat() if ts else "",
            "type": "message",
            "title": m.subject or "(No subject)",
            "description": (m.body_plain or "")[:300],
            "severity": "",
        })

    call_result = await db.execute(
        select(CallSummary).where(
            CallSummary.workspace_id == workspace_id,
            CallSummary.contact_id == contact_id,
        )
    )
    for c in call_result.scalars().all():
        rows.append({
            "date": c.call_date.isoformat() if c.call_date else "",
            "type": "call",
            "title": c.title or "(No title)",
            "description": (c.summary or "")[:300],
            "severity": "",
        })

    deal_result = await db.execute(
        select(Deal).where(
            Deal.workspace_id == workspace_id,
            Deal.contact_id == contact_id,
        )
    )
    for d in deal_result.scalars().all():
        ts = d.stage_changed_at or d.created_at
        rows.append({
            "date": ts.isoformat() if ts else "",
            "type": "deal_stage",
            "title": f"Deal: {d.title or 'Untitled'}",
            "description": f"Stage: {d.stage} | Value: ${d.value:,.0f}",
            "severity": "",
        })

    note_result = await db.execute(
        select(ContactNote).where(
            ContactNote.workspace_id == workspace_id,
            ContactNote.contact_id == contact_id,
        )
    )
    for n in note_result.scalars().all():
        rows.append({
            "date": n.created_at.isoformat() if n.created_at else "",
            "type": "note",
            "title": "Contact Note",
            "description": (n.body or "")[:300],
            "severity": "",
        })

    contact_meta = f"contact:{contact_id}"
    evt_result = await db.execute(
        select(ActivityEvent).where(
            ActivityEvent.workspace_id == workspace_id,
            ActivityEvent.meta.like(f"%{contact_meta}%"),
        )
    )
    for e in evt_result.scalars().all():
        rows.append({
            "date": e.created_at.isoformat() if e.created_at else "",
            "type": "activity",
            "title": e.type or "Activity",
            "description": e.description or "",
            "severity": e.severity or "",
        })

    rows.sort(key=lambda x: x["date"], reverse=True)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["date", "type", "title", "description", "severity"])
    for row in rows:
        writer.writerow([row["date"], row["type"], row["title"], row["description"], row["severity"]])

    buf.seek(0)
    filename = f"timeline_{contact_id}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/workspaces/{workspace_id}/contacts/{contact_id}/last-touch")
async def contact_last_touch(
    workspace_id: uuid.UUID,
    contact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Return the most recent touch point for a contact across messages, notes, and activity events."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    contact_result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.workspace_id == workspace_id)
    )
    if contact_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    from app.models.message import Message

    msg_result = await db.execute(
        select(Message.received_at, Message.created_at).where(
            Message.workspace_id == workspace_id,
            Message.contact_id == contact_id,
        ).order_by(Message.received_at.desc().nullslast()).limit(1)
    )
    msg_row = msg_result.first()
    last_message_date = (msg_row[0] or msg_row[1]).isoformat() if msg_row and (msg_row[0] or msg_row[1]) else None

    note_result = await db.execute(
        select(ContactNote.created_at).where(
            ContactNote.workspace_id == workspace_id,
            ContactNote.contact_id == contact_id,
        ).order_by(ContactNote.created_at.desc()).limit(1)
    )
    note_row = note_result.first()
    last_note_date = note_row[0].isoformat() if note_row and note_row[0] else None

    contact_meta = f"contact:{contact_id}"
    evt_result = await db.execute(
        select(ActivityEvent.created_at).where(
            ActivityEvent.workspace_id == workspace_id,
            ActivityEvent.meta.like(f"%{contact_meta}%"),
        ).order_by(ActivityEvent.created_at.desc()).limit(1)
    )
    evt_row = evt_result.first()
    last_activity_date = evt_row[0].isoformat() if evt_row and evt_row[0] else None

    candidates: list[tuple[str, str]] = []
    if last_message_date:
        candidates.append((last_message_date, "message"))
    if last_note_date:
        candidates.append((last_note_date, "note"))
    if last_activity_date:
        candidates.append((last_activity_date, "activity"))

    now = datetime.utcnow()
    most_recent_type: str | None = None
    days_ago: int | None = None
    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        most_recent_type = candidates[0][1]
        try:
            most_recent_dt = datetime.fromisoformat(candidates[0][0].replace("Z", "+00:00")).replace(tzinfo=None)
            days_ago = max(0, (now - most_recent_dt).days)
        except ValueError:
            days_ago = None

    return {
        "last_message_date": last_message_date,
        "last_note_date": last_note_date,
        "last_activity_date": last_activity_date,
        "most_recent_type": most_recent_type,
        "days_ago": days_ago,
    }
