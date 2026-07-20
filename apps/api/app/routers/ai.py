import datetime
import json
import uuid
from collections import Counter, defaultdict
from datetime import timezone

import anthropic as _anthropic
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.limiter import limiter
from app.models.user import User
from app.models.contact import Contact
from app.models.contact_note import ContactNote
from app.models.clarity_score import ClarityScore
from app.models.deal import Deal
from app.models.message import Message
from app.models.task import Task
from app.models.activity_event import ActivityEvent

router = APIRouter()

_SYSTEM_PROMPT = """\
You are Nova, the AI assistant embedded in NovaCRM — an agentic CRM with AI-driven lead scoring, \
deal health monitoring, call transcription, and semantic contact search.

You have access to a snapshot of the workspace's current state (provided by the user). \
Answer questions concisely and helpfully. When suggesting actions, name the specific \
CRM feature that would accomplish them (e.g. "use the AI Search on /contacts", \
"check Deal Health Alerts on /dashboard", "run Auto-Enrich on the contact drawer").

Respond in 1-3 short paragraphs. No markdown headers. Plain prose only.\
"""


class AIQueryRequest(BaseModel):
    query: str


class AIQueryResponse(BaseModel):
    answer: str


async def answer_crm_query(query: str, workspace_id: uuid.UUID, db: AsyncSession) -> str:
    """Answer a freeform CRM question with live workspace context.

    Shared by the POST /ai/query route and the /mcp `ask_crm` tool so both speak to
    the same Nova system prompt + workspace snapshot. Raises on AI failure.
    """
    # Build workspace snapshot for context
    contact_count = await db.scalar(
        select(func.count()).where(Contact.workspace_id == workspace_id)
    ) or 0

    deal_rows = await db.execute(
        select(Deal.stage, Deal.title, Deal.company, Deal.value, Deal.health_score)
        .where(Deal.workspace_id == workspace_id)
        .limit(20)
    )
    deals = deal_rows.all()

    open_tasks = await db.scalar(
        select(func.count()).where(Task.workspace_id == workspace_id, Task.status == "open")
    ) or 0

    recent_events = await db.execute(
        select(ActivityEvent.type, ActivityEvent.description, ActivityEvent.agent_name)
        .where(ActivityEvent.workspace_id == workspace_id)
        .order_by(ActivityEvent.created_at.desc())
        .limit(5)
    )
    events = recent_events.all()

    active_deals = [d for d in deals if d.stage not in ("closed_won", "closed_lost")]
    stale_deals = [d for d in active_deals if d.health_score < 40]
    pipeline_value = sum(d.value for d in active_deals)

    context = (
        f"Workspace snapshot:\n"
        f"- Contacts: {contact_count}\n"
        f"- Active deals: {len(active_deals)} (pipeline value: ${pipeline_value:,.0f})\n"
        f"- Stale deals (health < 40): {len(stale_deals)}\n"
        f"- Open tasks: {open_tasks}\n"
    )
    if deals:
        deal_lines = "\n".join(
            f"  • {d.title or 'Untitled'} @ {d.company or '?'} — ${d.value:,.0f}, stage={d.stage}, health={d.health_score}"
            for d in deals[:10]
        )
        context += f"- Top deals:\n{deal_lines}\n"
    if events:
        event_lines = "\n".join(
            f"  • [{e.type}] {e.agent_name}: {e.description}" for e in events
        )
        context += f"- Recent activity:\n{event_lines}\n"

    client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"{context}\n\nUser question: {query}"}],
    )
    return msg.content[0].text.strip() if msg.content else "I couldn't generate a response."


@router.post("/workspaces/{workspace_id}/ai/query", response_model=AIQueryResponse)
@limiter.limit("20/minute")
async def ai_query(
    request: Request,
    workspace_id: uuid.UUID,
    body: AIQueryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AIQueryResponse:
    """Freeform CRM question answered by Claude with live workspace context."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if not body.query.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Query cannot be empty")

    try:
        answer = await answer_crm_query(body.query, workspace_id, db)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    return AIQueryResponse(answer=answer)


# ---------------------------------------------------------------------------
# Workspace digest
# ---------------------------------------------------------------------------

_DIGEST_SYSTEM = """\
You are Nova, the AI assistant for NovaCRM. Generate a concise weekly digest for a sales/PM team.

Structure your response in exactly three sections using these headers:
**Top Wins** — 2-3 bullet points of recent successes (deals moved forward, contacts engaged, tasks completed).
**Watch Out** — 2-3 bullet points of risks or items needing attention (stale deals, overdue tasks, low clarity messages).
**Recommended Actions** — 2-3 specific, actionable next steps referencing CRM features where helpful.

Keep each bullet to one crisp sentence. No intro or closing paragraphs outside the three sections.\
"""


class DigestResponse(BaseModel):
    digest: str
    generated_at: str
    contact_count: int
    active_deal_count: int
    open_task_count: int
    message_count: int


@router.post("/workspaces/{workspace_id}/ai/digest", response_model=DigestResponse)
@limiter.limit("5/minute")
async def generate_digest(
    request: Request,
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DigestResponse:
    """Generate a Claude Haiku weekly digest for the workspace."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    # Gather counts and summaries
    contact_count = await db.scalar(
        select(func.count()).where(Contact.workspace_id == workspace_id)
    ) or 0

    deal_rows = await db.execute(
        select(Deal.stage, Deal.title, Deal.company, Deal.value, Deal.health_score, Deal.ml_win_probability)
        .where(Deal.workspace_id == workspace_id)
        .limit(30)
    )
    deals = deal_rows.all()
    active_deals = [d for d in deals if d.stage not in ("closed_won", "closed_lost")]
    won_deals = [d for d in deals if d.stage == "closed_won"]
    stale_deals = [d for d in active_deals if d.health_score < 40]

    open_task_count = await db.scalar(
        select(func.count()).where(Task.workspace_id == workspace_id, Task.status == "open")
    ) or 0
    overdue_task_count = await db.scalar(
        select(func.count()).where(
            Task.workspace_id == workspace_id,
            Task.status == "open",
            Task.due_date < datetime.date.today(),
        )
    ) or 0

    message_count = await db.scalar(
        select(func.count()).where(Message.workspace_id == workspace_id)
    ) or 0

    recent_events = await db.execute(
        select(ActivityEvent.type, ActivityEvent.description, ActivityEvent.agent_name, ActivityEvent.severity)
        .where(ActivityEvent.workspace_id == workspace_id)
        .order_by(ActivityEvent.created_at.desc())
        .limit(10)
    )
    events = recent_events.all()

    pipeline_value = sum(d.value for d in active_deals)
    won_value = sum(d.value for d in won_deals)

    context_lines = [
        f"Workspace snapshot (as of {datetime.date.today().isoformat()}):",
        f"- Contacts: {contact_count}",
        f"- Active deals: {len(active_deals)} (pipeline ${pipeline_value:,.0f})",
        f"- Closed-won deals: {len(won_deals)} (value ${won_value:,.0f})",
        f"- Stale deals (health < 40): {len(stale_deals)}",
        f"- Open tasks: {open_task_count} ({overdue_task_count} overdue)",
        f"- Messages ingested: {message_count}",
    ]
    if stale_deals:
        context_lines.append("- Stale deal details: " + "; ".join(
            f"{d.title or 'Untitled'} @ {d.company or '?'} health={d.health_score}" for d in stale_deals[:5]
        ))
    if won_deals:
        context_lines.append("- Recent wins: " + "; ".join(
            f"{d.title or 'Untitled'} @ {d.company or '?'} ${d.value:,.0f}" for d in won_deals[:3]
        ))
    if events:
        context_lines.append("- Recent activity: " + "; ".join(
            f"[{e.type}/{e.severity}] {e.agent_name}: {e.description}" for e in events[:5]
        ))

    context = "\n".join(context_lines)

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            system=_DIGEST_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        digest_text = msg.content[0].text.strip() if msg.content else "Digest unavailable."
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    return DigestResponse(
        digest=digest_text,
        generated_at=datetime.datetime.utcnow().isoformat() + "Z",
        contact_count=contact_count,
        active_deal_count=len(active_deals),
        open_task_count=open_task_count,
        message_count=message_count,
    )


# ---------------------------------------------------------------------------
# Per-deal AI coaching
# ---------------------------------------------------------------------------

_COACH_SYSTEM = """\
You are Nova, the AI sales coach in NovaCRM. Analyze the provided deal snapshot and return coaching advice.

Respond in exactly this JSON format (no extra text, no markdown fences):
{
  "urgency": "low",
  "bullets": [
    "First coaching point — one concise sentence with a specific action.",
    "Second coaching point — one concise sentence with a specific action.",
    "Third coaching point — one concise sentence with a specific action."
  ]
}

Urgency rules:
- "high": health < 40, OR win_prob < 30, OR next action overdue by 3+ days, OR stuck in stage > 21 days, OR 2+ active competitors
- "medium": health 40–69, OR win_prob 30–59, OR stuck in stage 14–21 days, OR next action overdue 1–2 days
- "low": deal is progressing normally with no red flags

Each bullet must name a specific CRM action the rep can take today to improve this deal.\
"""


@router.post("/workspaces/{workspace_id}/deals/{deal_id}/ai/coach")
@limiter.limit("10/minute")
async def deal_coaching(
    request: Request,
    workspace_id: uuid.UUID,
    deal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Generate 3-bullet AI coaching advice for a deal using Claude Haiku."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    deal_result = await db.execute(
        select(Deal).where(Deal.id == deal_id, Deal.workspace_id == workspace_id)
    )
    deal = deal_result.scalar_one_or_none()
    if deal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found")

    # Days stuck in current stage
    days_in_stage: int | None = None
    if deal.stage_changed_at:
        ref = deal.stage_changed_at
        if ref.tzinfo is None:
            ref = ref.replace(tzinfo=timezone.utc)
        days_in_stage = (datetime.datetime.now(timezone.utc) - ref).days

    # Next-action overdue
    days_overdue = 0
    if deal.next_action_date:
        today = datetime.date.today()
        delta = (today - deal.next_action_date).days
        days_overdue = max(0, delta)

    competitors = deal.competitors or []

    context = (
        f"Deal: {deal.title or 'Untitled'} at {deal.company or 'Unknown Company'}\n"
        f"Stage: {deal.stage}\n"
        f"Value: ${float(deal.value):,.0f}\n"
        f"Health score: {deal.health_score}/100\n"
        f"ML win probability: {deal.ml_win_probability}%\n"
        f"Days in current stage: {days_in_stage if days_in_stage is not None else 'unknown'}\n"
        f"Competitors tracked: {', '.join(competitors) if competitors else 'none'}\n"
        f"Next action: {deal.next_action or 'none set'}\n"
        f"Next action overdue by: {days_overdue} day{'s' if days_overdue != 1 else ''}\n"
    )

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=350,
            system=_COACH_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg.content[0].text.strip() if msg.content else "{}"
        data = json.loads(raw)
        urgency = data.get("urgency", "medium")
        bullets = data.get("bullets", [])
        if urgency not in ("low", "medium", "high"):
            urgency = "medium"
        bullets = [str(b) for b in bullets[:3]]
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    return {
        "urgency": urgency,
        "bullets": bullets,
        "deal_id": str(deal_id),
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
    }


# ---------------------------------------------------------------------------
# Contact outreach draft
# ---------------------------------------------------------------------------

_OUTREACH_SYSTEM = """\
You are Nova, the AI writing assistant in NovaCRM. Draft a personalised outreach email for a sales rep.

The email must be:
- Genuinely personalised — reference the contact's name, role, company, and any recent interaction
- Concise — subject under 60 chars, body 3–4 short paragraphs maximum
- Professional but warm in tone, not salesy or generic
- Action-oriented with a single clear CTA (typically a 15–20 minute call or quick reply)

Respond in exactly this JSON format (no markdown fences, no extra keys):
{
  "subject": "The email subject line (under 60 chars)",
  "body": "The email body. Use \\n for line breaks between paragraphs."
}
"""


@router.post("/workspaces/{workspace_id}/ai/contacts/{contact_id}/outreach")
@limiter.limit("10/minute")
async def draft_outreach(
    request: Request,
    workspace_id: uuid.UUID,
    contact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Generate a personalised outreach email draft for a contact using Claude Haiku."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    contact_result = await db.execute(
        select(Contact).where(Contact.workspace_id == workspace_id, Contact.id == contact_id)
    )
    contact = contact_result.scalar_one_or_none()
    if contact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    # Recent messages from this contact with clarity scores
    msg_result = await db.execute(
        select(Message.subject, Message.received_at, ClarityScore.score)
        .outerjoin(ClarityScore, Message.id == ClarityScore.message_id)
        .where(Message.workspace_id == workspace_id, Message.contact_id == contact_id)
        .order_by(Message.received_at.desc())
        .limit(3)
    )
    recent_messages = msg_result.all()

    # Open / in-progress tasks for this contact
    task_result = await db.execute(
        select(Task.title, Task.due_date)
        .where(
            Task.workspace_id == workspace_id,
            Task.contact_id == contact_id,
            Task.status.in_(["open", "in_progress"]),
        )
        .order_by(Task.due_date.asc())
        .limit(3)
    )
    open_tasks = task_result.all()

    # Build context
    lines = [
        f"Contact: {contact.name or 'Unknown'} — {contact.role or 'unknown role'} at {contact.company or 'Unknown Company'}",
        f"Contact email: {contact.email or 'unknown'}",
        f"Relationship status: {contact.status}",
    ]
    if recent_messages:
        lines.append("Recent message history:")
        for msg in recent_messages:
            clarity = f" (clarity {msg.score}/100)" if msg.score is not None else ""
            ts = msg.received_at.strftime("%b %d") if msg.received_at else "unknown date"
            lines.append(f"  - \"{msg.subject or '(no subject)'}\" received {ts}{clarity}")
    else:
        lines.append("No prior message history — this is a first-touch outreach.")

    if open_tasks:
        lines.append("Open tasks linked to this contact:")
        for task in open_tasks:
            due = f" (due {task.due_date})" if task.due_date else ""
            lines.append(f"  - {task.title}{due}")

    context = "\n".join(lines)

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            system=_OUTREACH_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg.content[0].text.strip() if msg.content else "{}"
        data = json.loads(raw)
        subject = str(data.get("subject", f"Following up, {contact.name or 'there'}"))
        body = str(data.get("body", "Hi,\n\nI wanted to reach out and connect.\n\nBest,"))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    return {
        "subject": subject,
        "body": body,
        "contact_id": str(contact_id),
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
    }


# ---------------------------------------------------------------------------
# Pipeline AI summary
# ---------------------------------------------------------------------------

_PIPELINE_SUMMARY_SYSTEM = """\
You are Nova, the AI pipeline analyst in NovaCRM. Analyse the provided pipeline snapshot and return a structured summary.

Respond in exactly this JSON format (no markdown fences, no extra keys):
{
  "headline": "One compelling sentence summarising overall pipeline health and momentum (max 120 chars).",
  "opportunities": [
    "Specific opportunity the team should act on today — one concise sentence.",
    "Second opportunity — one concise sentence.",
    "Third opportunity — one concise sentence."
  ],
  "risks": [
    "Specific risk that needs attention — one concise sentence.",
    "Second risk — one concise sentence.",
    "Third risk — one concise sentence."
  ]
}

Each opportunity or risk must reference specific deals, stages, or metrics from the data, and recommend a concrete CRM action.\
"""

_STAGE_ORDER = ["discovery", "qualified", "proposal", "negotiation"]


@router.post("/workspaces/{workspace_id}/ai/pipeline-summary")
@limiter.limit("5/minute")
async def pipeline_summary(
    request: Request,
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Generate a pipeline AI summary: headline + opportunities + risks, via Claude Haiku."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    deal_result = await db.execute(
        select(Deal).where(
            Deal.workspace_id == workspace_id,
            Deal.stage.not_in(["closed_won", "closed_lost"]),
        )
    )
    open_deals = deal_result.scalars().all()

    today = datetime.date.today()
    overdue = [d for d in open_deals if d.next_action_date and d.next_action_date < today]
    stale = [d for d in open_deals if d.health_score is not None and d.health_score < 40]

    all_competitors: list[str] = []
    for d in open_deals:
        if d.competitors:
            all_competitors.extend(d.competitors)
    top_competitors = [c for c, _ in Counter(all_competitors).most_common(5)]

    by_stage: dict[str, list] = defaultdict(list)
    for d in open_deals:
        by_stage[d.stage].append(d)

    pipeline_value = sum(float(d.value) for d in open_deals)

    lines = [
        f"Pipeline snapshot ({today.isoformat()}):",
        f"Total active pipeline: ${pipeline_value:,.0f} across {len(open_deals)} open deals",
        f"Stale deals (health < 40): {len(stale)}",
        f"Overdue next actions: {len(overdue)}",
        f"Top competitors: {', '.join(top_competitors) if top_competitors else 'none'}",
        "",
        "Deals by stage:",
    ]
    for stage in _STAGE_ORDER:
        stage_deals = by_stage.get(stage, [])
        if stage_deals:
            lines.append(f"  {stage.upper()} ({len(stage_deals)} deals):")
            for d in stage_deals[:5]:
                lines.append(
                    f"    - {d.title or 'Untitled'} @ {d.company or '?'}"
                    f" | ${float(d.value):,.0f} | health={d.health_score} | win_prob={d.ml_win_probability}%"
                )
    if stale:
        lines.append("")
        lines.append("Stale deals needing attention:")
        for d in stale[:5]:
            lines.append(f"  - {d.title or 'Untitled'} @ {d.company or '?'} health={d.health_score}/100")
    if overdue:
        lines.append("")
        lines.append("Overdue next actions:")
        for d in overdue[:5]:
            delta = (today - d.next_action_date).days
            lines.append(f"  - {d.title or 'Untitled'}: \"{d.next_action or 'unset'}\" ({delta}d overdue)")

    context = "\n".join(lines)

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            system=_PIPELINE_SUMMARY_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg.content[0].text.strip() if msg.content else "{}"
        data = json.loads(raw)
        headline = str(data.get("headline", "Pipeline summary unavailable."))
        opportunities = [str(b) for b in (data.get("opportunities") or [])[:3]]
        risks = [str(b) for b in (data.get("risks") or [])[:3]]
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    return {
        "headline": headline,
        "opportunities": opportunities,
        "risks": risks,
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
    }


# ---------------------------------------------------------------------------
# AI task suggestions for a contact
# ---------------------------------------------------------------------------

_SUGGEST_TASKS_SYSTEM = """\
You are Nova, the AI assistant in NovaCRM. Suggest specific, actionable follow-up tasks for a sales rep based on their contact's profile and recent interactions.

Respond in exactly this JSON format (no markdown fences, no extra keys):
{
  "suggestions": [
    {"title": "Task title — specific and actionable (max 80 chars)", "due_days": 3, "priority": "high"},
    {"title": "Second task", "due_days": 7, "priority": "medium"},
    {"title": "Third task", "due_days": 14, "priority": "low"}
  ]
}

Rules:
- Return 3–5 suggestions maximum
- Each title must be specific and name the contact or deal where relevant (max 80 chars)
- due_days: how many days from today the task should be due (integer, 1–30)
- priority: exactly "high", "medium", or "low"
- Follow up on recent messages, open deals, or relationship gaps visible in the data
- Avoid vague tasks — always name a concrete action\
"""


@router.post("/workspaces/{workspace_id}/ai/contacts/{contact_id}/suggest-tasks")
@limiter.limit("10/minute")
async def suggest_contact_tasks(
    request: Request,
    workspace_id: uuid.UUID,
    contact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Suggest 3–5 actionable follow-up tasks for a contact using Claude Haiku."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    contact_result = await db.execute(
        select(Contact).where(Contact.workspace_id == workspace_id, Contact.id == contact_id)
    )
    contact = contact_result.scalar_one_or_none()
    if contact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    # Last 3 messages
    msg_result = await db.execute(
        select(Message.subject, Message.received_at)
        .where(Message.workspace_id == workspace_id, Message.contact_id == contact_id)
        .order_by(Message.received_at.desc())
        .limit(3)
    )
    recent_messages = msg_result.all()

    # Open deals linked to this contact
    deal_result = await db.execute(
        select(Deal.title, Deal.stage, Deal.value, Deal.health_score)
        .where(
            Deal.workspace_id == workspace_id,
            Deal.contact_id == contact_id,
            Deal.stage.not_in(["closed_won", "closed_lost"]),
        )
        .limit(3)
    )
    open_deals = deal_result.all()

    lines = [
        f"Contact: {contact.name or 'Unknown'} ({contact.role or 'unknown role'} at {contact.company or 'Unknown'})",
        f"Status: {contact.status}",
        f"Email: {contact.email or 'unknown'}",
    ]
    if recent_messages:
        lines.append("Recent messages:")
        for m in recent_messages:
            ts = m.received_at.strftime("%b %d") if m.received_at else "unknown date"
            lines.append(f"  - \"{m.subject or '(no subject)'}\" on {ts}")
    else:
        lines.append("No prior messages — this is a first-touch contact.")
    if open_deals:
        lines.append("Open deals:")
        for d in open_deals:
            lines.append(f"  - {d.title or 'Untitled'} ({d.stage}) ${float(d.value):,.0f} health={d.health_score}")

    context = "\n".join(lines)

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            system=_SUGGEST_TASKS_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg.content[0].text.strip() if msg.content else "{}"
        data = json.loads(raw)
        raw_suggestions = data.get("suggestions") or []
        suggestions = []
        for s in raw_suggestions[:5]:
            priority = str(s.get("priority", "medium"))
            if priority not in ("high", "medium", "low"):
                priority = "medium"
            try:
                due_days = max(1, min(30, int(s.get("due_days", 7))))
            except (TypeError, ValueError):
                due_days = 7
            suggestions.append({
                "title": str(s.get("title", "Follow up"))[:80],
                "due_days": due_days,
                "priority": priority,
            })
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    return {
        "suggestions": suggestions,
        "contact_id": str(contact_id),
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
    }


# ---------------------------------------------------------------------------
# AI win/loss analysis for closed deals
# ---------------------------------------------------------------------------

_WIN_LOSS_SYSTEM = """\
You are Nova, the AI sales analyst in NovaCRM. Analyse the provided closed deal data and return a structured win/loss analysis.

Respond in exactly this JSON format (no markdown fences, no extra keys):
{
  "narrative": "2–3 sentence narrative explaining the outcome — be specific about the deal, company, and the deciding factors.",
  "key_factors": [
    "Factor 1 — specific one-sentence insight about what drove the outcome.",
    "Factor 2 — specific one-sentence insight.",
    "Factor 3 — specific one-sentence insight."
  ],
  "lessons": [
    "Lesson 1 — actionable takeaway for the team going forward.",
    "Lesson 2 — actionable takeaway.",
    "Lesson 3 — actionable takeaway."
  ]
}

Rules:
- narrative: 2–3 sentences, specific to this deal (name the company, stage, value, outcome reason)
- key_factors: 3 items, each naming a specific data point from the deal that drove the outcome
- lessons: 3 items, each prescribing a concrete change the team can make for future deals
- Be honest about the data — if a deal was lost, name the real weakness\
"""


@router.post("/workspaces/{workspace_id}/deals/{deal_id}/ai/win-loss-analysis")
@limiter.limit("10/minute")
async def deal_win_loss_analysis(
    request: Request,
    workspace_id: uuid.UUID,
    deal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Generate a win/loss analysis for a closed deal using Claude Haiku."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    deal_result = await db.execute(
        select(Deal).where(Deal.id == deal_id, Deal.workspace_id == workspace_id)
    )
    deal = deal_result.scalar_one_or_none()
    if deal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found")

    if deal.stage not in ("closed_won", "closed_lost"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Win/loss analysis is only available for closed deals",
        )

    # Fetch deal notes
    from app.models.deal_note import DealNote
    notes_result = await db.execute(
        select(DealNote.body, DealNote.author, DealNote.created_at)
        .where(DealNote.workspace_id == workspace_id, DealNote.deal_id == deal_id)
        .order_by(DealNote.created_at.desc())
        .limit(5)
    )
    notes = notes_result.all()

    verdict = "won" if deal.stage == "closed_won" else "lost"
    competitors = deal.competitors or []

    # Days from creation to close
    days_to_close: int | None = None
    if deal.stage_changed_at and deal.created_at:
        ref = deal.stage_changed_at
        start = deal.created_at
        if ref.tzinfo is None:
            ref = ref.replace(tzinfo=timezone.utc)
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        days_to_close = (ref - start).days

    lines = [
        f"Deal: {deal.title or 'Untitled'} at {deal.company or 'Unknown Company'}",
        f"Outcome: {verdict.upper()} (stage: {deal.stage})",
        f"Value: ${float(deal.value):,.0f}",
        f"Win/loss reason on record: {deal.win_loss_reason or 'not recorded'}",
        f"Final health score: {deal.health_score}/100",
        f"Final ML win probability: {deal.ml_win_probability}%",
        f"Days to close: {days_to_close if days_to_close is not None else 'unknown'}",
        f"Competitors tracked: {', '.join(competitors) if competitors else 'none'}",
    ]
    if notes:
        lines.append("Deal notes:")
        for n in notes:
            ts = n.created_at.strftime("%b %d") if n.created_at else "unknown"
            lines.append(f"  - [{ts}] {n.author or 'Unknown'}: {n.body[:120]}")
    else:
        lines.append("No deal notes recorded.")

    context = "\n".join(lines)

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            system=_WIN_LOSS_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg.content[0].text.strip() if msg.content else "{}"
        data = json.loads(raw)
        narrative = str(data.get("narrative", "Analysis unavailable."))
        key_factors = [str(f) for f in (data.get("key_factors") or [])[:3]]
        lessons = [str(l) for l in (data.get("lessons") or [])[:3]]
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    return {
        "verdict": verdict,
        "narrative": narrative,
        "key_factors": key_factors,
        "lessons": lessons,
        "deal_id": str(deal_id),
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
    }


# ---------------------------------------------------------------------------
# AI deal risk narrative
# ---------------------------------------------------------------------------

_RISK_NARRATIVE_SYSTEM = """\
You are Nova, the AI risk analyst in NovaCRM. Analyse the provided open deal data and return a concise risk narrative.

Respond in exactly this JSON format (no markdown fences, no extra keys):
{
  "risk_level": "medium",
  "narrative": "2–3 sentence prose describing the specific risk profile of this deal — name the company, stage, and the primary risk driver.",
  "top_risks": [
    "Risk 1 — one concise sentence naming a specific risk factor and its potential impact.",
    "Risk 2 — one concise sentence.",
    "Risk 3 — one concise sentence."
  ]
}

Risk level rules (pick exactly one):
- "high": health score < 40, OR win probability < 25%, OR close date overdue by 14+ days, OR at least 2 of: competitors > 2, days in stage > 30, next-action overdue
- "low": health score >= 70 AND win probability >= 60% AND no overdue next-action AND close date not slipped
- "medium": everything else that does not qualify as high or low

Return 2–3 top_risks. Be specific — reference actual data from the deal, not generic advice.\
"""


@router.post("/workspaces/{workspace_id}/deals/{deal_id}/ai/risk-narrative")
@limiter.limit("10/minute")
async def deal_risk_narrative(
    request: Request,
    workspace_id: uuid.UUID,
    deal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Generate a risk narrative for an open deal using Claude Haiku."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    deal_result = await db.execute(
        select(Deal).where(Deal.id == deal_id, Deal.workspace_id == workspace_id)
    )
    deal = deal_result.scalar_one_or_none()
    if deal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found")

    if deal.stage in ("closed_won", "closed_lost"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Risk narrative is only available for open deals",
        )

    # Days in current stage
    now = datetime.datetime.now(timezone.utc)
    stage_ref = deal.stage_changed_at or deal.created_at
    if stage_ref and stage_ref.tzinfo is None:
        stage_ref = stage_ref.replace(tzinfo=timezone.utc)
    days_in_stage = (now - stage_ref).days if stage_ref else 0

    # Close date slippage
    close_overdue_days: int | None = None
    if deal.expected_close:
        try:
            expected = datetime.date.fromisoformat(str(deal.expected_close))
            overdue = (datetime.date.today() - expected).days
            if overdue > 0:
                close_overdue_days = overdue
        except (ValueError, TypeError):
            pass

    # Overdue next action
    next_action_overdue = False
    if deal.next_action_date:
        try:
            na_date = deal.next_action_date
            if hasattr(na_date, "isoformat"):
                next_action_overdue = na_date < datetime.date.today()
        except (ValueError, TypeError):
            pass

    competitors = deal.competitors or []

    # Last 3 deal notes
    from app.models.deal_note import DealNote
    notes_result = await db.execute(
        select(DealNote.body, DealNote.author, DealNote.created_at)
        .where(DealNote.workspace_id == workspace_id, DealNote.deal_id == deal_id)
        .order_by(DealNote.created_at.desc())
        .limit(3)
    )
    notes = notes_result.all()

    lines = [
        f"Deal: {deal.title or 'Untitled'} at {deal.company or 'Unknown Company'}",
        f"Stage: {deal.stage}",
        f"Value: ${float(deal.value):,.0f}",
        f"Health score: {deal.health_score}/100",
        f"ML win probability: {deal.ml_win_probability}%",
        f"Days in current stage: {days_in_stage}",
        f"Competitors tracked: {', '.join(competitors) if competitors else 'none'} ({len(competitors)} total)",
        f"Next action overdue: {'yes' if next_action_overdue else 'no'}",
    ]
    if close_overdue_days is not None:
        lines.append(f"Close date overdue by: {close_overdue_days} days")
    else:
        lines.append("Close date: not overdue or not set")

    if notes:
        lines.append("Recent deal notes:")
        for n in notes:
            ts = n.created_at.strftime("%b %d") if n.created_at else "unknown"
            lines.append(f"  - [{ts}] {n.author or 'Unknown'}: {n.body[:120]}")
    else:
        lines.append("No deal notes recorded.")

    context = "\n".join(lines)

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            system=_RISK_NARRATIVE_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg.content[0].text.strip() if msg.content else "{}"
        data = json.loads(raw)
        risk_level = str(data.get("risk_level", "medium"))
        if risk_level not in ("low", "medium", "high"):
            risk_level = "medium"
        narrative = str(data.get("narrative", "Risk assessment unavailable."))
        top_risks = [str(r) for r in (data.get("top_risks") or [])[:3]]
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    return {
        "risk_level": risk_level,
        "narrative": narrative,
        "top_risks": top_risks,
        "deal_id": str(deal_id),
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
    }


# ---------------------------------------------------------------------------
# Contact relationship health summary
# ---------------------------------------------------------------------------

_RELATIONSHIP_HEALTH_SYSTEM = """\
You are Nova, the AI relationship intelligence in NovaCRM. Analyse the provided contact relationship data and return a structured health assessment.

Respond in exactly this JSON format (no markdown fences, no extra keys):
{
  "health_rating": "strong",
  "summary": "Exactly two sentences: first describes the current state of this relationship with specific numbers where available; second identifies the key trend or risk.",
  "action_items": [
    {"priority": "high", "action": "Specific, actionable next step — max 80 chars, reference a CRM feature where helpful."},
    {"priority": "medium", "action": "Second action."},
    {"priority": "low", "action": "Third action."}
  ]
}

Health rating rules (pick exactly one):
- "strong": 5+ touches (messages + notes) in the last 90 days, AND avg response ≤ 8h or response data unavailable, AND no 30+ day silence
- "at_risk": 0–1 touches in 90 days, OR avg response > 72h, OR last touch was 30+ days ago
- "neutral": everything else that doesn't qualify as strong or at_risk

Return 2–3 action_items maximum. Tailor every item specifically to this contact's data — no generic advice.\
"""


@router.post("/workspaces/{workspace_id}/ai/contacts/{contact_id}/relationship-health")
@limiter.limit("10/minute")
async def contact_relationship_health(
    request: Request,
    workspace_id: uuid.UUID,
    contact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Generate an AI relationship health summary for a contact using Claude Haiku."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    contact_result = await db.execute(
        select(Contact).where(Contact.workspace_id == workspace_id, Contact.id == contact_id)
    )
    contact = contact_result.scalar_one_or_none()
    if contact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    cutoff_90 = datetime.datetime.now(timezone.utc) - datetime.timedelta(days=90)

    # Message and note counts for last 90 days
    msg_count = await db.scalar(
        select(func.count()).where(
            Message.workspace_id == workspace_id,
            Message.contact_id == contact_id,
            Message.received_at >= cutoff_90,
        )
    ) or 0

    note_count = await db.scalar(
        select(func.count()).where(
            ContactNote.workspace_id == workspace_id,
            ContactNote.contact_id == contact_id,
            ContactNote.created_at >= cutoff_90,
        )
    ) or 0

    tasks_total = await db.scalar(
        select(func.count()).where(
            Task.workspace_id == workspace_id,
            Task.contact_id == contact_id,
        )
    ) or 0

    tasks_done = await db.scalar(
        select(func.count()).where(
            Task.workspace_id == workspace_id,
            Task.contact_id == contact_id,
            Task.status == "done",
        )
    ) or 0

    # Last 3 messages with clarity scores
    msg_result = await db.execute(
        select(Message.subject, Message.received_at, ClarityScore.score)
        .outerjoin(ClarityScore, Message.id == ClarityScore.message_id)
        .where(Message.workspace_id == workspace_id, Message.contact_id == contact_id)
        .order_by(Message.received_at.desc())
        .limit(3)
    )
    recent_messages = msg_result.all()

    # Days since last touch
    last_touch_days: int | None = None
    if recent_messages and recent_messages[0].received_at:
        ref = recent_messages[0].received_at
        if ref.tzinfo is None:
            ref = ref.replace(tzinfo=timezone.utc)
        last_touch_days = (datetime.datetime.now(timezone.utc) - ref).days

    total_touches = msg_count + note_count
    task_rate = f"{tasks_done}/{tasks_total}" if tasks_total > 0 else "no tasks"

    lines = [
        f"Contact: {contact.name or 'Unknown'} ({contact.role or 'unknown role'} at {contact.company or 'Unknown'})",
        f"Status: {contact.status}",
        f"Last activity: {contact.last_activity}",
        "",
        f"Engagement last 90 days:",
        f"  Messages received: {msg_count}",
        f"  Notes added: {note_count}",
        f"  Total touches: {total_touches}",
        f"  Tasks: {task_rate} completed",
    ]

    if last_touch_days is not None:
        lines.append(f"  Days since last touch: {last_touch_days}")

    if recent_messages:
        lines.append("")
        lines.append("Recent messages (newest first):")
        for m in recent_messages:
            clarity = f" — clarity {m.score}/100" if m.score is not None else ""
            ts = m.received_at.strftime("%b %d") if m.received_at else "unknown"
            lines.append(f"  - [{ts}] \"{m.subject or '(no subject)'}\"  {clarity}")
    else:
        lines.append("")
        lines.append("No message history on record.")

    context = "\n".join(lines)

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            system=_RELATIONSHIP_HEALTH_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg.content[0].text.strip() if msg.content else "{}"
        data = json.loads(raw)
        health_rating = str(data.get("health_rating", "neutral"))
        if health_rating not in ("strong", "neutral", "at_risk"):
            health_rating = "neutral"
        summary = str(data.get("summary", "Relationship health assessment unavailable."))
        raw_items = data.get("action_items") or []
        action_items = []
        for item in raw_items[:3]:
            priority = str(item.get("priority", "medium"))
            if priority not in ("high", "medium", "low"):
                priority = "medium"
            action_items.append({
                "priority": priority,
                "action": str(item.get("action", "Review relationship data"))[:80],
            })
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    return {
        "health_rating": health_rating,
        "summary": summary,
        "action_items": action_items,
        "contact_id": str(contact_id),
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
    }
