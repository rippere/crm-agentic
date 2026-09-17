import datetime
import json
import uuid
from collections import Counter, defaultdict
from datetime import timezone

import statistics

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
from app.models.deal_note import DealNote
from app.models.message import Message
from app.models.connector import Connector
from app.models.task import Task
from app.models.activity_event import ActivityEvent
from app.models.deal_health_history import DealHealthHistory

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
# AI pipeline pulse (structured data + 2-sentence insight)
# ---------------------------------------------------------------------------

_PIPELINE_PULSE_SYSTEM = """\
You are Nova, the AI pipeline analyst in NovaCRM. Generate a 2-sentence insight about the provided pipeline.

Respond with exactly this JSON format (no markdown fences, no extra keys):
{"insight": "First sentence about overall health and momentum. Second sentence with a specific, actionable recommendation referencing a CRM feature."}

Rules:
- Exactly 2 sentences separated by a period and a space
- Cite specific numbers from the context (total value, at-risk count, top stage)
- End with a concrete CRM action: "Run Deal Health check", "Schedule a QBR call", "Draft Outreach email", "Update ML win probability"\
"""


@router.get("/workspaces/{workspace_id}/ai/pipeline-pulse")
@limiter.limit("10/minute")
async def pipeline_pulse(
    request: Request,
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    deal_result = await db.execute(
        select(Deal).where(
            Deal.workspace_id == workspace_id,
            Deal.stage.not_in(["closed_won", "closed_lost"]),
        )
    )
    open_deals = deal_result.scalars().all()

    total_value = sum(float(d.value) for d in open_deals)
    at_risk_count = sum(1 for d in open_deals if (d.health_score or 0) < 50)
    health_avg = (
        round(sum(d.health_score or 0 for d in open_deals) / len(open_deals))
        if open_deals else 0
    )

    top_deal = None
    if open_deals:
        td = max(open_deals, key=lambda d: float(d.value))
        top_deal = {"title": td.title or "Untitled", "value": float(td.value), "stage": td.stage}

    by_stage: dict[str, dict] = {}
    for d in open_deals:
        s = d.stage
        if s not in by_stage:
            by_stage[s] = {"stage": s, "count": 0, "value": 0.0}
        by_stage[s]["count"] += 1
        by_stage[s]["value"] += float(d.value)
    stage_breakdown = [by_stage[s] for s in _STAGE_ORDER if s in by_stage]

    lines = [
        f"Open pipeline: {len(open_deals)} deals, ${total_value:,.0f} total",
        f"Average health score: {health_avg}/100",
        f"At-risk deals (health < 50): {at_risk_count}",
        f"Stage breakdown: " + ", ".join(
            f"{s['stage'].upper()} {s['count']} deals ${s['value']:,.0f}" for s in stage_breakdown
        ),
    ]
    if top_deal:
        lines.append(
            f"Top deal by value: \"{top_deal['title']}\" ${top_deal['value']:,.0f} in {top_deal['stage']}"
        )
    context = "\n".join(lines)

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            system=_PIPELINE_PULSE_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg.content[0].text.strip() if msg.content else "{}"
        data = json.loads(raw)
        insight = str(data.get("insight", "Pipeline health is nominal. Review at-risk deals and update next actions."))[:300]
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    return {
        "total_value": total_value,
        "at_risk_count": at_risk_count,
        "top_deal": top_deal,
        "stage_breakdown": stage_breakdown,
        "health_avg": health_avg,
        "insight": insight,
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


# ---------------------------------------------------------------------------
# AI outreach sequence planner
# ---------------------------------------------------------------------------

_OUTREACH_SEQUENCE_SYSTEM = """\
You are Nova, the AI outreach strategist in NovaCRM. Given a contact profile and recent context, \
design a concise 3-step outreach sequence to re-engage or advance the relationship.

Respond in exactly this JSON format (no markdown fences, no extra keys):
{
  "steps": [
    {
      "step": 1,
      "channel": "email",
      "timing": "now",
      "subject": "Quick check-in on <topic>",
      "body_preview": "Hi <name>, I wanted to follow up on...",
      "goal": "Re-open the conversation and gauge interest"
    },
    {
      "step": 2,
      "channel": "call",
      "timing": "3d",
      "subject": null,
      "body_preview": "Call script: confirm receipt of email, ask about timeline and blockers...",
      "goal": "Qualify urgency and identify decision-maker"
    },
    {
      "step": 3,
      "channel": "email",
      "timing": "7d",
      "subject": "Resources + next steps for <company>",
      "body_preview": "Hi <name>, sharing the case study we discussed plus a proposal outline...",
      "goal": "Deliver value and propose a meeting"
    }
  ]
}

Rules:
- Exactly 3 steps
- channel must be one of: email, slack, call
- timing must be one of: now, 3d, 7d, 14d
- subject is required for email/slack steps; null for call steps
- body_preview: 1–2 sentences only, personalised with contact name and company
- goal: one sentence, outcome-focused
- Base timing on urgency: if last touch > 30 days use "now", otherwise spread across 3d/7d/14d\
"""


@router.post("/workspaces/{workspace_id}/ai/contacts/{contact_id}/outreach-sequence")
@limiter.limit("10/minute")
async def suggest_outreach_sequence(
    request: Request,
    workspace_id: uuid.UUID,
    contact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Generate a 3-step AI outreach sequence for a contact using Claude Haiku."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    contact_result = await db.execute(
        select(Contact).where(Contact.workspace_id == workspace_id, Contact.id == contact_id)
    )
    contact = contact_result.scalar_one_or_none()
    if contact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    # Last 3 messages with clarity scores
    msg_result = await db.execute(
        select(Message.subject, Message.received_at, ClarityScore.score)
        .outerjoin(ClarityScore, Message.id == ClarityScore.message_id)
        .where(Message.workspace_id == workspace_id, Message.contact_id == contact_id)
        .order_by(Message.received_at.desc())
        .limit(3)
    )
    recent_messages = msg_result.all()

    # Open tasks
    task_result = await db.execute(
        select(Task.title, Task.due_date)
        .where(
            Task.workspace_id == workspace_id,
            Task.contact_id == contact_id,
            Task.status.in_(["open", "in_progress"]),
        )
        .limit(5)
    )
    open_tasks = task_result.all()

    # Days since last touch
    last_touch_days: int | None = None
    if recent_messages and recent_messages[0].received_at:
        ref = recent_messages[0].received_at
        if ref.tzinfo is None:
            ref = ref.replace(tzinfo=timezone.utc)
        last_touch_days = (datetime.datetime.now(timezone.utc) - ref).days

    lines = [
        f"Contact: {contact.name or 'Unknown'} ({contact.role or 'unknown role'} at {contact.company or 'Unknown'})",
        f"Status: {contact.status}",
        f"Email: {contact.email or 'unknown'}",
    ]
    if last_touch_days is not None:
        lines.append(f"Days since last touch: {last_touch_days}")
    else:
        lines.append("No prior contact history — first-touch sequence.")

    if recent_messages:
        lines.append("Recent messages (newest first):")
        for m in recent_messages:
            clarity = f" — clarity {m.score}/100" if m.score is not None else ""
            ts = m.received_at.strftime("%b %d") if m.received_at else "unknown"
            lines.append(f"  - [{ts}] \"{m.subject or '(no subject)'}\"{clarity}")
    else:
        lines.append("No messages on record.")

    if open_tasks:
        lines.append("Open tasks:")
        for t in open_tasks:
            due = str(t.due_date) if t.due_date else "no due date"
            lines.append(f"  - {t.title} (due {due})")

    context = "\n".join(lines)

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            system=_OUTREACH_SEQUENCE_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg.content[0].text.strip() if msg.content else "{}"
        data = json.loads(raw)
        raw_steps = data.get("steps") or []
        valid_channels = {"email", "slack", "call"}
        valid_timings = {"now", "3d", "7d", "14d"}
        steps = []
        for s in raw_steps[:3]:
            channel = str(s.get("channel", "email"))
            if channel not in valid_channels:
                channel = "email"
            timing = str(s.get("timing", "7d"))
            if timing not in valid_timings:
                timing = "7d"
            steps.append({
                "step": int(s.get("step", len(steps) + 1)),
                "channel": channel,
                "timing": timing,
                "subject": str(s["subject"])[:120] if s.get("subject") else None,
                "body_preview": str(s.get("body_preview", ""))[:200],
                "goal": str(s.get("goal", ""))[:120],
            })
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    return {
        "steps": steps,
        "contact_id": str(contact_id),
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
    }


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


# ---------------------------------------------------------------------------
# Contact health overview (workspace-level)
# ---------------------------------------------------------------------------

_HEALTH_OVERVIEW_SYSTEM = """\
You are Nova, the AI assistant for NovaCRM. Write a single concise summary sentence \
(max 25 words) describing the overall contact health state for this workspace — \
mention at-risk count or strong count if notable. No JSON. Plain sentence only.\
"""


@router.get("/workspaces/{workspace_id}/ai/contacts/health-overview")
@limiter.limit("5/minute")
async def contact_health_overview(
    request: Request,
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Scan top 10 contacts by pipeline value, compute health, return a structured overview."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    # Top 10 contacts by sum of open deal values
    subq = (
        select(Deal.contact_id, func.sum(Deal.value).label("pipeline_value"))
        .where(
            Deal.workspace_id == workspace_id,
            Deal.stage.notin_(["closed_won", "closed_lost"]),
        )
        .group_by(Deal.contact_id)
        .order_by(func.sum(Deal.value).desc())
        .limit(10)
        .subquery()
    )
    contact_rows = await db.execute(
        select(Contact, subq.c.pipeline_value)
        .join(subq, Contact.id == subq.c.contact_id)
        .where(Contact.workspace_id == workspace_id)
        .order_by(subq.c.pipeline_value.desc())
    )
    contacts_with_value = contact_rows.all()

    if not contacts_with_value:
        fallback_rows = await db.execute(
            select(Contact)
            .where(Contact.workspace_id == workspace_id)
            .order_by(Contact.created_at.desc())
            .limit(10)
        )
        contacts_with_value = [(c, 0) for c in fallback_rows.scalars().all()]

    cutoff_90 = datetime.datetime.now(timezone.utc) - datetime.timedelta(days=90)

    result_contacts = []
    for contact, _pipeline_val in contacts_with_value:
        msg_count = await db.scalar(
            select(func.count()).where(
                Message.workspace_id == workspace_id,
                Message.contact_id == contact.id,
                Message.received_at >= cutoff_90,
            )
        ) or 0
        note_count = await db.scalar(
            select(func.count()).where(
                ContactNote.workspace_id == workspace_id,
                ContactNote.contact_id == contact.id,
                ContactNote.created_at >= cutoff_90,
            )
        ) or 0
        tasks_total = await db.scalar(
            select(func.count()).where(
                Task.workspace_id == workspace_id,
                Task.contact_id == contact.id,
                Task.created_at >= cutoff_90,
            )
        ) or 0
        tasks_done = await db.scalar(
            select(func.count()).where(
                Task.workspace_id == workspace_id,
                Task.contact_id == contact.id,
                Task.status == "done",
                Task.created_at >= cutoff_90,
            )
        ) or 0

        last_msg_row = await db.execute(
            select(Message.received_at)
            .where(Message.workspace_id == workspace_id, Message.contact_id == contact.id)
            .order_by(Message.received_at.desc())
            .limit(1)
        )
        last_msg_date = last_msg_row.scalar_one_or_none()

        last_note_row = await db.execute(
            select(ContactNote.created_at)
            .where(ContactNote.workspace_id == workspace_id, ContactNote.contact_id == contact.id)
            .order_by(ContactNote.created_at.desc())
            .limit(1)
        )
        last_note_date = last_note_row.scalar_one_or_none()

        dates = [d for d in [last_msg_date, last_note_date] if d is not None]
        if dates:
            most_recent = max(
                d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d for d in dates
            )
            days_since_touch = (datetime.datetime.now(timezone.utc) - most_recent).days
        else:
            days_since_touch = None

        messages_score = min(40, msg_count * 8)
        notes_score = min(30, note_count * 10)
        tasks_score = round(30 * tasks_done / tasks_total) if tasks_total > 0 else 0
        engagement_score = messages_score + notes_score + tasks_score

        going_dark = days_since_touch is None or days_since_touch > 30
        if engagement_score >= 60 and not going_dark:
            health = "strong"
        elif engagement_score < 40 or going_dark:
            health = "at_risk"
        else:
            health = "neutral"

        if going_dark:
            if days_since_touch is not None:
                top_action = f"Re-engage — no contact in {days_since_touch} days"
            else:
                top_action = "Re-engage — no contact history found"
        elif health == "strong":
            top_action = "Maintain cadence and look for expansion"
        elif health == "neutral":
            top_action = "Add a note or follow-up task"
        else:
            top_action = "Increase engagement frequency"

        result_contacts.append({
            "id": str(contact.id),
            "name": contact.name or "Unknown",
            "health": health,
            "days_since_touch": days_since_touch,
            "top_action": top_action,
            "engagement_score": engagement_score,
        })

    at_risk_count = sum(1 for c in result_contacts if c["health"] == "at_risk")
    strong_count = sum(1 for c in result_contacts if c["health"] == "strong")

    contact_lines = []
    for c in result_contacts:
        touch_label = f"{c['days_since_touch']}d ago" if c["days_since_touch"] is not None else "never"
        contact_lines.append(
            f"  - {c['name']}: health={c['health']}, last_touch={touch_label}, engagement={c['engagement_score']}/100"
        )
    context = (
        f"Top {len(result_contacts)} contacts by pipeline value:\n"
        + "\n".join(contact_lines)
        + f"\n\nSummary: {at_risk_count} at risk, {strong_count} strong, "
        + f"{len(result_contacts) - at_risk_count - strong_count} neutral."
    )

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=60,
            system=_HEALTH_OVERVIEW_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        summary_sentence = msg.content[0].text.strip() if msg.content else ""
    except Exception:
        summary_sentence = ""

    if not summary_sentence:
        summary_sentence = (
            f"{at_risk_count} contact{'s' if at_risk_count != 1 else ''} at risk, "
            f"{strong_count} in strong health."
        )

    return {
        "at_risk_count": at_risk_count,
        "strong_count": strong_count,
        "summary_sentence": summary_sentence,
        "contacts": result_contacts,
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
    }


# ---------------------------------------------------------------------------
# AI deal momentum check
# ---------------------------------------------------------------------------

_MOMENTUM_SYSTEM = """\
You are Nova, the AI deal intelligence in NovaCRM. Assess the current momentum of the provided deal.

Respond in exactly this JSON format (no markdown fences, no extra keys):
{
  "momentum": "gaining",
  "drivers": [
    "One sentence — specific data point that justifies this momentum direction.",
    "Second driver — another concrete data point."
  ],
  "recommendation": "One specific action to sustain or reverse this momentum — max 100 chars, reference a CRM feature."
}

Momentum rules (pick exactly one):
- "gaining": health score trend is improving across last readings, OR high recent activity (5+ events in 30d) AND last touch within 14 days
- "declining": health score trend is decreasing across 2+ consecutive readings, OR no activity in 30+ days, OR next action overdue and health < 50
- "stalling": everything else — deal is present but not clearly moving either direction

drivers: 2–3 items, each citing a specific metric from the provided data (score, days, counts)
recommendation: 1 sentence naming a specific CRM action — e.g. "Schedule a QBR call", "Add a Deal Note to capture latest discussion", "Run Deal Health check"\
"""


@router.post("/workspaces/{workspace_id}/deals/{deal_id}/ai/momentum-check")
@limiter.limit("10/minute")
async def deal_momentum_check(
    request: Request,
    workspace_id: uuid.UUID,
    deal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Assess deal momentum using health score trend, activity, and engagement signals via Claude Haiku."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    deal_result = await db.execute(
        select(Deal).where(Deal.id == deal_id, Deal.workspace_id == workspace_id)
    )
    deal = deal_result.scalar_one_or_none()
    if deal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found")

    # Last 5 health score history entries (oldest first for trend)
    history_result = await db.execute(
        select(DealHealthHistory.score, DealHealthHistory.recorded_at)
        .where(DealHealthHistory.workspace_id == workspace_id, DealHealthHistory.deal_id == deal_id)
        .order_by(DealHealthHistory.recorded_at.desc())
        .limit(5)
    )
    history_rows = list(reversed(history_result.all()))  # oldest→newest

    # Recent activity count (last 30 days)
    cutoff_30 = datetime.datetime.now(timezone.utc) - datetime.timedelta(days=30)
    recent_activity = await db.scalar(
        select(func.count()).where(
            ActivityEvent.workspace_id == workspace_id,
            ActivityEvent.created_at >= cutoff_30,
        ).correlate(False)
    ) or 0

    # Days in current stage
    now = datetime.datetime.now(timezone.utc)
    stage_ref = deal.stage_changed_at or deal.created_at
    if stage_ref and stage_ref.tzinfo is None:
        stage_ref = stage_ref.replace(tzinfo=timezone.utc)
    days_in_stage = (now - stage_ref).days if stage_ref else 0

    # Next-action overdue
    next_action_overdue_days = 0
    if deal.next_action_date:
        try:
            na_date = deal.next_action_date
            delta = (datetime.date.today() - na_date).days
            next_action_overdue_days = max(0, delta)
        except (ValueError, TypeError):
            pass

    competitors = deal.competitors or []

    # Build context lines
    lines = [
        f"Deal: {deal.title or 'Untitled'} at {deal.company or 'Unknown Company'}",
        f"Stage: {deal.stage}",
        f"Value: ${float(deal.value):,.0f}",
        f"Current health score: {deal.health_score}/100",
        f"ML win probability: {deal.ml_win_probability}%",
        f"Days in current stage: {days_in_stage}",
        f"Competitors tracked: {len(competitors)}",
        f"Next action overdue by: {next_action_overdue_days} day{'s' if next_action_overdue_days != 1 else ''}",
        f"Recent workspace activity (last 30d): {recent_activity} events",
    ]

    if history_rows:
        score_trail = " → ".join(str(h.score) for h in history_rows)
        lines.append(f"Health score trend (oldest→newest): {score_trail}")
        if len(history_rows) >= 2:
            delta = history_rows[-1].score - history_rows[-2].score
            trend_label = f"up {delta}" if delta > 0 else (f"down {abs(delta)}" if delta < 0 else "flat")
            lines.append(f"Latest score change: {trend_label}")
    else:
        lines.append("Health score history: no prior readings")

    context = "\n".join(lines)

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            system=_MOMENTUM_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg.content[0].text.strip() if msg.content else "{}"
        data = json.loads(raw)
        momentum = str(data.get("momentum", "stalling"))
        if momentum not in ("gaining", "stalling", "declining"):
            momentum = "stalling"
        drivers = [str(d) for d in (data.get("drivers") or [])[:3]]
        recommendation = str(data.get("recommendation", "Review deal health and update the next action."))[:100]
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    return {
        "momentum": momentum,
        "drivers": drivers,
        "recommendation": recommendation,
        "deal_id": str(deal_id),
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
    }


# ---------------------------------------------------------------------------
# AI deal close plan
# ---------------------------------------------------------------------------

_CLOSE_PLAN_SYSTEM = """\
You are Nova, the AI deal intelligence in NovaCRM. Generate a 3-phase close plan for the provided deal.

Respond in exactly this JSON format (no markdown fences, no extra keys):
{
  "phases": [
    {
      "label": "Next 30 days",
      "actions": [
        "Specific, concrete action referencing the deal context — e.g. Run Deal Health check to confirm score stabilisation.",
        "Second action — name a CRM feature or meeting type."
      ]
    },
    {
      "label": "30–60 days",
      "actions": [
        "Action for this timeframe.",
        "Another action."
      ]
    },
    {
      "label": "60–90 days",
      "actions": [
        "Action to finalise or escalate.",
        "Final action to close the deal."
      ]
    }
  ],
  "recommended_close_date": "YYYY-MM-DD"
}

Rules:
- phases: exactly 3 items, labels must be "Next 30 days", "30–60 days", "60–90 days" in that order
- actions: 2–4 items per phase, each citing a specific metric or CRM feature from the deal context
- recommended_close_date: realistic YYYY-MM-DD target based on current stage and expected_close; if expected_close is set and realistic, lean toward it
- CRM feature references: "Schedule a QBR call", "Add a Deal Note", "Run Deal Health check", "Draft Outreach email", "Update ML win probability"
- Keep each action concise (max 120 chars)\
"""


@router.post("/workspaces/{workspace_id}/deals/{deal_id}/ai/close-plan")
@limiter.limit("10/minute")
async def deal_close_plan(
    request: Request,
    workspace_id: uuid.UUID,
    deal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    result = await db.execute(
        select(Deal).where(Deal.id == deal_id, Deal.workspace_id == workspace_id)
    )
    deal = result.scalar_one_or_none()
    if deal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found")

    if deal.stage in ("closed_won", "closed_lost"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Close plan is not available for closed deals",
        )

    # Last 3 deal notes (oldest-first for context ordering)
    notes_result = await db.execute(
        select(DealNote)
        .where(DealNote.deal_id == deal_id, DealNote.workspace_id == workspace_id)
        .order_by(DealNote.created_at.desc())
        .limit(3)
    )
    recent_notes = list(reversed(notes_result.all()))

    # Days in current stage
    now = datetime.datetime.now(tz=timezone.utc)
    stage_ref = deal.stage_changed_at or deal.created_at
    if stage_ref and stage_ref.tzinfo is None:
        stage_ref = stage_ref.replace(tzinfo=timezone.utc)
    days_in_stage = (now - stage_ref).days if stage_ref else 0

    # Next-action overdue
    next_action_overdue_days = 0
    if deal.next_action_date:
        try:
            delta = (datetime.date.today() - deal.next_action_date).days
            next_action_overdue_days = max(0, delta)
        except (ValueError, TypeError):
            pass

    competitors = deal.competitors or []

    lines = [
        f"Deal: {deal.title or 'Untitled'} at {deal.company or 'Unknown Company'}",
        f"Stage: {deal.stage}",
        f"Value: ${float(deal.value):,.0f}",
        f"Current health score: {deal.health_score}/100",
        f"ML win probability: {deal.ml_win_probability}%",
        f"Days in current stage: {days_in_stage}",
        f"Competitors tracked: {len(competitors)}",
        f"Next action overdue by: {next_action_overdue_days} day{'s' if next_action_overdue_days != 1 else ''}",
        f"Expected close date: {deal.expected_close or 'Not set'}",
        f"Today: {datetime.date.today().isoformat()}",
    ]

    if recent_notes:
        lines.append("Recent deal notes (oldest→newest):")
        for note in recent_notes:
            body_preview = (note.body or "")[:200]
            lines.append(f"  - {body_preview}")
    else:
        lines.append("Recent deal notes: none")

    context = "\n".join(lines)

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            system=_CLOSE_PLAN_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg.content[0].text.strip() if msg.content else "{}"
        data = json.loads(raw)

        valid_labels = ("Next 30 days", "30–60 days", "60–90 days")
        phases = []
        for phase in (data.get("phases") or [])[:3]:
            label = str(phase.get("label", ""))
            if label not in valid_labels:
                continue
            actions = [str(a)[:120] for a in (phase.get("actions") or [])[:4]]
            phases.append({"label": label, "actions": actions})

        raw_date = str(data.get("recommended_close_date", ""))
        try:
            datetime.date.fromisoformat(raw_date)
            recommended_close_date = raw_date
        except (ValueError, TypeError):
            recommended_close_date = (
                datetime.date.today() + datetime.timedelta(days=60)
            ).isoformat()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    return {
        "phases": phases,
        "recommended_close_date": recommended_close_date,
        "deal_id": str(deal_id),
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
    }


# ---------------------------------------------------------------------------
# AI contact summary card
# ---------------------------------------------------------------------------

_CONTACT_SUMMARY_SYSTEM = """\
You are Nova, the AI assistant in NovaCRM. Generate a concise relationship summary for the provided contact.

Respond in exactly this JSON format (no markdown fences, no extra keys):
{
  "relationship_status": "strong",
  "summary": "2-3 sentence narrative describing the relationship quality, recent engagement patterns, and deal context.",
  "next_best_action": "One specific, actionable CRM step referencing a feature name."
}

Rules:
- relationship_status must be exactly one of: "strong", "warm", "cold", "at_risk"
  - strong: active engagement, healthy deals, positive signals
  - warm: moderate engagement, some open deals, no major red flags
  - cold: low engagement, few or no recent messages/notes
  - at_risk: declining engagement, overdue tasks, stalled deals, low health scores
- summary: 2-3 sentences, plain prose, no markdown; reference specific signals from the context
- next_best_action: one specific step, max 120 chars, name a CRM feature where helpful
  (e.g. "Schedule a QBR call", "Draft Outreach email", "Add a Contact Note", "Run Auto-Enrich")\
"""


@router.get("/workspaces/{workspace_id}/ai/contacts/{contact_id}/summary")
@limiter.limit("10/minute")
async def contact_summary(
    request: Request,
    workspace_id: uuid.UUID,
    contact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    # Contact profile
    contact_result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.workspace_id == workspace_id)
    )
    contact = contact_result.scalar_one_or_none()
    if contact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    # Last 3 messages with clarity scores
    msg_result = await db.execute(
        select(Message, ClarityScore.score)
        .outerjoin(ClarityScore, ClarityScore.message_id == Message.id)
        .where(Message.contact_id == contact_id, Message.workspace_id == workspace_id)
        .order_by(Message.created_at.desc())
        .limit(3)
    )
    recent_messages = msg_result.all()

    # Open task count
    open_task_count = await db.scalar(
        select(func.count()).where(
            Task.workspace_id == workspace_id,
            Task.contact_id == contact_id,
            Task.status == "open",
        )
    ) or 0

    # Open deals + total value
    deal_result = await db.execute(
        select(Deal.title, Deal.value, Deal.stage, Deal.health_score)
        .where(
            Deal.workspace_id == workspace_id,
            Deal.contact_id == contact_id,
            Deal.stage.notin_(["closed_won", "closed_lost"]),
        )
    )
    open_deals = deal_result.all()
    open_deal_count = len(open_deals)
    deal_value = sum(float(d.value) for d in open_deals)

    # Last contact note
    note_result = await db.execute(
        select(ContactNote)
        .where(ContactNote.contact_id == contact_id, ContactNote.workspace_id == workspace_id)
        .order_by(ContactNote.created_at.desc())
        .limit(1)
    )
    last_note = note_result.scalar_one_or_none()

    # Build context
    lines = [
        f"Contact: {contact.name or 'Unknown'} ({contact.role or 'Unknown role'} at {contact.company or 'Unknown company'})",
        f"Email: {contact.email or 'N/A'}",
        f"Open tasks: {open_task_count}",
        f"Open deals: {open_deal_count} (total pipeline value: ${deal_value:,.0f})",
    ]
    if open_deals:
        for d in open_deals[:3]:
            lines.append(f"  - Deal: {d.title or 'Untitled'} | stage={d.stage} | value=${float(d.value):,.0f} | health={d.health_score}")
    if recent_messages:
        lines.append("Recent messages (newest first):")
        for msg, cs in recent_messages:
            preview = (msg.body_plain or "")[:150]
            clarity = f", clarity={cs}" if cs is not None else ""
            lines.append(f"  - [{msg.subject or 'No subject'}{clarity}] {preview}")
    else:
        lines.append("Recent messages: none")
    if last_note:
        lines.append(f"Last contact note: {(last_note.body or '')[:200]}")
    else:
        lines.append("Last contact note: none")

    context = "\n".join(lines)

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            system=_CONTACT_SUMMARY_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg.content[0].text.strip() if msg.content else "{}"
        data = json.loads(raw)

        valid_statuses = ("strong", "warm", "cold", "at_risk")
        relationship_status = str(data.get("relationship_status", "warm"))
        if relationship_status not in valid_statuses:
            relationship_status = "warm"
        summary = str(data.get("summary", ""))[:500]
        next_best_action = str(data.get("next_best_action", ""))[:120]
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    return {
        "relationship_status": relationship_status,
        "summary": summary,
        "next_best_action": next_best_action,
        "deal_value": deal_value,
        "contact_id": str(contact_id),
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
    }


# ---------------------------------------------------------------------------
# POST /workspaces/{wid}/ai/deals/compare
# ---------------------------------------------------------------------------

_DEAL_COMPARE_SYSTEM = """\
You are Nova, the AI assistant in NovaCRM. Compare 2–3 CRM deals and identify which offers the
strongest sales opportunity. Return ONLY valid JSON in this exact format:
{"winner_id": "<uuid string of winning deal>",
 "rationale": "<2-sentence explanation of why this deal should be prioritised>",
 "comparison_points": [
   {"dimension": "<dimension name>", "verdict": "<brief comparison verdict>"}
 ]}
Include 3–4 comparison_points covering dimensions such as: Deal Value, Health Score,
Win Probability, Stage Progress, Competitor Risk.
"""


class _DealCompareRequest(BaseModel):
    deal_ids: list[uuid.UUID]


@router.post("/workspaces/{workspace_id}/ai/deals/compare")
@limiter.limit("10/minute")
async def compare_deals(
    request: Request,
    workspace_id: uuid.UUID,
    body: _DealCompareRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    if len(body.deal_ids) < 2 or len(body.deal_ids) > 3:
        raise HTTPException(status_code=400, detail="Provide 2 or 3 deal IDs to compare")

    result = await db.execute(
        select(Deal).where(
            Deal.id.in_(body.deal_ids),
            Deal.workspace_id == workspace_id,
        )
    )
    deals = result.scalars().all()

    if len(deals) < 2:
        raise HTTPException(status_code=404, detail="Could not find enough deals in this workspace")

    lines: list[str] = ["Compare these deals and identify the strongest opportunity:"]
    for deal in deals:
        comp_names: list[str] = []
        if deal.competitors:
            try:
                comp_names = [
                    c.get("name", str(c)) if isinstance(c, dict) else str(c)
                    for c in deal.competitors
                ]
            except Exception:
                pass
        lines.append(
            f"\nDeal ID: {deal.id}"
            f"\n  Title: {deal.title}"
            f"\n  Company: {deal.company}"
            f"\n  Value: ${deal.value:,.0f}"
            f"\n  Stage: {deal.stage}"
            f"\n  Health Score: {deal.health_score}/100"
            f"\n  Win Probability: {deal.ml_win_probability}%"
            f"\n  Competitors: {', '.join(comp_names) if comp_names else 'none'}"
        )

    context = "\n".join(lines)

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            system=_DEAL_COMPARE_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg.content[0].text.strip() if msg.content else "{}"
        data = json.loads(raw)

        winner_id = str(data.get("winner_id", str(deals[0].id)))
        rationale = str(data.get("rationale", ""))[:400]
        raw_points = data.get("comparison_points") or []
        comparison_points = [
            {
                "dimension": str(p.get("dimension", ""))[:60],
                "verdict": str(p.get("verdict", ""))[:120],
            }
            for p in raw_points[:5]
        ]
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    return {
        "winner_id": winner_id,
        "rationale": rationale,
        "comparison_points": comparison_points,
        "deal_ids": [str(d.id) for d in deals],
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
    }


# ---------------------------------------------------------------------------
# POST /workspaces/{workspace_id}/ai/messages/triage
# ---------------------------------------------------------------------------

_TRIAGE_SYSTEM = """\
You are an AI inbox triage assistant for NovaCRM. Given a list of messages, assign each a priority \
and one-sentence recommended action.

Respond with a JSON array only — no other text, no markdown fences.

Each item must follow this schema exactly:
{"message_id": "<id>", "priority": "urgent"|"high"|"normal"|"low", "action": "<one-sentence recommended action>", "rationale": "<one short reason for this priority>"}

Priority guidance:
- urgent: requires same-day response; hard deadlines, escalations, or deal-blocking issues
- high: important, should be addressed within 24h; active prospects, upsell signals, or specific asks
- normal: standard follow-up or informational; can be addressed in 2-3 days
- low: FYI, newsletters, or no clear action needed\
"""


class _TriageItem(BaseModel):
    message_id: str
    priority: str
    action: str
    rationale: str


class TriageResponse(BaseModel):
    items: list[_TriageItem]
    message_count: int
    generated_at: str


_VALID_PRIORITIES = {"urgent", "high", "normal", "low"}


@router.post("/workspaces/{workspace_id}/ai/messages/triage", response_model=TriageResponse)
@limiter.limit("5/minute")
async def triage_messages(
    request: Request,
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TriageResponse:
    """Batch-triage up to 20 inbox messages with Claude Haiku."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    result = await db.execute(
        select(Message)
        .where(Message.workspace_id == workspace_id)
        .order_by(Message.received_at.desc())
        .limit(20)
    )
    msgs = result.scalars().all()

    if not msgs:
        return TriageResponse(
            items=[],
            message_count=0,
            generated_at=datetime.datetime.utcnow().isoformat() + "Z",
        )

    lines: list[str] = ["Triage these inbox messages. Return a JSON array only.\n"]
    for m in msgs:
        snippet = (m.body_plain or "")[:300].replace("\n", " ")
        lines.append(
            f"- id: {m.id}"
            f"  subject: {m.subject or '(no subject)'}"
            f"  sender: {m.sender_email or 'unknown'}"
            f"  preview: {snippet}"
        )
    context = "\n".join(lines)

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg_resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            system=_TRIAGE_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg_resp.content[0].text.strip() if msg_resp.content else "[]"
        items_data = json.loads(raw)
        items = [
            _TriageItem(
                message_id=str(i.get("message_id", "")),
                priority=i.get("priority", "normal") if i.get("priority") in _VALID_PRIORITIES else "normal",
                action=str(i.get("action", "Review and respond as needed."))[:200],
                rationale=str(i.get("rationale", ""))[:200],
            )
            for i in items_data
            if isinstance(i, dict)
        ]
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    return TriageResponse(
        items=items,
        message_count=len(msgs),
        generated_at=datetime.datetime.utcnow().isoformat() + "Z",
    )


# ---------------------------------------------------------------------------
# POST /workspaces/{workspace_id}/ai/contacts/reengagement-plan
# ---------------------------------------------------------------------------

_REENGAGEMENT_SYSTEM = """\
You are Nova, the AI assistant in NovaCRM. Generate a personalised re-engagement plan for contacts who have gone silent.

For each contact provided, return one plan item with:
- "contact_id": the exact ID string provided
- "contact_name": the contact's name
- "days_silent": number of days since last contact (integer)
- "channel": best outreach channel — exactly one of "email", "slack", or "call"
- "message_template": a 2-3 sentence personalised outreach draft (warm, professional, not generic)
- "urgency": exactly one of "low", "medium", or "high"

Urgency rules:
- high: silent 60+ days or is a customer with open deals
- medium: silent 30-59 days, prospect or warm lead
- low: silent 30-45 days, early-stage or low-value contact

Respond with a JSON array only — no markdown fences, no extra keys:
[{"contact_id": "...", "contact_name": "...", "days_silent": 45, "channel": "email", "message_template": "...", "urgency": "medium"}]
"""


@router.post("/workspaces/{workspace_id}/ai/contacts/reengagement-plan")
@limiter.limit("5/minute")
async def contact_reengagement_plan(
    request: Request,
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Generate a prioritised re-engagement plan for up to 10 going-dark contacts."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    now = datetime.datetime.now(datetime.timezone.utc)
    cutoff_30 = now - datetime.timedelta(days=30)
    cutoff_90 = now - datetime.timedelta(days=90)

    contact_result = await db.execute(
        select(Contact).where(
            Contact.workspace_id == workspace_id,
            Contact.status.in_(["customer", "prospect"]),
        )
    )
    contacts = contact_result.scalars().all()
    if not contacts:
        return {"plan": [], "generated_at": datetime.datetime.utcnow().isoformat() + "Z"}

    contact_ids = [c.id for c in contacts]

    msg_result = await db.execute(
        select(Message.contact_id, Message.received_at)
        .where(
            Message.workspace_id == workspace_id,
            Message.contact_id.in_(contact_ids),
            Message.received_at >= cutoff_90,
        )
    )
    messages = msg_result.all()

    note_result = await db.execute(
        select(ContactNote.contact_id, ContactNote.created_at)
        .where(
            ContactNote.workspace_id == workspace_id,
            ContactNote.contact_id.in_(contact_ids),
            ContactNote.created_at >= cutoff_90,
        )
    )
    notes = note_result.all()

    last_touch: dict = {}
    for m in messages:
        if m.contact_id and m.received_at:
            ts = m.received_at
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=datetime.timezone.utc)
            if m.contact_id not in last_touch or ts > last_touch[m.contact_id]:
                last_touch[m.contact_id] = ts
    for n in notes:
        if n.contact_id and n.created_at:
            ts = n.created_at
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=datetime.timezone.utc)
            if n.contact_id not in last_touch or ts > last_touch[n.contact_id]:
                last_touch[n.contact_id] = ts

    dark_contacts = []
    for c in contacts:
        lt = last_touch.get(c.id)
        if lt and lt >= cutoff_30:
            continue
        days_silent = int((now - lt).total_seconds() / 86400) if lt else 90
        dark_contacts.append((c, days_silent))

    dark_contacts.sort(key=lambda x: x[1], reverse=True)
    dark_contacts = dark_contacts[:10]

    if not dark_contacts:
        return {"plan": [], "generated_at": datetime.datetime.utcnow().isoformat() + "Z"}

    lines: list[str] = ["Generate a re-engagement plan for these contacts:"]
    for c, days in dark_contacts:
        lines.append(
            f"\nID: {c.id}"
            f"\nName: {c.name or 'Unknown'}"
            f"\nEmail: {c.email or 'unknown'}"
            f"\nCompany: {c.company or 'unknown'}"
            f"\nRole: {c.role or 'unknown'}"
            f"\nStatus: {c.status}"
            f"\nDays silent: {days}"
        )

    context = "\n".join(lines)

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1500,
            system=_REENGAGEMENT_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg.content[0].text.strip() if msg.content else "[]"
        data = json.loads(raw)
        if not isinstance(data, list):
            data = []

        _valid_channels = {"email", "slack", "call"}
        _valid_urgencies = {"low", "medium", "high"}
        plan = []
        for item in data:
            if not isinstance(item, dict):
                continue
            channel = str(item.get("channel", "email"))
            if channel not in _valid_channels:
                channel = "email"
            urgency = str(item.get("urgency", "medium"))
            if urgency not in _valid_urgencies:
                urgency = "medium"
            plan.append({
                "contact_id": str(item.get("contact_id", ""))[:64],
                "contact_name": str(item.get("contact_name", "Unknown"))[:100],
                "days_silent": int(item.get("days_silent", 30)),
                "channel": channel,
                "message_template": str(item.get("message_template", ""))[:500],
                "urgency": urgency,
            })
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    return {
        "plan": plan,
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
    }


# ---------------------------------------------------------------------------
# POST /workspaces/{workspace_id}/deals/{deal_id}/ai/objection-handler
# ---------------------------------------------------------------------------

_OBJECTION_SYSTEM = """\
You are Nova, the AI assistant in NovaCRM. Generate exactly 4 realistic sales objections this deal might face and concise rep responses.

For each objection return:
- "objection": the specific concern the buyer might raise (1-2 sentences, realistic and specific to this deal context)
- "response": a confident, consultative reply the sales rep can use verbatim or adapt (2-3 sentences)
- "strategy": exactly one of "empathize", "redirect", "prove", or "challenge"

Strategy definitions:
- empathize: acknowledge the concern, validate it, then reframe toward value
- redirect: pivot away from the objection toward a stronger value point
- prove: use evidence, benchmarks, or social proof to overcome the concern
- challenge: politely question the assumption behind the objection

Respond with a JSON array of exactly 4 items — no markdown fences, no extra keys:
[{"objection": "...", "response": "...", "strategy": "empathize"}]
"""


@router.post("/workspaces/{workspace_id}/deals/{deal_id}/ai/objection-handler")
@limiter.limit("5/minute")
async def deal_objection_handler(
    request: Request,
    workspace_id: uuid.UUID,
    deal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Generate common objections and tailored responses for an open deal."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    result = await db.execute(
        select(Deal).where(Deal.id == deal_id, Deal.workspace_id == workspace_id)
    )
    deal = result.scalar_one_or_none()
    if deal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found")

    if deal.stage in {"closed_won", "closed_lost"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Objection handler is only available for open deals",
        )

    notes_result = await db.execute(
        select(DealNote.body)
        .where(DealNote.deal_id == deal_id)
        .order_by(DealNote.created_at.desc())
        .limit(3)
    )
    notes = [r[0] for r in notes_result.fetchall()]

    now = datetime.datetime.now(datetime.timezone.utc)
    stage_changed = deal.stage_changed_at
    if stage_changed and stage_changed.tzinfo is None:
        stage_changed = stage_changed.replace(tzinfo=datetime.timezone.utc)
    days_in_stage = (now - stage_changed).days if stage_changed else 0

    competitors = deal.competitors or []
    next_action_overdue = False
    if deal.next_action_date:
        try:
            nad = datetime.date.fromisoformat(str(deal.next_action_date))
            next_action_overdue = nad < now.date()
        except (ValueError, TypeError):
            pass

    context = (
        f"Deal: {deal.title}\n"
        f"Company: {deal.company or 'Unknown'}\n"
        f"Stage: {deal.stage}\n"
        f"Value: ${deal.value or 0:,.0f}\n"
        f"Health score: {deal.health_score}/100\n"
        f"Win probability: {deal.ml_win_probability or 0:.0f}%\n"
        f"Days in current stage: {days_in_stage}\n"
        f"Competitors: {', '.join(str(c) for c in competitors) if competitors else 'None known'}\n"
        f"Next action overdue: {'Yes' if next_action_overdue else 'No'}\n"
    )
    if notes:
        context += "Recent deal notes:\n" + "\n".join(f"- {n}" for n in notes)

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1200,
            system=_OBJECTION_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg.content[0].text.strip() if msg.content else "[]"
        data = json.loads(raw)
        if not isinstance(data, list):
            data = []

        _valid_strategies = {"empathize", "redirect", "prove", "challenge"}
        objections = []
        for item in data[:4]:
            if not isinstance(item, dict):
                continue
            strategy = str(item.get("strategy", "empathize"))
            if strategy not in _valid_strategies:
                strategy = "empathize"
            objections.append({
                "objection": str(item.get("objection", ""))[:300],
                "response": str(item.get("response", ""))[:500],
                "strategy": strategy,
            })
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    return {
        "objections": objections,
        "deal_id": str(deal_id),
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
    }


# ---------------------------------------------------------------------------
# POST /workspaces/{workspace_id}/deals/{deal_id}/ai/stakeholder-map
# ---------------------------------------------------------------------------

_STAKEHOLDER_SYSTEM = """\
You are Nova, the AI assistant in NovaCRM. Analyze this deal and generate a stakeholder map with exactly 4 key people involved in the buying process.

For each stakeholder return:
- "name": the person's name (infer from mentions or use placeholders like "Economic Buyer", "Technical Evaluator" if names are unknown)
- "role": exactly one of "decision_maker", "champion", "blocker", or "influencer"
- "engagement": exactly one of "high", "medium", or "low"
- "recommended_action": one specific CRM action the rep should take with this person (max 100 chars, e.g. "Schedule exec briefing", "Send ROI case study")

Role definitions:
- decision_maker: holds budget authority and final sign-off
- champion: internal advocate who wants the deal to succeed
- blocker: person raising objections or slowing progress
- influencer: shapes opinion without final authority (e.g. IT, legal, end users)

Respond with a JSON array of exactly 4 items — no markdown fences, no extra keys:
[{"name": "...", "role": "decision_maker", "engagement": "high", "recommended_action": "..."}]
"""


@router.post("/workspaces/{workspace_id}/deals/{deal_id}/ai/stakeholder-map")
@limiter.limit("5/minute")
async def deal_stakeholder_map(
    request: Request,
    workspace_id: uuid.UUID,
    deal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Generate a stakeholder map for an open deal using deal context and mentions."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    result = await db.execute(
        select(Deal).where(Deal.id == deal_id, Deal.workspace_id == workspace_id)
    )
    deal = result.scalar_one_or_none()
    if deal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found")

    if deal.stage in {"closed_won", "closed_lost"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Stakeholder map is only available for open deals",
        )

    notes_result = await db.execute(
        select(DealNote.body)
        .where(DealNote.deal_id == deal_id)
        .order_by(DealNote.created_at.desc())
        .limit(3)
    )
    notes = [r[0] for r in notes_result.fetchall()]

    mentions = deal.mentions or []
    competitors = deal.competitors or []

    now = datetime.datetime.now(datetime.timezone.utc)
    stage_changed = deal.stage_changed_at
    if stage_changed and stage_changed.tzinfo is None:
        stage_changed = stage_changed.replace(tzinfo=datetime.timezone.utc)
    days_in_stage = (now - stage_changed).days if stage_changed else 0

    mention_lines = ""
    if mentions:
        mention_lines = "Known stakeholders (name, type):\n" + "\n".join(
            f"- {m.get('name', 'Unknown')} ({m.get('type', 'unknown')})"
            for m in mentions
            if isinstance(m, dict)
        )

    context = (
        f"Deal: {deal.title}\n"
        f"Company: {deal.company or 'Unknown'}\n"
        f"Stage: {deal.stage}\n"
        f"Value: ${deal.value or 0:,.0f}\n"
        f"Health score: {deal.health_score}/100\n"
        f"Win probability: {deal.ml_win_probability or 0:.0f}%\n"
        f"Days in current stage: {days_in_stage}\n"
        f"Competitors: {', '.join(str(c) for c in competitors) if competitors else 'None known'}\n"
    )
    if mention_lines:
        context += f"\n{mention_lines}\n"
    if notes:
        context += "\nRecent deal notes:\n" + "\n".join(f"- {n}" for n in notes)

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1000,
            system=_STAKEHOLDER_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg.content[0].text.strip() if msg.content else "[]"
        data = json.loads(raw)
        if not isinstance(data, list):
            data = []

        _valid_roles = {"decision_maker", "champion", "blocker", "influencer"}
        _valid_engagements = {"high", "medium", "low"}
        stakeholders = []
        for item in data[:4]:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role", "influencer"))
            if role not in _valid_roles:
                role = "influencer"
            engagement = str(item.get("engagement", "medium"))
            if engagement not in _valid_engagements:
                engagement = "medium"
            stakeholders.append({
                "name": str(item.get("name", "Unknown"))[:80],
                "role": role,
                "engagement": engagement,
                "recommended_action": str(item.get("recommended_action", ""))[:120],
            })
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    return {
        "stakeholders": stakeholders,
        "deal_id": str(deal_id),
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
    }


# ---------------------------------------------------------------------------
# POST /workspaces/{workspace_id}/deals/{deal_id}/ai/negotiation-script
# ---------------------------------------------------------------------------

_NEGOTIATION_SYSTEM = """\
You are Nova, the AI sales negotiation coach in NovaCRM. Generate a tactical negotiation script for the provided deal.

Return ONLY valid JSON in this exact format:
{
  "opening_move": "string — one confident opening statement (max 120 chars)",
  "concessions": [
    {"offer": "string", "condition": "string", "limit": "string"},
    {"offer": "string", "condition": "string", "limit": "string"},
    {"offer": "string", "condition": "string", "limit": "string"}
  ],
  "walk_away_signal": "string — specific behaviour that means the deal is dead (max 120 chars)",
  "closing_line": "string — one line to use when pushing for signature (max 120 chars)"
}

Rules:
- Exactly 3 concessions. No more, no less.
- Each offer is a tangible concession the rep can make (discount, timeline, feature, support tier, etc.)
- Each condition is what the buyer must give in return for that concession.
- Each limit is the maximum the rep should concede before walking away.
- Keep every string under 120 characters.
- Return nothing except the JSON object.\
"""


@router.post("/workspaces/{workspace_id}/deals/{deal_id}/ai/negotiation-script")
@limiter.limit("5/minute")
async def deal_negotiation_script(
    request: Request,
    workspace_id: uuid.UUID,
    deal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Generate a negotiation script for a proposal or negotiation-stage deal."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    result = await db.execute(
        select(Deal).where(Deal.id == deal_id, Deal.workspace_id == workspace_id)
    )
    deal = result.scalar_one_or_none()
    if deal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found")

    if deal.stage not in {"proposal", "negotiation"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Negotiation script is only available for proposal or negotiation stage deals",
        )

    notes_result = await db.execute(
        select(DealNote.body)
        .where(DealNote.deal_id == deal_id)
        .order_by(DealNote.created_at.desc())
        .limit(3)
    )
    notes = [r[0] for r in notes_result.fetchall()]
    competitors = deal.competitors or []

    now = datetime.datetime.now(datetime.timezone.utc)
    stage_changed = deal.stage_changed_at
    if stage_changed and stage_changed.tzinfo is None:
        stage_changed = stage_changed.replace(tzinfo=datetime.timezone.utc)
    days_in_stage = (now - stage_changed).days if stage_changed else 0

    overdue_next_action = False
    if deal.next_action_date:
        nad = deal.next_action_date
        if hasattr(nad, "date"):
            nad = nad.date()
        overdue_next_action = nad < datetime.date.today()

    context = (
        f"Deal: {deal.title}\n"
        f"Company: {deal.company or 'Unknown'}\n"
        f"Stage: {deal.stage}\n"
        f"Value: ${deal.value or 0:,.0f}\n"
        f"Health score: {deal.health_score}/100\n"
        f"Win probability: {deal.ml_win_probability or 0:.0f}%\n"
        f"Days in current stage: {days_in_stage}\n"
        f"Next action overdue: {overdue_next_action}\n"
        f"Competitors: {', '.join(str(c) for c in competitors) if competitors else 'None known'}\n"
    )
    if notes:
        context += "\nRecent deal notes:\n" + "\n".join(f"- {n}" for n in notes)

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=800,
            system=_NEGOTIATION_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg.content[0].text.strip() if msg.content else "{}"
        data = json.loads(raw)

        concessions_raw = data.get("concessions", [])
        if not isinstance(concessions_raw, list):
            concessions_raw = []
        concessions = []
        for c in concessions_raw[:3]:
            if not isinstance(c, dict):
                continue
            concessions.append({
                "offer": str(c.get("offer", ""))[:120],
                "condition": str(c.get("condition", ""))[:120],
                "limit": str(c.get("limit", ""))[:120],
            })
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    return {
        "opening_move": str(data.get("opening_move", ""))[:200],
        "concessions": concessions,
        "walk_away_signal": str(data.get("walk_away_signal", ""))[:200],
        "closing_line": str(data.get("closing_line", ""))[:200],
        "deal_id": str(deal_id),
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
    }


# POST /workspaces/{workspace_id}/deals/{deal_id}/ai/sentiment-digest
# ---------------------------------------------------------------------------

_SENTIMENT_DIGEST_SYSTEM = """\
You are Nova, the AI deal intelligence in NovaCRM. Analyse the sentiment signals from recent deal notes \
and contact messages and return a structured sentiment digest.

Respond in exactly this JSON format (no markdown fences, no extra keys):
{
  "overall_sentiment": "positive",
  "key_signals": [
    "One sentence — specific quote or behaviour that signals this sentiment.",
    "Second signal — another concrete example.",
    "Third signal — optional third data point."
  ],
  "sentiment_trend": "improving"
}

Rules:
- "overall_sentiment": exactly one of "positive", "neutral", "negative"
- "key_signals": 2–4 items, each a concise sentence citing a specific quote or observed behaviour
- "sentiment_trend": exactly one of "improving", "stable", "declining" — compare earlier vs later signals\
"""


@router.post("/workspaces/{workspace_id}/deals/{deal_id}/ai/sentiment-digest")
@limiter.limit("5/minute")
async def deal_sentiment_digest(
    request: Request,
    workspace_id: uuid.UUID,
    deal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Return an AI sentiment digest for a deal using deal notes and contact messages via Claude Haiku."""
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
            detail="Sentiment digest is only available for open deals",
        )

    # Last 5 deal note bodies (oldest → newest for chronological context)
    notes_result = await db.execute(
        select(DealNote.body, DealNote.created_at)
        .where(DealNote.deal_id == deal_id)
        .order_by(DealNote.created_at.desc())
        .limit(5)
    )
    note_rows = list(reversed(notes_result.all()))  # oldest → newest

    # Last 3 messages from the deal's contact (if any)
    messages: list[str] = []
    if deal.contact_id:
        msg_result = await db.execute(
            select(Message.body_plain, Message.sender_email, Message.received_at)
            .where(
                Message.workspace_id == workspace_id,
                Message.contact_id == deal.contact_id,
            )
            .order_by(Message.received_at.desc())
            .limit(3)
        )
        messages = [
            f"[{r.sender_email or 'unknown'}] {(r.body_plain or '')[:300]}"
            for r in reversed(msg_result.all())
        ]

    context = (
        f"Deal: {deal.title or 'Untitled'} at {deal.company or 'Unknown Company'}\n"
        f"Stage: {deal.stage}\n"
        f"Value: ${float(deal.value):,.0f}\n"
        f"Health score: {deal.health_score}/100\n"
    )

    if note_rows:
        context += "\nDeal notes (oldest→newest):\n"
        for row in note_rows:
            ts = row.created_at.strftime("%Y-%m-%d") if row.created_at else "unknown date"
            context += f"  [{ts}] {(row.body or '')[:300]}\n"
    else:
        context += "\nDeal notes: none recorded\n"

    if messages:
        context += "\nRecent contact messages (oldest→newest):\n"
        for m in messages:
            context += f"  {m}\n"
    else:
        context += "\nRecent contact messages: none available\n"

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            system=_SENTIMENT_DIGEST_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg.content[0].text.strip() if msg.content else "{}"
        data = json.loads(raw)

        overall_sentiment = str(data.get("overall_sentiment", "neutral"))
        if overall_sentiment not in ("positive", "neutral", "negative"):
            overall_sentiment = "neutral"

        key_signals = [str(s)[:200] for s in (data.get("key_signals") or [])[:4]]

        sentiment_trend = str(data.get("sentiment_trend", "stable"))
        if sentiment_trend not in ("improving", "stable", "declining"):
            sentiment_trend = "stable"
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    return {
        "overall_sentiment": overall_sentiment,
        "key_signals": key_signals,
        "sentiment_trend": sentiment_trend,
        "deal_id": str(deal_id),
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
    }


# POST /workspaces/{workspace_id}/messages/{message_id}/ai/reply
# ---------------------------------------------------------------------------

_REPLY_SYSTEM = """\
You are Nova, the AI assistant in NovaCRM. Draft a professional email reply to the provided message.

Return a JSON object with exactly these keys:
- "subject": reply subject line (prefix with "Re: " if not already, keep under 80 chars)
- "body": the full reply body (2-4 paragraphs, professional, warm, action-oriented)
- "tone": exactly one of "professional", "friendly", or "urgent" based on the message context

Return valid JSON only — no markdown fences, no extra keys:
{"subject": "...", "body": "...", "tone": "professional"}
"""


@router.post("/workspaces/{workspace_id}/messages/{message_id}/ai/reply")
@limiter.limit("10/minute")
async def draft_message_reply(
    request: Request,
    workspace_id: uuid.UUID,
    message_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Draft an AI email reply for a given inbox message."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    msg_result = await db.execute(
        select(Message).where(Message.id == message_id, Message.workspace_id == workspace_id)
    )
    message = msg_result.scalar_one_or_none()
    if message is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")

    contact: Contact | None = None
    if message.contact_id:
        contact_result = await db.execute(
            select(Contact).where(Contact.id == message.contact_id)
        )
        contact = contact_result.scalar_one_or_none()

    deal_notes: list[str] = []
    if contact:
        notes_result = await db.execute(
            select(DealNote.body)
            .join(Deal, DealNote.deal_id == Deal.id)
            .where(Deal.contact_id == contact.id)
            .order_by(DealNote.created_at.desc())
            .limit(2)
        )
        deal_notes = [r[0] for r in notes_result.fetchall()]

    context = (
        f"From: {message.sender_email or 'Unknown'}\n"
        f"Subject: {message.subject or '(No subject)'}\n"
        f"Message:\n{(message.body_plain or '')[:1200]}\n"
    )
    if contact:
        context += (
            f"\nContact profile:\n"
            f"  Name: {contact.name}\n"
            f"  Company: {contact.company or 'Unknown'}\n"
            f"  Role: {contact.role or 'Unknown'}\n"
        )
    if deal_notes:
        context += "\nRecent deal notes:\n" + "\n".join(f"- {n}" for n in deal_notes)

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg_resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=700,
            system=_REPLY_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg_resp.content[0].text.strip() if msg_resp.content else "{}"
        data = json.loads(raw)
        if not isinstance(data, dict):
            data = {}

        tone = str(data.get("tone", "professional"))
        if tone not in {"professional", "friendly", "urgent"}:
            tone = "professional"
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    subject = str(data.get("subject", f"Re: {message.subject or ''}")[:80])
    body = str(data.get("body", ""))[:2000]

    return {
        "subject": subject,
        "body": body,
        "tone": tone,
        "message_id": str(message_id),
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
    }


# ---------------------------------------------------------------------------
# POST /workspaces/{workspace_id}/ai/contacts/{contact_id}/communication-style
# ---------------------------------------------------------------------------

_COMMS_STYLE_SYSTEM = """\
You are Nova, the AI communications analyst in NovaCRM. Analyse the provided contact profile \
and recent messages to determine how this contact prefers to communicate, and return a structured profile.

Respond in exactly this JSON format (no markdown fences, no extra keys):
{
  "style": "direct",
  "preferred_channel": "email",
  "best_time": "morning",
  "tone_tips": ["...", "..."]
}

Rules:
- style must be exactly one of: "direct", "analytical", "relational", "expressive"
  direct = brief, action-oriented; analytical = data-driven, detail-heavy;
  relational = warm, rapport-first; expressive = enthusiastic, story-driven
- preferred_channel must be exactly one of: "email", "slack", "call"
- best_time must be exactly one of: "morning", "afternoon", "end_of_day"
- tone_tips: 2-4 practical tips for how to communicate effectively with this contact
- Base conclusions on the message content, response patterns, phrasing choices, and tone

Output only the JSON object, nothing else.\
"""


@router.post("/workspaces/{workspace_id}/ai/contacts/{contact_id}/communication-style")
@limiter.limit("5/minute")
async def contact_communication_style(
    request: Request,
    workspace_id: uuid.UUID,
    contact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Return an AI communication style profile for a contact using their recent messages."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    contact_result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.workspace_id == workspace_id)
    )
    contact = contact_result.scalar_one_or_none()
    if contact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    messages_result = await db.execute(
        select(Message)
        .where(Message.workspace_id == workspace_id, Message.contact_id == contact_id)
        .order_by(Message.received_at.desc())
        .limit(5)
    )
    messages = messages_result.scalars().all()

    context = (
        f"Contact: {contact.name}\n"
        f"Company: {contact.company or 'Unknown'}\n"
        f"Role: {contact.role or 'Unknown'}\n"
        f"Email: {contact.email or 'Unknown'}\n\n"
    )

    if messages:
        context += "Recent messages (newest first):\n"
        for i, msg in enumerate(messages, 1):
            context += (
                f"\n[Message {i}]\n"
                f"Subject: {msg.subject or '(No subject)'}\n"
                f"From: {msg.sender_email or 'Unknown'}\n"
                f"Body: {(msg.body_plain or '')[:500]}\n"
            )
    else:
        context += "No recent messages available.\n"

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg_resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            system=_COMMS_STYLE_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg_resp.content[0].text.strip() if msg_resp.content else "{}"
        data = json.loads(raw)
        if not isinstance(data, dict):
            data = {}

        style = str(data.get("style", "relational"))
        if style not in {"direct", "analytical", "relational", "expressive"}:
            style = "relational"

        preferred_channel = str(data.get("preferred_channel", "email"))
        if preferred_channel not in {"email", "slack", "call"}:
            preferred_channel = "email"

        best_time = str(data.get("best_time", "morning"))
        if best_time not in {"morning", "afternoon", "end_of_day"}:
            best_time = "morning"

        raw_tips = data.get("tone_tips", [])
        tone_tips = [str(t) for t in raw_tips if isinstance(t, str)][:4]
        if not tone_tips:
            tone_tips = ["Adapt your messaging to their preferred communication style."]

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    return {
        "style": style,
        "preferred_channel": preferred_channel,
        "best_time": best_time,
        "tone_tips": tone_tips,
        "contact_id": str(contact_id),
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
    }


# ── Lead Score Explanation ─────────────────────────────────────────────────────

_LEAD_SCORE_SYSTEM = """\
You are a CRM lead scoring analyst. Given a contact's ML lead score, their recent messages, \
deal pipeline, and task history, explain whether the score appears accurate and provide actionable advice.

Return ONLY valid JSON with this exact structure:
{
  "score_assessment": "accurate",
  "score_summary": "One or two sentence narrative about the lead score.",
  "key_signals": ["signal 1", "signal 2", "signal 3"],
  "improvement_tips": ["tip 1", "tip 2"]
}

Rules:
- score_assessment must be exactly one of: "accurate", "overestimated", "underestimated"
  accurate = score reflects the contact's real buying intent and engagement
  overestimated = score is too high relative to observed engagement/signals
  underestimated = score is too low; contact shows stronger potential than score suggests
- score_summary: 1-2 sentences explaining why the score assessment was made
- key_signals: 2-4 concrete signals (positive or negative) driving the current score
- improvement_tips: 2-3 specific CRM actions to improve the contact's score or engagement
- Base everything on the provided data. Be direct and specific.

Output only the JSON object, nothing else.\
"""


@router.post("/workspaces/{workspace_id}/ai/contacts/{contact_id}/lead-score-explanation")
@limiter.limit("5/minute")
async def contact_lead_score_explanation(
    request: Request,
    workspace_id: uuid.UUID,
    contact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Explain why a contact has their current ML lead score and suggest improvements."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    contact_result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.workspace_id == workspace_id)
    )
    contact = contact_result.scalar_one_or_none()
    if contact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    messages_result = await db.execute(
        select(Message)
        .where(Message.workspace_id == workspace_id, Message.contact_id == contact_id)
        .order_by(Message.received_at.desc())
        .limit(3)
    )
    messages = messages_result.scalars().all()

    deals_result = await db.execute(
        select(Deal)
        .where(Deal.workspace_id == workspace_id, Deal.contact_id == contact_id)
        .order_by(Deal.created_at.desc())
        .limit(5)
    )
    deals = deals_result.scalars().all()

    tasks_result = await db.execute(
        select(Task)
        .where(Task.workspace_id == workspace_id, Task.contact_id == contact_id)
    )
    tasks = tasks_result.scalars().all()
    task_done = sum(1 for t in tasks if t.status == "done")
    task_total = len(tasks)
    task_rate = round(task_done / task_total * 100) if task_total else 0

    ml = contact.ml_score or {}
    score_value = int(ml.get("value", 50))
    score_label = str(ml.get("label", "warm"))
    existing_signals = ml.get("signals", [])

    open_deals = [d for d in deals if d.stage not in ("closed_won", "closed_lost")]
    pipeline_value = sum(d.value for d in open_deals)

    context = (
        f"Contact: {contact.name}\n"
        f"Company: {contact.company or 'Unknown'}\n"
        f"Role: {contact.role or 'Unknown'}\n"
        f"Status: {contact.status}\n"
        f"Current ML lead score: {score_value}/100 ({score_label})\n"
        f"Existing score signals: {', '.join(existing_signals) if existing_signals else 'none recorded'}\n"
        f"Open deals: {len(open_deals)} (pipeline value: ${pipeline_value:,.0f})\n"
        f"Task completion: {task_done}/{task_total} tasks done ({task_rate}%)\n"
    )

    if messages:
        context += "\nRecent messages (newest first):\n"
        for i, msg in enumerate(messages, 1):
            context += (
                f"\n[Message {i}]\n"
                f"Subject: {msg.subject or '(No subject)'}\n"
                f"From: {msg.sender_email or 'Unknown'}\n"
                f"Body: {(msg.body_plain or '')[:400]}\n"
            )
    else:
        context += "\nNo recent messages available.\n"

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg_resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=450,
            system=_LEAD_SCORE_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg_resp.content[0].text.strip() if msg_resp.content else "{}"
        data = json.loads(raw)
        if not isinstance(data, dict):
            data = {}

        assessment = str(data.get("score_assessment", "accurate"))
        if assessment not in {"accurate", "overestimated", "underestimated"}:
            assessment = "accurate"

        score_summary = str(data.get("score_summary", "Score assessment complete."))[:300]

        raw_signals = data.get("key_signals", [])
        key_signals = [str(s) for s in raw_signals if isinstance(s, str)][:4]
        if not key_signals:
            key_signals = ["Engagement level is consistent with current score."]

        raw_tips = data.get("improvement_tips", [])
        improvement_tips = [str(t) for t in raw_tips if isinstance(t, str)][:3]
        if not improvement_tips:
            improvement_tips = ["Log more interactions to refine the score."]

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    return {
        "score_assessment": assessment,
        "score_summary": score_summary,
        "key_signals": key_signals,
        "improvement_tips": improvement_tips,
        "contact_id": str(contact_id),
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
    }


# ── Win Probability Explainer ──────────────────────────────────────────────────

_WIN_PROB_SYSTEM = """\
You are a sales intelligence assistant analyzing deal win probability accuracy.
Given deal data, assess whether the ML-predicted win probability is accurate,
identify key drivers and risk factors, and suggest an adjustment if warranted.

Return ONLY valid JSON with this exact structure:
{
  "probability_assessment": "on_track" | "overestimated" | "underestimated",
  "key_drivers": ["driver1", "driver2", "driver3"],
  "risk_factors": ["risk1", "risk2"],
  "recommended_adjustment": <integer -30 to 30, or null if on_track>
}

Rules:
- probability_assessment: "on_track" if ML probability seems accurate, "overestimated" if deal is riskier than score suggests, "underestimated" if stronger than score suggests
- key_drivers: 2-4 specific factors positively influencing the deal
- risk_factors: 1-3 specific concerns (empty array if none)
- recommended_adjustment: integer points to add/subtract from ML probability, or null if assessment is "on_track"
- Be data-driven and specific; reference the actual numbers provided\
"""


@router.post("/workspaces/{workspace_id}/deals/{deal_id}/ai/win-probability-explainer")
@limiter.limit("5/minute")
async def deal_win_probability_explainer(
    request: Request,
    workspace_id: uuid.UUID,
    deal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    deal_result = await db.execute(
        select(Deal).where(Deal.id == deal_id, Deal.workspace_id == workspace_id)
    )
    deal = deal_result.scalar_one_or_none()
    if not deal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found")

    if deal.stage in ("closed_won", "closed_lost"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Win probability analysis is not available for closed deals.",
        )

    notes_result = await db.execute(
        select(DealNote)
        .where(DealNote.deal_id == deal_id, DealNote.workspace_id == workspace_id)
        .order_by(DealNote.created_at.desc())
        .limit(3)
    )
    notes = notes_result.scalars().all()

    days_in_stage = 0
    if deal.stage_changed_at:
        delta = datetime.datetime.utcnow() - deal.stage_changed_at.replace(tzinfo=None)
        days_in_stage = max(0, delta.days)

    next_action_overdue = False
    if deal.next_action_date:
        next_action_overdue = deal.next_action_date < datetime.date.today()

    competitor_count = len(deal.competitors or [])

    context = (
        f"Deal Stage: {deal.stage}\n"
        f"ML Win Probability: {deal.ml_win_probability or 0}%\n"
        f"Health Score: {deal.health_score or 0}\n"
        f"Days in Current Stage: {days_in_stage}\n"
        f"Competitor Count: {competitor_count}\n"
        f"Next Action Overdue: {'Yes' if next_action_overdue else 'No'}\n"
    )

    if notes:
        context += "\nRecent Deal Notes:\n"
        for i, note in enumerate(notes, 1):
            context += f"{i}. {(note.body or '')[:300]}\n"
    else:
        context += "\nNo recent deal notes available.\n"

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg_resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            system=_WIN_PROB_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg_resp.content[0].text.strip() if msg_resp.content else "{}"
        data = json.loads(raw)
        if not isinstance(data, dict):
            data = {}

        assessment = str(data.get("probability_assessment", "on_track"))
        if assessment not in {"on_track", "overestimated", "underestimated"}:
            assessment = "on_track"

        raw_drivers = data.get("key_drivers", [])
        key_drivers = [str(d) for d in raw_drivers if isinstance(d, str)][:4]
        if not key_drivers:
            key_drivers = ["Insufficient data for analysis."]

        raw_risks = data.get("risk_factors", [])
        risk_factors = [str(r) for r in raw_risks if isinstance(r, str)][:3]

        raw_adj = data.get("recommended_adjustment")
        recommended_adjustment: int | None = None
        if isinstance(raw_adj, (int, float)) and not isinstance(raw_adj, bool):
            adj = int(raw_adj)
            if adj != 0:
                recommended_adjustment = max(-30, min(30, adj))

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    return {
        "probability_assessment": assessment,
        "key_drivers": key_drivers,
        "risk_factors": risk_factors,
        "recommended_adjustment": recommended_adjustment,
        "deal_id": str(deal_id),
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
    }


# ── Task Prioritization ────────────────────────────────────────────────────────

_TASK_PRIORITY_SYSTEM = """\
You are a productivity coach helping a sales or PM team prioritize their open tasks.
Given a list of tasks with titles, descriptions, and due dates, rank them by urgency and importance.

Return ONLY valid JSON with this exact structure:
{
  "items": [
    {
      "task_id": "<id string>",
      "priority_rank": <integer starting at 1>,
      "urgency": "critical" | "high" | "medium" | "low",
      "reason": "<one sentence explaining why this rank>"
    }
  ],
  "summary_note": "<2 sentence overall summary of the task load and top recommendation>"
}

Rules:
- Include every task_id from the input, no omissions
- priority_rank 1 = most urgent/important
- urgency: "critical" = overdue or due today; "high" = due within 3 days; "medium" = due this week or high-impact; "low" = no due date or far out
- reason: specific, actionable, reference the actual task title
- summary_note: identify the #1 priority and any bottleneck theme\
"""


@router.post("/workspaces/{workspace_id}/ai/tasks/prioritize")
@limiter.limit("5/minute")
async def prioritize_tasks(
    request: Request,
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    tasks_result = await db.execute(
        select(Task)
        .where(Task.workspace_id == workspace_id, Task.status.in_(["open", "in_progress"]))
        .order_by(Task.due_date.asc().nullslast())
        .limit(30)
    )
    tasks = tasks_result.scalars().all()

    if not tasks:
        return {
            "items": [],
            "summary_note": "No open tasks found. Add tasks to get AI prioritization.",
            "workspace_id": str(workspace_id),
            "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        }

    today = datetime.date.today()
    context_lines = []
    for t in tasks:
        due_str = str(t.due_date) if t.due_date else "no due date"
        overdue = ""
        if t.due_date and t.due_date < today:
            overdue = f" (OVERDUE by {(today - t.due_date).days} days)"
        desc_snippet = (t.description or "")[:120].strip()
        context_lines.append(
            f"ID: {t.id} | Title: {t.title} | Status: {t.status} | Due: {due_str}{overdue}"
            + (f" | Description: {desc_snippet}" if desc_snippet else "")
        )

    context = f"Today's date: {today}\n\nOpen tasks:\n" + "\n".join(context_lines)

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg_resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=800,
            system=_TASK_PRIORITY_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg_resp.content[0].text.strip() if msg_resp.content else "{}"
        data = json.loads(raw)
        if not isinstance(data, dict):
            data = {}

        raw_items = data.get("items", [])
        valid_ids = {str(t.id) for t in tasks}
        items = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            tid = str(item.get("task_id", ""))
            if tid not in valid_ids:
                continue
            urgency = str(item.get("urgency", "medium"))
            if urgency not in {"critical", "high", "medium", "low"}:
                urgency = "medium"
            items.append({
                "task_id": tid,
                "priority_rank": int(item.get("priority_rank", 99)),
                "urgency": urgency,
                "reason": str(item.get("reason", ""))[:200],
            })
        # Sort by rank and fill in any missing tasks
        items.sort(key=lambda x: x["priority_rank"])
        seen = {i["task_id"] for i in items}
        rank = len(items) + 1
        for t in tasks:
            if str(t.id) not in seen:
                items.append({"task_id": str(t.id), "priority_rank": rank, "urgency": "low", "reason": "Not ranked by AI."})
                rank += 1

        summary_note = str(data.get("summary_note", "Prioritization complete."))[:400]

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    return {
        "items": items,
        "summary_note": summary_note,
        "workspace_id": str(workspace_id),
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
    }


_PIPELINE_HEALTH_SYSTEM = """\
You are Nova, an AI assistant for NovaCRM. You will receive a pipeline snapshot.
Respond with ONLY a JSON object — no markdown, no prose — with exactly these keys:
{
  "health_score": <integer 0-100>,
  "rating": <"strong"|"healthy"|"at_risk"|"critical">,
  "briefing": "<2-3 sentence narrative about overall pipeline health>",
  "priorities": ["<specific action 1>", "<specific action 2>", "<specific action 3>"]
}
Score guide: 80-100=strong, 60-79=healthy, 40-59=at_risk, 0-39=critical.
Priorities must be 3 concrete, actionable CRM recommendations.\
"""


@router.get("/workspaces/{workspace_id}/ai/pipeline-health-briefing")
@limiter.limit("5/minute")
async def pipeline_health_briefing(
    request: Request,
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    # Open deals aggregate
    open_agg = await db.execute(
        select(
            func.count(Deal.id).label("total"),
            func.coalesce(func.sum(Deal.value), 0).label("pipeline_value"),
            func.coalesce(func.avg(Deal.ml_win_probability), 0).label("avg_win_prob"),
        ).where(
            Deal.workspace_id == workspace_id,
            Deal.stage.not_in(["closed_won", "closed_lost"]),
        )
    )
    agg = open_agg.one()
    total_open = int(agg.total or 0)
    pipeline_value = float(agg.pipeline_value or 0)
    avg_win_prob = float(agg.avg_win_prob or 0)

    # At-risk open deals (health_score < 50)
    at_risk_res = await db.execute(
        select(func.count(Deal.id)).where(
            Deal.workspace_id == workspace_id,
            Deal.stage.not_in(["closed_won", "closed_lost"]),
            Deal.health_score < 50,
        )
    )
    at_risk_count = int(at_risk_res.scalar() or 0)

    # Overdue close dates
    today_str = datetime.date.today().isoformat()
    overdue_res = await db.execute(
        select(func.count(Deal.id)).where(
            Deal.workspace_id == workspace_id,
            Deal.stage.not_in(["closed_won", "closed_lost"]),
            Deal.expected_close.isnot(None),
            Deal.expected_close < today_str,
        )
    )
    overdue_count = int(overdue_res.scalar() or 0)

    # Stage breakdown
    stage_rows = await db.execute(
        select(
            Deal.stage,
            func.count(Deal.id).label("count"),
            func.coalesce(func.sum(Deal.value), 0).label("value"),
        ).where(
            Deal.workspace_id == workspace_id,
            Deal.stage.not_in(["closed_won", "closed_lost"]),
        ).group_by(Deal.stage).order_by(func.count(Deal.id).desc()).limit(4)
    )
    stage_breakdown = [
        {"stage": row.stage, "count": int(row.count), "value": float(row.value or 0)}
        for row in stage_rows.all()
    ]

    # Closed won totals
    won_agg = await db.execute(
        select(
            func.count(Deal.id).label("count"),
            func.coalesce(func.sum(Deal.value), 0).label("value"),
        ).where(
            Deal.workspace_id == workspace_id,
            Deal.stage == "closed_won",
        )
    )
    won_row = won_agg.one()
    total_won = int(won_row.count or 0)
    total_won_value = float(won_row.value or 0)

    context = (
        f"Pipeline Snapshot:\n"
        f"- Open deals: {total_open}\n"
        f"- Total pipeline value: ${pipeline_value:,.0f}\n"
        f"- Average win probability: {avg_win_prob:.0f}%\n"
        f"- At-risk deals (health < 50): {at_risk_count}\n"
        f"- Deals with overdue close dates: {overdue_count}\n"
        f"- Total closed-won deals: {total_won} (${total_won_value:,.0f})\n"
        f"- Stage breakdown: {stage_breakdown}\n"
        "\nGenerate the pipeline health assessment JSON."
    )

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg_resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            system=_PIPELINE_HEALTH_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg_resp.content[0].text.strip() if msg_resp.content else "{}"
        data = json.loads(raw)
        if not isinstance(data, dict):
            data = {}

        score_raw = data.get("health_score")
        health_score = (
            int(score_raw)
            if isinstance(score_raw, (int, float)) and not isinstance(score_raw, bool)
            else 50
        )
        health_score = max(0, min(100, health_score))

        rating = str(data.get("rating", "healthy"))
        if rating not in {"strong", "healthy", "at_risk", "critical"}:
            rating = "healthy"

        briefing = str(data.get("briefing", "Pipeline health analysis is in progress."))[:600]

        raw_prio = data.get("priorities", [])
        priorities = [str(p) for p in raw_prio if isinstance(p, str)][:3]
        if not priorities:
            priorities = ["Review at-risk deals and update health scores."]

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    return {
        "health_score": health_score,
        "rating": rating,
        "briefing": briefing,
        "priorities": priorities,
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
    }


# ---------------------------------------------------------------------------
# Phase 15c: AI team performance summary
# ---------------------------------------------------------------------------

_TEAM_PERF_SYSTEM = """\
You are a CRM performance analyst. Given metrics about a sales/PM team's activity over the last 30 days, \
produce a JSON object with exactly these fields:
{
  "performance_rating": "excellent" | "good" | "needs_improvement" | "critical",
  "highlights": ["string1", "string2", "string3"],
  "areas_for_improvement": ["string1", "string2"],
  "summary_sentence": "A 2-sentence narrative about overall team performance."
}
Be specific and data-driven — reference actual numbers. JSON only, no markdown.\
"""


@router.get("/workspaces/{workspace_id}/ai/team-performance")
@limiter.limit("5/minute")
async def get_team_performance(
    request: Request,
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    thirty_days_ago = datetime.datetime.utcnow() - datetime.timedelta(days=30)

    # Agent runs in last 30 days
    agent_runs = int(
        await db.scalar(
            select(func.count(ActivityEvent.id)).where(
                ActivityEvent.workspace_id == workspace_id,
                ActivityEvent.type.like("agent_%"),
                ActivityEvent.created_at >= thirty_days_ago,
            )
        ) or 0
    )

    # Task metrics (all-time totals for completion rate)
    task_total = int(
        await db.scalar(
            select(func.count(Task.id)).where(Task.workspace_id == workspace_id)
        ) or 0
    )
    task_done = int(
        await db.scalar(
            select(func.count(Task.id)).where(
                Task.workspace_id == workspace_id,
                Task.status == "done",
            )
        ) or 0
    )
    task_completion_rate = round(task_done / task_total * 100) if task_total > 0 else 0

    # Messages processed in last 30 days
    messages_processed = int(
        await db.scalar(
            select(func.count(Message.id)).where(
                Message.workspace_id == workspace_id,
                Message.received_at >= thirty_days_ago,
            )
        ) or 0
    )

    # Deal stage moves in last 30 days
    deals_moved = int(
        await db.scalar(
            select(func.count(ActivityEvent.id)).where(
                ActivityEvent.workspace_id == workspace_id,
                ActivityEvent.type == "deal_moved",
                ActivityEvent.created_at >= thirty_days_ago,
            )
        ) or 0
    )

    # Distinct contacts with messages in last 30 days
    active_contacts = int(
        await db.scalar(
            select(func.count(func.distinct(Message.contact_id))).where(
                Message.workspace_id == workspace_id,
                Message.contact_id.isnot(None),
                Message.received_at >= thirty_days_ago,
            )
        ) or 0
    )

    context = (
        f"Team Activity (Last 30 Days):\n"
        f"- AI agent runs: {agent_runs}\n"
        f"- Tasks: {task_done} completed out of {task_total} total ({task_completion_rate}% completion rate)\n"
        f"- Messages processed: {messages_processed}\n"
        f"- Deals moved to a new stage: {deals_moved}\n"
        f"- Contacts actively engaged: {active_contacts}\n"
        "\nGenerate the team performance JSON assessment."
    )

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg_resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            system=_TEAM_PERF_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg_resp.content[0].text.strip() if msg_resp.content else "{}"
        data = json.loads(raw)
        if not isinstance(data, dict):
            data = {}

        rating = str(data.get("performance_rating", "good"))
        if rating not in {"excellent", "good", "needs_improvement", "critical"}:
            rating = "good"

        raw_highlights = data.get("highlights", [])
        highlights = [str(h) for h in raw_highlights if isinstance(h, str)][:3]
        if not highlights:
            highlights = ["Team is actively engaging contacts through the CRM."]

        raw_areas = data.get("areas_for_improvement", [])
        areas_for_improvement = [str(a) for a in raw_areas if isinstance(a, str)][:2]
        if not areas_for_improvement:
            areas_for_improvement = ["Increase AI agent usage to surface insights faster."]

        summary_sentence = str(
            data.get("summary_sentence", "Team performance data is being compiled.")
        )[:600]

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    return {
        "performance_rating": rating,
        "highlights": highlights,
        "areas_for_improvement": areas_for_improvement,
        "summary_sentence": summary_sentence,
        "metrics": {
            "agent_runs": agent_runs,
            "task_completion_rate": task_completion_rate,
            "messages_processed": messages_processed,
            "deals_moved": deals_moved,
            "active_contacts": active_contacts,
        },
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
    }


# ── Meeting Prep ───────────────────────────────────────────────────────────────

_MEETING_PREP_SYSTEM = """\
You are an expert sales coach. Given a deal's context, generate concise meeting prep notes.

Return ONLY valid JSON with this exact structure:
{
  "agenda_items": [
    {"topic": "string", "goal": "string (one sentence)", "talking_points": ["string", "string", "string"]},
    {"topic": "string", "goal": "string", "talking_points": ["string", "string"]},
    {"topic": "string", "goal": "string", "talking_points": ["string"]}
  ],
  "questions_to_ask": ["string", "string", "string"],
  "things_to_avoid": ["string", "string"]
}
Rules:
- Exactly 3 agenda_items, each with 1-3 talking_points
- Exactly 3 questions_to_ask
- Exactly 2 things_to_avoid
- Keep all strings concise (20 words or fewer)
- Be specific to the deal context provided
"""


@router.post("/workspaces/{workspace_id}/deals/{deal_id}/ai/meeting-prep")
@limiter.limit("5/minute")
async def deal_meeting_prep(
    request: Request,
    workspace_id: uuid.UUID,
    deal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    deal_result = await db.execute(
        select(Deal).where(Deal.id == deal_id, Deal.workspace_id == workspace_id)
    )
    deal = deal_result.scalar_one_or_none()
    if not deal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found")

    if deal.stage in ("closed_won", "closed_lost"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Meeting prep is not available for closed deals.",
        )

    contact_lines: list[str] = []
    if deal.contact_id:
        contact_result = await db.execute(
            select(Contact).where(Contact.id == deal.contact_id, Contact.workspace_id == workspace_id)
        )
        contact = contact_result.scalar_one_or_none()
        if contact:
            contact_lines.append(
                f"Contact: {contact.name or 'Unknown'} — {contact.role or 'unknown role'} at {contact.company or 'Unknown'}"
            )
            contact_lines.append(f"Contact email: {contact.email or 'unknown'}")

        msg_result = await db.execute(
            select(Message.subject, Message.received_at, ClarityScore.score)
            .outerjoin(ClarityScore, Message.id == ClarityScore.message_id)
            .where(Message.workspace_id == workspace_id, Message.contact_id == deal.contact_id)
            .order_by(Message.received_at.desc())
            .limit(3)
        )
        recent_messages = msg_result.all()
        if recent_messages:
            contact_lines.append("Recent messages:")
            for msg in recent_messages:
                clarity = f" (clarity {msg.score}/100)" if msg.score is not None else ""
                ts = msg.received_at.strftime("%b %d") if msg.received_at else "?"
                contact_lines.append(f"  - \"{msg.subject or '(no subject)'}\" received {ts}{clarity}")

    notes_result = await db.execute(
        select(DealNote)
        .where(DealNote.deal_id == deal_id, DealNote.workspace_id == workspace_id)
        .order_by(DealNote.created_at.desc())
        .limit(3)
    )
    notes = notes_result.scalars().all()

    days_in_stage = 0
    if deal.stage_changed_at:
        delta = datetime.datetime.utcnow() - deal.stage_changed_at.replace(tzinfo=None)
        days_in_stage = max(0, delta.days)

    next_action_overdue = bool(deal.next_action_date and deal.next_action_date < datetime.date.today())
    competitor_count = len(deal.competitors or [])

    context_parts = [
        f"Deal: {deal.title or 'Untitled'}",
        f"Stage: {deal.stage}",
        f"Value: ${deal.value or 0:,.0f}",
        f"Health Score: {deal.health_score or 0}/100",
        f"ML Win Probability: {deal.ml_win_probability or 0}%",
        f"Days in Stage: {days_in_stage}",
        f"Competitor Count: {competitor_count}",
        f"Next Action Overdue: {'Yes' if next_action_overdue else 'No'}",
    ]
    if contact_lines:
        context_parts.extend(contact_lines)
    if notes:
        context_parts.append("Recent Deal Notes:")
        for i, note in enumerate(notes, 1):
            context_parts.append(f"  {i}. {(note.body or '')[:250]}")
    else:
        context_parts.append("No deal notes yet.")

    context = "\n".join(context_parts)

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg_resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            system=_MEETING_PREP_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg_resp.content[0].text.strip() if msg_resp.content else "{}"
        data = json.loads(raw)
        if not isinstance(data, dict):
            data = {}

        raw_agenda = data.get("agenda_items", [])
        agenda_items = []
        for item in raw_agenda[:3]:
            if not isinstance(item, dict):
                continue
            topic = str(item.get("topic", ""))[:80]
            goal = str(item.get("goal", ""))[:120]
            raw_tps = item.get("talking_points", [])
            talking_points = [str(tp)[:120] for tp in raw_tps if isinstance(tp, str)][:3]
            if topic:
                agenda_items.append({"topic": topic, "goal": goal, "talking_points": talking_points})
        if not agenda_items:
            agenda_items = [
                {"topic": "Deal Overview", "goal": "Align on current status and next steps.", "talking_points": ["Recap progress so far"]}
            ]

        raw_questions = data.get("questions_to_ask", [])
        questions_to_ask = [str(q)[:150] for q in raw_questions if isinstance(q, str)][:3]
        if not questions_to_ask:
            questions_to_ask = ["What is your timeline for a decision?"]

        raw_avoid = data.get("things_to_avoid", [])
        things_to_avoid = [str(a)[:150] for a in raw_avoid if isinstance(a, str)][:2]
        if not things_to_avoid:
            things_to_avoid = ["Pressuring for immediate commitment"]

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    return {
        "agenda_items": agenda_items,
        "questions_to_ask": questions_to_ask,
        "things_to_avoid": things_to_avoid,
        "deal_id": str(deal_id),
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
    }

# ── Workspace Digest ───────────────────────────────────────────────────────────

_WORKSPACE_DIGEST_SYSTEM = """\
You are a CRM analytics expert generating a weekly workspace health digest for an admin.
Given workspace metrics, produce an honest, actionable health report.

Return ONLY valid JSON with this exact structure:
{
  "health_rating": "excellent" | "good" | "needs_attention" | "critical",
  "summary": "2-3 sentence narrative on workspace health",
  "highlights": ["achievement 1", "achievement 2"],
  "warnings": ["concern 1", "concern 2"],
  "recommended_actions": ["action 1", "action 2", "action 3"]
}

Rules:
- health_rating: excellent = all KPIs green; good = mostly healthy; needs_attention = 1-2 issues; critical = multiple problems
- summary: be direct and specific — reference actual numbers from the context
- highlights: 2 recent wins or positive trends (keep to 15 words each max)
- warnings: 2 concerns that need admin attention (keep to 15 words each max)
- recommended_actions: 3 specific, actionable steps (keep to 20 words each max)
- If metrics are sparse (new workspace), focus on next-step recommendations
"""


@router.get("/workspaces/{workspace_id}/ai/workspace-digest")
@limiter.limit("5/minute")
async def workspace_digest(
    request: Request,
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    today = datetime.date.today()
    thirty_days_ago = datetime.datetime.utcnow() - datetime.timedelta(days=30)

    # Total contacts
    total_contacts_result = await db.execute(
        select(func.count(Contact.id)).where(Contact.workspace_id == workspace_id)
    )
    total_contacts = total_contacts_result.scalar() or 0

    # Contacts going dark (no touch in 30 days)
    recent_msg_cids = select(Message.contact_id).where(
        Message.workspace_id == workspace_id,
        Message.received_at >= thirty_days_ago,
        Message.contact_id.isnot(None),
    )
    recent_note_cids = select(ContactNote.contact_id).where(
        ContactNote.workspace_id == workspace_id,
        ContactNote.created_at >= thirty_days_ago,
    )
    going_dark_result = await db.execute(
        select(func.count(Contact.id)).where(
            Contact.workspace_id == workspace_id,
            Contact.status.in_(["customer", "prospect"]),
            Contact.id.not_in(recent_msg_cids),
            Contact.id.not_in(recent_note_cids),
        )
    )
    going_dark_count = going_dark_result.scalar() or 0

    # Open deals stats
    open_deals_result = await db.execute(
        select(Deal.value, Deal.ml_win_probability, Deal.health_score, Deal.stage_changed_at).where(
            Deal.workspace_id == workspace_id,
            Deal.stage.not_in(["closed_won", "closed_lost"]),
        )
    )
    open_deals_rows = open_deals_result.all()
    open_deal_count = len(open_deals_rows)
    total_pipeline = sum((r.value or 0) for r in open_deals_rows)
    at_risk_deals = sum(1 for r in open_deals_rows if (r.health_score or 0) < 50)
    avg_win_prob = (
        round(sum((r.ml_win_probability or 0) for r in open_deals_rows) / open_deal_count)
        if open_deal_count else 0
    )

    # Overdue close dates
    overdue_close_result = await db.execute(
        select(func.count(Deal.id)).where(
            Deal.workspace_id == workspace_id,
            Deal.stage.not_in(["closed_won", "closed_lost"]),
            # expected_close is a String column holding ISO dates ("YYYY-MM-DD"),
            # so compare against a string — comparing to a date object raises
            # "operator does not exist: text < date". Lexical order matches date
            # order for ISO strings. Mirrors the /deals overdue query in this file.
            Deal.expected_close.isnot(None),
            Deal.expected_close < today.isoformat(),
        )
    )
    overdue_close_count = overdue_close_result.scalar() or 0

    # Open tasks
    open_tasks_result = await db.execute(
        select(func.count(Task.id)).where(
            Task.workspace_id == workspace_id,
            Task.status.in_(["open", "in_progress"]),
        )
    )
    open_task_count = open_tasks_result.scalar() or 0

    # Overdue tasks
    overdue_tasks_result = await db.execute(
        select(func.count(Task.id)).where(
            Task.workspace_id == workspace_id,
            Task.status.in_(["open", "in_progress"]),
            Task.due_date < today,
        )
    )
    overdue_task_count = overdue_tasks_result.scalar() or 0

    # Recent agent runs (last 30 days)
    agent_runs_result = await db.execute(
        select(func.count(ActivityEvent.id)).where(
            ActivityEvent.workspace_id == workspace_id,
            ActivityEvent.type == "agent_run",
            ActivityEvent.created_at >= thirty_days_ago,
        )
    )
    agent_run_count = agent_runs_result.scalar() or 0

    # Closed won in last 30 days
    closed_won_result = await db.execute(
        select(func.count(Deal.id), func.coalesce(func.sum(Deal.value), 0)).where(
            Deal.workspace_id == workspace_id,
            Deal.stage == "closed_won",
            Deal.stage_changed_at >= thirty_days_ago,
        )
    )
    closed_won_row = closed_won_result.one()
    closed_won_count = closed_won_row[0] or 0
    closed_won_value = float(closed_won_row[1] or 0)

    context = (
        f"=== Workspace Health Snapshot (Last 30 Days) ===\n"
        f"Total Contacts: {total_contacts}\n"
        f"Contacts Going Dark (no touch in 30d): {going_dark_count}\n"
        f"\nPipeline:\n"
        f"  Open Deals: {open_deal_count} (total pipeline ${total_pipeline:,.0f})\n"
        f"  At-Risk Deals (health < 50): {at_risk_deals}\n"
        f"  Avg Win Probability: {avg_win_prob}%\n"
        f"  Overdue Close Dates: {overdue_close_count}\n"
        f"  Closed Won (last 30d): {closed_won_count} deals worth ${closed_won_value:,.0f}\n"
        f"\nTasks:\n"
        f"  Open Tasks: {open_task_count}\n"
        f"  Overdue Tasks: {overdue_task_count}\n"
        f"\nAgents:\n"
        f"  Agent Runs (last 30d): {agent_run_count}\n"
    )

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg_resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            system=_WORKSPACE_DIGEST_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg_resp.content[0].text.strip() if msg_resp.content else "{}"
        data = json.loads(raw)
        if not isinstance(data, dict):
            data = {}

        rating = str(data.get("health_rating", "good"))
        if rating not in {"excellent", "good", "needs_attention", "critical"}:
            rating = "good"

        summary = str(data.get("summary", "Workspace health assessment complete."))[:500]

        raw_highlights = data.get("highlights", [])
        highlights = [str(h) for h in raw_highlights if isinstance(h, str)][:3]
        if not highlights:
            highlights = ["Workspace is active and operational."]

        raw_warnings = data.get("warnings", [])
        warnings = [str(w) for w in raw_warnings if isinstance(w, str)][:3]
        if not warnings:
            warnings = ["Review contacts for engagement gaps."]

        raw_actions = data.get("recommended_actions", [])
        recommended_actions = [str(a) for a in raw_actions if isinstance(a, str)][:4]
        if not recommended_actions:
            recommended_actions = ["Connect a Gmail or Slack account to start ingesting messages."]

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    return {
        "health_rating": rating,
        "summary": summary,
        "highlights": highlights,
        "warnings": warnings,
        "recommended_actions": recommended_actions,
        "metrics": {
            "total_contacts": total_contacts,
            "going_dark_count": going_dark_count,
            "open_deal_count": open_deal_count,
            "total_pipeline": total_pipeline,
            "at_risk_deals": at_risk_deals,
            "overdue_close_count": overdue_close_count,
            "closed_won_count": closed_won_count,
            "closed_won_value": closed_won_value,
            "open_task_count": open_task_count,
            "overdue_task_count": overdue_task_count,
            "agent_run_count": agent_run_count,
        },
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
    }

# ── Contact Onboarding Checklist ───────────────────────────────────────────────

_ONBOARDING_CHECKLIST_SYSTEM = """\
You are a CRM onboarding coach. Given a contact's current profile, generate a prioritised
checklist of next steps the sales rep should take to properly onboard and develop this relationship.

Return ONLY valid JSON with this exact structure:
{
  "checklist": [
    {
      "step": "short action title (5-8 words)",
      "detail": "one sentence explaining why this matters",
      "category": "data" | "outreach" | "research" | "relationship",
      "priority": "high" | "medium" | "low"
    }
  ],
  "readiness": "new" | "in_progress" | "ready",
  "readiness_reason": "one sentence explaining the readiness assessment"
}

Rules:
- Return exactly 5 steps — not 4, not 6
- category:
    data = filling in missing profile fields (email, role, company, LinkedIn)
    outreach = sending a first/follow-up message or scheduling a call
    research = understanding the contact's context, company, competitors
    relationship = tasks that deepen trust (notes, referrals, QBRs)
- priority: high = should happen today/this week; medium = this month; low = nice-to-have
- readiness:
    new = fewer than 2 touches (messages or notes), missing key profile fields
    in_progress = some engagement but not enough to qualify
    ready = 5+ touches, key fields filled, open pipeline deal
- Be specific to the contact's actual data (name, company, status, score)
"""


@router.post("/workspaces/{workspace_id}/ai/contacts/{contact_id}/onboarding-checklist")
@limiter.limit("5/minute")
async def contact_onboarding_checklist(
    request: Request,
    workspace_id: uuid.UUID,
    contact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    contact_result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.workspace_id == workspace_id)
    )
    contact = contact_result.scalar_one_or_none()
    if contact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    # Message count
    msg_count_result = await db.execute(
        select(func.count(Message.id)).where(
            Message.workspace_id == workspace_id, Message.contact_id == contact_id
        )
    )
    msg_count = msg_count_result.scalar() or 0

    # Note count
    note_count_result = await db.execute(
        select(func.count(ContactNote.id)).where(
            ContactNote.workspace_id == workspace_id, ContactNote.contact_id == contact_id
        )
    )
    note_count = note_count_result.scalar() or 0

    # Open deals
    deals_result = await db.execute(
        select(Deal.title, Deal.stage, Deal.value).where(
            Deal.workspace_id == workspace_id,
            Deal.contact_id == contact_id,
            Deal.stage.not_in(["closed_won", "closed_lost"]),
        )
    )
    open_deals = deals_result.all()

    ml = contact.ml_score or {}
    score_value = int(ml.get("value", 0))
    score_label = str(ml.get("label", "unknown"))

    missing_fields: list[str] = []
    if not contact.company:
        missing_fields.append("company")
    if not contact.role:
        missing_fields.append("role")
    if not contact.email:
        missing_fields.append("email")
    if not contact.phone:
        missing_fields.append("phone")

    context = (
        f"Contact: {contact.name or 'Unknown'}\n"
        f"Company: {contact.company or 'Unknown — MISSING'}\n"
        f"Role: {contact.role or 'Unknown — MISSING'}\n"
        f"Email: {contact.email or 'Unknown — MISSING'}\n"
        f"Phone: {contact.phone or 'Unknown — MISSING'}\n"
        f"Status: {contact.status}\n"
        f"ML Lead Score: {score_value}/100 ({score_label})\n"
        f"Messages exchanged: {msg_count}\n"
        f"Notes recorded: {note_count}\n"
        f"Open deals: {len(open_deals)}\n"
        f"Missing profile fields: {', '.join(missing_fields) if missing_fields else 'none — profile complete'}\n"
    )
    if open_deals:
        context += "Open deals:\n"
        for d in open_deals:
            context += f"  - {d.title or 'Untitled'} ({d.stage}, ${d.value or 0:,.0f})\n"

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg_resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            system=_ONBOARDING_CHECKLIST_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg_resp.content[0].text.strip() if msg_resp.content else "{}"
        data = json.loads(raw)
        if not isinstance(data, dict):
            data = {}

        raw_checklist = data.get("checklist", [])
        checklist = []
        valid_cats = {"data", "outreach", "research", "relationship"}
        valid_pris = {"high", "medium", "low"}
        for item in raw_checklist[:6]:
            if not isinstance(item, dict):
                continue
            step = str(item.get("step", ""))[:80]
            detail = str(item.get("detail", ""))[:150]
            category = str(item.get("category", "outreach"))
            priority = str(item.get("priority", "medium"))
            if category not in valid_cats:
                category = "outreach"
            if priority not in valid_pris:
                priority = "medium"
            if step:
                checklist.append({"step": step, "detail": detail, "category": category, "priority": priority})

        if not checklist:
            checklist = [{"step": "Add contact details", "detail": "Fill in company, role, and phone.", "category": "data", "priority": "high"}]

        readiness = str(data.get("readiness", "new"))
        if readiness not in {"new", "in_progress", "ready"}:
            readiness = "new"

        readiness_reason = str(data.get("readiness_reason", "Contact is newly added."))[:200]

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    return {
        "checklist": checklist,
        "readiness": readiness,
        "readiness_reason": readiness_reason,
        "contact_id": str(contact_id),
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
    }


# ---------------------------------------------------------------------------
# AI deal ROI projection
# ---------------------------------------------------------------------------

_DEAL_ROI_SYSTEM = """\
You are Nova, an AI assistant in NovaCRM. Calculate a realistic ROI projection \
for a deal prospect — the return on investment the CUSTOMER would achieve by \
purchasing this product.

Return valid JSON (no markdown) in exactly this shape:
{
  "roi_multiplier": <float, e.g. 3.2 — total 3-year return divided by total 3-year cost>,
  "payback_months": <int 1–36, months until the customer breaks even>,
  "year1_value": <int, estimated first-year value generated in dollars>,
  "year3_value": <int, estimated 3-year cumulative value in dollars>,
  "assumptions": [<exactly 3 concise assumption strings, each under 120 chars>]
}

Base year1_value on the deal notes and deal context. Be conservative — \
realistic estimates build credibility. The roi_multiplier should reflect \
year3_value divided by (annual deal value × 3).\
"""


@router.post("/workspaces/{workspace_id}/deals/{deal_id}/ai/roi-projection")
@limiter.limit("5/minute")
async def deal_roi_projection(
    request: Request,
    workspace_id: uuid.UUID,
    deal_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    deal_result = await db.execute(
        select(Deal).where(Deal.id == deal_id, Deal.workspace_id == workspace_id)
    )
    deal = deal_result.scalar_one_or_none()
    if deal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found")

    if deal.stage in ("closed_won", "closed_lost"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ROI projection is only available for open deals",
        )

    notes_result = await db.execute(
        select(DealNote.body)
        .where(DealNote.deal_id == deal_id)
        .order_by(DealNote.created_at.desc())
        .limit(3)
    )
    note_bodies = [row[0] for row in notes_result.all() if row[0]]

    today = datetime.date.today()
    if deal.stage_changed_at:
        days_in_stage = (today - deal.stage_changed_at.date()).days
    else:
        days_in_stage = 0

    context = (
        f"Deal: {deal.title or 'Untitled'}\n"
        f"Company: {deal.company or 'Unknown'}\n"
        f"Annual contract value: ${float(deal.value or 0):,.0f}\n"
        f"Current stage: {deal.stage}\n"
        f"Health score: {deal.health_score or 0}/100\n"
        f"Days in current stage: {days_in_stage}\n"
        f"ML win probability: {deal.ml_win_probability or 0}%\n"
        f"Competitor count: {len(deal.competitors) if deal.competitors else 0}\n"
    )
    if note_bodies:
        context += "\nRecent deal notes (latest first):\n"
        for body in note_bodies:
            context += f"  - {body[:200]}\n"

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            system=_DEAL_ROI_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg.content[0].text.strip() if msg.content else "{}"
        data = json.loads(raw)
        if not isinstance(data, dict):
            data = {}

        roi_multiplier = round(float(data.get("roi_multiplier", 2.5)), 1)
        payback_months = max(1, min(36, int(data.get("payback_months", 12))))
        year1_value = max(0, int(data.get("year1_value", 0)))
        year3_value = max(0, int(data.get("year3_value", 0)))
        raw_assumptions = data.get("assumptions") or []
        assumptions = [str(a)[:120] for a in raw_assumptions[:3]]
        if not assumptions:
            assumptions = [
                "Based on industry-average productivity gains for the buyer's team size",
                "Assumes 70-80% feature adoption within the first 3 months",
                "Excludes one-time implementation and onboarding costs",
            ]

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    return {
        "roi_multiplier": roi_multiplier,
        "payback_months": payback_months,
        "year1_value": year1_value,
        "year3_value": year3_value,
        "assumptions": assumptions,
        "deal_id": str(deal_id),
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
    }


# ---------------------------------------------------------------------------
# Phase 15g: AI contact growth forecast
# ---------------------------------------------------------------------------

_CONTACT_GROWTH_FORECAST_SYSTEM = """\
You are a CRM revenue intelligence AI. Given a contact's deal history and
recent engagement data, produce a realistic growth forecast.

Return ONLY a JSON object with these fields:
{
  "forecast_revenue_3m": <int, realistic new pipeline/revenue expected in next 3 months>,
  "forecast_revenue_12m": <int, realistic cumulative revenue in next 12 months>,
  "growth_trajectory": "<one of: declining|flat|growing|accelerating>",
  "key_drivers": ["<driver 1>", "<driver 2>", "<driver 3>"]
}
Base estimates on the patterns described. Be conservative and realistic. Never invent
numbers that contradict the provided data. key_drivers should be specific and actionable.
"""


@router.post("/workspaces/{workspace_id}/ai/contacts/{contact_id}/growth-forecast")
@limiter.limit("5/minute")
async def contact_growth_forecast(
    request: Request,
    workspace_id: uuid.UUID,
    contact_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    contact_result = await db.execute(
        select(Contact).where(
            Contact.id == contact_id,
            Contact.workspace_id == workspace_id,
        )
    )
    contact = contact_result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    # Fetch all deals for this contact
    deals_result = await db.execute(
        select(Deal).where(
            Deal.workspace_id == workspace_id,
            Deal.contact_id == contact_id,
        )
    )
    deals = deals_result.scalars().all()

    # Message count last 90 days
    ninety_days_ago = datetime.datetime.utcnow() - datetime.timedelta(days=90)
    msg_result = await db.execute(
        select(func.count(Message.id)).where(
            Message.workspace_id == workspace_id,
            Message.contact_id == contact_id,
            Message.received_at >= ninety_days_ago,
        )
    )
    recent_message_count = msg_result.scalar() or 0

    # Note count last 90 days
    note_result = await db.execute(
        select(func.count(ContactNote.id)).where(
            ContactNote.workspace_id == workspace_id,
            ContactNote.contact_id == contact_id,
            ContactNote.created_at >= ninety_days_ago,
        )
    )
    recent_note_count = note_result.scalar() or 0

    # Build context
    open_deals = [d for d in deals if d.stage not in ("closed_won", "closed_lost")]
    won_deals = [d for d in deals if d.stage == "closed_won"]
    lost_deals = [d for d in deals if d.stage == "closed_lost"]
    total_pipeline = sum(d.value or 0 for d in open_deals)
    closed_won_value = sum(d.value or 0 for d in won_deals)

    context = (
        f"Contact: {contact.name} ({contact.email})\n"
        f"Company: {contact.company or 'Unknown'}\n"
        f"Status: {contact.status}\n"
        f"ML score: {contact.ml_score or 0} ({contact.ml_score_label or 'unknown'})\n\n"
        f"Deal history:\n"
        f"  Open deals: {len(open_deals)} (total pipeline ${total_pipeline:,.0f})\n"
        f"  Won deals: {len(won_deals)} (total ${closed_won_value:,.0f})\n"
        f"  Lost deals: {len(lost_deals)}\n\n"
        f"Recent activity (last 90 days):\n"
        f"  Messages: {recent_message_count}\n"
        f"  Notes: {recent_note_count}\n"
    )

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=350,
            system=_CONTACT_GROWTH_FORECAST_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg.content[0].text.strip() if msg.content else "{}"
        data = json.loads(raw)
        if not isinstance(data, dict):
            data = {}

        valid_trajectories = {"declining", "flat", "growing", "accelerating"}
        trajectory = data.get("growth_trajectory", "flat")
        if trajectory not in valid_trajectories:
            trajectory = "flat"

        forecast_3m = max(0, int(data.get("forecast_revenue_3m", 0)))
        forecast_12m = max(0, int(data.get("forecast_revenue_12m", 0)))
        raw_drivers = data.get("key_drivers") or []
        key_drivers = [str(d)[:120] for d in raw_drivers[:3]]
        if not key_drivers:
            key_drivers = [
                "Engagement level and deal activity trend",
                "Current pipeline stage distribution",
                "Historical win rate for this contact type",
            ]

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    return {
        "forecast_revenue_3m": forecast_3m,
        "forecast_revenue_12m": forecast_12m,
        "growth_trajectory": trajectory,
        "key_drivers": key_drivers,
        "contact_id": str(contact_id),
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
    }


# ---------------------------------------------------------------------------
# AI workspace goal tracker
# ---------------------------------------------------------------------------

_GOAL_TRACKER_SYSTEM = """\
You are Nova, the AI workspace intelligence in NovaCRM. Analyze the provided workspace metrics
and infer 4 implied business goals. For each goal, assess current progress and provide insight.

Respond in exactly this JSON format (no markdown fences, no extra keys):
{
  "goals": [
    {
      "name": "<short goal name, max 5 words>",
      "target_description": "<what success looks like in 1 sentence>",
      "progress_pct": <integer 0-100>,
      "status": "<on_track|at_risk|behind>",
      "insight": "<1-2 sentence specific insight about progress>"
    }
  ],
  "overall_health": "<on_track|at_risk|behind>"
}

Infer realistic goals from the data (e.g. "Close $X in pipeline", "Improve win rate",
"Reduce task backlog", "Re-engage dark contacts"). Be specific and actionable. Base
progress_pct on the real numbers provided. Use "on_track" when progress is solid,
"at_risk" when momentum is flagging, and "behind" when clearly failing.
"""


@router.get("/workspaces/{workspace_id}/ai/goal-tracker")
@limiter.limit("5/minute")
async def workspace_goal_tracker(
    request: Request,
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    total_contacts = await db.scalar(
        select(func.count(Contact.id)).where(Contact.workspace_id == workspace_id)
    ) or 0

    open_deals_result = await db.execute(
        select(Deal.value, Deal.health_score, Deal.ml_win_probability).where(
            Deal.workspace_id == workspace_id,
            Deal.stage.notin_(["closed_won", "closed_lost"]),
        )
    )
    open_deal_rows = open_deals_result.all()
    open_deal_count = len(open_deal_rows)
    total_pipeline = sum(float(r.value or 0) for r in open_deal_rows)
    at_risk_count = sum(1 for r in open_deal_rows if (r.health_score or 0) < 50)

    cw_result = await db.execute(
        select(func.count(Deal.id), func.sum(Deal.value)).where(
            Deal.workspace_id == workspace_id,
            Deal.stage == "closed_won",
        )
    )
    cw_row = cw_result.first()
    closed_won_count = cw_row[0] or 0
    closed_won_value = float(cw_row[1] or 0)

    total_tasks = await db.scalar(
        select(func.count(Task.id)).where(Task.workspace_id == workspace_id)
    ) or 0
    done_tasks = await db.scalar(
        select(func.count(Task.id)).where(
            Task.workspace_id == workspace_id,
            Task.status == "done",
        )
    ) or 0
    task_completion_rate = round(done_tasks / total_tasks * 100) if total_tasks > 0 else 0

    thirty_days_ago = datetime.datetime.utcnow() - datetime.timedelta(days=30)
    contacts_with_recent_msg = await db.scalar(
        select(func.count(func.distinct(Message.contact_id))).where(
            Message.workspace_id == workspace_id,
            Message.received_at >= thirty_days_ago,
            Message.contact_id.isnot(None),
        )
    ) or 0

    context = (
        f"Workspace metrics:\n"
        f"  Total contacts: {total_contacts}\n"
        f"  Active contacts (messaged in 30d): {contacts_with_recent_msg}\n"
        f"  Open deals: {open_deal_count}\n"
        f"  Total pipeline value: ${total_pipeline:,.0f}\n"
        f"  At-risk deals (health < 50): {at_risk_count}\n"
        f"  Closed-won deals: {closed_won_count} (total ${closed_won_value:,.0f})\n"
        f"  Open tasks: {total_tasks - done_tasks}\n"
        f"  Task completion rate: {task_completion_rate}%\n"
    )

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            system=_GOAL_TRACKER_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg.content[0].text.strip() if msg.content else "{}"
        data = json.loads(raw)
        if not isinstance(data, dict):
            data = {}

        valid_statuses = {"on_track", "at_risk", "behind"}
        raw_goals = data.get("goals", [])
        goals = []
        for g in raw_goals[:4]:
            if not isinstance(g, dict):
                continue
            s = g.get("status", "at_risk")
            if s not in valid_statuses:
                s = "at_risk"
            goals.append({
                "name": str(g.get("name", "Goal"))[:60],
                "target_description": str(g.get("target_description", ""))[:200],
                "progress_pct": max(0, min(100, int(g.get("progress_pct", 0)))),
                "status": s,
                "insight": str(g.get("insight", ""))[:300],
            })

        overall = data.get("overall_health", "at_risk")
        if overall not in valid_statuses:
            overall = "at_risk"

        if not goals:
            goals = [{
                "name": "Close pipeline deals",
                "target_description": "Convert open deals to closed-won revenue",
                "progress_pct": min(100, closed_won_count * 10),
                "status": "at_risk",
                "insight": "No goal data available. Review open deal health.",
            }]

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    return {
        "goals": goals,
        "overall_health": overall,
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
    }


# AI workspace competitive landscape summary
# ---------------------------------------------------------------------------

_COMPETITIVE_LANDSCAPE_SYSTEM = """\
You are Nova, the AI sales intelligence in NovaCRM. Analyze the provided competitor data from
active deals and produce a concise competitive landscape summary.

Respond in exactly this JSON format (no markdown fences, no extra keys):
{
  "top_competitors": [
    {
      "name": "<competitor name>",
      "deal_count": <integer>,
      "stages_present": ["<stage1>", "<stage2>"],
      "threat_level": "<low|medium|high>",
      "positioning_note": "<1-sentence note on how to counter this competitor>"
    }
  ],
  "competitive_summary": "<2-sentence overall landscape narrative>",
  "win_strategies": ["<strategy 1>", "<strategy 2>", "<strategy 3>"]
}

Rate threat_level as "high" if deal_count >= 3, "medium" if 2, "low" if 1.
Limit top_competitors to the 5 most common. Provide exactly 3 win_strategies.
"""


@router.get("/workspaces/{workspace_id}/ai/competitive-landscape")
@limiter.limit("5/minute")
async def workspace_competitive_landscape(
    request: Request,
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    open_deals_result = await db.execute(
        select(Deal.title, Deal.stage, Deal.competitors, Deal.value).where(
            Deal.workspace_id == workspace_id,
            Deal.stage.notin_(["closed_won", "closed_lost"]),
            Deal.competitors.isnot(None),
        )
    )
    open_deals = open_deals_result.all()

    competitor_counts: Counter = Counter()
    competitor_stages: dict = defaultdict(set)
    for row in open_deals:
        competitors = row.competitors or []
        for comp in competitors:
            name = comp if isinstance(comp, str) else comp.get("name", "Unknown")
            competitor_counts[name] += 1
            competitor_stages[name].add(row.stage)

    top_5 = competitor_counts.most_common(5)
    total_open = len(open_deals)

    if not top_5:
        return {
            "top_competitors": [],
            "competitive_summary": "No competitor data found in open deals. Add competitor information to deal records for landscape analysis.",
            "win_strategies": [
                "Establish unique value proposition early in the sales cycle.",
                "Track competitor mentions consistently across all open deals.",
                "Focus on customer success stories to differentiate.",
            ],
            "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        }

    context_lines = [
        f"Open deals analyzed: {total_open}",
        "Competitor occurrences in open deals:",
    ]
    for name, count in top_5:
        stages = sorted(competitor_stages[name])
        context_lines.append(f"  - {name}: {count} deal(s), stages: {', '.join(stages)}")

    context = "\n".join(context_lines)

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=700,
            system=_COMPETITIVE_LANDSCAPE_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg.content[0].text.strip() if msg.content else "{}"
        data = json.loads(raw)
        if not isinstance(data, dict):
            data = {}

        valid_threats = {"low", "medium", "high"}
        raw_competitors = data.get("top_competitors", [])
        top_competitors = []
        for c in raw_competitors[:5]:
            if not isinstance(c, dict):
                continue
            threat = c.get("threat_level", "medium")
            if threat not in valid_threats:
                threat = "medium"
            top_competitors.append({
                "name": str(c.get("name", "Unknown"))[:80],
                "deal_count": max(0, int(c.get("deal_count", 1))),
                "stages_present": [str(s) for s in (c.get("stages_present") or [])[:6]],
                "threat_level": threat,
                "positioning_note": str(c.get("positioning_note", ""))[:300],
            })

        strategies = [str(s)[:300] for s in (data.get("win_strategies") or [])[:3]]
        while len(strategies) < 3:
            strategies.append("Focus on differentiated value and customer outcomes.")

        summary = str(data.get("competitive_summary", ""))[:500]

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    return {
        "top_competitors": top_competitors,
        "competitive_summary": summary,
        "win_strategies": strategies,
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
    }


# AI deal follow-up sequence
# ---------------------------------------------------------------------------

_FOLLOWUP_SEQUENCE_SYSTEM = """\
You are Nova, the AI sales intelligence in NovaCRM. Generate a 3-step follow-up sequence
for an open sales deal based on its context.

Respond in exactly this JSON format (no markdown fences, no extra keys):
{
  "steps": [
    {
      "step": 1,
      "timing": "<now|3d|7d|14d>",
      "channel": "<email|call|slack>",
      "action": "<one specific action to take, max 200 chars>",
      "goal": "<desired outcome of this step, max 150 chars>"
    }
  ],
  "rationale": "<1-2 sentence explanation of the overall sequence strategy>"
}

Provide exactly 3 steps with varied timings and channels appropriate to deal context.
timing must be one of: now, 3d, 7d, 14d.
channel must be one of: email, call, slack.
"""


@router.post("/workspaces/{workspace_id}/deals/{deal_id}/ai/followup-sequence")
@limiter.limit("5/minute")
async def deal_followup_sequence(
    request: Request,
    workspace_id: uuid.UUID,
    deal_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    deal_result = await db.execute(
        select(Deal).where(Deal.id == deal_id, Deal.workspace_id == workspace_id)
    )
    deal = deal_result.scalar_one_or_none()
    if deal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found")

    if deal.stage in ("closed_won", "closed_lost"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Follow-up sequences are only available for open deals",
        )

    notes_result = await db.execute(
        select(DealNote.body)
        .where(DealNote.deal_id == deal_id)
        .order_by(DealNote.created_at.desc())
        .limit(3)
    )
    recent_notes = [r[0] for r in notes_result.fetchall()]

    stage_changed = deal.stage_changed_at or deal.created_at
    days_in_stage = 0
    if stage_changed:
        days_in_stage = max(0, (datetime.datetime.utcnow() - stage_changed.replace(tzinfo=None)).days)

    next_action_overdue = False
    if deal.next_action_date:
        try:
            na_date = datetime.date.fromisoformat(str(deal.next_action_date))
            next_action_overdue = na_date < datetime.date.today()
        except ValueError:
            pass

    context_lines = [
        f"Deal: {deal.title or 'Untitled'} | Company: {deal.company or 'Unknown'}",
        f"Stage: {deal.stage} | Value: ${deal.value:,.0f}",
        f"Health score: {deal.health_score} | Win probability: {deal.ml_win_probability}%",
        f"Days in current stage: {days_in_stage}",
        f"Next action overdue: {next_action_overdue}",
        f"Competitor count: {len(deal.competitors) if deal.competitors else 0}",
    ]
    if recent_notes:
        context_lines.append("\nRecent deal notes (newest first):")
        for i, note in enumerate(recent_notes, 1):
            context_lines.append(f"  Note {i}: {note[:300]}")

    context = "\n".join(context_lines)

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=700,
            system=_FOLLOWUP_SEQUENCE_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg.content[0].text.strip() if msg.content else "{}"
        data = json.loads(raw)
        if not isinstance(data, dict):
            data = {}

        valid_timings = {"now", "3d", "7d", "14d"}
        valid_channels = {"email", "call", "slack"}
        steps = []
        for s in (data.get("steps") or [])[:3]:
            if not isinstance(s, dict):
                continue
            timing = s.get("timing", "3d")
            if timing not in valid_timings:
                timing = "3d"
            channel = s.get("channel", "email")
            if channel not in valid_channels:
                channel = "email"
            steps.append({
                "step": len(steps) + 1,
                "timing": timing,
                "channel": channel,
                "action": str(s.get("action", ""))[:300],
                "goal": str(s.get("goal", ""))[:200],
            })

        while len(steps) < 3:
            steps.append({
                "step": len(steps) + 1,
                "timing": "7d",
                "channel": "email",
                "action": "Follow up with the prospect to check on next steps.",
                "goal": "Maintain momentum and keep the deal moving forward.",
            })

        rationale = str(data.get("rationale", ""))[:500]

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    return {
        "steps": steps,
        "rationale": rationale,
        "deal_id": str(deal_id),
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
    }


# ---------------------------------------------------------------------------
# Phase 15o: AI deal champion risk assessment
# ---------------------------------------------------------------------------

_CHAMPION_RISK_SYSTEM = """\
You are Nova, an AI sales intelligence engine. Assess the champion risk for an \
open deal — specifically the risk that the internal champion or decision-maker \
may be weakening, gone silent, or absent.

Return valid JSON (no markdown) in exactly this shape:
{
  "risk_level": "<one of: low|medium|high|critical>",
  "champion_status": "<one of: active|uncertain|at_risk|unknown>",
  "risk_signals": ["<signal 1>", "<signal 2>", "<signal 3>"],
  "mitigation_steps": ["<step 1>", "<step 2>", "<step 3>"]
}

Definitions:
- risk_level: low = champion clearly engaged; medium = some uncertainty; \
high = champion likely losing influence or going silent; critical = no champion or key stakeholder gone
- champion_status: active = confirmed champion actively pushing deal; \
uncertain = champion present but silent lately; at_risk = champion may have left or lost authority; \
unknown = no champion identified
- risk_signals: exactly 3 specific observations from the deal data explaining the risk
- mitigation_steps: exactly 3 concrete actions to strengthen the champion relationship
\
"""


@router.post("/workspaces/{workspace_id}/deals/{deal_id}/ai/champion-risk")
@limiter.limit("5/minute")
async def deal_champion_risk(
    request: Request,
    workspace_id: uuid.UUID,
    deal_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    deal_result = await db.execute(
        select(Deal).where(Deal.id == deal_id, Deal.workspace_id == workspace_id)
    )
    deal = deal_result.scalar_one_or_none()
    if deal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found")

    if deal.stage in ("closed_won", "closed_lost"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Champion risk is only available for open deals",
        )

    notes_result = await db.execute(
        select(DealNote.body)
        .where(DealNote.deal_id == deal_id)
        .order_by(DealNote.created_at.desc())
        .limit(3)
    )
    note_bodies = [row[0] for row in notes_result.all() if row[0]]

    today = datetime.date.today()
    if deal.stage_changed_at:
        days_in_stage = (today - deal.stage_changed_at.date()).days
    else:
        days_in_stage = 0

    mentions = deal.mentions or []
    champion_count = sum(1 for m in mentions if isinstance(m, dict) and m.get("type") == "champion")
    decision_maker_count = sum(1 for m in mentions if isinstance(m, dict) and m.get("type") == "decision_maker")

    champion_names = [m.get("name", "Unknown") for m in mentions if isinstance(m, dict) and m.get("type") == "champion"]
    dm_names = [m.get("name", "Unknown") for m in mentions if isinstance(m, dict) and m.get("type") == "decision_maker"]

    context = (
        f"Deal: {deal.title or 'Untitled'}\n"
        f"Company: {deal.company or 'Unknown'}\n"
        f"Stage: {deal.stage}\n"
        f"Value: ${float(deal.value or 0):,.0f}\n"
        f"Health score: {deal.health_score or 0}/100\n"
        f"Days in current stage: {days_in_stage}\n"
        f"ML win probability: {deal.ml_win_probability or 0}%\n"
        f"Identified champions: {champion_count} ({', '.join(champion_names) if champion_names else 'none'})\n"
        f"Identified decision-makers: {decision_maker_count} ({', '.join(dm_names) if dm_names else 'none'})\n"
        f"Total stakeholders mapped: {len(mentions)}\n"
    )
    if note_bodies:
        context += "\nRecent deal notes (latest first):\n"
        for body in note_bodies:
            context += f"  - {body[:200]}\n"

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            system=_CHAMPION_RISK_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg.content[0].text.strip() if msg.content else "{}"
        data = json.loads(raw)
        if not isinstance(data, dict):
            data = {}

        valid_risk_levels = {"low", "medium", "high", "critical"}
        valid_statuses = {"active", "uncertain", "at_risk", "unknown"}

        risk_level = str(data.get("risk_level", "medium"))
        if risk_level not in valid_risk_levels:
            risk_level = "medium"

        champion_status = str(data.get("champion_status", "unknown"))
        if champion_status not in valid_statuses:
            champion_status = "unknown"

        risk_signals = [str(s)[:200] for s in (data.get("risk_signals") or [])[:3]]
        while len(risk_signals) < 3:
            risk_signals.append("Insufficient deal activity to assess champion engagement.")

        mitigation_steps = [str(s)[:200] for s in (data.get("mitigation_steps") or [])[:3]]
        while len(mitigation_steps) < 3:
            mitigation_steps.append("Identify and engage a named internal champion.")

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    return {
        "risk_level": risk_level,
        "champion_status": champion_status,
        "risk_signals": risk_signals,
        "mitigation_steps": mitigation_steps,
        "deal_id": str(deal_id),
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
    }


# ---------------------------------------------------------------------------
# POST /workspaces/{workspace_id}/deals/{deal_id}/ai/competitive-response
# ---------------------------------------------------------------------------

_COMPETITIVE_RESPONSE_SYSTEM = """You are a sales intelligence AI that generates battle cards for competitive deals.

Given the deal context and list of competitors, return a JSON object with exactly these keys:
{
  "primary_competitor": "<string — name of the top competitor>",
  "battle_card": {
    "strengths": ["<string>", "<string>", "<string>"],
    "weaknesses": ["<string>", "<string>", "<string>"],
    "key_differentiators": ["<string>", "<string>", "<string>"],
    "suggested_talk_track": "<string — 2–3 sentences>"
  }
}

All list fields must have exactly 3 items. Output only valid JSON, no prose."""


@router.post(
    "/workspaces/{workspace_id}/deals/{deal_id}/ai/competitive-response",
    summary="AI deal competitive response battle card",
)
@limiter.limit("5/minute")
async def get_deal_competitive_response(
    request: Request,
    workspace_id: uuid.UUID,
    deal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    result = await db.execute(
        select(Deal).where(Deal.id == deal_id, Deal.workspace_id == workspace_id)
    )
    deal = result.scalar_one_or_none()
    if not deal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found")
    if deal.stage in ("closed_won", "closed_lost"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Competitive response not available for closed deals",
        )

    competitors: list[str] = deal.competitors or []
    if not competitors:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No competitors tracked for this deal",
        )

    note_result = await db.execute(
        select(DealNote.body)
        .where(DealNote.deal_id == deal_id)
        .order_by(DealNote.created_at.desc())
        .limit(3)
    )
    notes = [row[0] for row in note_result.all()]

    days_in_stage: int = 0
    if deal.stage_changed_at:
        days_in_stage = (datetime.datetime.utcnow() - deal.stage_changed_at.replace(tzinfo=None)).days

    competitor_list = ", ".join(competitors)
    note_snippets = "; ".join(f'"{n[:120]}"' for n in notes) if notes else "none"

    context = (
        f"Deal: {deal.title}, Company: {deal.company or 'unknown'}, "
        f"Stage: {deal.stage}, Value: ${deal.value or 0:,.0f}, "
        f"Health score: {deal.health_score or 0}/100, Days in stage: {days_in_stage}, "
        f"ML win probability: {deal.ml_win_probability or 0}%, "
        f"Competitors tracked: {competitor_list}. "
        f"Recent deal notes: {note_snippets}."
    )

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            system=_COMPETITIVE_RESPONSE_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = message.content[0].text.strip()
        parsed = json.loads(raw)

        primary_competitor = str(parsed.get("primary_competitor", competitors[0]))
        bc = parsed.get("battle_card", {})

        def _pad(lst: list, default: str) -> list:
            lst = [str(x) for x in lst] if isinstance(lst, list) else []
            while len(lst) < 3:
                lst.append(default)
            return lst[:3]

        strengths = _pad(bc.get("strengths", []), "Established market presence.")
        weaknesses = _pad(bc.get("weaknesses", []), "Limited customisation options.")
        key_differentiators = _pad(bc.get("key_differentiators", []), "Superior integrations and support.")
        suggested_talk_track = str(bc.get("suggested_talk_track", "Focus on our unique value proposition and proven ROI."))

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    return {
        "primary_competitor": primary_competitor,
        "battle_card": {
            "strengths": strengths,
            "weaknesses": weaknesses,
            "key_differentiators": key_differentiators,
            "suggested_talk_track": suggested_talk_track,
        },
        "deal_id": str(deal_id),
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
    }


# Phase 15q: AI deal expansion opportunity
# ---------------------------------------------------------------------------

_EXPANSION_OPPORTUNITY_SYSTEM = """You are a sales intelligence AI that identifies expansion opportunities for recently closed deals.

Given a closed_won deal context, return a JSON object with exactly these keys:
{
  "opportunity_score": <integer 0-100>,
  "upsell_products": ["<string>", "<string>", "<string>"],
  "cross_sell_signals": ["<string>", "<string>", "<string>"],
  "recommended_timing": "<one of: immediate|3_months|6_months>",
  "next_step": "<string — one specific action to take>"
}

opportunity_score: 0 = no expansion potential, 100 = very high expansion potential.
upsell_products: 3 specific product/service upgrades or add-ons relevant to this deal.
cross_sell_signals: 3 signals from the deal context suggesting adjacent product interest.
recommended_timing: when to approach the customer about expansion.
Output only valid JSON, no prose."""


@router.post(
    "/workspaces/{workspace_id}/deals/{deal_id}/ai/expansion-opportunity",
    summary="AI deal expansion opportunity analysis",
)
@limiter.limit("5/minute")
async def deal_expansion_opportunity(
    request: Request,
    workspace_id: uuid.UUID,
    deal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    result = await db.execute(
        select(Deal).where(Deal.id == deal_id, Deal.workspace_id == workspace_id)
    )
    deal = result.scalar_one_or_none()
    if not deal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found")
    if deal.stage != "closed_won":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Expansion opportunity is only available for closed_won deals",
        )

    contact = None
    if deal.contact_id:
        contact_result = await db.execute(
            select(Contact).where(Contact.id == deal.contact_id)
        )
        contact = contact_result.scalar_one_or_none()

    note_result = await db.execute(
        select(DealNote.body)
        .where(DealNote.deal_id == deal_id)
        .order_by(DealNote.created_at.desc())
        .limit(3)
    )
    notes = [row[0] for row in note_result.all()]

    open_task_count = 0
    if deal.contact_id:
        open_task_count = await db.scalar(
            select(func.count()).where(
                Task.workspace_id == workspace_id,
                Task.contact_id == deal.contact_id,
                Task.status.in_(["open", "in_progress"]),
            )
        ) or 0

    contact_info = ""
    if contact:
        contact_info = (
            f"Contact: {contact.name or 'unknown'}, Company: {contact.company or 'unknown'}, "
            f"Status: {contact.status or 'unknown'}, ML Score: {contact.ml_score or 0}/100. "
        )

    note_snippets = "; ".join(f'"{n[:120]}"' for n in notes) if notes else "none"

    context = (
        f"Deal: {deal.title}, Company: {deal.company or 'unknown'}, "
        f"Value: ${deal.value or 0:,.0f}, "
        f"Health score: {deal.health_score or 0}/100. "
        f"{contact_info}"
        f"Open tasks for this contact: {open_task_count}. "
        f"Recent deal notes: {note_snippets}."
    )

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            system=_EXPANSION_OPPORTUNITY_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = message.content[0].text.strip()
        parsed = json.loads(raw)

        opportunity_score = max(0, min(100, int(parsed.get("opportunity_score", 50))))

        def _pad3(lst: list, default: str) -> list:
            lst = [str(x) for x in lst] if isinstance(lst, list) else []
            while len(lst) < 3:
                lst.append(default)
            return lst[:3]

        upsell_products = _pad3(parsed.get("upsell_products", []), "Enterprise tier upgrade")
        cross_sell_signals = _pad3(
            parsed.get("cross_sell_signals", []), "Expressed interest in related features"
        )

        raw_timing = str(parsed.get("recommended_timing", "3_months"))
        if raw_timing not in ("immediate", "3_months", "6_months"):
            raw_timing = "3_months"
        recommended_timing = raw_timing

        next_step = str(
            parsed.get("next_step", "Schedule a 30-day post-implementation review call")
        )

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    return {
        "opportunity_score": opportunity_score,
        "upsell_products": upsell_products,
        "cross_sell_signals": cross_sell_signals,
        "recommended_timing": recommended_timing,
        "next_step": next_step,
        "deal_id": str(deal_id),
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
    }


# ---------------------------------------------------------------------------
# AI contact churn risk assessment
# ---------------------------------------------------------------------------

_CHURN_RISK_SYSTEM = """\
You are a CRM analyst specialized in customer retention. Given a contact's engagement
profile, return a JSON object assessing their churn risk:
{
  "risk_level": "<one of: low|medium|high|critical>",
  "churn_signals": ["<signal 1>", "<signal 2>", "<signal 3>"],
  "retention_actions": ["<action 1>", "<action 2>", "<action 3>"]
}
Rules:
- risk_level must be exactly one of: low, medium, high, critical
- churn_signals: 3 specific, evidence-based signals from the data
- retention_actions: 3 concrete, actionable steps to retain this contact
- Base risk_level on: days since last touch (>30=elevated, >60=high, >90=critical),
  message frequency decline, going-dark flag, pipeline value at stake, task neglect
Return ONLY the JSON object, no markdown, no explanation.
"""


@router.post("/workspaces/{workspace_id}/ai/contacts/{contact_id}/churn-risk")
@limiter.limit("5/minute")
async def contact_churn_risk(
    request: Request,
    workspace_id: uuid.UUID,
    contact_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    contact_result = await db.execute(
        select(Contact).where(
            Contact.id == contact_id,
            Contact.workspace_id == workspace_id,
        )
    )
    contact = contact_result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    ninety_days_ago = datetime.datetime.utcnow() - datetime.timedelta(days=90)
    thirty_days_ago = datetime.datetime.utcnow() - datetime.timedelta(days=30)

    # Message count last 90 days
    msg_result = await db.execute(
        select(func.count(Message.id)).where(
            Message.workspace_id == workspace_id,
            Message.contact_id == contact_id,
            Message.received_at >= ninety_days_ago,
        )
    )
    recent_message_count = msg_result.scalar() or 0

    # Note count last 90 days
    note_result = await db.execute(
        select(func.count(ContactNote.id)).where(
            ContactNote.workspace_id == workspace_id,
            ContactNote.contact_id == contact_id,
            ContactNote.created_at >= ninety_days_ago,
        )
    )
    recent_note_count = note_result.scalar() or 0

    # Open deal pipeline value
    deal_result = await db.execute(
        select(func.coalesce(func.sum(Deal.value), 0)).where(
            Deal.workspace_id == workspace_id,
            Deal.contact_id == contact_id,
            Deal.stage.notin_(["closed_won", "closed_lost"]),
        )
    )
    open_pipeline_value = float(deal_result.scalar() or 0)

    # Open task count
    task_result = await db.execute(
        select(func.count(Task.id)).where(
            Task.workspace_id == workspace_id,
            Task.contact_id == contact_id,
            Task.status.in_(["open", "in_progress"]),
        )
    )
    open_task_count = task_result.scalar() or 0

    # Days since last touch (latest of message or note)
    last_msg_result = await db.execute(
        select(func.max(Message.received_at)).where(
            Message.workspace_id == workspace_id,
            Message.contact_id == contact_id,
        )
    )
    last_msg_at = last_msg_result.scalar()

    last_note_result = await db.execute(
        select(func.max(ContactNote.created_at)).where(
            ContactNote.workspace_id == workspace_id,
            ContactNote.contact_id == contact_id,
        )
    )
    last_note_at = last_note_result.scalar()

    last_touch = None
    for ts in (last_msg_at, last_note_at):
        if ts is not None:
            if last_touch is None or ts > last_touch:
                last_touch = ts

    now = datetime.datetime.utcnow()
    days_since_last_touch = (now - last_touch).days if last_touch else 999
    going_dark = days_since_last_touch >= 30

    context = (
        f"Contact: {contact.name} ({contact.email})\n"
        f"Company: {contact.company or 'Unknown'}\n"
        f"Status: {contact.status}\n"
        f"ML score: {contact.ml_score or 0} ({contact.ml_score_label or 'unknown'})\n\n"
        f"Engagement (last 90 days):\n"
        f"  Messages: {recent_message_count}\n"
        f"  Notes: {recent_note_count}\n"
        f"  Open tasks: {open_task_count}\n\n"
        f"Last touch: {days_since_last_touch} days ago\n"
        f"Going dark (30+ days silent): {'Yes' if going_dark else 'No'}\n"
        f"Open pipeline at risk: ${open_pipeline_value:,.0f}\n"
    )

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=350,
            system=_CHURN_RISK_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg.content[0].text.strip() if msg.content else "{}"
        data = json.loads(raw)
        if not isinstance(data, dict):
            data = {}

        valid_risk_levels = {"low", "medium", "high", "critical"}
        risk_level = data.get("risk_level", "medium")
        if risk_level not in valid_risk_levels:
            risk_level = "medium"

        def _pad3(lst: list, default: str) -> list:
            lst = [str(x) for x in lst] if isinstance(lst, list) else []
            while len(lst) < 3:
                lst.append(default)
            return lst[:3]

        churn_signals = _pad3(
            data.get("churn_signals", []),
            "Reduced engagement activity detected",
        )
        retention_actions = _pad3(
            data.get("retention_actions", []),
            "Schedule a check-in call to re-engage",
        )

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    return {
        "risk_level": risk_level,
        "churn_signals": churn_signals,
        "retention_actions": retention_actions,
        "contact_id": str(contact_id),
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
    }


# ---------------------------------------------------------------------------
# AI contact deal velocity benchmark
# ---------------------------------------------------------------------------

_VELOCITY_BENCHMARK_SYSTEM = """\
You are a CRM analyst specializing in sales performance benchmarking. Given a contact's
deal velocity data compared to workspace averages, return a JSON object:
{
  "velocity_rating": "<one of: fast|on_par|slow>",
  "insight": "<one concise sentence explaining the rating and its business implication>"
}
Rules:
- velocity_rating: fast = contact avg is ≥15% faster than workspace avg; slow = ≥15% slower; otherwise on_par
- insight: exactly one sentence, specific to the numbers provided, no generic platitudes
Return ONLY the JSON object, no markdown, no explanation.
"""


@router.post("/workspaces/{workspace_id}/ai/contacts/{contact_id}/deal-velocity-benchmark")
@limiter.limit("5/minute")
async def contact_deal_velocity_benchmark(
    request: Request,
    workspace_id: uuid.UUID,
    contact_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    contact_result = await db.execute(
        select(Contact).where(
            Contact.id == contact_id,
            Contact.workspace_id == workspace_id,
        )
    )
    contact = contact_result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    # All closed deals for this contact with timing data
    contact_deals_result = await db.execute(
        select(Deal).where(
            Deal.workspace_id == workspace_id,
            Deal.contact_id == contact_id,
            Deal.stage.in_(["closed_won", "closed_lost"]),
        )
    )
    contact_deals = contact_deals_result.scalars().all()

    # All closed deals in workspace for comparison
    workspace_deals_result = await db.execute(
        select(Deal).where(
            Deal.workspace_id == workspace_id,
            Deal.stage.in_(["closed_won", "closed_lost"]),
        )
    )
    workspace_deals = workspace_deals_result.scalars().all()

    def _avg_days(deals: list) -> float | None:
        deltas = []
        for d in deals:
            if d.stage_changed_at and d.created_at:
                delta = (d.stage_changed_at - d.created_at).days
                if delta >= 0:
                    deltas.append(delta)
        return round(sum(deltas) / len(deltas), 1) if deltas else None

    def _stage_days(deals: list) -> dict:
        by_stage: dict[str, list[float]] = defaultdict(list)
        for d in deals:
            if d.stage_changed_at and d.created_at:
                delta = (d.stage_changed_at - d.created_at).days
                if delta >= 0:
                    by_stage[d.stage].append(float(delta))
        return {s: round(sum(v) / len(v), 1) for s, v in by_stage.items()}

    contact_avg = _avg_days(contact_deals)
    workspace_avg = _avg_days(workspace_deals)

    contact_stage_map = _stage_days(contact_deals)
    workspace_stage_map = _stage_days(workspace_deals)

    all_stages = sorted(set(list(contact_stage_map.keys()) + list(workspace_stage_map.keys())))
    stage_breakdown = [
        {
            "stage": s,
            "contact_days": contact_stage_map.get(s),
            "workspace_days": workspace_stage_map.get(s),
        }
        for s in all_stages
    ]

    # Default velocity_rating when we have no data
    if contact_avg is None or workspace_avg is None or workspace_avg == 0:
        velocity_rating = "on_par"
        insight = "Insufficient closed-deal history to benchmark velocity against workspace average."
    else:
        pct_diff = (workspace_avg - contact_avg) / workspace_avg
        if pct_diff >= 0.15:
            default_rating = "fast"
        elif pct_diff <= -0.15:
            default_rating = "slow"
        else:
            default_rating = "on_par"

        context = (
            f"Contact: {contact.name} ({contact.email})\n"
            f"Contact closed deals: {len(contact_deals)}\n"
            f"Contact avg days to close: {contact_avg}\n"
            f"Workspace avg days to close: {workspace_avg}\n"
            f"Percentage difference: {pct_diff*100:.1f}% ({'faster' if pct_diff > 0 else 'slower'} than average)\n"
        )

        try:
            client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
            msg = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=150,
                system=_VELOCITY_BENCHMARK_SYSTEM,
                messages=[{"role": "user", "content": context}],
            )
            raw = msg.content[0].text.strip() if msg.content else "{}"
            data = json.loads(raw)
            if not isinstance(data, dict):
                data = {}

            valid_ratings = {"fast", "on_par", "slow"}
            velocity_rating = data.get("velocity_rating", default_rating)
            if velocity_rating not in valid_ratings:
                velocity_rating = default_rating

            insight = str(data.get("insight", "Velocity assessment completed."))

        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"AI unavailable: {exc}",
            ) from exc

    return {
        "contact_avg_days": contact_avg,
        "workspace_avg_days": workspace_avg,
        "velocity_rating": velocity_rating,
        "stage_breakdown": stage_breakdown,
        "insight": insight,
        "contact_id": str(contact_id),
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
    }


# AI contact deal outcome predictor
# ---------------------------------------------------------------------------

_DEAL_OUTCOME_PREDICTOR_SYSTEM = """\
You are an expert CRM analyst predicting deal outcomes. Given a contact's open deals with
their stage, value, health score, and ML win probability, return a JSON object:
{
  "predicted_outcome": "<one of: win|loss|stalled>",
  "confidence": "<one of: high|medium|low>",
  "key_risks": ["<risk 1>", "<risk 2>", "<risk 3>"],
  "recommended_actions": ["<action 1>", "<action 2>", "<action 3>"]
}
Rules:
- predicted_outcome: win = avg win prob ≥60%; loss = avg win prob <30% and low health; stalled = in between or mixed signals
- confidence: high = clear signal from multiple deals; medium = mixed signals; low = single deal or insufficient data
- key_risks: exactly 3 specific, actionable risks based on the deal data
- recommended_actions: exactly 3 concrete next steps to improve the outcome
Return ONLY the JSON object, no markdown, no explanation.
"""


@router.post("/workspaces/{workspace_id}/ai/contacts/{contact_id}/deal-outcome-predictor")
@limiter.limit("5/minute")
async def contact_deal_outcome_predictor(
    request: Request,
    workspace_id: uuid.UUID,
    contact_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    contact_result = await db.execute(
        select(Contact).where(
            Contact.id == contact_id,
            Contact.workspace_id == workspace_id,
        )
    )
    contact = contact_result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    open_stages = ["discovery", "qualified", "proposal", "negotiation"]
    deals_result = await db.execute(
        select(Deal).where(
            Deal.workspace_id == workspace_id,
            Deal.contact_id == contact_id,
            Deal.stage.in_(open_stages),
        )
    )
    open_deals = deals_result.scalars().all()

    if not open_deals:
        return {
            "predicted_outcome": "stalled",
            "confidence": "low",
            "key_risks": [
                "No open deals for this contact.",
                "Contact may have disengaged.",
                "Pipeline coverage is zero.",
            ],
            "recommended_actions": [
                "Initiate a discovery call to identify new opportunities.",
                "Review past deal history to understand why deals closed.",
                "Send a re-engagement message to gauge interest.",
            ],
            "contact_id": str(contact_id),
            "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        }

    deals_summary = "\n".join(
        f"- Deal '{d.title}' | stage={d.stage} | value=${d.value or 0:,.0f} "
        f"| health={d.health_score or 0} | ml_win_prob={d.ml_win_probability or 0}%"
        for d in open_deals
    )
    context = (
        f"Contact: {contact.name} ({contact.email}), status={contact.status}\n"
        f"Open deals ({len(open_deals)}):\n{deals_summary}\n"
    )

    valid_outcomes = {"win", "loss", "stalled"}
    valid_confidences = {"high", "medium", "low"}

    # Compute defaults from data
    probs = [d.ml_win_probability or 0 for d in open_deals]
    avg_prob = sum(probs) / len(probs)
    avg_health = sum(d.health_score or 0 for d in open_deals) / len(open_deals)

    if avg_prob >= 60:
        default_outcome = "win"
    elif avg_prob < 30 and avg_health < 40:
        default_outcome = "loss"
    else:
        default_outcome = "stalled"
    default_confidence = "high" if len(open_deals) >= 3 else ("medium" if len(open_deals) >= 2 else "low")

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            system=_DEAL_OUTCOME_PREDICTOR_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg.content[0].text.strip() if msg.content else "{}"
        data = json.loads(raw)
        if not isinstance(data, dict):
            data = {}

        predicted_outcome = data.get("predicted_outcome", default_outcome)
        if predicted_outcome not in valid_outcomes:
            predicted_outcome = default_outcome

        confidence = data.get("confidence", default_confidence)
        if confidence not in valid_confidences:
            confidence = default_confidence

        key_risks = data.get("key_risks", [])
        if not isinstance(key_risks, list):
            key_risks = []
        key_risks = [str(r) for r in key_risks[:3]]
        while len(key_risks) < 3:
            key_risks.append("Monitor deal progress closely.")

        recommended_actions = data.get("recommended_actions", [])
        if not isinstance(recommended_actions, list):
            recommended_actions = []
        recommended_actions = [str(a) for a in recommended_actions[:3]]
        while len(recommended_actions) < 3:
            recommended_actions.append("Follow up with the contact.")

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    return {
        "predicted_outcome": predicted_outcome,
        "confidence": confidence,
        "key_risks": key_risks,
        "recommended_actions": recommended_actions,
        "contact_id": str(contact_id),
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
    }


_DEAL_PORTFOLIO_OVERVIEW_SYSTEM = """\
You are an expert CRM analyst reviewing a contact's full deal portfolio across all pipeline stages.
Given the contact profile and their deals (open and closed), return a JSON object:
{
  "pipeline_health": "<one of: strong|at_risk|mixed>",
  "highlights": ["<highlight 1>", "<highlight 2>", "<highlight 3>"],
  "risks": ["<risk 1>", "<risk 2>", "<risk 3>"]
}
Rules:
- pipeline_health: strong = open deals healthy + good win probability; at_risk = most deals stalled or low health; mixed = a blend of healthy and struggling deals
- highlights: exactly 3 positive observations about the contact's portfolio (closed won, high-value stages, strong momentum, etc.)
- risks: exactly 3 specific risks or gaps in the portfolio (stalled deals, low health, no pipeline, overdue actions, etc.)
Return ONLY the JSON object, no markdown, no explanation.
"""


@router.post("/workspaces/{workspace_id}/ai/contacts/{contact_id}/deal-portfolio-overview")
@limiter.limit("5/minute")
async def contact_deal_portfolio_overview(
    request: Request,
    workspace_id: uuid.UUID,
    contact_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    contact_result = await db.execute(
        select(Contact).where(
            Contact.id == contact_id,
            Contact.workspace_id == workspace_id,
        )
    )
    contact = contact_result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    deals_result = await db.execute(
        select(Deal).where(
            Deal.workspace_id == workspace_id,
            Deal.contact_id == contact_id,
        )
    )
    all_deals = deals_result.scalars().all()

    open_stages = {"discovery", "qualified", "proposal", "negotiation"}
    open_deals = [d for d in all_deals if d.stage in open_stages]
    closed_won = [d for d in all_deals if d.stage == "closed_won"]
    closed_lost = [d for d in all_deals if d.stage == "closed_lost"]

    total_pipeline_value = sum(d.value or 0 for d in open_deals)
    closed_won_value = sum(d.value or 0 for d in closed_won)
    open_deal_count = len(open_deals)

    if not all_deals:
        return {
            "pipeline_health": "at_risk",
            "total_pipeline_value": 0,
            "open_deal_count": 0,
            "highlights": [
                "No deal history found — fresh relationship to develop.",
                "Opportunity to establish the first deal and set the foundation.",
                "Contact profile is active and ready for pipeline engagement.",
            ],
            "risks": [
                "Zero pipeline coverage for this contact.",
                "No historical deal data to benchmark performance.",
                "Risk of contact disengagement without active opportunities.",
            ],
            "contact_id": str(contact_id),
            "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        }

    avg_health = sum(d.health_score or 0 for d in open_deals) / max(len(open_deals), 1)
    avg_prob = sum(d.ml_win_probability or 0 for d in open_deals) / max(len(open_deals), 1)

    deals_summary = "\n".join(
        f"- Deal '{d.title}' | stage={d.stage} | value=${d.value or 0:,.0f} "
        f"| health={d.health_score or 0} | ml_win_prob={d.ml_win_probability or 0}%"
        for d in all_deals
    )
    context = (
        f"Contact: {contact.name} ({contact.email}), status={contact.status}\n"
        f"Total deals: {len(all_deals)} | Open: {open_deal_count} | "
        f"Closed Won: {len(closed_won)} (${closed_won_value:,.0f}) | "
        f"Closed Lost: {len(closed_lost)}\n"
        f"Open pipeline: ${total_pipeline_value:,.0f} | Avg health: {avg_health:.0f} | Avg win prob: {avg_prob:.0f}%\n"
        f"All deals:\n{deals_summary}\n"
    )

    if avg_health >= 65 and avg_prob >= 55:
        default_health = "strong"
    elif avg_health < 40 or avg_prob < 25:
        default_health = "at_risk"
    else:
        default_health = "mixed"

    valid_health = {"strong", "at_risk", "mixed"}

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            system=_DEAL_PORTFOLIO_OVERVIEW_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg.content[0].text.strip() if msg.content else "{}"
        data = json.loads(raw)
        if not isinstance(data, dict):
            data = {}

        pipeline_health = data.get("pipeline_health", default_health)
        if pipeline_health not in valid_health:
            pipeline_health = default_health

        highlights = data.get("highlights", [])
        if not isinstance(highlights, list):
            highlights = []
        highlights = [str(h) for h in highlights[:3]]
        while len(highlights) < 3:
            highlights.append("Portfolio shows consistent engagement with multiple active deals.")

        risks = data.get("risks", [])
        if not isinstance(risks, list):
            risks = []
        risks = [str(r) for r in risks[:3]]
        while len(risks) < 3:
            risks.append("Monitor deal progression to prevent pipeline stagnation.")

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    return {
        "pipeline_health": pipeline_health,
        "total_pipeline_value": total_pipeline_value,
        "open_deal_count": open_deal_count,
        "highlights": highlights,
        "risks": risks,
        "contact_id": str(contact_id),
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
    }


# ---------------------------------------------------------------------------
# AI contact competitive positioning
# ---------------------------------------------------------------------------

_COMPETITIVE_POSITIONING_SYSTEM = """\
You are Nova, the AI sales positioning expert in NovaCRM.

Analyze this contact's competitive positioning based on their deal history and competitor data.

Respond in exactly this JSON format (no markdown fences, no extra keys):
{
  "positioning_strength": "strong",
  "top_competitor": "Salesforce",
  "win_rate_vs_competitor": 67,
  "positioning_tips": [
    "Tip 1 — specific tactical advice referencing the competitive situation and deal data.",
    "Tip 2 — second positioning tip using a specific CRM action (e.g. run competitive-response analysis).",
    "Tip 3 — third positioning tip."
  ],
  "differentiators": [
    "Differentiator 1 — what sets NovaCRM apart from the top competitor for this deal context.",
    "Differentiator 2.",
    "Differentiator 3."
  ]
}

Rules:
- positioning_strength: exactly one of "strong" | "moderate" | "weak"
  - "strong" if win rate vs top competitor is >= 60%, or no competitors tracked
  - "weak" if win rate vs top competitor is <= 30%, or all deals lost/stalled
  - "moderate" otherwise
- top_competitor: name of the most-frequently-appearing competitor, or null if none
- win_rate_vs_competitor: integer 0-100, percentage of closed deals won vs that competitor, or null if no competitor data
- positioning_tips: exactly 3 items, each citing a specific metric or action
- differentiators: exactly 3 items, each a concrete value proposition vs the top competitor\
"""


@router.post("/workspaces/{workspace_id}/ai/contacts/{contact_id}/competitive-positioning")
@limiter.limit("5/minute")
async def contact_competitive_positioning(
    request: Request,
    workspace_id: uuid.UUID,
    contact_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Assess this contact's competitive positioning using deal history and competitor data via Claude Haiku."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    contact_result = await db.execute(
        select(Contact).where(
            Contact.id == contact_id,
            Contact.workspace_id == workspace_id,
        )
    )
    contact = contact_result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    deals_result = await db.execute(
        select(Deal).where(
            Deal.workspace_id == workspace_id,
            Deal.contact_id == contact_id,
        )
    )
    all_deals = deals_result.scalars().all()

    # Tally competitor occurrences and compute win rate vs each
    competitor_counts: Counter = Counter()
    competitor_wins: Counter = Counter()
    competitor_total: Counter = Counter()

    for deal in all_deals:
        comps = deal.competitors or []
        for comp in comps:
            name = str(comp).strip()
            if not name:
                continue
            competitor_counts[name] += 1
            if deal.stage in ("closed_won", "closed_lost"):
                competitor_total[name] += 1
                if deal.stage == "closed_won":
                    competitor_wins[name] += 1

    top_competitor: str | None = None
    win_rate_vs_competitor: int | None = None
    if competitor_counts:
        top_competitor = competitor_counts.most_common(1)[0][0]
        total_vs_top = competitor_total.get(top_competitor, 0)
        if total_vs_top > 0:
            win_rate_vs_competitor = round(
                100 * competitor_wins.get(top_competitor, 0) / total_vs_top
            )

    # Graceful default when no deals or no competitors
    if not all_deals:
        return {
            "positioning_strength": "weak",
            "top_competitor": None,
            "win_rate_vs_competitor": None,
            "positioning_tips": [
                "No deal history found — establish the first deal to build a competitive baseline.",
                "Create a deal record and add any known competitors to enable positioning analysis.",
                "Use the Contact AI summary to craft an outreach strategy before competitors engage.",
            ],
            "differentiators": [
                "NovaCRM's agentic AI gives real-time deal health scoring with no setup required.",
                "Unified sales + PM intelligence eliminates the need for separate tools.",
                "Built-in semantic search and lead scoring outperform traditional CRM data silos.",
            ],
            "contact_id": str(contact_id),
            "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        }

    # Determine default positioning strength
    if not top_competitor:
        default_strength = "strong"
    elif win_rate_vs_competitor is not None and win_rate_vs_competitor >= 60:
        default_strength = "strong"
    elif win_rate_vs_competitor is not None and win_rate_vs_competitor <= 30:
        default_strength = "weak"
    else:
        default_strength = "moderate"

    open_stages = {"discovery", "qualified", "proposal", "negotiation"}
    deals_summary = "\n".join(
        f"- '{d.title}' | stage={d.stage} | value=${d.value or 0:,.0f} "
        f"| health={d.health_score or 0} | competitors={d.competitors or []}"
        for d in all_deals
        if d.stage in open_stages or d.stage in ("closed_won", "closed_lost")
    )

    context_lines = [
        f"Contact: {contact.name} ({contact.email}), status={contact.status}",
        f"Total deals: {len(all_deals)}",
        f"Top competitor: {top_competitor or 'None identified'}",
        f"Win rate vs top competitor: {win_rate_vs_competitor}%" if win_rate_vs_competitor is not None else "Win rate vs top competitor: N/A (no closed deals with this competitor)",
        f"All competitor occurrences: {dict(competitor_counts) or 'none'}",
        f"Deals:\n{deals_summary or 'No open or closed deals.'}",
    ]
    context = "\n".join(context_lines)

    valid_strengths = {"strong", "moderate", "weak"}

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            system=_COMPETITIVE_POSITIONING_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg.content[0].text.strip() if msg.content else "{}"
        data = json.loads(raw)
        if not isinstance(data, dict):
            data = {}

        positioning_strength = data.get("positioning_strength", default_strength)
        if positioning_strength not in valid_strengths:
            positioning_strength = default_strength

        returned_top = data.get("top_competitor")
        if returned_top is not None and str(returned_top).strip():
            top_competitor = str(returned_top).strip()

        returned_wr = data.get("win_rate_vs_competitor")
        if returned_wr is not None:
            try:
                win_rate_vs_competitor = max(0, min(100, int(returned_wr)))
            except (ValueError, TypeError):
                pass

        positioning_tips = data.get("positioning_tips", [])
        if not isinstance(positioning_tips, list):
            positioning_tips = []
        positioning_tips = [str(t) for t in positioning_tips[:3]]
        while len(positioning_tips) < 3:
            positioning_tips.append("Review deal notes and run a competitive-response analysis for this contact.")

        differentiators = data.get("differentiators", [])
        if not isinstance(differentiators, list):
            differentiators = []
        differentiators = [str(d) for d in differentiators[:3]]
        while len(differentiators) < 3:
            differentiators.append("NovaCRM's agentic AI pipeline intelligence delivers faster deal insights than alternatives.")

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    return {
        "positioning_strength": positioning_strength,
        "top_competitor": top_competitor,
        "win_rate_vs_competitor": win_rate_vs_competitor,
        "positioning_tips": positioning_tips,
        "differentiators": differentiators,
        "contact_id": str(contact_id),
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
    }


# ---------------------------------------------------------------------------

_MEETING_AGENDA_SYSTEM = """\
You are Nova, the AI meeting preparation expert in NovaCRM.

Generate a structured next-meeting agenda for a contact based on their profile, recent messages, open tasks, and deals.

Respond in exactly this JSON format (no markdown fences, no extra keys):
{
  "opening_hook": "A specific, personalized 1-2 sentence opener referencing something concrete about the contact or their deals.",
  "agenda_items": [
    {
      "topic": "Topic title (3-6 words)",
      "goal": "One sentence stating what you want to achieve with this topic.",
      "talking_points": [
        "First specific talking point with actionable detail.",
        "Second specific talking point with actionable detail."
      ],
      "time_estimate_mins": 10
    }
  ]
}

Rules:
- opening_hook: a warm, specific opener referencing the contact by name or a recent interaction
- agenda_items: exactly 4 items covering deal status, open tasks, relationship, and next steps
- Each topic: 3-6 words
- Each goal: exactly one sentence
- talking_points: exactly 2 items per agenda item, each concrete and actionable
- time_estimate_mins: integer 5, 10, or 15 only
- Total time should sum to approximately 40-45 minutes\
"""


@router.post("/workspaces/{workspace_id}/ai/contacts/{contact_id}/meeting-agenda")
@limiter.limit("5/minute")
async def contact_meeting_agenda(
    request: Request,
    workspace_id: uuid.UUID,
    contact_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Generate a structured next-meeting agenda for a contact via Claude Haiku."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    contact_result = await db.execute(
        select(Contact).where(
            Contact.id == contact_id,
            Contact.workspace_id == workspace_id,
        )
    )
    contact = contact_result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    msg_result = await db.execute(
        select(Message, ClarityScore)
        .outerjoin(ClarityScore, ClarityScore.message_id == Message.id)
        .where(
            Message.workspace_id == workspace_id,
            Message.contact_id == contact_id,
        )
        .order_by(Message.received_at.desc())
        .limit(3)
    )
    msg_rows = msg_result.all()

    tasks_result = await db.execute(
        select(Task).where(
            Task.workspace_id == workspace_id,
            Task.contact_id == contact_id,
            Task.status.in_(["open", "in_progress"]),
        )
        .limit(5)
    )
    open_tasks = tasks_result.scalars().all()

    deals_result = await db.execute(
        select(Deal).where(
            Deal.workspace_id == workspace_id,
            Deal.contact_id == contact_id,
            Deal.stage.in_(["discovery", "qualified", "proposal", "negotiation"]),
        )
        .limit(3)
    )
    open_deals = deals_result.scalars().all()

    msgs_summary = "\n".join(
        f"- Subject: {m.subject or '(none)'} | Clarity: {cs.score if cs else 'N/A'} | "
        f"Preview: {(m.body_plain or '')[:120]}"
        for m, cs in msg_rows
    ) or "No recent messages."

    tasks_summary = "\n".join(
        f"- [{t.status}] {t.title} | due: {t.due_date or 'none'}"
        for t in open_tasks
    ) or "No open tasks."

    deals_summary = "\n".join(
        f"- '{d.title}' | stage={d.stage} | value=${d.value or 0:,.0f} | health={d.health_score or 0}"
        for d in open_deals
    ) or "No open deals."

    context = "\n".join([
        f"Contact: {contact.name} ({contact.email}), status={contact.status}, company={contact.company or 'N/A'}",
        f"Lead score: {contact.ml_score or 0}",
        f"Open deals:\n{deals_summary}",
        f"Open tasks:\n{tasks_summary}",
        f"Recent messages:\n{msgs_summary}",
    ])

    _default_agenda = [
        {
            "topic": "Relationship check-in",
            "goal": "Reconnect and surface any unaddressed concerns.",
            "talking_points": [
                "Ask about recent developments at their company since your last touchpoint.",
                "Acknowledge any pending tasks and confirm priorities have not shifted.",
            ],
            "time_estimate_mins": 10,
        },
        {
            "topic": "Deal status review",
            "goal": "Confirm the current deal stage and remove any blockers.",
            "talking_points": [
                "Walk through open deal health scores and flag any at-risk items.",
                "Confirm next steps and timeline expectations with the contact.",
            ],
            "time_estimate_mins": 15,
        },
        {
            "topic": "Open task follow-up",
            "goal": "Ensure all outstanding action items are acknowledged and assigned.",
            "talking_points": [
                "Review the open task list and confirm ownership for each item.",
                "Set due-date commitments for any overdue tasks.",
            ],
            "time_estimate_mins": 10,
        },
        {
            "topic": "Next steps and close",
            "goal": "Agree on clear next actions and meeting cadence.",
            "talking_points": [
                "Summarise agreed actions and assign owners on both sides.",
                "Schedule the next touchpoint before leaving the call.",
            ],
            "time_estimate_mins": 5,
        },
    ]

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            system=_MEETING_AGENDA_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg.content[0].text.strip() if msg.content else "{}"
        data = json.loads(raw)
        if not isinstance(data, dict):
            data = {}

        opening_hook = str(data.get(
            "opening_hook",
            f"Great to connect, {contact.name} — let's make the most of our time today.",
        )).strip()
        if not opening_hook:
            opening_hook = f"Great to connect, {contact.name} — let's align on priorities today."

        raw_items = data.get("agenda_items", [])
        if not isinstance(raw_items, list):
            raw_items = []

        agenda_items = []
        for item in raw_items[:4]:
            if not isinstance(item, dict):
                continue
            topic = str(item.get("topic", "Discussion topic")).strip()
            goal = str(item.get("goal", "Advance the conversation.")).strip()
            tps = item.get("talking_points", [])
            if not isinstance(tps, list):
                tps = []
            talking_points = [str(t) for t in tps[:2]]
            while len(talking_points) < 2:
                talking_points.append("Confirm next steps before closing this topic.")
            try:
                time_est = int(item.get("time_estimate_mins", 10))
                if time_est not in (5, 10, 15):
                    time_est = 10
            except (ValueError, TypeError):
                time_est = 10
            agenda_items.append({
                "topic": topic,
                "goal": goal,
                "talking_points": talking_points,
                "time_estimate_mins": time_est,
            })

        while len(agenda_items) < 4:
            agenda_items.append(_default_agenda[len(agenda_items)])

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    return {
        "opening_hook": opening_hook,
        "agenda_items": agenda_items,
        "contact_id": str(contact_id),
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
    }


# ---------------------------------------------------------------------------
# POST /workspaces/{workspace_id}/ai/contacts/{contact_id}/communication-gap-analysis
# ---------------------------------------------------------------------------

_COMM_GAP_SYSTEM = """\
You are a sales communication analyst. Given data about a contact's messaging frequency and gap metrics, \
produce exactly 3 actionable recommendations to improve communication frequency and re-engage the contact. \
Reply ONLY with a valid JSON object: {"recommendations": ["…", "…", "…"]}
No markdown. No explanation. Pure JSON only."""


@router.post("/workspaces/{workspace_id}/ai/contacts/{contact_id}/communication-gap-analysis")
@limiter.limit("5/minute")
async def contact_communication_gap_analysis(
    request: Request,
    workspace_id: uuid.UUID,
    contact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    contact_row = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.workspace_id == workspace_id)
    )
    contact = contact_row.scalar_one_or_none()
    if contact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    msgs_result = await db.execute(
        select(Message.received_at)
        .where(
            Message.contact_id == contact_id,
            Message.workspace_id == workspace_id,
            Message.received_at.isnot(None),
        )
        .order_by(Message.received_at.desc())
        .limit(10)
    )
    msg_dates = msgs_result.scalars().all()

    ws_msgs_result = await db.execute(
        select(Message.received_at)
        .where(Message.workspace_id == workspace_id, Message.received_at.isnot(None))
        .order_by(Message.received_at.desc())
        .limit(100)
    )
    ws_dates = ws_msgs_result.scalars().all()

    now_utc = datetime.datetime.now(tz=timezone.utc)

    def _make_aware(dt: datetime.datetime) -> datetime.datetime:
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt

    if not msg_dates:
        avg_gap_days = 0.0
        longest_silence_days = 0.0
        gap_assessment = "dark"
        risk_level = "critical"
    else:
        sorted_contact = sorted(_make_aware(d) for d in msg_dates)
        all_pts = sorted_contact + [now_utc]
        gaps = [(all_pts[i] - all_pts[i - 1]).total_seconds() / 86400.0 for i in range(1, len(all_pts))]
        avg_gap_days = sum(gaps) / len(gaps)
        longest_silence_days = max(gaps)

        if avg_gap_days < 7:
            gap_assessment = "frequent"
        elif avg_gap_days < 14:
            gap_assessment = "normal"
        elif avg_gap_days < 30:
            gap_assessment = "sparse"
        else:
            gap_assessment = "dark"

        if avg_gap_days >= 30:
            risk_level = "critical"
        elif avg_gap_days >= 14:
            risk_level = "high"
        elif avg_gap_days >= 7:
            risk_level = "medium"
        else:
            risk_level = "low"

    if len(ws_dates) >= 2:
        sorted_ws = sorted(_make_aware(d) for d in ws_dates)
        ws_gaps = [
            (sorted_ws[i] - sorted_ws[i - 1]).total_seconds() / 86400.0
            for i in range(1, len(sorted_ws))
        ]
        workspace_avg_gap_days = sum(ws_gaps) / len(ws_gaps)
    else:
        workspace_avg_gap_days = avg_gap_days

    context = "\n".join([
        f"Contact: {contact.name} ({contact.email or 'N/A'})",
        f"Messages analyzed (last 10): {len(msg_dates)}",
        f"Average gap between messages: {avg_gap_days:.1f} days",
        f"Longest silence period: {longest_silence_days:.1f} days",
        f"Workspace average gap: {workspace_avg_gap_days:.1f} days",
        f"Gap assessment: {gap_assessment}",
        f"Risk level: {risk_level}",
        "Provide 3 specific, actionable recommendations to improve communication with this contact.",
    ])

    _default_recs = [
        "Send a personalised check-in email referencing a recent industry trend relevant to their business.",
        "Schedule a brief 15-minute reconnect call to surface any unaddressed concerns.",
        "Share a relevant case study or product update to provide value and re-open the conversation.",
    ]

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            system=_COMM_GAP_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg.content[0].text.strip() if msg.content else "{}"
        data = json.loads(raw)
        recs = data.get("recommendations", []) if isinstance(data, dict) else []
        if not isinstance(recs, list):
            recs = []
        recommendations = [str(r) for r in recs[:3]]
        while len(recommendations) < 3:
            recommendations.append(_default_recs[len(recommendations) % 3])
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    return {
        "avg_gap_days": round(avg_gap_days, 1),
        "longest_silence_days": round(longest_silence_days, 1),
        "workspace_avg_gap_days": round(workspace_avg_gap_days, 1),
        "gap_assessment": gap_assessment,
        "risk_level": risk_level,
        "recommendations": recommendations,
        "contact_id": str(contact_id),
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
    }


# ---------------------------------------------------------------------------
# POST /workspaces/{workspace_id}/ai/contacts/{contact_id}/sentiment-trend
# ---------------------------------------------------------------------------

_SENTIMENT_TREND_SYSTEM = """\
You are a sentiment analysis specialist. Given a list of email messages from a contact, score each message's \
sentiment from -1.0 (very negative) to 1.0 (very positive). Also provide 3 actionable recommendations \
for improving the relationship based on the overall sentiment trend. \
Reply ONLY with a valid JSON object: \
{"sentiment_points": [{"received_at": "<iso>", "score": <float>}, ...], "recommendations": ["…", "…", "…"]} \
No markdown. No explanation. Pure JSON only."""


@router.post("/workspaces/{workspace_id}/ai/contacts/{contact_id}/sentiment-trend")
@limiter.limit("5/minute")
async def contact_sentiment_trend(
    request: Request,
    workspace_id: uuid.UUID,
    contact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    contact_row = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.workspace_id == workspace_id)
    )
    contact = contact_row.scalar_one_or_none()
    if contact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    msgs_result = await db.execute(
        select(Message.received_at, Message.body_plain)
        .where(
            Message.contact_id == contact_id,
            Message.workspace_id == workspace_id,
            Message.received_at.isnot(None),
        )
        .order_by(Message.received_at.desc())
        .limit(20)
    )
    messages = msgs_result.all()
    messages_analyzed = len(messages)

    _default_recs = [
        "Schedule a personalised check-in to acknowledge recent concerns and rebuild rapport.",
        "Share a success story or case study that directly addresses their industry challenges.",
        "Propose a short roadmap review call to realign on goals and demonstrate commitment.",
    ]

    if not messages:
        return {
            "messages_analyzed": 0,
            "avg_sentiment": 0.0,
            "trend_direction": "stable",
            "recent_sentiment": 0.0,
            "oldest_sentiment": 0.0,
            "sentiment_points": [],
            "recommendations": _default_recs,
            "contact_id": str(contact_id),
            "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        }

    ordered = list(reversed(messages))  # oldest first
    msgs_list = []
    for received_at, body_plain in ordered:
        ts = received_at.isoformat() if received_at else "unknown"
        snippet = (body_plain or "")[:300].strip()
        msgs_list.append(f"[{ts}] {snippet}")

    context = "\n".join([
        f"Contact: {contact.name} ({contact.email or 'N/A'})",
        f"Messages to analyse ({messages_analyzed} total, oldest first):",
        *msgs_list,
        "Score each message sentiment from -1.0 (very negative) to 1.0 (very positive).",
        "Return sentiment_points in chronological order (oldest first).",
        "Include 3 specific, actionable recommendations based on the overall sentiment trend.",
    ])

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            system=_SENTIMENT_TREND_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg.content[0].text.strip() if msg.content else "{}"
        data = json.loads(raw)

        raw_points = data.get("sentiment_points", []) if isinstance(data, dict) else []
        sentiment_points = []
        if isinstance(raw_points, list):
            for i, pt in enumerate(raw_points[:messages_analyzed]):
                ts = ordered[i][0].isoformat() if i < len(ordered) else "unknown"
                score = float(pt.get("score", 0.0)) if isinstance(pt, dict) else 0.0
                score = max(-1.0, min(1.0, score))
                sentiment_points.append({"received_at": ts, "score": round(score, 3)})

        recs = data.get("recommendations", []) if isinstance(data, dict) else []
        if not isinstance(recs, list):
            recs = []
        recommendations = [str(r) for r in recs[:3]]
        while len(recommendations) < 3:
            recommendations.append(_default_recs[len(recommendations) % 3])

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    if sentiment_points:
        scores = [pt["score"] for pt in sentiment_points]
        avg_sentiment = round(sum(scores) / len(scores), 3)
        recent_sentiment = round(scores[-1], 3)
        oldest_sentiment = round(scores[0], 3)
        half = max(1, len(scores) // 2)
        old_avg = sum(scores[:half]) / half
        new_avg = sum(scores[-half:]) / half
        diff = new_avg - old_avg
        if diff > 0.1:
            trend_direction = "improving"
        elif diff < -0.1:
            trend_direction = "declining"
        else:
            trend_direction = "stable"
    else:
        avg_sentiment = 0.0
        recent_sentiment = 0.0
        oldest_sentiment = 0.0
        trend_direction = "stable"

    return {
        "messages_analyzed": messages_analyzed,
        "avg_sentiment": avg_sentiment,
        "trend_direction": trend_direction,
        "recent_sentiment": recent_sentiment,
        "oldest_sentiment": oldest_sentiment,
        "sentiment_points": sentiment_points,
        "recommendations": recommendations,
        "contact_id": str(contact_id),
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
    }


# POST /workspaces/{workspace_id}/ai/contacts/{contact_id}/account-plan
# ---------------------------------------------------------------------------

_ACCOUNT_PLAN_SYSTEM = """\
You are a strategic account planning expert. Given a CRM contact's profile, deal data, and recent communication context, \
create a concise account plan. Reply ONLY with a valid JSON object: \
{"account_status": "<strategic|growth|maintain|at_risk>", "plan_horizon": <30|90|180>, \
"objectives": [{"objective": "...", "metric": "...", "timeline": "..."}, ...], \
"key_risks": ["...", "...", "..."], "recommended_actions": ["...", "...", "..."]} \
Provide exactly 3 objectives, 3 key_risks, and 3 recommended_actions. No markdown. Pure JSON only."""


@router.post("/workspaces/{workspace_id}/ai/contacts/{contact_id}/account-plan")
@limiter.limit("5/minute")
async def contact_account_plan(
    request: Request,
    workspace_id: uuid.UUID,
    contact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    contact_row = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.workspace_id == workspace_id)
    )
    contact = contact_row.scalar_one_or_none()
    if contact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    deals_result = await db.execute(
        select(Deal.id, Deal.title, Deal.stage, Deal.value, Deal.ml_win_probability)
        .where(Deal.contact_id == contact_id, Deal.workspace_id == workspace_id)
    )
    deals = deals_result.all()
    total_pipeline = sum((d.value or 0) for d in deals if d.stage not in ("closed_won", "closed_lost"))
    closed_won_value = sum((d.value or 0) for d in deals if d.stage == "closed_won")

    tasks_count_result = await db.execute(
        select(func.count(Task.id)).where(
            Task.contact_id == contact_id,
            Task.workspace_id == workspace_id,
            Task.status.in_(("open", "in_progress")),
        )
    )
    open_task_count = tasks_count_result.scalar() or 0

    msgs_result = await db.execute(
        select(Message.subject, Message.body_plain, Message.received_at)
        .where(Message.contact_id == contact_id, Message.workspace_id == workspace_id)
        .order_by(Message.received_at.desc())
        .limit(3)
    )
    messages = msgs_result.all()

    deal_lines = []
    for d in deals:
        deal_lines.append(
            f"  - {d.title or 'Untitled'} | stage={d.stage} | value=${d.value or 0:,.0f} | win_prob={d.ml_win_probability or 0}%"
        )
    msg_lines = []
    for m in messages:
        snippet = (m.body_plain or "")[:200].strip()
        ts = m.received_at.isoformat() if m.received_at else "unknown"
        msg_lines.append(f"  - [{ts}] {m.subject or '(no subject)'}: {snippet}")

    context = "\n".join([
        f"Contact: {contact.name} ({contact.email or 'N/A'}) | status={contact.status or 'unknown'}",
        f"Company: {contact.company or 'N/A'}",
        f"ML Lead Score: {contact.ml_score or 0}",
        f"Open pipeline: ${total_pipeline:,.0f} | Closed won: ${closed_won_value:,.0f}",
        f"Open tasks: {open_task_count}",
        "Deals:" if deal_lines else "Deals: none",
        *deal_lines,
        "Recent messages:" if msg_lines else "Recent messages: none",
        *msg_lines,
    ])

    _defaults = {
        "account_status": "maintain",
        "plan_horizon": 90,
        "objectives": [
            {"objective": "Deepen product adoption", "metric": "50% feature utilisation", "timeline": "30 days"},
            {"objective": "Expand deal value", "metric": "$10K upsell", "timeline": "60 days"},
            {"objective": "Strengthen executive relationship", "metric": "Monthly EBR", "timeline": "90 days"},
        ],
        "key_risks": [
            "Low engagement may signal churn risk",
            "Competing vendors actively targeting the account",
            "No open tasks means follow-up gaps",
        ],
        "recommended_actions": [
            "Schedule a quarterly business review",
            "Share a product roadmap update aligned to their goals",
            "Identify a new champion within the account",
        ],
    }

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=700,
            system=_ACCOUNT_PLAN_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg.content[0].text.strip() if msg.content else "{}"
        data = json.loads(raw)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    valid_statuses = {"strategic", "growth", "maintain", "at_risk"}
    account_status = data.get("account_status", _defaults["account_status"])
    if account_status not in valid_statuses:
        account_status = _defaults["account_status"]

    valid_horizons = {30, 90, 180}
    try:
        plan_horizon = int(data.get("plan_horizon", _defaults["plan_horizon"]))
    except (TypeError, ValueError):
        plan_horizon = _defaults["plan_horizon"]
    if plan_horizon not in valid_horizons:
        plan_horizon = _defaults["plan_horizon"]

    raw_objectives = data.get("objectives", [])
    if not isinstance(raw_objectives, list):
        raw_objectives = []
    objectives = []
    for obj in raw_objectives[:3]:
        if isinstance(obj, dict):
            objectives.append({
                "objective": str(obj.get("objective", "")),
                "metric": str(obj.get("metric", "")),
                "timeline": str(obj.get("timeline", "")),
            })
    while len(objectives) < 3:
        objectives.append(_defaults["objectives"][len(objectives)])

    key_risks = [str(r) for r in (data.get("key_risks") or [])[:3]]
    while len(key_risks) < 3:
        key_risks.append(_defaults["key_risks"][len(key_risks)])

    recommended_actions = [str(a) for a in (data.get("recommended_actions") or [])[:3]]
    while len(recommended_actions) < 3:
        recommended_actions.append(_defaults["recommended_actions"][len(recommended_actions)])

    return {
        "account_status": account_status,
        "plan_horizon": plan_horizon,
        "objectives": objectives,
        "key_risks": key_risks,
        "recommended_actions": recommended_actions,
        "contact_id": str(contact_id),
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
    }


# ---------------------------------------------------------------------------
# POST /workspaces/{workspace_id}/ai/pipeline-narrative
# ---------------------------------------------------------------------------

_PIPELINE_NARRATIVE_SYSTEM = """\
You are a strategic sales intelligence analyst. Given a snapshot of an open pipeline, write a concise strategic narrative \
that tells the story of the pipeline's health, momentum, and key opportunities or risks. \
Reply ONLY with a valid JSON object: \
{"narrative": "<2-3 paragraph strategic story separated by \\n\\n>", \
"key_themes": ["...", "...", "..."], "momentum": "<accelerating|steady|stalling>"} \
Exactly 3 key_themes. No markdown. Pure JSON only."""


@router.post("/workspaces/{workspace_id}/ai/pipeline-narrative")
@limiter.limit("5/minute")
async def pipeline_narrative(
    request: Request,
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    open_deals_result = await db.execute(
        select(Deal.title, Deal.value, Deal.stage, Deal.health_score, Deal.ml_win_probability, Deal.company)
        .where(
            Deal.workspace_id == workspace_id,
            Deal.stage.notin_(["closed_won", "closed_lost"]),
        )
        .order_by(Deal.value.desc().nullslast())
    )
    open_deals = open_deals_result.all()

    total_value = sum(d.value or 0 for d in open_deals)
    deal_count = len(open_deals)
    at_risk_count = sum(1 for d in open_deals if (d.health_score or 0) < 50)
    avg_win_prob = round(sum(d.ml_win_probability or 0 for d in open_deals) / max(deal_count, 1), 1)

    stage_counts: dict[str, int] = {}
    for d in open_deals:
        stage_counts[d.stage] = stage_counts.get(d.stage, 0) + 1

    thirty_days_ago = datetime.datetime.utcnow() - datetime.timedelta(days=30)
    closed_won_result = await db.execute(
        select(func.count(Deal.id), func.sum(Deal.value))
        .where(
            Deal.workspace_id == workspace_id,
            Deal.stage == "closed_won",
            Deal.stage_changed_at >= thirty_days_ago,
        )
    )
    closed_row = closed_won_result.one()
    closed_won_count = closed_row[0] or 0
    closed_won_value = float(closed_row[1] or 0)

    top_5 = open_deals[:5]
    top_deals_lines = [
        f"- {d.title or 'Untitled'} ({d.company or 'N/A'}): stage={d.stage}, value=${d.value or 0:,.0f}, "
        f"health={d.health_score or 0}, win_prob={d.ml_win_probability or 0}%"
        for d in top_5
    ]
    stage_lines = [f"  {stage}: {count} deals" for stage, count in sorted(stage_counts.items())]

    context = "\n".join([
        f"Open pipeline: {deal_count} deals, total value: ${total_value:,.0f}",
        f"At-risk deals (health<50): {at_risk_count}",
        f"Avg win probability: {avg_win_prob}%",
        "Stage breakdown:\n" + ("\n".join(stage_lines) if stage_lines else "  (empty)"),
        "Top 5 deals by value:\n" + ("\n".join(top_deals_lines) if top_deals_lines else "  (none)"),
        f"Closed-won last 30 days: {closed_won_count} deals, value: ${closed_won_value:,.0f}",
        "\nWrite a 2-3 paragraph strategic narrative, 3 key themes, and assess momentum.",
    ])

    _default_narrative = (
        "The pipeline presents a balanced mix of early-stage opportunities and advanced deals nearing close. "
        "With total open value providing a solid foundation, the team is well-positioned to close meaningful revenue this quarter.\n\n"
        "Several deals show strong health scores and high win probabilities, signalling that focused effort now can accelerate closures. "
        "However, a portion of the pipeline remains at risk and requires active intervention to prevent value leakage.\n\n"
        "Overall momentum is steady. Prioritising high-value deals with clear next actions while reviving at-risk opportunities "
        "will be key to hitting targets."
    )
    _default_themes = [
        "Accelerate high-probability deals with clear next-action plans.",
        "Shore up at-risk opportunities before they exit the funnel.",
        "Sustain early-stage pipeline to secure future quarters.",
    ]

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=800,
            system=_PIPELINE_NARRATIVE_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg.content[0].text.strip() if msg.content else "{}"
        data = json.loads(raw)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    narrative = data.get("narrative", _default_narrative)
    if not isinstance(narrative, str) or not narrative.strip():
        narrative = _default_narrative

    raw_themes = data.get("key_themes", [])
    key_themes = [str(t) for t in (raw_themes if isinstance(raw_themes, list) else [])[:3]]
    while len(key_themes) < 3:
        key_themes.append(_default_themes[len(key_themes) % 3])

    valid_momentums = {"accelerating", "steady", "stalling"}
    momentum = data.get("momentum", "steady")
    if momentum not in valid_momentums:
        momentum = "steady"

    return {
        "narrative": narrative,
        "key_themes": key_themes,
        "momentum": momentum,
        "total_value": total_value,
        "deal_count": deal_count,
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
    }



# ---------------------------------------------------------------------------
# Phase 16b: AI workspace contact health summary
# ---------------------------------------------------------------------------
_CONTACT_HEALTH_SYSTEM = """\
You are a CRM analyst specialising in contact engagement. Given workspace contact statistics, \
write a concise 2-sentence health summary and suggest the 3 highest-priority actions. \
Reply ONLY with a valid JSON object: \
{"summary": "<2-sentence narrative>", \
"health_rating": "<strong|healthy|needs_attention|critical>", \
"top_actions": ["...", "...", "..."]} \
Exactly 3 top_actions. No markdown. Pure JSON only."""


@router.get("/workspaces/{workspace_id}/ai/contacts/health-summary")
@limiter.limit("5/minute")
async def contact_health_summary(
    request: Request,
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    thirty_days_ago = datetime.datetime.utcnow() - datetime.timedelta(days=30)
    fourteen_days_ago = datetime.datetime.utcnow() - datetime.timedelta(days=14)

    # All contacts in workspace
    contacts_result = await db.execute(
        select(Contact.id).where(Contact.workspace_id == workspace_id)
    )
    contact_ids = [row[0] for row in contacts_result.all()]
    total_contacts = len(contact_ids)

    if total_contacts == 0:
        return {
            "summary": "No contacts exist in this workspace yet. Start adding contacts to track engagement health.",
            "health_rating": "needs_attention",
            "going_dark_count": 0,
            "at_risk_count": 0,
            "total_contacts": 0,
            "top_actions": [
                "Import your existing contacts to get started.",
                "Connect your email to begin tracking message activity.",
                "Add notes after meetings to build engagement history.",
            ],
            "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        }

    # Last-touch per contact: max(messages.received_at, notes.created_at)
    msg_touch_result = await db.execute(
        select(Message.contact_id, func.max(Message.received_at).label("last_msg"))
        .where(Message.contact_id.in_(contact_ids))
        .group_by(Message.contact_id)
    )
    msg_touches = {row[0]: row[1] for row in msg_touch_result.all()}

    note_touch_result = await db.execute(
        select(ContactNote.contact_id, func.max(ContactNote.created_at).label("last_note"))
        .where(ContactNote.contact_id.in_(contact_ids))
        .group_by(ContactNote.contact_id)
    )
    note_touches = {row[0]: row[1] for row in note_touch_result.all()}

    going_dark_count = 0
    at_risk_count = 0
    touched_count = 0
    for cid in contact_ids:
        mt = msg_touches.get(cid)
        nt = note_touches.get(cid)
        candidates = [t for t in (mt, nt) if t is not None]
        if not candidates:
            going_dark_count += 1
            continue
        last = max(candidates)
        if hasattr(last, "tzinfo") and last.tzinfo is not None:
            last = last.replace(tzinfo=None)
        touched_count += 1
        if last < thirty_days_ago:
            going_dark_count += 1
        elif last < fourteen_days_ago:
            at_risk_count += 1

    engaged_count = total_contacts - going_dark_count - at_risk_count
    going_dark_pct = round(going_dark_count / total_contacts * 100) if total_contacts else 0

    context = (
        f"Workspace contact health snapshot:\n"
        f"- Total contacts: {total_contacts}\n"
        f"- Engaged (touched within 14 days): {engaged_count}\n"
        f"- At-risk (no touch in 14-30 days): {at_risk_count}\n"
        f"- Going dark (no touch in 30+ days or never touched): {going_dark_count} ({going_dark_pct}%)\n"
    )

    _default_summary = (
        f"The workspace has {total_contacts} contacts with {going_dark_count} going dark "
        f"and {at_risk_count} at risk. Prioritise re-engagement to protect relationship quality."
    )
    _default_actions = [
        f"Re-engage the {going_dark_count} contacts who have gone dark.",
        f"Schedule follow-ups for the {at_risk_count} at-risk contacts.",
        "Review and update contact records to improve data quality.",
    ]

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            system=_CONTACT_HEALTH_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg.content[0].text.strip() if msg.content else "{}"
        data = json.loads(raw)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    summary = data.get("summary", _default_summary)
    if not isinstance(summary, str) or not summary.strip():
        summary = _default_summary

    valid_ratings = {"strong", "healthy", "needs_attention", "critical"}
    health_rating = data.get("health_rating", "needs_attention")
    if health_rating not in valid_ratings:
        health_rating = "needs_attention"

    raw_actions = data.get("top_actions", [])
    top_actions = [str(a) for a in (raw_actions if isinstance(raw_actions, list) else [])[:3]]
    while len(top_actions) < 3:
        top_actions.append(_default_actions[len(top_actions) % 3])

    return {
        "summary": summary,
        "health_rating": health_rating,
        "going_dark_count": going_dark_count,
        "at_risk_count": at_risk_count,
        "total_contacts": total_contacts,
        "top_actions": top_actions,
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
    }


# ── Win Probability Calibration ───────────────────────────────────────────────

_CALIBRATION_SYSTEM = """\
You are a sales analytics expert reviewing ML model calibration data for a CRM.
Given win-probability calibration buckets (predicted vs actual win rates), write a
concise analysis and actionable recommendations.

Return ONLY valid JSON with this exact structure:
{
  "narrative": "2-3 sentence analysis of the calibration results",
  "recommendations": ["rec1", "rec2", "rec3"]
}

Rules:
- narrative: describe overall calibration quality, where the model is most/least accurate
- recommendations: exactly 3 specific, actionable steps to improve forecast accuracy
- Be data-driven and reference the calibration_score and bias provided\
"""


@router.get("/workspaces/{workspace_id}/ai/deals/win-probability-calibration")
@limiter.limit("5/minute")
async def win_probability_calibration(
    request: Request,
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    result = await db.execute(
        select(Deal.ml_win_probability, Deal.stage).where(
            Deal.workspace_id == workspace_id,
            Deal.ml_win_probability.isnot(None),
        )
    )
    rows = result.all()

    # Build 10% buckets
    buckets: dict[int, dict] = {b: {"predicted_sum": 0, "won": 0, "lost": 0, "total": 0} for b in range(0, 100, 10)}
    for prob, stage in rows:
        b = min(int(prob) // 10 * 10, 90)
        buckets[b]["predicted_sum"] += prob
        buckets[b]["total"] += 1
        if stage == "closed_won":
            buckets[b]["won"] += 1
        elif stage == "closed_lost":
            buckets[b]["lost"] += 1

    calibration_buckets = []
    errors = []
    bias_deltas = []
    for b in range(0, 100, 10):
        d = buckets[b]
        total = d["total"]
        predicted_avg = round(d["predicted_sum"] / total, 1) if total > 0 else b + 5.0
        closed = d["won"] + d["lost"]
        actual_win_rate = round(d["won"] / closed * 100, 1) if closed > 0 else None
        calibration_buckets.append({
            "bucket_label": f"{b}–{b+9}%",
            "predicted_avg": predicted_avg,
            "actual_win_rate": actual_win_rate,
            "deal_count": total,
        })
        if actual_win_rate is not None:
            errors.append(abs(predicted_avg - actual_win_rate))
            bias_deltas.append(predicted_avg - actual_win_rate)

    calibration_score = round(max(0, 100 - (sum(errors) / len(errors))), 1) if errors else None
    if bias_deltas:
        avg_bias = sum(bias_deltas) / len(bias_deltas)
        overall_bias = "optimistic" if avg_bias > 5 else ("pessimistic" if avg_bias < -5 else "well_calibrated")
    else:
        overall_bias = "well_calibrated"

    _default_narrative = (
        "Insufficient closed deal data to fully evaluate model calibration. "
        "As deals close, the calibration report will reveal how accurately the ML model predicts outcomes."
    )
    _default_recommendations = [
        "Close more deals to build a statistically significant calibration dataset.",
        "Review deals stuck in early stages for accurate ML probability inputs.",
        "Manually audit deals with probabilities above 70% to validate model signals.",
    ]

    if not rows:
        return {
            "calibration_buckets": calibration_buckets,
            "calibration_score": None,
            "overall_bias": "well_calibrated",
            "narrative": _default_narrative,
            "recommendations": _default_recommendations,
            "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        }

    context = (
        f"Calibration Score: {calibration_score if calibration_score is not None else 'N/A'}/100\n"
        f"Overall Bias: {overall_bias}\n"
        f"Buckets with closed deal data: {len(errors)}\n\n"
        "Calibration buckets (predicted% → actual win rate%):\n"
    )
    for bk in calibration_buckets:
        actual = f"{bk['actual_win_rate']}%" if bk["actual_win_rate"] is not None else "no closed data"
        context += f"  {bk['bucket_label']}: predicted {bk['predicted_avg']}% → actual {actual} ({bk['deal_count']} deals)\n"

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            system=_CALIBRATION_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg.content[0].text.strip() if msg.content else "{}"
        data = json.loads(raw)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    narrative = data.get("narrative", _default_narrative)
    if not isinstance(narrative, str) or not narrative.strip():
        narrative = _default_narrative

    raw_recs = data.get("recommendations", [])
    recommendations = [str(r) for r in (raw_recs if isinstance(raw_recs, list) else []) if str(r).strip()][:3]
    while len(recommendations) < 3:
        recommendations.append(_default_recommendations[len(recommendations)])

    return {
        "calibration_buckets": calibration_buckets,
        "calibration_score": calibration_score,
        "overall_bias": overall_bias,
        "narrative": narrative,
        "recommendations": recommendations,
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
    }


# ── Agent Performance Report ──────────────────────────────────────────────────

_AGENT_PERF_SYSTEM = """\
You are a CRM operations analyst reviewing AI agent performance data for a sales team.
Given agent run statistics from the last 30 days, write a concise performance summary.

Return ONLY valid JSON with this exact structure:
{
  "narrative": "2-sentence summary of overall agent performance and any standout patterns",
  "recommendations": ["rec1", "rec2", "rec3"]
}

Rules:
- narrative: 2 sentences, reference specific agents by name where useful, plain prose
- recommendations: exactly 3 specific, actionable steps to improve agent reliability or utilization\
"""


@router.get("/workspaces/{workspace_id}/ai/agents/performance-report")
@limiter.limit("5/minute")
async def agent_performance_report(
    request: Request,
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=30)

    result = await db.execute(
        select(ActivityEvent.agent_name, ActivityEvent.severity)
        .where(
            ActivityEvent.workspace_id == workspace_id,
            ActivityEvent.agent_name.isnot(None),
            ActivityEvent.created_at >= cutoff,
        )
    )
    rows = result.all()

    stats_map: dict[str, dict] = {}
    for agent_name, severity in rows:
        name = str(agent_name)
        if name not in stats_map:
            stats_map[name] = {"run_count": 0, "success_count": 0, "failure_count": 0}
        stats_map[name]["run_count"] += 1
        if severity == "error":
            stats_map[name]["failure_count"] += 1
        else:
            stats_map[name]["success_count"] += 1

    agent_stats = []
    for name, s in sorted(stats_map.items(), key=lambda x: -x[1]["run_count"]):
        rate = round(s["success_count"] / s["run_count"] * 100, 1) if s["run_count"] > 0 else 0.0
        agent_stats.append({
            "agent_name": name,
            "run_count": s["run_count"],
            "success_count": s["success_count"],
            "failure_count": s["failure_count"],
            "success_rate": rate,
        })

    total_runs = sum(s["run_count"] for s in stats_map.values())
    total_success = sum(s["success_count"] for s in stats_map.values())
    overall_success_rate = round(total_success / total_runs * 100, 1) if total_runs > 0 else 0.0

    most_active_agent = max(stats_map, key=lambda n: stats_map[n]["run_count"]) if stats_map else None
    least_reliable_agent = min(
        stats_map,
        key=lambda n: stats_map[n]["success_count"] / stats_map[n]["run_count"] if stats_map[n]["run_count"] > 0 else 1,
    ) if stats_map else None

    _default_narrative = (
        "No agent activity was recorded in the last 30 days. "
        "Run agents from the Agents page to start tracking performance."
    )
    _default_recommendations = [
        "Schedule regular automated agent runs using Celery beat tasks.",
        "Review agent failure logs to identify recurring error patterns.",
        "Enable email alerts for agent failure rates above 20%.",
    ]

    if not agent_stats:
        return {
            "agent_stats": [],
            "overall_success_rate": 0.0,
            "most_active_agent": None,
            "least_reliable_agent": None,
            "narrative": _default_narrative,
            "recommendations": _default_recommendations,
            "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        }

    context = (
        f"Overall success rate: {overall_success_rate}% ({total_success}/{total_runs} runs succeeded)\n"
        f"Most active agent: {most_active_agent}\n"
        f"Least reliable agent: {least_reliable_agent}\n\n"
        "Per-agent stats (last 30 days):\n"
    )
    for a in agent_stats:
        context += f"  {a['agent_name']}: {a['run_count']} runs, {a['success_rate']}% success ({a['failure_count']} failures)\n"

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=350,
            system=_AGENT_PERF_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg.content[0].text.strip() if msg.content else "{}"
        data = json.loads(raw)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    narrative = data.get("narrative", _default_narrative)
    if not isinstance(narrative, str) or not narrative.strip():
        narrative = _default_narrative

    raw_recs = data.get("recommendations", [])
    recommendations = [str(r) for r in (raw_recs if isinstance(raw_recs, list) else []) if str(r).strip()][:3]
    while len(recommendations) < 3:
        recommendations.append(_default_recommendations[len(recommendations)])

    return {
        "agent_stats": agent_stats,
        "overall_success_rate": overall_success_rate,
        "most_active_agent": most_active_agent,
        "least_reliable_agent": least_reliable_agent,
        "narrative": narrative,
        "recommendations": recommendations,
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
    }


_CONTACT_FUNNEL_SYSTEM = (
    "You are a CRM analytics expert. Given a contact acquisition funnel with stage counts and "
    "conversion rates, return a JSON object with exactly two keys:\n"
    "  \"top_insight\": a single sentence summarising the biggest opportunity or risk in the funnel,\n"
    "  \"recommendations\": a JSON array of exactly 3 concise, actionable strings to improve conversion.\n"
    "Return ONLY valid JSON. No markdown, no explanation."
)


@router.get("/workspaces/{workspace_id}/ai/contacts/acquisition-funnel")
@limiter.limit("5/minute")
async def contact_acquisition_funnel(
    request: Request,
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    funnel_stages = ["lead", "prospect", "customer"]

    result = await db.execute(
        select(Contact.status, func.count(Contact.id).label("cnt"))
        .where(Contact.workspace_id == workspace_id)
        .where(Contact.status.in_(funnel_stages))
        .group_by(Contact.status)
    )
    counts: dict[str, int] = {row.status: row.cnt for row in result.all()}

    stage_counts = [counts.get(s, 0) for s in funnel_stages]

    funnel: list[dict] = []
    for i, stage in enumerate(funnel_stages):
        count = stage_counts[i]
        if i == 0:
            conversion_rate = None
        else:
            prev = stage_counts[i - 1]
            conversion_rate = round(count / prev * 100, 1) if prev > 0 else 0.0
        funnel.append({"stage": stage, "count": count, "conversion_rate": conversion_rate})

    _default_insight = (
        "No contacts in the funnel yet — start by importing leads and tracking their progress."
    )
    _default_recommendations = [
        "Import leads via CSV or connect Gmail/Slack to auto-create contacts from inbound messages.",
        "Set up a weekly review cadence to move stalled leads to prospect or mark them as churned.",
        "Use the Lead Scorer agent to prioritise which prospects to advance to customer.",
    ]

    total = sum(stage_counts)
    if total == 0:
        return {
            "funnel_stages": funnel,
            "top_insight": _default_insight,
            "recommendations": _default_recommendations,
            "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        }

    context_lines = ["Contact acquisition funnel (stage: count — conversion from previous stage):"]
    for f in funnel:
        conv_str = f"(conversion: {f['conversion_rate']}%)" if f["conversion_rate"] is not None else "(top of funnel)"
        context_lines.append(f"  {f['stage']}: {f['count']} contacts {conv_str}")
    context = "\n".join(context_lines)

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            system=_CONTACT_FUNNEL_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg.content[0].text.strip() if msg.content else "{}"
        data = json.loads(raw)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    top_insight = data.get("top_insight", _default_insight)
    if not isinstance(top_insight, str) or not top_insight.strip():
        top_insight = _default_insight

    raw_recs = data.get("recommendations", [])
    recommendations = [str(r) for r in (raw_recs if isinstance(raw_recs, list) else []) if str(r).strip()][:3]
    while len(recommendations) < 3:
        recommendations.append(_default_recommendations[len(recommendations)])

    return {
        "funnel_stages": funnel,
        "top_insight": top_insight,
        "recommendations": recommendations,
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
    }


_SOURCE_ATTRIBUTION_SYSTEM = (
    "You are a CRM revenue analyst. Given a contact source attribution breakdown showing pipeline value "
    "and won revenue per company/domain cluster, return a JSON object with exactly two keys:\n"
    "  \"insight\": a single sentence summarising the most important finding,\n"
    "  \"recommendations\": a JSON array of exactly 3 concise, actionable strings.\n"
    "Return ONLY valid JSON. No markdown, no explanation."
)


@router.get("/workspaces/{workspace_id}/ai/contacts/source-attribution")
@limiter.limit("5/minute")
async def contact_source_attribution(
    request: Request,
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    contacts_result = await db.execute(
        select(Contact.id, Contact.email, Contact.company)
        .where(Contact.workspace_id == workspace_id)
    )
    contacts = contacts_result.all()

    _default_insight = "No contacts found — import contacts to see source attribution."
    _default_recommendations = [
        "Import contacts via CSV to start tracking pipeline by source.",
        "Connect Gmail or Slack to auto-create contacts from inbound messages.",
        "Use company fields consistently to improve source attribution accuracy.",
    ]

    if not contacts:
        return {
            "sources": [],
            "top_source": None,
            "insight": _default_insight,
            "recommendations": _default_recommendations,
            "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        }

    # Build contact_id → source_label map using company or email domain
    contact_source_map: dict[str, str] = {}
    for c in contacts:
        if c.company and c.company.strip():
            source = c.company.strip()
        elif c.email and "@" in c.email:
            domain_part = c.email.split("@")[1].split(".")[0]
            source = f"{domain_part.capitalize()} (domain)"
        else:
            source = "Unknown"
        contact_source_map[str(c.id)] = source

    # Fetch all deals for the workspace contacts
    contact_uuids = [uuid.UUID(cid) for cid in contact_source_map]
    deals_result = await db.execute(
        select(Deal.contact_id, Deal.value, Deal.stage)
        .where(Deal.workspace_id == workspace_id)
        .where(Deal.contact_id.in_(contact_uuids))
    )
    deal_rows = deals_result.all()

    # Aggregate by source label
    source_stats: dict[str, dict] = {}
    for cid in contact_source_map:
        source = contact_source_map[cid]
        if source not in source_stats:
            source_stats[source] = {"contact_ids": set(), "pipeline_value": 0, "won_revenue": 0, "deal_count": 0, "won_count": 0}
        source_stats[source]["contact_ids"].add(cid)

    for row in deal_rows:
        cid = str(row.contact_id)
        source = contact_source_map.get(cid, "Unknown")
        if source not in source_stats:
            source_stats[source] = {"contact_ids": set(), "pipeline_value": 0, "won_revenue": 0, "deal_count": 0, "won_count": 0}
        val = int(row.value or 0)
        source_stats[source]["pipeline_value"] += val
        source_stats[source]["deal_count"] += 1
        if row.stage == "closed_won":
            source_stats[source]["won_revenue"] += val
            source_stats[source]["won_count"] += 1

    sources = []
    for source_label, stats in source_stats.items():
        dc = stats["deal_count"]
        wc = stats["won_count"]
        sources.append({
            "source_label": source_label,
            "contact_count": len(stats["contact_ids"]),
            "pipeline_value": stats["pipeline_value"],
            "won_revenue": stats["won_revenue"],
            "win_rate": round(wc / dc * 100, 1) if dc > 0 else 0.0,
        })
    sources.sort(key=lambda x: x["pipeline_value"], reverse=True)
    sources = sources[:10]

    top_source = sources[0]["source_label"] if sources else None

    context_lines = ["Contact source attribution (sorted by pipeline value):"]
    for s in sources:
        context_lines.append(
            f"  {s['source_label']}: {s['contact_count']} contacts, "
            f"${s['pipeline_value']:,} pipeline, ${s['won_revenue']:,} won, "
            f"{s['win_rate']}% win rate"
        )
    context = "\n".join(context_lines)

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            system=_SOURCE_ATTRIBUTION_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg.content[0].text.strip() if msg.content else "{}"
        data = json.loads(raw)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    insight = data.get("insight", _default_insight)
    if not isinstance(insight, str) or not insight.strip():
        insight = _default_insight

    raw_recs = data.get("recommendations", [])
    recommendations = [str(r) for r in (raw_recs if isinstance(raw_recs, list) else []) if str(r).strip()][:3]
    while len(recommendations) < 3:
        recommendations.append(_default_recommendations[len(recommendations)])

    return {
        "sources": sources,
        "top_source": top_source,
        "insight": insight,
        "recommendations": recommendations,
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
    }


# ---------------------------------------------------------------------------
# Phase 16g: AI workspace task completion trends
# ---------------------------------------------------------------------------

_TASK_COMPLETION_TRENDS_SYSTEM = (
    "You are a CRM task analytics expert. Given weekly task completion data, return a JSON object with exactly two keys:\n"
    '  "insight": a single sentence summarising the team\'s task completion patterns and trajectory,\n'
    '  "recommendations": a JSON array of exactly 3 concise, actionable strings to improve task completion rate.\n'
    "Return ONLY valid JSON. No markdown, no explanation."
)


@router.get("/workspaces/{workspace_id}/ai/tasks/completion-trends")
@limiter.limit("5/minute")
async def get_task_completion_trends(
    request: Request,
    workspace_id: uuid.UUID,
    weeks: int = 12,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    weeks = max(1, min(weeks, 52))

    today = datetime.datetime.now(timezone.utc).date()
    this_monday = today - datetime.timedelta(days=today.weekday())
    week_starts = [this_monday - datetime.timedelta(weeks=i) for i in range(weeks - 1, -1, -1)]
    cutoff_date = week_starts[0]
    cutoff = datetime.datetime.combine(cutoff_date, datetime.datetime.min.time()).replace(tzinfo=timezone.utc)

    r1 = await db.execute(
        select(Task).where(
            Task.workspace_id == workspace_id,
            Task.created_at >= cutoff,
        )
    )
    created_tasks = r1.scalars().all()

    r2 = await db.execute(
        select(Task).where(
            Task.workspace_id == workspace_id,
            Task.status == "done",
            Task.updated_at >= cutoff,
        )
    )
    completed_tasks = r2.scalars().all()

    r3 = await db.execute(
        select(Task).where(
            Task.workspace_id == workspace_id,
            Task.due_date.isnot(None),
            Task.due_date >= cutoff_date,
            Task.due_date < today,
            Task.status.notin_(["done", "cancelled"]),
        )
    )
    overdue_tasks = r3.scalars().all()

    def _to_utc(ts: datetime.datetime) -> datetime.datetime:
        return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)

    weeks_data = []
    for ws in week_starts:
        we = ws + datetime.timedelta(weeks=1)
        ws_dt = datetime.datetime.combine(ws, datetime.datetime.min.time()).replace(tzinfo=timezone.utc)
        we_dt = datetime.datetime.combine(we, datetime.datetime.min.time()).replace(tzinfo=timezone.utc)

        created = sum(
            1 for t in created_tasks
            if t.created_at and ws_dt <= _to_utc(t.created_at) < we_dt
        )
        completed = sum(
            1 for t in completed_tasks
            if t.updated_at and ws_dt <= _to_utc(t.updated_at) < we_dt
        )
        overdue = sum(
            1 for t in overdue_tasks
            if t.due_date and ws <= t.due_date < we
        )
        completion_rate = round(completed / created * 100, 1) if created > 0 else 0.0
        weeks_data.append({
            "week_start": ws.isoformat(),
            "created": created,
            "completed": completed,
            "overdue": overdue,
            "completion_rate": completion_rate,
        })

    rates = [w["completion_rate"] for w in weeks_data if w["created"] > 0]
    avg_completion_rate = round(sum(rates) / len(rates), 1) if rates else 0.0

    if len(rates) >= 4:
        mid = len(rates) // 2
        first_half = sum(rates[:mid]) / mid
        second_half = sum(rates[mid:]) / (len(rates) - mid)
        if second_half > first_half + 5:
            trend = "improving"
        elif second_half < first_half - 5:
            trend = "declining"
        else:
            trend = "stable"
    else:
        trend = "stable"

    _default_insight = "Task completion data is being collected — check back once more tasks are tracked."
    _default_recommendations = [
        "Set clear due dates on all tasks to improve accountability.",
        "Review and close overdue tasks weekly to keep the backlog healthy.",
        "Break large tasks into smaller subtasks to increase completion velocity.",
    ]

    if not any(w["created"] > 0 for w in weeks_data):
        return {
            "weeks": weeks_data,
            "avg_completion_rate": 0.0,
            "trend": trend,
            "insight": _default_insight,
            "recommendations": _default_recommendations,
            "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        }

    context = (
        f"Task completion trends over {weeks} weeks:\n"
        f"Average completion rate: {avg_completion_rate}%\n"
        f"Trend: {trend}\n"
        "Weekly breakdown (week_start, created, completed, overdue, completion_rate%):\n"
    )
    for w in weeks_data:
        context += f"  {w['week_start']}: created={w['created']}, completed={w['completed']}, overdue={w['overdue']}, rate={w['completion_rate']}%\n"

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            system=_TASK_COMPLETION_TRENDS_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg.content[0].text.strip() if msg.content else "{}"
        data = json.loads(raw)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    insight = data.get("insight", _default_insight)
    if not isinstance(insight, str) or not insight.strip():
        insight = _default_insight

    raw_recs = data.get("recommendations", [])
    recommendations = [str(r) for r in (raw_recs if isinstance(raw_recs, list) else []) if str(r).strip()][:3]
    while len(recommendations) < 3:
        recommendations.append(_default_recommendations[len(recommendations)])

    return {
        "weeks": weeks_data,
        "avg_completion_rate": avg_completion_rate,
        "trend": trend,
        "insight": insight,
        "recommendations": recommendations,
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
    }


@router.get("/workspaces/{workspace_id}/ai/messages/response-time-benchmark")
@limiter.limit("5/minute")
async def get_message_response_time_benchmark(
    request: Request,
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    # Fetch all messages with connector service, ordered for pairing
    stmt = (
        select(
            Message.sender_email,
            Message.received_at,
            Message.subject,
            Message.connector_id,
            Connector.service,
        )
        .join(Connector, Message.connector_id == Connector.id)
        .where(Message.workspace_id == workspace_id)
        .order_by(Connector.service, Message.connector_id, Message.received_at)
    )
    result = await db.execute(stmt)
    rows = result.all()

    # Group by (service, connector_id, normalized_subject) to identify threads
    threads: dict = defaultdict(list)
    for row in rows:
        normalized_subject = (row.subject or "").lower().replace("re: ", "").replace("fwd: ", "").strip()
        key = (row.service, str(row.connector_id), normalized_subject)
        threads[key].append(row)

    # Compute response lags per service by pairing alternating senders
    service_lags: dict[str, list[float]] = defaultdict(list)
    for (service, _connector_id, _subj), msgs in threads.items():
        if len(msgs) < 2:
            continue
        for i in range(1, len(msgs)):
            prev = msgs[i - 1]
            curr = msgs[i]
            if prev.sender_email and curr.sender_email and prev.sender_email != curr.sender_email:
                if prev.received_at and curr.received_at:
                    delta_h = (curr.received_at - prev.received_at).total_seconds() / 3600
                    if 0 < delta_h < 168:  # exclude outliers > 1 week
                        service_lags[service].append(delta_h)

    def _compute_stats(lags: list[float]) -> dict:
        sorted_lags = sorted(lags)
        n = len(sorted_lags)
        avg = sum(lags) / n
        p50 = sorted_lags[n // 2]
        p90 = sorted_lags[int(n * 0.9)]
        return {
            "avg_hours": round(avg, 1),
            "p50_hours": round(p50, 1),
            "p90_hours": round(p90, 1),
            "message_count": n,
        }

    benchmark = []
    all_lags: list[float] = []
    for service in ["gmail", "slack", "teams"]:
        lags = service_lags.get(service, [])
        if lags:
            stats = _compute_stats(lags)
            stats["service"] = service
            benchmark.append(stats)
            all_lags.extend(lags)

    overall_avg = round(sum(all_lags) / len(all_lags), 1) if all_lags else None

    if overall_avg is None:
        rating = "slow"
    elif overall_avg < 2:
        rating = "excellent"
    elif overall_avg < 8:
        rating = "good"
    elif overall_avg < 24:
        rating = "fair"
    else:
        rating = "slow"

    if not all_lags:
        return {
            "benchmark": [],
            "overall_avg_hours": None,
            "rating": "slow",
            "insight": "No message reply data found. Connect Gmail or Slack to start tracking response times.",
            "recommendations": [
                "Connect a Gmail or Slack connector to begin tracking response times.",
                "Aim to reply to all inbound messages within 4 hours.",
                "Use AI triage to prioritize urgent messages first.",
            ],
            "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        }

    context_lines = [f"Overall avg response time: {overall_avg}h (rating: {rating})"]
    for b in benchmark:
        context_lines.append(
            f"- {b['service'].title()}: avg={b['avg_hours']}h, p50={b['p50_hours']}h, p90={b['p90_hours']}h ({b['message_count']} pairs)"
        )
    context = "\n".join(context_lines)

    client = _anthropic.Anthropic()
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        messages=[{
            "role": "user",
            "content": (
                "Analyze this workspace message response time data and provide a 1-sentence insight and "
                "3 actionable recommendations to improve response times.\n\n"
                f"{context}\n\n"
                'Return JSON: {"insight": "...", "recommendations": ["...", "...", "..."]}'
            ),
        }],
    )

    text = msg.content[0].text.strip()
    try:
        parsed = json.loads(text[text.find("{"):text.rfind("}") + 1])
        insight = parsed.get("insight", "")
        recommendations = parsed.get("recommendations", [])[:3]
    except Exception:
        insight = text[:200]
        recommendations = [
            "Prioritize urgent messages to improve overall response rate.",
            "Set up automated acknowledgment replies to buy processing time.",
            "Review high p90 channels for bottlenecks in the response workflow.",
        ]

    return {
        "benchmark": benchmark,
        "overall_avg_hours": overall_avg,
        "rating": rating,
        "insight": insight,
        "recommendations": recommendations,
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
    }


# ---------------------------------------------------------------------------
# Phase 16i — AI workspace contact engagement benchmark
# ---------------------------------------------------------------------------

@router.get("/workspaces/{workspace_id}/ai/contacts/engagement-benchmark")
@limiter.limit("5/minute")
async def get_contact_engagement_benchmark(
    request: Request,
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=90)

    contacts_result = await db.execute(
        select(Contact.id, Contact.name, Contact.email).where(Contact.workspace_id == workspace_id)
    )
    contacts = contacts_result.all()

    if not contacts:
        return {
            "buckets": [
                {"label": "Low (0–33)", "count": 0, "avg_score": 0},
                {"label": "Medium (34–66)", "count": 0, "avg_score": 0},
                {"label": "High (67–100)", "count": 0, "avg_score": 0},
            ],
            "top_contacts": [],
            "bottom_contacts": [],
            "avg_score": 0,
            "insight": "No contacts found. Add contacts to begin tracking engagement.",
            "recommendations": [
                "Import contacts via CSV or connect a Gmail/Slack connector.",
                "Begin logging notes and tasks for each contact to build engagement history.",
                "Use AI outreach drafts to start meaningful conversations.",
            ],
            "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        }

    contact_ids = [c.id for c in contacts]

    msg_result = await db.execute(
        select(Message.contact_id, func.count(Message.id).label("msg_count"))
        .where(
            Message.workspace_id == workspace_id,
            Message.received_at >= cutoff,
            Message.contact_id.in_(contact_ids),
        )
        .group_by(Message.contact_id)
    )
    msg_counts = {row.contact_id: row.msg_count for row in msg_result.all()}

    note_result = await db.execute(
        select(ContactNote.contact_id, func.count(ContactNote.id).label("note_count"))
        .where(
            ContactNote.workspace_id == workspace_id,
            ContactNote.created_at >= cutoff,
            ContactNote.contact_id.in_(contact_ids),
        )
        .group_by(ContactNote.contact_id)
    )
    note_counts = {row.contact_id: row.note_count for row in note_result.all()}

    task_result = await db.execute(
        select(Task).where(
            Task.workspace_id == workspace_id,
            Task.created_at >= cutoff,
            Task.contact_id.in_(contact_ids),
        )
    )
    all_tasks = task_result.scalars().all()
    task_stats: dict = {}
    for t in all_tasks:
        cid = t.contact_id
        if cid not in task_stats:
            task_stats[cid] = [0, 0]
        task_stats[cid][0] += 1
        if t.status == "done":
            task_stats[cid][1] += 1

    scored = []
    for c in contacts:
        msg_count = msg_counts.get(c.id, 0)
        note_count = note_counts.get(c.id, 0)
        total_tasks, done_tasks = task_stats.get(c.id, [0, 0])
        messages_score = min(40, msg_count * 8)
        notes_score = min(30, note_count * 10)
        tasks_score = round(30 * done_tasks / total_tasks) if total_tasks > 0 else 0
        score = messages_score + notes_score + tasks_score
        scored.append({"id": str(c.id), "name": c.name, "email": c.email, "score": score})

    low = [s for s in scored if s["score"] <= 33]
    medium = [s for s in scored if 34 <= s["score"] <= 66]
    high = [s for s in scored if s["score"] >= 67]

    def _bucket_avg(group: list) -> int:
        return round(sum(s["score"] for s in group) / len(group)) if group else 0

    buckets = [
        {"label": "Low (0–33)", "count": len(low), "avg_score": _bucket_avg(low)},
        {"label": "Medium (34–66)", "count": len(medium), "avg_score": _bucket_avg(medium)},
        {"label": "High (67–100)", "count": len(high), "avg_score": _bucket_avg(high)},
    ]
    avg_score = round(sum(s["score"] for s in scored) / len(scored)) if scored else 0

    sorted_by_score = sorted(scored, key=lambda x: x["score"], reverse=True)
    top_contacts = [{"id": s["id"], "name": s["name"], "email": s["email"], "score": s["score"]} for s in sorted_by_score[:3]]
    bottom_contacts = [{"id": s["id"], "name": s["name"], "email": s["email"], "score": s["score"]} for s in sorted_by_score[-3:]]
    bottom_contacts = sorted(bottom_contacts, key=lambda x: x["score"])

    context = (
        f"Workspace has {len(scored)} contacts. Overall avg engagement score: {avg_score}/100.\n"
        f"Low engagement (0–33): {len(low)} contacts. "
        f"Medium (34–66): {len(medium)}. High (67–100): {len(high)}.\n"
    )
    if top_contacts:
        context += f"Most engaged: {top_contacts[0]['name']} (score {top_contacts[0]['score']}).\n"
    if bottom_contacts:
        context += f"Least engaged: {bottom_contacts[0]['name']} (score {bottom_contacts[0]['score']}).\n"

    client = _anthropic.Anthropic()
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        messages=[{
            "role": "user",
            "content": (
                "Analyze this workspace contact engagement benchmark data and provide a 1-sentence insight "
                "and 3 actionable recommendations to improve overall engagement.\n\n"
                f"{context}\n\n"
                'Return JSON: {"insight": "...", "recommendations": ["...", "...", "..."]}'
            ),
        }],
    )

    text = msg.content[0].text.strip()
    try:
        parsed = json.loads(text[text.find("{"):text.rfind("}") + 1])
        insight = parsed.get("insight", "")
        recommendations = parsed.get("recommendations", [])[:3]
    except Exception:
        insight = text[:200]
        recommendations = [
            "Focus outreach on low-engagement contacts to bring them into active conversation.",
            "Schedule regular check-ins with your top contacts to maintain strong engagement.",
            "Use AI task suggestions to create follow-up actions for each contact.",
        ]

    return {
        "buckets": buckets,
        "top_contacts": top_contacts,
        "bottom_contacts": bottom_contacts,
        "avg_score": avg_score,
        "insight": insight,
        "recommendations": recommendations,
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
    }


# Phase 16j — AI workspace deal negotiation readiness report
# ---------------------------------------------------------------------------

_NEGOT_PROMPT = """You are Nova, a CRM AI sales coach. Given a list of open deals in the proposal or negotiation stage, evaluate each deal's negotiation readiness and produce a 1-sentence workspace-level summary.

Deal context:
{deal_context}

For each deal, determine:
- readiness: "ready" (strong health, no critical blockers), "needs_work" (some issues but fixable), or "not_ready" (critical blockers)
- blockers: list of 1-3 short phrases for what's blocking (empty if ready)
- next_steps: list of 1-2 short specific actions

Return JSON:
{{
  "summary": "one sentence workspace-level summary of negotiation readiness",
  "deals": [
    {{
      "id": "<deal_id>",
      "readiness": "ready|needs_work|not_ready",
      "blockers": ["..."],
      "next_steps": ["..."]
    }}
  ]
}}"""


@router.get("/workspaces/{workspace_id}/ai/deals/negotiation-readiness")
@limiter.limit("5/minute")
async def get_deals_negotiation_readiness(
    request: Request,
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    now = datetime.datetime.utcnow()

    deals_result = await db.execute(
        select(Deal).where(
            Deal.workspace_id == workspace_id,
            Deal.stage.in_(["proposal", "negotiation"]),
        ).order_by(Deal.value.desc())
    )
    deals = deals_result.scalars().all()

    if not deals:
        return {
            "total_deals": 0,
            "ready_count": 0,
            "not_ready_count": 0,
            "deals": [],
            "summary": "No deals are currently in proposal or negotiation stages.",
            "generated_at": now.isoformat() + "Z",
        }

    deal_rows = []
    for d in deals:
        competitors = d.competitors if isinstance(d.competitors, list) else []
        stage_changed = d.stage_changed_at or d.created_at or now
        days_in_stage = max(0, (now - stage_changed).days) if stage_changed else 0
        next_action_date = d.next_action_date
        overdue_days = 0
        if next_action_date:
            import datetime as _dt
            try:
                nad = _dt.date.fromisoformat(str(next_action_date))
                delta = (now.date() - nad).days
                overdue_days = max(0, delta)
            except Exception:
                pass
        deal_rows.append({
            "id": str(d.id),
            "title": d.title or "Untitled",
            "company": d.company or "",
            "stage": d.stage,
            "health": d.health_score or 0,
            "competitors": len(competitors),
            "days_in_stage": days_in_stage,
            "overdue_days": overdue_days,
        })

    deal_context = "\n".join(
        f"- Deal '{r['title']}' ({r['company']}): stage={r['stage']}, health={r['health']}/100, "
        f"competitors={r['competitors']}, days_in_stage={r['days_in_stage']}, "
        f"action_overdue_by={r['overdue_days']}d [id={r['id']}]"
        for r in deal_rows
    )

    client = _anthropic.Anthropic()
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=600,
        messages=[{
            "role": "user",
            "content": _NEGOT_PROMPT.format(deal_context=deal_context),
        }],
    )

    text = msg.content[0].text.strip()
    try:
        parsed = json.loads(text[text.find("{"):text.rfind("}") + 1])
        summary = parsed.get("summary", "")
        ai_deals = {d["id"]: d for d in parsed.get("deals", []) if "id" in d}
    except Exception:
        summary = "Negotiation readiness analysis complete."
        ai_deals = {}

    result_deals = []
    for r in deal_rows:
        ai = ai_deals.get(r["id"], {})
        readiness = ai.get("readiness", "needs_work")
        if readiness not in {"ready", "needs_work", "not_ready"}:
            readiness = "needs_work"
        result_deals.append({
            "id": r["id"],
            "title": r["title"],
            "company": r["company"],
            "stage": r["stage"],
            "readiness": readiness,
            "blockers": ai.get("blockers", [])[:3],
            "next_steps": ai.get("next_steps", [])[:2],
        })

    ready_count = sum(1 for d in result_deals if d["readiness"] == "ready")
    not_ready_count = sum(1 for d in result_deals if d["readiness"] == "not_ready")

    return {
        "total_deals": len(result_deals),
        "ready_count": ready_count,
        "not_ready_count": not_ready_count,
        "deals": result_deals,
        "summary": summary,
        "generated_at": now.isoformat() + "Z",
    }


# ---------------------------------------------------------------------------
# Phase 16k — AI workspace message source reliability report
# ---------------------------------------------------------------------------

_MSG_SRC_RELIABILITY_PROMPT = """\
You are an AI assistant analyzing message source reliability for a CRM workspace.

Message source statistics:
{source_context}

Return JSON only:
{{
    "insight": "one concise sentence about reliability patterns across sources",
    "recommendations": ["specific action 1", "specific action 2", "specific action 3"]
}}
"""


@router.get("/workspaces/{workspace_id}/ai/messages/source-reliability")
@limiter.limit("5/minute")
async def get_message_source_reliability(
    request: Request,
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    now = datetime.datetime.utcnow()

    # 12-week Mon-Sun calendar buckets
    days_since_monday = now.weekday()
    current_monday = (now - datetime.timedelta(days=days_since_monday)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    week_starts = [current_monday - datetime.timedelta(weeks=i) for i in range(11, -1, -1)]
    twelve_weeks_ago = week_starts[0]

    # Query 1: total message count per service
    total_result = await db.execute(
        select(Connector.service, func.count(Message.id).label("total"))
        .join(Connector, Message.connector_id == Connector.id)
        .where(Message.workspace_id == workspace_id)
        .group_by(Connector.service)
    )
    total_by_service: dict = {row.service: row.total for row in total_result.all()}

    if not total_by_service:
        return {
            "sources": [],
            "most_reliable_source": None,
            "insight": "No messages ingested yet. Connect a Gmail or Slack account to begin.",
            "recommendations": [
                "Connect a Gmail connector to start ingesting emails.",
                "Connect a Slack connector to monitor team communications.",
                "Configure webhook push notifications for real-time message delivery.",
            ],
            "generated_at": now.isoformat() + "Z",
        }

    # Query 2: processed message count per service
    processed_result = await db.execute(
        select(Connector.service, func.count(Message.id).label("processed"))
        .join(Connector, Message.connector_id == Connector.id)
        .where(Message.workspace_id == workspace_id, Message.processed == True)
        .group_by(Connector.service)
    )
    processed_by_service: dict = {row.service: row.processed for row in processed_result.all()}

    # Query 3: weekly message timestamps for last 12 weeks
    weekly_result = await db.execute(
        select(Connector.service, Message.received_at)
        .join(Connector, Message.connector_id == Connector.id)
        .where(
            Message.workspace_id == workspace_id,
            Message.received_at >= twelve_weeks_ago,
        )
    )
    weekly_rows = weekly_result.all()

    # Build per-service weekly trend (12 buckets, oldest-first)
    service_weekly: dict = {svc: [0] * 12 for svc in total_by_service}
    for service, received_at in weekly_rows:
        if received_at is None or service not in service_weekly:
            continue
        ts = received_at.replace(tzinfo=None) if received_at.tzinfo else received_at
        for i, ws in enumerate(week_starts):
            if ws <= ts < ws + datetime.timedelta(weeks=1):
                service_weekly[service][i] += 1
                break

    # Build sources list sorted by total desc
    sources = []
    for svc, total in sorted(total_by_service.items(), key=lambda x: x[1], reverse=True):
        processed = processed_by_service.get(svc, 0)
        rate = round(processed / total * 100, 1) if total > 0 else 0.0
        sources.append({
            "service": svc,
            "total_messages": total,
            "processed_rate": rate,
            "weekly_trend": service_weekly.get(svc, [0] * 12),
        })

    most_reliable_source = (
        max(sources, key=lambda s: s["processed_rate"])["service"] if sources else None
    )

    source_context = "\n".join(
        f"- {s['service'].capitalize()}: {s['total_messages']} total, {s['processed_rate']}% processing rate"
        for s in sources
    )

    client = _anthropic.Anthropic()
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        messages=[{
            "role": "user",
            "content": _MSG_SRC_RELIABILITY_PROMPT.format(source_context=source_context),
        }],
    )

    text = msg.content[0].text.strip()
    try:
        parsed = json.loads(text[text.find("{"):text.rfind("}") + 1])
        insight = parsed.get("insight", "Message sources are performing normally.")
        recommendations = parsed.get("recommendations", [])[:3]
    except Exception:
        insight = "Message sources are performing normally."
        recommendations = []

    while len(recommendations) < 3:
        recommendations.append("Monitor processing rates regularly to ensure timely message delivery.")

    return {
        "sources": sources,
        "most_reliable_source": most_reliable_source,
        "insight": insight,
        "recommendations": recommendations,
        "generated_at": now.isoformat() + "Z",
    }


# ---------------------------------------------------------------------------
# Phase 16l — AI workspace deal stage transition analysis
# ---------------------------------------------------------------------------

_STAGE_TRANSITION_ANALYSIS_PROMPT = (
    "You are a CRM pipeline analyst. Given deal stage transition data for the last 90 days, "
    "provide a concise insight and 3 actionable recommendations to improve pipeline velocity.\n\n"
    "Stage Transitions:\n{transition_context}\n\n"
    "Respond with JSON only — no markdown, no preamble:\n"
    '{{"insight": "one sentence", "recommendations": ["rec1", "rec2", "rec3"]}}'
)


@router.get("/workspaces/{workspace_id}/ai/deals/stage-transition-analysis")
@limiter.limit("5/minute")
async def get_stage_transition_analysis(
    request: Request,
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    import re as _re

    now = datetime.datetime.now(datetime.timezone.utc)
    cutoff = now - datetime.timedelta(days=90)

    _valid_stages = {"discovery", "qualified", "proposal", "negotiation", "closed_won", "closed_lost"}
    _stage_re = _re.compile(r"→\s*([a-z_]+)")
    _title_re = _re.compile(r"Deal '([^']+)'")

    result = await db.execute(
        select(ActivityEvent.description, ActivityEvent.created_at)
        .where(
            ActivityEvent.workspace_id == workspace_id,
            ActivityEvent.type == "deal_moved",
            ActivityEvent.created_at >= cutoff,
        )
        .order_by(ActivityEvent.created_at.asc())
    )
    rows = result.all()

    # Group events by deal title and parse destination stage from description
    deal_events: dict[str, list[tuple[str, datetime.datetime]]] = defaultdict(list)
    for desc, created_at in rows:
        if not desc:
            continue
        title_m = _title_re.search(desc)
        stage_m = _stage_re.search(desc)
        if title_m and stage_m and stage_m.group(1) in _valid_stages:
            title = title_m.group(1)
            stage = stage_m.group(1)
            ts = created_at.replace(tzinfo=datetime.timezone.utc) if not created_at.tzinfo else created_at
            deal_events[title].append((stage, ts))

    # Compute (from_stage → to_stage) transition counts and avg days
    from_to_days: dict[tuple[str, str], list[float]] = defaultdict(list)
    for events_list in deal_events.values():
        for i in range(1, len(events_list)):
            prev_stage, prev_ts = events_list[i - 1]
            curr_stage, curr_ts = events_list[i]
            if prev_stage != curr_stage:
                days = (curr_ts - prev_ts).total_seconds() / 86400.0
                from_to_days[(prev_stage, curr_stage)].append(days)

    if not from_to_days:
        return {
            "transitions": [],
            "bottleneck_stage": None,
            "fastest_transition": None,
            "insight": "No stage transition data available for the last 90 days.",
            "recommendations": [
                "Start recording deal stage movements to see transition analysis.",
                "Ensure deals are updated regularly to track pipeline velocity.",
                "Use the pipeline view to move deals through stages and build history.",
            ],
            "generated_at": now.isoformat() + "Z",
        }

    transitions = []
    for (from_s, to_s), days_list in sorted(from_to_days.items(), key=lambda x: -len(x[1])):
        avg_days = round(sum(days_list) / len(days_list), 1)
        transitions.append({
            "from_stage": from_s,
            "to_stage": to_s,
            "count": len(days_list),
            "avg_days": avg_days,
        })

    bottleneck = max(transitions, key=lambda t: t["avg_days"])
    bottleneck_stage = bottleneck["from_stage"]
    fastest = min(transitions, key=lambda t: t["avg_days"])
    fastest_transition = f"{fastest['from_stage']} → {fastest['to_stage']}"

    transition_context = "\n".join(
        f"- {t['from_stage']} → {t['to_stage']}: {t['count']} transition(s), avg {t['avg_days']} days"
        for t in transitions[:10]
    )

    client = _anthropic.Anthropic()
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        messages=[{
            "role": "user",
            "content": _STAGE_TRANSITION_ANALYSIS_PROMPT.format(transition_context=transition_context),
        }],
    )

    text = msg.content[0].text.strip()
    try:
        parsed = json.loads(text[text.find("{"):text.rfind("}") + 1])
        insight = parsed.get("insight", "Stage transitions are within normal ranges.")
        recommendations = parsed.get("recommendations", [])[:3]
    except Exception:
        insight = "Stage transitions are within normal ranges."
        recommendations = []

    while len(recommendations) < 3:
        recommendations.append("Review stage transition timing to optimize pipeline velocity.")

    return {
        "transitions": transitions,
        "bottleneck_stage": bottleneck_stage,
        "fastest_transition": fastest_transition,
        "insight": insight,
        "recommendations": recommendations,
        "generated_at": now.isoformat() + "Z",
    }


# ---------------------------------------------------------------------------
# Phase 16m: AI workspace revenue trend analysis
# ---------------------------------------------------------------------------

_REVENUE_TREND_PROMPT = (
    "You are a CRM revenue analyst. Given 12 months of closed-won revenue data, return a JSON object "
    "with exactly two keys:\n"
    "- \"insight\": one concise sentence summarising the most important pattern in the revenue trend.\n"
    "- \"recommendations\": an array of exactly 3 short, specific, actionable recommendations.\n"
    "Return only raw JSON, no markdown.\n\n"
    "Revenue data (YYYY-MM → revenue $, deal_count):\n{monthly_context}"
)


@router.get("/workspaces/{workspace_id}/ai/revenue/trend-analysis")
@limiter.limit("5/minute")
async def get_revenue_trend_analysis(
    request: Request,
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    now = datetime.datetime.now(timezone.utc)

    # Query closed_won deals for the last 12 months
    cutoff = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    for _ in range(11):
        if cutoff.month == 1:
            cutoff = cutoff.replace(year=cutoff.year - 1, month=12)
        else:
            cutoff = cutoff.replace(month=cutoff.month - 1)

    result = await db.execute(
        select(Deal.value, Deal.stage_changed_at, Deal.created_at)
        .where(
            Deal.workspace_id == workspace_id,
            Deal.stage == "closed_won",
        )
    )
    rows = result.all()

    # Build 12-month buckets (YYYY-MM)
    month_buckets: dict[str, dict] = {}
    ref = now
    for i in range(11, -1, -1):
        if ref.month - i <= 0:
            y = ref.year - 1
            m = ref.month - i + 12
        else:
            y = ref.year
            m = ref.month - i
        key = f"{y}-{m:02d}"
        month_buckets[key] = {"month": key, "revenue": 0, "deal_count": 0, "avg_deal_size": 0}

    for value, stage_changed_at, created_at in rows:
        close_dt = stage_changed_at or created_at
        if close_dt is None:
            continue
        if not close_dt.tzinfo:
            close_dt = close_dt.replace(tzinfo=timezone.utc)
        key = f"{close_dt.year}-{close_dt.month:02d}"
        if key in month_buckets:
            month_buckets[key]["revenue"] += float(value or 0)
            month_buckets[key]["deal_count"] += 1

    monthly_trend = list(month_buckets.values())
    for row in monthly_trend:
        if row["deal_count"] > 0:
            row["avg_deal_size"] = round(row["revenue"] / row["deal_count"])
        row["revenue"] = round(row["revenue"])

    total_revenue = sum(r["revenue"] for r in monthly_trend)
    if total_revenue == 0:
        return {
            "monthly_trend": monthly_trend,
            "growth_rate": None,
            "best_month": None,
            "trend_direction": "stable",
            "insight": "No closed-won revenue data available for the last 12 months.",
            "recommendations": [
                "Close your first deals to start tracking revenue trends.",
                "Set expected close dates on open deals to forecast upcoming revenue.",
                "Review pipeline health to identify deals ready to close.",
            ],
            "generated_at": now.isoformat(),
        }

    # Compute growth rate and trend direction
    first_half = sum(r["revenue"] for r in monthly_trend[:6])
    second_half = sum(r["revenue"] for r in monthly_trend[6:])
    if first_half > 0:
        half_growth = (second_half - first_half) / first_half
    else:
        half_growth = 1.0 if second_half > 0 else 0.0

    if half_growth > 0.3:
        trend_direction = "accelerating"
    elif half_growth > 0.05:
        trend_direction = "growing"
    elif half_growth > -0.1:
        trend_direction = "stable"
    else:
        trend_direction = "declining"

    nonzero = [r for r in monthly_trend if r["revenue"] > 0]
    if len(nonzero) >= 2:
        growth_rate = round(half_growth * 100, 1)
    else:
        growth_rate = None

    best = max(monthly_trend, key=lambda r: r["revenue"])
    best_month = best["month"] if best["revenue"] > 0 else None

    monthly_context = "\n".join(
        f"- {r['month']}: ${r['revenue']:,} ({r['deal_count']} deal{'s' if r['deal_count'] != 1 else ''})"
        for r in monthly_trend
    )

    client = _anthropic.Anthropic()
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        messages=[{
            "role": "user",
            "content": _REVENUE_TREND_PROMPT.format(monthly_context=monthly_context),
        }],
    )

    text = msg.content[0].text.strip()
    try:
        parsed = json.loads(text[text.find("{"):text.rfind("}") + 1])
        insight = parsed.get("insight", "Revenue trends are within normal ranges.")
        recommendations = parsed.get("recommendations", [])[:3]
    except Exception:
        insight = "Revenue trends are within normal ranges."
        recommendations = []

    while len(recommendations) < 3:
        recommendations.append("Review closed-won deals to identify patterns driving revenue.")

    return {
        "monthly_trend": monthly_trend,
        "growth_rate": growth_rate,
        "best_month": best_month,
        "trend_direction": trend_direction,
        "insight": insight,
        "recommendations": recommendations,
        "generated_at": now.isoformat(),
    }


# ── Contact Inactivity Risk ───────────────────────────────────────────────────

_INACTIVITY_RISK_SYSTEM = """\
You are a CRM analyst specialising in contact re-engagement. Given contact inactivity statistics, \
write a concise 2-sentence insight and 3 prioritised recommendations. \
Reply ONLY with a valid JSON object: \
{"insight": "<2-sentence analysis>", "recommendations": ["...", "...", "..."]} \
Exactly 3 recommendations. No markdown. Pure JSON only."""


@router.get("/workspaces/{workspace_id}/ai/contacts/inactivity-risk")
@limiter.limit("5/minute")
async def get_contact_inactivity_risk(
    request: Request,
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    now = datetime.datetime.utcnow()

    # All customer/prospect contacts in workspace
    contacts_result = await db.execute(
        select(Contact.id, Contact.name, Contact.email, Contact.company)
        .where(
            Contact.workspace_id == workspace_id,
            Contact.status.in_(["customer", "prospect"]),
        )
    )
    contacts = contacts_result.all()
    total_contacts = len(contacts)

    if total_contacts == 0:
        return {
            "critical_count": 0,
            "high_risk_count": 0,
            "watch_count": 0,
            "total_contacts": 0,
            "contacts_by_bucket": [],
            "insight": "No customer or prospect contacts exist in this workspace yet. Add contacts to track inactivity.",
            "recommendations": [
                "Import your existing contacts and set their status to prospect or customer.",
                "Connect your email to automatically track message activity.",
                "Add notes after meetings to build engagement history.",
            ],
            "generated_at": now.isoformat() + "Z",
        }

    contact_ids = [c[0] for c in contacts]
    contact_map = {
        c[0]: {"id": str(c[0]), "name": c[1] or "", "email": c[2] or "", "company": c[3] or ""}
        for c in contacts
    }

    # Last message touch per contact
    msg_result = await db.execute(
        select(Message.contact_id, func.max(Message.received_at).label("last_msg"))
        .where(Message.contact_id.in_(contact_ids))
        .group_by(Message.contact_id)
    )
    msg_touches = {row[0]: row[1] for row in msg_result.all()}

    # Last note touch per contact
    note_result = await db.execute(
        select(ContactNote.contact_id, func.max(ContactNote.created_at).label("last_note"))
        .where(ContactNote.contact_id.in_(contact_ids))
        .group_by(ContactNote.contact_id)
    )
    note_touches = {row[0]: row[1] for row in note_result.all()}

    critical_contacts: list[dict] = []
    high_risk_contacts: list[dict] = []
    watch_contacts: list[dict] = []

    for cid in contact_ids:
        mt = msg_touches.get(cid)
        nt = note_touches.get(cid)
        candidates = [t for t in (mt, nt) if t is not None]
        if not candidates:
            days_since = 999
        else:
            last = max(candidates)
            if hasattr(last, "tzinfo") and last.tzinfo is not None:
                last = last.replace(tzinfo=None)
            days_since = (now - last).days

        entry = {**contact_map[cid], "days_since_touch": days_since}
        if days_since > 60:
            critical_contacts.append(entry)
        elif days_since > 30:
            high_risk_contacts.append(entry)
        elif days_since > 14:
            watch_contacts.append(entry)

    critical_count = len(critical_contacts)
    high_risk_count = len(high_risk_contacts)
    watch_count = len(watch_contacts)

    contacts_by_bucket: list[dict] = []
    if critical_contacts:
        contacts_by_bucket.append({"bucket": "critical", "contacts": critical_contacts})
    if high_risk_contacts:
        contacts_by_bucket.append({"bucket": "high_risk", "contacts": high_risk_contacts})
    if watch_contacts:
        contacts_by_bucket.append({"bucket": "watch", "contacts": watch_contacts})

    if critical_count == 0 and high_risk_count == 0 and watch_count == 0:
        return {
            "critical_count": 0,
            "high_risk_count": 0,
            "watch_count": 0,
            "total_contacts": total_contacts,
            "contacts_by_bucket": [],
            "insight": "All contacts have been recently engaged — excellent relationship health.",
            "recommendations": [
                "Maintain the current engagement cadence to keep contacts active.",
                "Set up recurring reminders to check in every 2 weeks.",
                "Review contact goals quarterly to ensure alignment.",
            ],
            "generated_at": now.isoformat() + "Z",
        }

    context = (
        f"Contact inactivity risk snapshot:\n"
        f"- Total customer/prospect contacts: {total_contacts}\n"
        f"- Critical (>60 days without any contact): {critical_count}\n"
        f"- High risk (30–60 days silent): {high_risk_count}\n"
        f"- Watch (14–30 days silent): {watch_count}\n"
    )

    _default_insight = (
        f"{critical_count} contact{'s are' if critical_count != 1 else ' is'} critically overdue for outreach "
        f"(60+ days silent), with {high_risk_count} more at high risk of going dark."
    )
    _default_recs = [
        f"Immediately reach out to the {critical_count} critically inactive contact{'s' if critical_count != 1 else ''}.",
        f"Schedule follow-up calls for the {high_risk_count} high-risk contact{'s' if high_risk_count != 1 else ''} this week.",
        "Set up automated email sequences to maintain a consistent 2-week engagement cadence.",
    ]

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            system=_INACTIVITY_RISK_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg.content[0].text.strip() if msg.content else "{}"
        data_json = json.loads(raw)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    insight = data_json.get("insight", _default_insight)
    if not isinstance(insight, str) or not insight.strip():
        insight = _default_insight

    raw_recs = data_json.get("recommendations", [])
    recommendations = [str(r) for r in (raw_recs if isinstance(raw_recs, list) else [])[:3]]
    while len(recommendations) < 3:
        recommendations.append(_default_recs[len(recommendations) % 3])

    return {
        "critical_count": critical_count,
        "high_risk_count": high_risk_count,
        "watch_count": watch_count,
        "total_contacts": total_contacts,
        "contacts_by_bucket": contacts_by_bucket,
        "insight": insight,
        "recommendations": recommendations,
        "generated_at": now.isoformat() + "Z",
    }


# ---------------------------------------------------------------------------
# Phase 16o — AI workspace deal pipeline momentum snapshot
# ---------------------------------------------------------------------------

_PIPELINE_MOMENTUM_SYSTEM = (
    "You are a CRM sales analytics expert. Analyse the pipeline momentum data "
    "and return a JSON object with exactly these keys:\n"
    "- highlights: list of 3 short positive observations about pipeline momentum\n"
    "- warnings: list of 3 short risk signals or concerns\n"
    "Return only valid JSON, no markdown."
)


@router.get("/workspaces/{workspace_id}/ai/deals/pipeline-momentum")
@limiter.limit("5/minute")
async def get_deals_pipeline_momentum(
    request: Request,
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    now = datetime.datetime.utcnow()
    cutoff_14d = now - datetime.timedelta(days=14)

    # Query 1: open deal count, at-risk count (health < 50), avg health
    deals_result = await db.execute(
        select(Deal.id, Deal.health_score, Deal.created_at, Deal.stage)
        .where(
            Deal.workspace_id == workspace_id,
            Deal.stage.notin_(["closed_won", "closed_lost"]),
        )
    )
    open_deals = deals_result.all()

    # Query 2: stage moves in last 14 days from activity_events
    moves_result = await db.execute(
        select(func.count(ActivityEvent.id))
        .where(
            ActivityEvent.workspace_id == workspace_id,
            ActivityEvent.type == "deal_moved",
            ActivityEvent.created_at >= cutoff_14d,
        )
    )
    stage_moves_14d = moves_result.scalar() or 0

    total_open = len(open_deals)
    new_deals_14d = sum(
        1 for d in open_deals
        if d.created_at and (
            (d.created_at.replace(tzinfo=None) if d.created_at.tzinfo else d.created_at) >= cutoff_14d
        )
    )
    at_risk_count = sum(1 for d in open_deals if (d.health_score or 0) < 50)
    avg_health = (
        sum((d.health_score or 0) for d in open_deals) / total_open
        if total_open > 0 else 0
    )

    # Momentum score: 0-100
    # Components: stage_moves (0-40), new deals (0-30), health (0-30)
    moves_score = min(40, stage_moves_14d * 4)
    new_deals_score = min(30, new_deals_14d * 5)
    health_score_comp = int(avg_health * 0.3)
    momentum_score = min(100, moves_score + new_deals_score + health_score_comp)

    if momentum_score >= 70:
        momentum_rating = "accelerating"
    elif momentum_score >= 45:
        momentum_rating = "steady"
    elif momentum_score >= 20:
        momentum_rating = "stalling"
    else:
        momentum_rating = "declining"

    if total_open == 0:
        return {
            "momentum_score": 0,
            "momentum_rating": "declining",
            "new_deals_14d": 0,
            "stage_moves_14d": 0,
            "at_risk_count": 0,
            "highlights": [
                "Pipeline is empty — add deals to start tracking momentum.",
                "Connect your CRM data sources to enable momentum tracking.",
                "Create your first deal to begin building pipeline velocity.",
            ],
            "warnings": [
                "No open deals in the pipeline.",
                "Pipeline momentum cannot be calculated without active deals.",
                "Revenue risk is high with no deals in progress.",
            ],
            "generated_at": now.isoformat() + "Z",
        }

    context = (
        f"Open deals: {total_open}\n"
        f"New deals in last 14 days: {new_deals_14d}\n"
        f"Stage moves in last 14 days: {stage_moves_14d}\n"
        f"At-risk deals (health < 50): {at_risk_count}\n"
        f"Average deal health: {round(avg_health, 1)}\n"
        f"Momentum score: {momentum_score}/100 ({momentum_rating})\n"
    )

    _default_highlights = [
        f"Pipeline has {total_open} active deal{'s' if total_open != 1 else ''}.",
        f"{stage_moves_14d} stage move{'s' if stage_moves_14d != 1 else ''} recorded in the last 14 days.",
        f"{new_deals_14d} new deal{'s' if new_deals_14d != 1 else ''} entered the pipeline this fortnight.",
    ]
    _default_warnings = [
        f"{at_risk_count} deal{'s' if at_risk_count != 1 else ''} flagged as at-risk (health < 50).",
        "Review stalled deals to re-activate pipeline movement.",
        "Monitor close dates to avoid revenue forecast slippage.",
    ]

    try:
        client = _anthropic.Anthropic()
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            system=_PIPELINE_MOMENTUM_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg.content[0].text.strip() if msg.content else "{}"
        data_json = json.loads(raw)
        highlights = [str(h) for h in (data_json.get("highlights") or [])[:3]]
        warnings = [str(w) for w in (data_json.get("warnings") or [])[:3]]
    except Exception:
        highlights = []
        warnings = []

    while len(highlights) < 3:
        highlights.append(_default_highlights[len(highlights) % 3])
    while len(warnings) < 3:
        warnings.append(_default_warnings[len(warnings) % 3])

    return {
        "momentum_score": momentum_score,
        "momentum_rating": momentum_rating,
        "new_deals_14d": new_deals_14d,
        "stage_moves_14d": stage_moves_14d,
        "at_risk_count": at_risk_count,
        "highlights": highlights,
        "warnings": warnings,
        "generated_at": now.isoformat() + "Z",
    }


# Phase 16p — AI workspace deal age risk report
# ---------------------------------------------------------------------------

_DEAL_AGE_RISK_PROMPT = """You are Nova, a CRM AI sales analyst. Given a deal age risk report, provide a 1-sentence insight and 3 actionable recommendations to reduce deal aging risk.

Deal age context:
{context}

Return JSON:
{{
  "insight": "one sentence summarising the key deal aging risk finding",
  "recommendations": ["action 1", "action 2", "action 3"]
}}"""


@router.get("/workspaces/{workspace_id}/ai/deals/age-risk")
@limiter.limit("5/minute")
async def get_deals_age_risk(
    request: Request,
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    now = datetime.datetime.now(timezone.utc)
    open_stages = ["discovery", "qualified", "proposal", "negotiation"]

    # Query open deals
    open_result = await db.execute(
        select(Deal.id, Deal.title, Deal.stage, Deal.created_at)
        .where(
            Deal.workspace_id == workspace_id,
            Deal.stage.in_(open_stages),
        )
    )
    open_deals = open_result.all()

    if not open_deals:
        return {
            "overdue_count": 0,
            "at_risk_count": 0,
            "on_track_count": 0,
            "total_open_deals": 0,
            "deals": [],
            "insight": "No open deals found. Add deals to begin tracking age risk.",
            "recommendations": [
                "Create your first deals and set expected close dates to enable age tracking.",
                "Import historical deal data to establish per-stage time benchmarks.",
                "Use the pipeline view to quickly add new deals from your prospect list.",
            ],
            "generated_at": now.isoformat(),
        }

    # Compute median days-to-close per stage from closed_won deals
    closed_result = await db.execute(
        select(Deal.stage, Deal.created_at, Deal.stage_changed_at)
        .where(
            Deal.workspace_id == workspace_id,
            Deal.stage == "closed_won",
        )
    )
    closed_rows = closed_result.all()

    # Build stage cycle-time benchmarks from closed deals
    # Use precursor stage as proxy: discovery→qualified→proposal→negotiation→closed
    stage_order = ["discovery", "qualified", "proposal", "negotiation", "closed_won"]
    stage_defaults = {
        "discovery": 14, "qualified": 21, "proposal": 30, "negotiation": 45,
    }

    # Compute days from created_at to stage_changed_at for closed deals
    closed_cycle_days: list[float] = []
    for row in closed_rows:
        if row.created_at and row.stage_changed_at:
            ca = row.created_at.replace(tzinfo=timezone.utc) if not row.created_at.tzinfo else row.created_at
            sa = row.stage_changed_at.replace(tzinfo=timezone.utc) if not row.stage_changed_at.tzinfo else row.stage_changed_at
            days = (sa - ca).total_seconds() / 86400
            if days > 0:
                closed_cycle_days.append(days)

    # Median overall cycle time — use as scaling reference
    if closed_cycle_days:
        closed_cycle_days.sort()
        n = len(closed_cycle_days)
        median_cycle = closed_cycle_days[n // 2]
    else:
        median_cycle = None  # fall back to defaults

    # Classify each open deal
    overdue_deals = []
    at_risk_deals = []
    on_track_deals = []

    for d in open_deals:
        stage = d.stage
        expected = stage_defaults.get(stage, 21)
        if median_cycle is not None:
            # Scale expected by ratio of median cycle vs sum of defaults up to this stage
            stage_idx = stage_order.index(stage) if stage in stage_order else 1
            default_until = sum(list(stage_defaults.values())[:stage_idx + 1])
            scale = median_cycle / max(sum(stage_defaults.values()), 1)
            expected = max(7, round(expected * scale))

        created = d.created_at
        if created and not created.tzinfo:
            created = created.replace(tzinfo=timezone.utc)
        days_open = (now - created).days if created else 0

        entry = {
            "id": str(d.id),
            "title": d.title,
            "stage": stage,
            "days_open": days_open,
            "expected_days": expected,
            "risk_level": "on_track",
        }

        if days_open > expected * 2:
            entry["risk_level"] = "overdue"
            overdue_deals.append(entry)
        elif days_open > expected * 1.5:
            entry["risk_level"] = "at_risk"
            at_risk_deals.append(entry)
        else:
            on_track_deals.append(entry)

    risk_order = {"overdue": 0, "at_risk": 1, "on_track": 2}
    all_deals = sorted(
        overdue_deals + at_risk_deals + on_track_deals,
        key=lambda x: (risk_order[x["risk_level"]], -x["days_open"]),
    )

    context = (
        f"Total open deals: {len(open_deals)}.\n"
        f"Overdue (>2× expected): {len(overdue_deals)} deals.\n"
        f"At-risk (>1.5× expected): {len(at_risk_deals)} deals.\n"
        f"On-track: {len(on_track_deals)} deals.\n"
    )
    if overdue_deals:
        oldest = max(overdue_deals, key=lambda x: x["days_open"])
        context += f"Most overdue: '{oldest['title']}' at {oldest['days_open']} days open in {oldest['stage']} stage.\n"

    client = _anthropic.Anthropic()
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        messages=[{
            "role": "user",
            "content": _DEAL_AGE_RISK_PROMPT.format(context=context),
        }],
    )

    text = msg.content[0].text.strip()
    try:
        parsed = json.loads(text[text.find("{"):text.rfind("}") + 1])
        insight = parsed.get("insight", "")
        recommendations = parsed.get("recommendations", [])[:3]
    except Exception:
        insight = text[:200]
        recommendations = []

    while len(recommendations) < 3:
        recommendations.append("Review aging deals and schedule follow-ups to re-activate them.")

    return {
        "overdue_count": len(overdue_deals),
        "at_risk_count": len(at_risk_deals),
        "on_track_count": len(on_track_deals),
        "total_open_deals": len(open_deals),
        "deals": all_deals,
        "insight": insight,
        "recommendations": recommendations,
        "generated_at": now.isoformat(),
    }


# ---------------------------------------------------------------------------
# Phase 16q: GET /workspaces/{wid}/ai/deals/top-performers
# ---------------------------------------------------------------------------

_TOP_PERFORMERS_SYSTEM = """\
You are a sales analytics AI. Given data about top-performing closed-won deals across three dimensions (value, speed, confidence), write a 1-sentence insight and exactly 3 specific recommendations to replicate the success patterns.
Respond with JSON only: {"insight": "...", "recommendations": ["...", "...", "..."]}"""


@router.get("/workspaces/{workspace_id}/ai/deals/top-performers")
@limiter.limit("5/minute")
async def top_performer_deals(
    request: Request,
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    now = datetime.datetime.utcnow()

    result = await db.execute(
        select(
            Deal.id, Deal.title, Deal.company, Deal.value,
            Deal.ml_win_probability, Deal.created_at, Deal.updated_at,
        ).where(
            Deal.workspace_id == workspace_id,
            Deal.stage == "closed_won",
        )
    )
    closed_won = result.all()

    if not closed_won:
        return {
            "top_by_value": [],
            "top_by_speed": [],
            "top_by_confidence": [],
            "avg_win_rate": None,
            "insight": "No closed-won deals to analyse yet.",
            "recommendations": [
                "Close your first deal to start building top-performer insights.",
                "Set ML win probability on open deals to enable confidence tracking.",
                "Record cycle time by tracking created_at and close date on each deal.",
            ],
            "generated_at": now.isoformat(),
        }

    deals_data = []
    for row in closed_won:
        deal_id, title, company, value, ml_win_prob, created_at, updated_at = (
            row[0], row[1], row[2], float(row[3] or 0), row[4] or 0, row[5], row[6],
        )
        ca = created_at.replace(tzinfo=None) if (created_at and created_at.tzinfo) else created_at
        ua = updated_at.replace(tzinfo=None) if (updated_at and updated_at.tzinfo) else updated_at
        cycle_days = (ua - ca).days if (ca and ua) else 9999

        deals_data.append({
            "id": str(deal_id),
            "title": title,
            "company": company,
            "value": round(float(value)),
            "win_probability": ml_win_prob,
            "cycle_days": cycle_days if cycle_days < 9999 else None,
        })

    top_by_value = sorted(deals_data, key=lambda d: -d["value"])[:5]
    top_by_speed = sorted(
        [d for d in deals_data if d["cycle_days"] is not None],
        key=lambda d: d["cycle_days"]
    )[:5]
    top_by_confidence = sorted(deals_data, key=lambda d: -d["win_probability"])[:5]

    avg_win_rate = round(sum(d["win_probability"] for d in deals_data) / len(deals_data), 1)

    summary_context = (
        f"Top performer deals analysis:\n"
        f"- total_closed_won: {len(deals_data)}\n"
        f"- avg_win_probability_at_close: {avg_win_rate}%\n"
        f"- top_value_deal: {top_by_value[0]['title']} (${top_by_value[0]['value']:,})\n"
        f"- fastest_deal_days: {top_by_speed[0]['cycle_days'] if top_by_speed else 'N/A'}\n"
        f"- highest_confidence_probability: {top_by_confidence[0]['win_probability']}%"
    )

    client = _anthropic.Anthropic()
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        system=_TOP_PERFORMERS_SYSTEM,
        messages=[{"role": "user", "content": summary_context}],
    )

    text = msg.content[0].text.strip()
    try:
        parsed = json.loads(text[text.find("{"):text.rfind("}") + 1])
        insight = parsed.get("insight", "High-value deals drive the most revenue impact.")
        recommendations = parsed.get("recommendations", [])[:3]
    except Exception:
        insight = "High-value deals drive the most revenue impact."
        recommendations = []

    while len(recommendations) < 3:
        recommendations.append("Study the patterns of your fastest-closing deals to replicate success.")

    return {
        "top_by_value": top_by_value,
        "top_by_speed": top_by_speed,
        "top_by_confidence": top_by_confidence,
        "avg_win_rate": avg_win_rate,
        "insight": insight,
        "recommendations": recommendations,
        "generated_at": now.isoformat(),
    }


# Phase 16r — AI workspace deal stage concentration report
# ---------------------------------------------------------------------------

_STAGE_CONCENTRATION_SYSTEM = """\
You are a CRM sales analyst. Given a breakdown of open deals by pipeline stage \
(count, total_value, avg_health per stage), write a 1-sentence insight about where \
value is concentrated or stalled, and suggest the 3 most impactful actions. \
Reply ONLY with valid JSON: \
{"insight": "<1-sentence>", "recommendations": ["...", "...", "..."]} \
No markdown. Pure JSON only."""


@router.get("/workspaces/{workspace_id}/ai/deals/stage-concentration")
@limiter.limit("5/minute")
async def get_deal_stage_concentration(
    request: Request,
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    now = datetime.datetime.utcnow()

    deals_result = await db.execute(
        select(Deal.stage, Deal.value, Deal.health_score)
        .where(
            Deal.workspace_id == workspace_id,
            Deal.stage.not_in(["closed_won", "closed_lost"]),
        )
    )
    deals = deals_result.all()

    if not deals:
        return {
            "stages": [],
            "highest_value_stage": None,
            "most_stalled_stage": None,
            "total_pipeline_value": 0,
            "insight": "No open deals found. Add deals to your pipeline to see stage concentration insights.",
            "recommendations": [
                "Create your first deal in the pipeline to start tracking stage concentration.",
                "Import existing opportunities to get an immediate pipeline view.",
                "Review your lead qualification criteria to ensure deals enter the right stage.",
            ],
            "generated_at": now.isoformat() + "Z",
        }

    stage_data: dict = {}
    for row in deals:
        stage = row.stage or "unknown"
        if stage not in stage_data:
            stage_data[stage] = {"count": 0, "total_value": 0.0, "health_scores": []}
        stage_data[stage]["count"] += 1
        stage_data[stage]["total_value"] += float(row.value or 0)
        if row.health_score is not None:
            stage_data[stage]["health_scores"].append(int(row.health_score))

    total_pipeline_value = sum(s["total_value"] for s in stage_data.values())

    stage_order = ["discovery", "qualified", "proposal", "negotiation"]
    sorted_stages = sorted(
        stage_data.keys(),
        key=lambda s: stage_order.index(s) if s in stage_order else len(stage_order),
    )

    stages = []
    for stage in sorted_stages:
        sd = stage_data[stage]
        avg_h = round(sum(sd["health_scores"]) / len(sd["health_scores"])) if sd["health_scores"] else None
        pct = round(sd["total_value"] / total_pipeline_value * 100, 1) if total_pipeline_value > 0 else 0.0
        stages.append({
            "stage": stage,
            "count": sd["count"],
            "total_value": round(sd["total_value"]),
            "avg_health": avg_h,
            "pct_of_pipeline": pct,
        })

    highest_value_stage = max(stages, key=lambda s: s["total_value"])["stage"] if stages else None
    health_stages = [s for s in stages if s["avg_health"] is not None]
    most_stalled_stage = min(health_stages, key=lambda s: s["avg_health"])["stage"] if health_stages else None  # type: ignore[arg-type]

    context = (
        f"Pipeline stage breakdown ({len(deals)} open deals, total ${total_pipeline_value:,.0f}):\n"
        + "\n".join(
            f"- {s['stage']}: {s['count']} deals, ${s['total_value']:,}, "
            f"avg health {s['avg_health'] if s['avg_health'] is not None else 'N/A'}/100, "
            f"{s['pct_of_pipeline']}% of pipeline"
            for s in stages
        )
        + f"\nHighest-value stage: {highest_value_stage}. Most stalled: {most_stalled_stage}."
    )

    client = _anthropic.Anthropic()
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        system=_STAGE_CONCENTRATION_SYSTEM,
        messages=[{"role": "user", "content": context}],
    )

    text = msg.content[0].text.strip()
    try:
        parsed = json.loads(text[text.find("{"):text.rfind("}") + 1])
        insight = parsed.get("insight", "")
        recommendations = parsed.get("recommendations", [])[:3]
    except Exception:
        insight = text[:200]
        recommendations = []

    if not insight:
        insight = f"${total_pipeline_value:,.0f} in pipeline is concentrated in {len(stages)} stages — review stalled stages to unblock flow."
    while len(recommendations) < 3:
        defaults = [
            f"Focus on advancing deals in {most_stalled_stage or 'the lowest-health stage'} to improve pipeline velocity.",
            "Set stage-specific targets to balance deal distribution across the pipeline.",
            "Review deals stuck in a single stage for more than 14 days and take action.",
        ]
        recommendations.append(defaults[len(recommendations) % 3])

    return {
        "stages": stages,
        "highest_value_stage": highest_value_stage,
        "most_stalled_stage": most_stalled_stage,
        "total_pipeline_value": round(total_pipeline_value),
        "insight": insight,
        "recommendations": recommendations,
        "generated_at": now.isoformat() + "Z",
    }


# ── Deal Close Rate by Stage ──────────────────────────────────────────────────

_CLOSE_RATE_SYSTEM = """\
You are a sales analytics expert reviewing deal close rates per pipeline stage.
Given win/loss data grouped by the stage deals were in when they closed, write
a 1-sentence insight and exactly 3 specific, actionable recommendations.

Return ONLY valid JSON with this exact structure:
{
  "insight": "1-sentence summary referencing the best and worst converting stages",
  "recommendations": ["rec1", "rec2", "rec3"]
}

Rules:
- insight: reference specific win rates and stage names, keep it data-driven
- recommendations: specific steps (e.g. improve proposal quality, address objections
  in negotiation, add qualification criteria at discovery)
- Be concise\
"""

_STAGE_ORDER = ["discovery", "qualified", "proposal", "negotiation"]


@router.get("/workspaces/{workspace_id}/ai/deals/close-rate-by-stage")
@limiter.limit("5/minute")
async def get_close_rate_by_stage(
    request: Request,
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    now = datetime.datetime.utcnow()

    # Query closed_won and closed_lost deals with their stage at close time
    # We infer closing stage from current stage for simplicity
    closed_result = await db.execute(
        select(Deal.stage, func.count(Deal.id))
        .where(Deal.workspace_id == workspace_id)
        .where(Deal.stage.in_(["closed_won", "closed_lost"]))
        .group_by(Deal.stage)
    )
    closed_counts: dict[str, int] = {}
    for stage, count in closed_result.all():
        closed_counts[stage] = count

    won_count = closed_counts.get("closed_won", 0)
    lost_count = closed_counts.get("closed_lost", 0)
    total_closed = won_count + lost_count

    if total_closed == 0:
        return {
            "stage_rates": [],
            "best_converting_stage": None,
            "worst_converting_stage": None,
            "insight": "No closed deals yet — close your first deals to start tracking close rate by stage.",
            "recommendations": [
                "Focus on advancing deals to close by setting clear next-action dates.",
                "Review deals in the proposal stage and schedule calls to push them forward.",
                "Use the Win/Loss Analysis on closed deals to identify patterns.",
            ],
            "generated_at": now.isoformat() + "Z",
        }

    # Query deal_moved activity events to infer last active stage before close
    # Description format: "Deal 'Title' moved: from_stage → to_stage"
    events_result = await db.execute(
        select(ActivityEvent.description)
        .where(ActivityEvent.workspace_id == workspace_id)
        .where(ActivityEvent.type == "deal_moved")
        .order_by(ActivityEvent.created_at.desc())
    )
    events_rows = events_result.all()

    import re as _re
    _close_re = _re.compile(r"moved[^:]*:\s*([a-z_]+)\s*→\s*(closed_won|closed_lost)")
    _title_re2 = _re.compile(r"Deal '([^']+)'")
    stage_wins: dict[str, int] = defaultdict(int)
    stage_losses: dict[str, int] = defaultdict(int)
    seen_titles: set[str] = set()

    for (desc,) in events_rows:
        if not desc or not isinstance(desc, str):
            continue
        m = _close_re.search(desc)
        if not m:
            continue
        from_s, to_s = m.group(1), m.group(2)
        if from_s not in _STAGE_ORDER:
            continue
        tm = _title_re2.search(desc)
        title_key = tm.group(1) if tm else desc[:50]
        if title_key in seen_titles:
            continue
        seen_titles.add(title_key)
        if to_s == "closed_won":
            stage_wins[from_s] += 1
        else:
            stage_losses[from_s] += 1

    # Unattributed deals (no event match) → fall back to "proposal" bucket
    attributed_won = sum(stage_wins.values())
    attributed_lost = sum(stage_losses.values())
    unattributed_won = max(0, won_count - attributed_won)
    unattributed_lost = max(0, lost_count - attributed_lost)
    if unattributed_won or unattributed_lost:
        stage_wins["proposal"] += unattributed_won
        stage_losses["proposal"] += unattributed_lost

    stage_rates = []
    for stage in _STAGE_ORDER:
        w = stage_wins.get(stage, 0)
        l = stage_losses.get(stage, 0)
        total = w + l
        if total == 0:
            continue
        win_rate = round(w / total * 100, 1)
        stage_rates.append({"stage": stage, "win_count": w, "loss_count": l, "total": total, "win_rate": win_rate})

    if not stage_rates:
        # All unattributed — show aggregate
        total = won_count + lost_count
        win_rate = round(won_count / total * 100, 1) if total else 0
        stage_rates = [{"stage": "proposal", "win_count": won_count, "loss_count": lost_count, "total": total, "win_rate": win_rate}]

    best = max(stage_rates, key=lambda s: s["win_rate"])
    worst = min(stage_rates, key=lambda s: s["win_rate"])
    best_converting_stage = best["stage"] if best["win_rate"] > 0 else None
    worst_converting_stage = worst["stage"] if len(stage_rates) > 1 else None

    rates_context = "\n".join(
        f"- {s['stage']}: {s['win_count']} won / {s['loss_count']} lost = {s['win_rate']}% win rate"
        for s in stage_rates
    )
    context = (
        f"Deal close rate by stage:\n{rates_context}\n"
        f"Best converting stage: {best_converting_stage} ({best['win_rate']}%)\n"
        f"Worst converting stage: {worst_converting_stage}\n"
    )

    default_insight = (
        f"The {best_converting_stage or 'proposal'} stage converts best "
        f"({best['win_rate']}% win rate), while "
        f"{worst_converting_stage or 'discovery'} has the most room to improve."
    )
    default_recs = [
        f"Study what works in {best_converting_stage or 'proposal'} stage and replicate across other stages.",
        f"Add structured qualification criteria at {worst_converting_stage or 'discovery'} stage to improve downstream close rates.",
        "Track objection patterns per stage using Win/Loss reason tagging.",
    ]

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=250,
            system=_CLOSE_RATE_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg.content[0].text.strip() if msg.content else "{}"
        data = json.loads(raw)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    insight = data.get("insight", default_insight)
    if not isinstance(insight, str) or not insight.strip():
        insight = default_insight

    raw_recs = data.get("recommendations", [])
    recommendations = [str(r) for r in (raw_recs if isinstance(raw_recs, list) else [])[:3]]
    while len(recommendations) < 3:
        recommendations.append(default_recs[len(recommendations) % 3])

    return {
        "stage_rates": stage_rates,
        "best_converting_stage": best_converting_stage,
        "worst_converting_stage": worst_converting_stage,
        "insight": insight,
        "recommendations": recommendations,
        "generated_at": now.isoformat() + "Z",
    }


# ---------------------------------------------------------------------------
# Phase 16t: GET /workspaces/{wid}/ai/deals/pipeline-churn
# ---------------------------------------------------------------------------

_PIPELINE_CHURN_SYSTEM = """\
You are a sales pipeline analyst identifying where deals are churning most.
Given data on which stages deals exit (via closed_lost or backward stage regression),
write a 1-sentence insight and exactly 3 specific, actionable recommendations.

Return ONLY valid JSON with this exact structure:
{
  "insight": "1-sentence summary referencing the highest-churn stage and churn rate",
  "recommendations": ["rec1", "rec2", "rec3"]
}

Rules:
- insight: cite the stage name and churn rate percentage, be concise and specific
- recommendations: practical steps to reduce churn at the worst stages
- Be concise\
"""


@router.get("/workspaces/{workspace_id}/ai/deals/pipeline-churn")
@limiter.limit("5/minute")
async def get_pipeline_churn(
    request: Request,
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    import re as _re
    now = datetime.datetime.now(datetime.timezone.utc)

    # Query all deal_moved activity events in last 90 days
    cutoff = now - datetime.timedelta(days=90)
    events_result = await db.execute(
        select(ActivityEvent.description, ActivityEvent.created_at)
        .where(ActivityEvent.workspace_id == workspace_id)
        .where(ActivityEvent.type == "deal_moved")
        .where(ActivityEvent.created_at >= cutoff)
        .order_by(ActivityEvent.created_at.asc())
    )
    events_rows = events_result.all()

    # Parse "Deal '...' moved: from_stage → to_stage" lines
    _move_re = _re.compile(r"moved[^:]*:\s*([a-z_]+)\s*→\s*([a-z_]+)")
    _title_re3 = _re.compile(r"Deal '([^']+)'")

    # Track, per deal title: list of (from_stage, to_stage, created_at) transitions
    deal_history: dict[str, list[tuple[str, str]]] = {}
    for desc, created_at in events_rows:
        if not desc or not isinstance(desc, str):
            continue
        m = _move_re.search(desc)
        if not m:
            continue
        from_s, to_s = m.group(1), m.group(2)
        tm = _title_re3.search(desc)
        title_key = tm.group(1) if tm else desc[:50]
        if title_key not in deal_history:
            deal_history[title_key] = []
        deal_history[title_key].append((from_s, to_s))

    # For each stage in _STAGE_ORDER, count:
    #   total_entered = how many deals entered (any transition to_stage == stage)
    #   churned_count = how many moved backward (from stage to earlier stage) OR to closed_lost
    stage_entered: dict[str, set[str]] = {s: set() for s in _STAGE_ORDER}
    stage_churned: dict[str, set[str]] = {s: set() for s in _STAGE_ORDER}

    stage_idx = {s: i for i, s in enumerate(_STAGE_ORDER)}

    for title, transitions in deal_history.items():
        for from_s, to_s in transitions:
            # Count deals entering a stage
            if to_s in stage_idx:
                stage_entered[to_s].add(title)

            # Count churn from a stage:
            # - moved to closed_lost (churn from that stage)
            # - moved backward (to_stage index < from_stage index)
            if from_s in stage_idx:
                if to_s == "closed_lost":
                    stage_churned[from_s].add(title)
                elif to_s in stage_idx and stage_idx[to_s] < stage_idx[from_s]:
                    stage_churned[from_s].add(title)

    stage_churn = []
    for stage in _STAGE_ORDER:
        entered = len(stage_entered[stage])
        churned = len(stage_churned[stage])
        churn_rate = round(churned / entered * 100, 1) if entered > 0 else 0.0
        stage_churn.append({
            "stage": stage,
            "total_entered": entered,
            "churned_count": churned,
            "churn_rate": churn_rate,
        })

    # Remove stages with zero activity
    active_stages = [s for s in stage_churn if s["total_entered"] > 0]

    if not active_stages:
        return {
            "stage_churn": [],
            "highest_churn_stage": None,
            "insight": "No deal movement data available for the last 90 days.",
            "recommendations": [
                "Ensure deals are being moved through pipeline stages so churn patterns can be tracked.",
                "Add deal_moved activity events by updating deal stages in the pipeline.",
                "Review your pipeline setup to ensure stages are configured correctly.",
            ],
            "generated_at": now.isoformat() + "Z",
        }

    highest_churn = max(active_stages, key=lambda s: s["churn_rate"])
    highest_churn_stage = highest_churn["stage"]

    churn_context = "\n".join(
        f"- {s['stage']}: {s['churned_count']} churned / {s['total_entered']} entered = {s['churn_rate']}% churn rate"
        for s in active_stages
    )
    context = (
        f"Pipeline churn by stage (last 90 days):\n{churn_context}\n"
        f"Highest churn stage: {highest_churn_stage} ({highest_churn['churn_rate']}% churn rate)\n"
    )

    default_insight = (
        f"The {highest_churn_stage} stage has the highest churn rate at "
        f"{highest_churn['churn_rate']}% — {highest_churn['churned_count']} of "
        f"{highest_churn['total_entered']} deals regressed or were lost here."
    )
    default_recs = [
        f"Add structured exit-criteria at the {highest_churn_stage} stage to catch deals before they regress.",
        "Review deals that churned back to earlier stages and identify common objection patterns.",
        "Set up automated alerts when a deal regresses to a previous stage for immediate rep intervention.",
    ]

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=250,
            system=_PIPELINE_CHURN_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg.content[0].text.strip() if msg.content else "{}"
        data = json.loads(raw)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    insight = data.get("insight", default_insight)
    if not isinstance(insight, str) or not insight.strip():
        insight = default_insight

    raw_recs = data.get("recommendations", [])
    recommendations = [str(r) for r in (raw_recs if isinstance(raw_recs, list) else [])[:3]]
    while len(recommendations) < 3:
        recommendations.append(default_recs[len(recommendations) % 3])

    return {
        "stage_churn": stage_churn,
        "highest_churn_stage": highest_churn_stage,
        "insight": insight,
        "recommendations": recommendations,
        "generated_at": now.isoformat() + "Z",
    }


# ---------------------------------------------------------------------------
# Phase 16u — AI workspace deal conversion quality report
# ---------------------------------------------------------------------------

_CONVERSION_QUALITY_SYSTEM = """\
You are a sales quality analyst evaluating closed-won deal conversion quality.
Given aggregated quality tier data (high/medium/low), write a 1-sentence insight
and exactly 3 specific, actionable recommendations to improve deal quality.

Return ONLY valid JSON with this exact structure:
{
  "insight": "1-sentence summary referencing quality distribution and what drives top-tier deals",
  "recommendations": ["rec1", "rec2", "rec3"]
}

Rules:
- insight: mention the high-quality tier count, avg health or cycle days, be concise and specific
- recommendations: practical steps to replicate top-tier patterns and improve lower-tier deals
- Be concise\
"""


@router.get("/workspaces/{workspace_id}/ai/deals/conversion-quality")
@limiter.limit("5/minute")
async def get_deal_conversion_quality(
    request: Request,
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    now = datetime.datetime.now(datetime.timezone.utc)

    # Fetch all closed_won deals with their metadata
    deals_result = await db.execute(
        select(
            Deal.id,
            Deal.value,
            Deal.created_at,
            Deal.stage_changed_at,
            Deal.competitors,
        )
        .where(Deal.workspace_id == workspace_id)
        .where(Deal.stage == "closed_won")
    )
    deals_rows = deals_result.all()

    if not deals_rows:
        return {
            "quality_tiers": [
                {"tier": "high", "count": 0, "avg_value": 0, "avg_cycle_days": 0, "avg_health": 0},
                {"tier": "medium", "count": 0, "avg_value": 0, "avg_cycle_days": 0, "avg_health": 0},
                {"tier": "low", "count": 0, "avg_value": 0, "avg_cycle_days": 0, "avg_health": 0},
            ],
            "avg_quality_score": 0,
            "insight": "No closed-won deals found to assess conversion quality.",
            "recommendations": [
                "Close your first deals to unlock quality analysis.",
                "Track deal health scores throughout the pipeline.",
                "Record deal competitors to improve quality benchmarking.",
            ],
            "generated_at": now.isoformat() + "Z",
        }

    # For each deal compute quality indicators
    deal_ids = [r[0] for r in deals_rows]

    # Fetch latest health score per deal from DealHealthHistory
    health_result = await db.execute(
        select(DealHealthHistory.deal_id, DealHealthHistory.score)
        .where(DealHealthHistory.workspace_id == workspace_id)
        .where(DealHealthHistory.deal_id.in_(deal_ids))
        .order_by(DealHealthHistory.recorded_at.desc())
    )
    health_rows = health_result.all()
    # Keep only first (most recent) score per deal
    health_by_deal: dict[uuid.UUID, float] = {}
    for deal_id, score in health_rows:
        if deal_id not in health_by_deal:
            health_by_deal[deal_id] = float(score)

    # Compute per-deal composite quality score
    # health×0.4 + velocity_score×0.3 + value_score×0.3
    # velocity_score = max(0, 100 - cycle_days) capped 0-100
    # value_score = min(100, value / 1000) capped 0-100
    deal_scores: list[tuple[float, float, float, float, int]] = []  # (score, value, cycle_days, health, competitor_count)
    for deal_id, value, created_at, stage_changed_at, competitors in deals_rows:
        v = float(value or 0)
        close_ts = stage_changed_at or now
        if close_ts.tzinfo is None:
            close_ts = close_ts.replace(tzinfo=datetime.timezone.utc)
        created_ts = created_at or now
        if created_ts.tzinfo is None:
            created_ts = created_ts.replace(tzinfo=datetime.timezone.utc)
        cycle_days = max(0, (close_ts - created_ts).days)
        health = health_by_deal.get(deal_id, 50.0)
        comp_count = len(competitors) if isinstance(competitors, list) else 0

        velocity_score = max(0.0, min(100.0, 100.0 - cycle_days))
        value_score = min(100.0, v / 1000.0)
        composite = health * 0.4 + velocity_score * 0.3 + value_score * 0.3
        deal_scores.append((composite, v, float(cycle_days), health, comp_count))

    # Bucket into tiers: high ≥ 66, medium 33-66, low < 33
    tiers: dict[str, list[tuple[float, float, float, float, int]]] = {"high": [], "medium": [], "low": []}
    for row in deal_scores:
        score = row[0]
        if score >= 66:
            tiers["high"].append(row)
        elif score >= 33:
            tiers["medium"].append(row)
        else:
            tiers["low"].append(row)

    def _tier_summary(tier_name: str) -> dict:
        rows = tiers[tier_name]
        if not rows:
            return {"tier": tier_name, "count": 0, "avg_value": 0, "avg_cycle_days": 0, "avg_health": 0}
        count = len(rows)
        avg_value = round(sum(r[1] for r in rows) / count)
        avg_cycle_days = round(sum(r[2] for r in rows) / count)
        avg_health = round(sum(r[3] for r in rows) / count, 1)
        return {
            "tier": tier_name,
            "count": count,
            "avg_value": avg_value,
            "avg_cycle_days": avg_cycle_days,
            "avg_health": avg_health,
        }

    quality_tiers = [_tier_summary("high"), _tier_summary("medium"), _tier_summary("low")]
    avg_quality_score = round(sum(r[0] for r in deal_scores) / len(deal_scores), 1)

    # Build Claude context
    context = (
        f"Total closed-won deals: {len(deal_scores)}\n"
        f"Average quality score: {avg_quality_score}/100\n"
        f"High-quality deals: {tiers['high'].__len__()} (avg health {quality_tiers[0]['avg_health']}, avg cycle {quality_tiers[0]['avg_cycle_days']} days, avg value ${quality_tiers[0]['avg_value']:,})\n"
        f"Medium-quality deals: {tiers['medium'].__len__()} (avg health {quality_tiers[1]['avg_health']}, avg cycle {quality_tiers[1]['avg_cycle_days']} days, avg value ${quality_tiers[1]['avg_value']:,})\n"
        f"Low-quality deals: {tiers['low'].__len__()} (avg health {quality_tiers[2]['avg_health']}, avg cycle {quality_tiers[2]['avg_cycle_days']} days, avg value ${quality_tiers[2]['avg_value']:,})\n"
    )

    default_insight = f"{len(tiers['high'])} high-quality wins averaging {quality_tiers[0]['avg_cycle_days']} days to close — focus on replicating their engagement patterns."
    default_recs = [
        "Review high-quality deal timelines to identify the engagement cadence that drives fast closes.",
        "Set minimum health score thresholds for deals entering the negotiation stage.",
        "Create playbooks based on high-quality deal patterns for reps to follow.",
    ]

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=250,
            system=_CONVERSION_QUALITY_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg.content[0].text.strip() if msg.content else "{}"
        data = json.loads(raw)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    insight = data.get("insight", default_insight)
    if not isinstance(insight, str) or not insight.strip():
        insight = default_insight

    raw_recs = data.get("recommendations", [])
    recommendations = [str(r) for r in (raw_recs if isinstance(raw_recs, list) else [])[:3]]
    while len(recommendations) < 3:
        recommendations.append(default_recs[len(recommendations) % 3])

    return {
        "quality_tiers": quality_tiers,
        "avg_quality_score": avg_quality_score,
        "insight": insight,
        "recommendations": recommendations,
        "generated_at": now.isoformat() + "Z",
    }


# ---------------------------------------------------------------------------
# Phase 16v — AI workspace deal win/loss pattern analysis
# ---------------------------------------------------------------------------

_WIN_LOSS_PATTERNS_SYSTEM = """\
You are a sales analyst identifying win/loss patterns across pipeline stages.
Given stage-level win/loss counts and competitor impact data, write a 1-sentence
insight and exactly 3 specific, actionable recommendations.

Return ONLY valid JSON with this exact structure:
{
  "insight": "1-sentence summary citing the best and worst converting stages or competitor impact",
  "recommendations": ["rec1", "rec2", "rec3"]
}

Rules:
- insight: mention the highest-win-rate stage and lowest-win-rate stage, or key competitor finding
- recommendations: practical steps to improve win rates at underperforming stages
- Be concise\
"""


@router.get("/workspaces/{workspace_id}/ai/deals/win-loss-patterns")
@limiter.limit("5/minute")
async def get_win_loss_patterns(
    request: Request,
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    now = datetime.datetime.now(datetime.timezone.utc)

    # Fetch all closed deals with stage, outcome and competitor info
    deals_result = await db.execute(
        select(Deal.stage, Deal.competitors)
        .where(Deal.workspace_id == workspace_id)
        .where(Deal.stage.in_(["closed_won", "closed_lost"]))
    )
    deals_rows = deals_result.all()

    if not deals_rows:
        return {
            "stage_patterns": [],
            "competitor_impact": {
                "with_competitors_win_rate": 0,
                "without_competitors_win_rate": 0,
                "insight": "No closed deals found to analyse win/loss patterns.",
            },
            "insight": "No closed deals found to analyse win/loss patterns.",
            "recommendations": [
                "Close your first deals to unlock win/loss pattern analysis.",
                "Tag deals with outcome reasons to improve future analysis.",
                "Record competitor information on each deal for richer insights.",
            ],
            "generated_at": now.isoformat() + "Z",
        }

    # Identify the last active stage for each closed deal via activity events
    # We reuse deal stage as the stage label since closed deals have stage = closed_won/closed_lost
    # Infer the stage from deal_moved activity events: last from_stage before closing
    closed_deal_stages: dict[str, dict] = {}  # stage -> {won, lost}

    # Aggregate by stage bucket (use "proposal" as fallback since most deals close from there)
    # Rather than complex event queries, use the stage field directly
    # For closed deals the stage IS closed_won or closed_lost, so we need to look at activity events
    # to find what stage they came from. Use a simplified approach: bucket all into one category
    # and distinguish by competitor presence.

    # Simpler approach: use deal's current stage (closed_won/closed_lost) as outcome,
    # and track competitor impact
    won_with = won_without = lost_with = lost_without = 0
    for stage, competitors in deals_rows:
        has_competitors = bool(competitors and isinstance(competitors, list) and len(competitors) > 0)
        if stage == "closed_won":
            if has_competitors:
                won_with += 1
            else:
                won_without += 1
        else:
            if has_competitors:
                lost_with += 1
            else:
                lost_without += 1

    total_won = won_with + won_without
    total_lost = lost_with + lost_without
    total = total_won + total_lost

    # Build stage_patterns from activity event data (deal_moved → closed_won/closed_lost)
    # Query the last stage each deal was in before closing
    events_result = await db.execute(
        select(ActivityEvent.description)
        .where(ActivityEvent.workspace_id == workspace_id)
        .where(ActivityEvent.type == "deal_moved")
    )
    event_rows = events_result.all()

    import re as _re2
    _move_re2 = _re2.compile(r"moved[^:]*:\s*([a-z_]+)\s*→\s*(closed_won|closed_lost)")
    stage_won: dict[str, int] = {}
    stage_lost: dict[str, int] = {}
    for (desc,) in event_rows:
        if not desc:
            continue
        m = _move_re2.search(desc)
        if not m:
            continue
        from_stage, outcome = m.group(1), m.group(2)
        if outcome == "closed_won":
            stage_won[from_stage] = stage_won.get(from_stage, 0) + 1
        else:
            stage_lost[from_stage] = stage_lost.get(from_stage, 0) + 1

    all_stages = set(stage_won) | set(stage_lost)
    stage_patterns = []
    for stg in sorted(all_stages, key=lambda s: _STAGE_ORDER.index(s) if s in _STAGE_ORDER else 99):
        won_n = stage_won.get(stg, 0)
        lost_n = stage_lost.get(stg, 0)
        tot = won_n + lost_n
        win_rate = round((won_n / tot) * 100, 1) if tot > 0 else 0.0
        stage_patterns.append({"stage": stg, "won": won_n, "lost": lost_n, "win_rate": win_rate})

    # Fallback if no activity events found
    if not stage_patterns:
        overall_rate = round((total_won / total) * 100, 1) if total > 0 else 0.0
        stage_patterns = [{"stage": "all_stages", "won": total_won, "lost": total_lost, "win_rate": overall_rate}]

    with_total = won_with + lost_with
    without_total = won_without + lost_without
    with_win_rate = round((won_with / with_total) * 100, 1) if with_total > 0 else 0.0
    without_win_rate = round((won_without / without_total) * 100, 1) if without_total > 0 else 0.0

    competitor_impact = {
        "with_competitors_win_rate": with_win_rate,
        "without_competitors_win_rate": without_win_rate,
    }

    # Build Claude context
    best = max(stage_patterns, key=lambda x: x["win_rate"]) if stage_patterns else None
    worst = min(stage_patterns, key=lambda x: x["win_rate"]) if stage_patterns else None
    context = (
        f"Total closed deals: {total} ({total_won} won, {total_lost} lost)\n"
        f"Stage patterns:\n" +
        "\n".join(f"  {p['stage']}: {p['won']} won / {p['lost']} lost = {p['win_rate']}% win rate" for p in stage_patterns) +
        f"\nCompetitor impact:\n"
        f"  Deals with competitors: {with_total} total, {with_win_rate}% win rate\n"
        f"  Deals without competitors: {without_total} total, {without_win_rate}% win rate\n"
    )

    best_stage = best["stage"] if best else "unknown"
    worst_stage = worst["stage"] if worst else "unknown"
    default_insight = (
        f"{best_stage.title()} stage has the highest win rate at {best['win_rate'] if best else 0}%; "
        f"{worst_stage.title()} lags at {worst['win_rate'] if worst else 0}% — focus rep coaching there."
    )
    default_recs = [
        f"Analyse what reps do differently at the {best_stage} stage to replicate those behaviours elsewhere.",
        f"Create targeted coaching for the {worst_stage} stage where win rates are lowest.",
        "Develop competitive battle cards for deals that have competitors to improve their win rate.",
    ]

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=250,
            system=_WIN_LOSS_PATTERNS_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg.content[0].text.strip() if msg.content else "{}"
        data = json.loads(raw)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    insight = data.get("insight", default_insight)
    if not isinstance(insight, str) or not insight.strip():
        insight = default_insight

    raw_recs = data.get("recommendations", [])
    recommendations = [str(r) for r in (raw_recs if isinstance(raw_recs, list) else [])[:3]]
    while len(recommendations) < 3:
        recommendations.append(default_recs[len(recommendations) % 3])

    return {
        "stage_patterns": stage_patterns,
        "competitor_impact": competitor_impact,
        "insight": insight,
        "recommendations": recommendations,
        "generated_at": now.isoformat() + "Z",
    }

# ---------------------------------------------------------------------------
# GET /workspaces/{workspace_id}/ai/deals/avg-deal-size-trend
# ---------------------------------------------------------------------------

_AVG_DEAL_SIZE_TREND_SYSTEM = """You are a revenue analytics assistant. Given monthly closed-won deal data,
write a one-sentence insight about the deal size trend and three actionable recommendations.
Respond ONLY with valid JSON: {"insight": "...", "recommendations": ["...", "...", "..."]}"""


@router.get("/workspaces/{workspace_id}/ai/deals/avg-deal-size-trend")
@limiter.limit("5/minute")
async def get_avg_deal_size_trend(
    workspace_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    now = datetime.datetime.now(datetime.timezone.utc)
    cutoff = now - datetime.timedelta(days=365)

    result = await db.execute(
        select(Deal.value, Deal.updated_at)
        .where(Deal.workspace_id == workspace_id)
        .where(Deal.stage == "closed_won")
        .where(Deal.updated_at >= cutoff)
        .order_by(Deal.updated_at)
    )
    rows = result.all()

    # Group by year-month in Python
    from collections import defaultdict as _dd2
    monthly: dict[str, list[float]] = _dd2(list)
    for val, closed_at in rows:
        if closed_at is None:
            continue
        if hasattr(closed_at, "tzinfo") and closed_at.tzinfo is None:
            closed_at = closed_at.replace(tzinfo=datetime.timezone.utc)
        key = closed_at.strftime("%Y-%m")
        monthly[key].append(float(val or 0))

    sorted_keys = sorted(monthly.keys())
    months_data = [
        {
            "month": k,
            "avg_value": round(sum(monthly[k]) / len(monthly[k]), 2) if monthly[k] else 0.0,
            "deal_count": len(monthly[k]),
        }
        for k in sorted_keys
    ]

    # Graceful empty default
    if not months_data:
        return {
            "months": [],
            "trend_direction": "stable",
            "best_month": None,
            "pct_change": 0.0,
            "insight": "No closed-won deals in the last 12 months — start closing deals to see your avg deal size trend.",
            "recommendations": [
                "Set a target average deal size to benchmark your pipeline value.",
                "Review deals stuck in late stages and develop a closing strategy.",
                "Identify your highest-value customers and look for similar prospects.",
            ],
            "generated_at": now.isoformat() + "Z",
        }

    # Trend: compare first-half vs second-half avg values
    mid = len(months_data) // 2
    first_vals = [m["avg_value"] for m in months_data[:mid]] if mid > 0 else []
    second_vals = [m["avg_value"] for m in months_data[mid:]]
    first_avg = sum(first_vals) / len(first_vals) if first_vals else 0.0
    second_avg = sum(second_vals) / len(second_vals) if second_vals else 0.0
    if first_avg > 0:
        pct_change = round(((second_avg - first_avg) / first_avg) * 100, 1)
    else:
        pct_change = 0.0

    if pct_change >= 20:
        trend_direction = "accelerating"
    elif pct_change >= 5:
        trend_direction = "growing"
    elif pct_change <= -5:
        trend_direction = "declining"
    else:
        trend_direction = "stable"

    best_month_obj = max(months_data, key=lambda m: m["avg_value"])
    best_month = best_month_obj["month"]

    overall_avg = round(sum(m["avg_value"] for m in months_data) / len(months_data), 2)

    default_insight = (
        f"Average deal size is {trend_direction} at ${overall_avg:,.0f}/month; "
        f"best month was {best_month} with ${best_month_obj['avg_value']:,.0f} avg."
    )
    default_recs = [
        f"Focus on the tactics used in {best_month} — the best-performing month — to replicate that avg deal size.",
        "Consider upsell or expansion offers to grow average deal value across all stages.",
        "Review pricing strategy if deal size trend is declining to identify whether discounting is eroding value.",
    ]

    context = (
        f"Monthly closed-won deal data (last 12 months):\n" +
        "\n".join(f"  {m['month']}: {m['deal_count']} deals, avg ${m['avg_value']:,.0f}" for m in months_data) +
        f"\nTrend: {trend_direction} ({pct_change:+.1f}% change first-half vs second-half)\n"
        f"Best month: {best_month}\n"
    )

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=250,
            system=_AVG_DEAL_SIZE_TREND_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg.content[0].text.strip() if msg.content else "{}"
        data = json.loads(raw)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    insight = data.get("insight", default_insight)
    if not isinstance(insight, str) or not insight.strip():
        insight = default_insight

    raw_recs = data.get("recommendations", [])
    recommendations = [str(r) for r in (raw_recs if isinstance(raw_recs, list) else [])[:3]]
    while len(recommendations) < 3:
        recommendations.append(default_recs[len(recommendations) % 3])

    return {
        "months": months_data,
        "trend_direction": trend_direction,
        "best_month": best_month,
        "pct_change": pct_change,
        "insight": insight,
        "recommendations": recommendations,
        "generated_at": now.isoformat() + "Z",
    }

# ---------------------------------------------------------------------------
# GET /workspaces/{workspace_id}/ai/deals/followup-gaps
# ---------------------------------------------------------------------------

_FOLLOWUP_GAPS_SYSTEM = """You are a sales coaching assistant. Given data on deals that haven't been contacted recently,
write a one-sentence insight about the follow-up gap risk and three actionable recommendations.
Respond ONLY with valid JSON: {"insight": "...", "recommendations": ["...", "...", "..."]}"""


@router.get("/workspaces/{workspace_id}/ai/deals/followup-gaps")
@limiter.limit("5/minute")
async def get_followup_gaps(
    workspace_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    now = datetime.datetime.now(datetime.timezone.utc)

    result = await db.execute(
        select(Deal.id, Deal.title, Deal.company, Deal.stage, Deal.updated_at)
        .where(Deal.workspace_id == workspace_id)
        .where(Deal.stage.not_in(["closed_won", "closed_lost"]))
        .order_by(Deal.updated_at)
    )
    rows = result.all()

    overdue = []
    due_soon = []
    on_track_count = 0
    total_days = 0
    total_count = 0

    for deal_id, title, company, stage, updated_at in rows:
        if updated_at is None:
            days = 0
        else:
            if hasattr(updated_at, "tzinfo") and updated_at.tzinfo is None:
                updated_at = updated_at.replace(tzinfo=datetime.timezone.utc)
            days = (now - updated_at).days

        total_days += days
        total_count += 1

        entry = {
            "deal_id": str(deal_id),
            "title": title or "Untitled",
            "company": company or "",
            "stage": stage,
            "days_since_contact": days,
        }
        if days > 14:
            overdue.append(entry)
        elif days >= 7:
            due_soon.append(entry)
        else:
            on_track_count += 1

    avg_days = round(total_days / total_count, 1) if total_count > 0 else 0.0

    # Graceful empty default
    if total_count == 0:
        return {
            "overdue": [],
            "due_soon": [],
            "on_track_count": 0,
            "avg_days_since_contact": 0.0,
            "insight": "No open deals to track — add deals to the pipeline to start monitoring follow-up cadence.",
            "recommendations": [
                "Import or create deals so the follow-up gap tracker can monitor your pipeline.",
                "Establish a follow-up SLA: aim to contact every open deal at least once every 7 days.",
                "Set up automated reminders in the system to flag deals that haven't been touched in 7+ days.",
            ],
            "generated_at": now.isoformat() + "Z",
        }

    default_insight = (
        f"{len(overdue)} deal{'' if len(overdue) == 1 else 's'} overdue for follow-up (>14 days), "
        f"{len(due_soon)} due soon (7–14 days); avg {avg_days} days since last contact."
    )
    default_recs = [
        f"Prioritise the {len(overdue)} overdue deal{'' if len(overdue) == 1 else 's'} for immediate outreach — radio silence beyond 14 days dramatically reduces close probability.",
        "Implement a daily follow-up habit: review the due-soon list each morning and send one personalised touch per deal.",
        "Set a 7-day follow-up SLA for all open deals and assign a team member as the DRI for each.",
    ]

    context = (
        f"Open deals follow-up summary:\n"
        f"  Overdue (>14 days): {len(overdue)} deal(s)\n"
        f"  Due soon (7–14 days): {len(due_soon)} deal(s)\n"
        f"  On track (<7 days): {on_track_count} deal(s)\n"
        f"  Avg days since last contact: {avg_days}\n"
    )
    if overdue:
        context += "Overdue deals:\n" + "\n".join(
            f"  {d['title']} ({d['company']}) — {d['stage']}, {d['days_since_contact']}d" for d in overdue[:5]
        ) + "\n"

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=250,
            system=_FOLLOWUP_GAPS_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg.content[0].text.strip() if msg.content else "{}"
        data = json.loads(raw)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    insight = data.get("insight", default_insight)
    if not isinstance(insight, str) or not insight.strip():
        insight = default_insight

    raw_recs = data.get("recommendations", [])
    recommendations = [str(r) for r in (raw_recs if isinstance(raw_recs, list) else [])[:3]]
    while len(recommendations) < 3:
        recommendations.append(default_recs[len(recommendations) % 3])

    return {
        "overdue": overdue,
        "due_soon": due_soon,
        "on_track_count": on_track_count,
        "avg_days_since_contact": avg_days,
        "insight": insight,
        "recommendations": recommendations,
        "generated_at": now.isoformat() + "Z",
    }

# ---------------------------------------------------------------------------
# GET /workspaces/{workspace_id}/ai/deals/value-at-risk
# ---------------------------------------------------------------------------

_VALUE_AT_RISK_SYSTEM = """You are a sales risk analyst. Given data on pipeline deals at risk of being lost,
write a one-sentence insight about the value at risk and three actionable recommendations.
Respond ONLY with valid JSON: {"insight": "...", "recommendations": ["...", "...", "..."]}"""

_STAGE_THRESHOLDS = {"discovery": 14, "qualified": 21, "proposal": 30, "negotiation": 45}


@router.get("/workspaces/{workspace_id}/ai/deals/value-at-risk")
@limiter.limit("5/minute")
async def get_value_at_risk(
    workspace_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    now = datetime.datetime.now(datetime.timezone.utc)

    result = await db.execute(
        select(Deal.id, Deal.title, Deal.company, Deal.stage, Deal.value, Deal.health_score, Deal.created_at, Deal.stage_changed_at)
        .where(Deal.workspace_id == workspace_id)
        .where(Deal.stage.not_in(["closed_won", "closed_lost"]))
        .order_by(Deal.value.desc())
    )
    rows = result.all()

    total_pipeline = 0.0
    at_risk_deals = []

    for deal_id, title, company, stage, value, health_score, created_at, stage_changed_at in rows:
        val = float(value or 0)
        total_pipeline += val

        # Compute days in current stage
        ref = stage_changed_at or created_at
        if ref is not None:
            if hasattr(ref, "tzinfo") and ref.tzinfo is None:
                ref = ref.replace(tzinfo=datetime.timezone.utc)
            days_in_stage = (now - ref).days
        else:
            days_in_stage = 0

        threshold = _STAGE_THRESHOLDS.get(stage, 30)
        stuck = days_in_stage > threshold

        risk_reasons = []
        if health_score < 50:
            risk_reasons.append(f"health score {health_score}")
        if stuck:
            risk_reasons.append(f"stuck in {stage} for {days_in_stage}d (threshold {threshold}d)")

        if risk_reasons:
            at_risk_deals.append({
                "deal_id": str(deal_id),
                "title": title or "Untitled",
                "company": company or "",
                "stage": stage,
                "value": round(val, 2),
                "health_score": health_score,
                "risk_reason": "; ".join(risk_reasons),
            })

    at_risk_value = sum(d["value"] for d in at_risk_deals)
    at_risk_pct = round((at_risk_value / total_pipeline) * 100, 1) if total_pipeline > 0 else 0.0

    # Graceful empty default
    if not rows:
        return {
            "total_pipeline_value": 0.0,
            "at_risk_value": 0.0,
            "at_risk_pct": 0.0,
            "at_risk_deals": [],
            "insight": "No open deals in the pipeline — add deals to start tracking value at risk.",
            "recommendations": [
                "Build your pipeline by prospecting and adding new deals to the system.",
                "Once deals are added, use this report to monitor at-risk value before it's lost.",
                "Set deal health thresholds and stage SLAs to keep the pipeline moving.",
            ],
            "generated_at": now.isoformat() + "Z",
        }

    default_insight = (
        f"${at_risk_value:,.0f} ({at_risk_pct}% of pipeline) is at risk across {len(at_risk_deals)} deal{'' if len(at_risk_deals) == 1 else 's'} "
        f"— act now to prevent these from slipping."
    )
    default_recs = [
        f"Focus immediate attention on the {len(at_risk_deals)} at-risk deal{'' if len(at_risk_deals) == 1 else 's'} to recover ${at_risk_value:,.0f} in pipeline value.",
        "Improve health scores on stalled deals by scheduling discovery calls and addressing known objections.",
        "Review stage SLAs quarterly and set automated alerts when deals exceed them.",
    ]

    context = (
        f"Pipeline value at risk:\n"
        f"  Total pipeline: ${total_pipeline:,.0f}\n"
        f"  At-risk value: ${at_risk_value:,.0f} ({at_risk_pct}% of pipeline)\n"
        f"  At-risk deals: {len(at_risk_deals)}\n"
    )
    if at_risk_deals:
        context += "Top at-risk deals:\n" + "\n".join(
            f"  {d['title']} ({d['company']}) — ${d['value']:,.0f}, {d['stage']}, risk: {d['risk_reason']}"
            for d in at_risk_deals[:5]
        ) + "\n"

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=250,
            system=_VALUE_AT_RISK_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg.content[0].text.strip() if msg.content else "{}"
        data = json.loads(raw)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    insight = data.get("insight", default_insight)
    if not isinstance(insight, str) or not insight.strip():
        insight = default_insight

    raw_recs = data.get("recommendations", [])
    recommendations = [str(r) for r in (raw_recs if isinstance(raw_recs, list) else [])[:3]]
    while len(recommendations) < 3:
        recommendations.append(default_recs[len(recommendations) % 3])

    return {
        "total_pipeline_value": round(total_pipeline, 2),
        "at_risk_value": round(at_risk_value, 2),
        "at_risk_pct": at_risk_pct,
        "at_risk_deals": at_risk_deals,
        "insight": insight,
        "recommendations": recommendations,
        "generated_at": now.isoformat() + "Z",
    }


# ── Phase 16z: Next-Best-Action Recommendations ─────────────────────────────

_NEXT_BEST_ACTIONS_SYSTEM = """\
You are a senior sales strategist. Given a list of deals with their stage, \
health score, value, days in stage, and competitors, output a JSON object with:
- "actions": array of objects, one per deal:
    - "deal_id": string
    - "priority": "high" | "medium" | "low"
    - "action": string (<=12 words, specific next step)
    - "rationale": string (<=20 words, why this action)
- "insight": string (1 sentence overall pattern)
- "recommendations": array of 3 strings (strategic recommendations)

Priority rules:
- high: value > $50k OR health_score < 40 OR stuck > 2x threshold
- low: health_score >= 70 AND days_in_stage < threshold
- medium: everything else

Action must be concrete (e.g. "Schedule executive sponsor call", "Send revised proposal", "Address pricing objection").
Return valid JSON only, no prose.\
"""

_NEXT_BEST_ACTIONS_STAGE_THRESHOLDS: dict[str, int] = {
    "discovery": 14,
    "qualified": 21,
    "proposal": 30,
    "negotiation": 45,
}


@router.get("/workspaces/{workspace_id}/ai/deals/next-best-actions")
@limiter.limit("5/minute")
async def get_next_best_actions(
    request: Request,
    workspace_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if str(current_user.workspace_id) != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    now = datetime.datetime.now(datetime.timezone.utc)

    result = await db.execute(
        select(
            Deal.id,
            Deal.title,
            Deal.company,
            Deal.stage,
            Deal.value,
            Deal.health_score,
            Deal.created_at,
            Deal.stage_changed_at,
            Deal.competitors,
        )
        .where(Deal.workspace_id == workspace_id)
        .where(Deal.stage.not_in(["closed_won", "closed_lost"]))
        .order_by(Deal.value.desc())
        .limit(10)
    )
    rows = result.all()

    if not rows:
        return {
            "actions": [],
            "insight": "No open deals found to generate next-best-action recommendations.",
            "recommendations": [
                "Create your first deal in the Pipeline to start receiving AI recommendations.",
                "Import deals from your CRM to get immediate prioritisation insights.",
                "Connect Gmail or Slack to auto-create deals from inbound conversations.",
            ],
            "generated_at": now.isoformat() + "Z",
        }

    deals_context: list[dict] = []
    for row in rows:
        deal_id, title, company, stage, value, health_score, created_at, stage_changed_at, competitors = row
        ref = stage_changed_at or created_at
        days_in_stage = (now - ref.replace(tzinfo=datetime.timezone.utc)).days if ref else 0
        threshold = _NEXT_BEST_ACTIONS_STAGE_THRESHOLDS.get(stage, 30)
        competitor_list: list[str] = competitors if isinstance(competitors, list) else []
        deals_context.append({
            "deal_id": str(deal_id),
            "title": title or "Untitled",
            "company": company or "",
            "stage": stage,
            "value": float(value or 0),
            "health_score": int(health_score or 0),
            "days_in_stage": days_in_stage,
            "threshold": threshold,
            "competitors": competitor_list,
        })

    context_lines = ["Top open deals (by value):\n"]
    for d in deals_context:
        comp_str = f", competitors: {', '.join(d['competitors'])}" if d["competitors"] else ""
        context_lines.append(
            f"  deal_id={d['deal_id']} title={d['title']!r} company={d['company']!r} "
            f"stage={d['stage']} value=${d['value']:,.0f} health={d['health_score']} "
            f"days_in_stage={d['days_in_stage']} threshold={d['threshold']}{comp_str}"
        )
    context = "\n".join(context_lines)

    default_actions = []
    for d in deals_context:
        if d["value"] > 50000 or d["health_score"] < 40 or d["days_in_stage"] > 2 * d["threshold"]:
            priority = "high"
        elif d["health_score"] >= 70 and d["days_in_stage"] < d["threshold"]:
            priority = "low"
        else:
            priority = "medium"
        if d["stage"] == "discovery":
            action = "Schedule qualification call to advance stage"
        elif d["stage"] == "qualified":
            action = "Send tailored proposal based on needs"
        elif d["stage"] == "proposal":
            action = "Follow up on proposal and address objections"
        else:
            action = "Align on terms and request verbal commitment"
        default_actions.append({
            "deal_id": d["deal_id"],
            "priority": priority,
            "action": action,
            "rationale": "Based on stage and health score.",
        })

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=800,
            system=_NEXT_BEST_ACTIONS_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg.content[0].text.strip() if msg.content else "{}"
        data = json.loads(raw)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    actions = data.get("actions", default_actions)
    if not isinstance(actions, list):
        actions = default_actions
    valid_priorities = {"high", "medium", "low"}
    cleaned_actions = []
    deal_ids_seen = {d["deal_id"] for d in deals_context}
    for a in actions:
        if not isinstance(a, dict):
            continue
        if str(a.get("deal_id", "")) not in deal_ids_seen:
            continue
        cleaned_actions.append({
            "deal_id": str(a.get("deal_id", "")),
            "priority": a.get("priority", "medium") if a.get("priority") in valid_priorities else "medium",
            "action": str(a.get("action", "Follow up with stakeholder"))[:80],
            "rationale": str(a.get("rationale", ""))[:100],
        })
    if not cleaned_actions:
        cleaned_actions = default_actions

    default_insight = (
        f"{len(deals_context)} deals prioritised — "
        f"{sum(1 for a in cleaned_actions if a['priority'] == 'high')} require immediate attention."
    )
    insight = data.get("insight", default_insight)
    if not isinstance(insight, str) or not insight.strip():
        insight = default_insight

    default_recs = [
        "Prioritise high-value, low-health deals to prevent pipeline leakage.",
        "Set weekly cadence for follow-ups on deals stuck beyond their stage threshold.",
        "Track competitor mentions and tailor messaging to differentiate your offering.",
    ]
    raw_recs = data.get("recommendations", [])
    recommendations = [str(r) for r in (raw_recs if isinstance(raw_recs, list) else [])[:3]]
    while len(recommendations) < 3:
        recommendations.append(default_recs[len(recommendations) % 3])

    return {
        "actions": cleaned_actions,
        "insight": insight,
        "recommendations": recommendations,
        "generated_at": now.isoformat() + "Z",
    }


# ── Phase 17a: Weekly Coaching Digest ────────────────────────────────────────

_COACHING_DIGEST_SYSTEM = """\
You are an expert sales coach. Given a list of deals (stage, health score, value, \
days in stage, competitors), produce a coaching digest for the 3 most actionable deals.

Output a JSON object with:
- "coached_deals": array of exactly 3 objects (or fewer if fewer than 3 deals):
    - "deal_id": string
    - "title": string
    - "stage": string
    - "value": number
    - "what_to_do": string (2-3 sentences: specific actions for this week)
    - "what_to_avoid": string (1-2 sentences: common mistakes at this stage)
    - "talking_points": array of 3 strings (key points to raise in next conversation)
- "weekly_theme": string (1 sentence identifying the week's biggest opportunity or risk)
- "recommendations": array of 3 strings (process-level recommendations)

Be specific, actionable, and coach-like. No generic platitudes.
Return valid JSON only.\
"""

_COACHING_STAGE_THRESHOLDS: dict[str, int] = {
    "discovery": 14,
    "qualified": 21,
    "proposal": 30,
    "negotiation": 45,
}


@router.get("/workspaces/{workspace_id}/ai/deals/coaching-digest")
@limiter.limit("5/minute")
async def get_coaching_digest(
    request: Request,
    workspace_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if str(current_user.workspace_id) != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    now = datetime.datetime.now(datetime.timezone.utc)

    result = await db.execute(
        select(
            Deal.id,
            Deal.title,
            Deal.company,
            Deal.stage,
            Deal.value,
            Deal.health_score,
            Deal.created_at,
            Deal.stage_changed_at,
            Deal.competitors,
        )
        .where(Deal.workspace_id == workspace_id)
        .where(Deal.stage.not_in(["closed_won", "closed_lost"]))
        .order_by(Deal.value.desc())
    )
    rows = result.all()

    if not rows:
        return {
            "coached_deals": [],
            "weekly_theme": "No open deals this week — focus on prospecting to build pipeline.",
            "recommendations": [
                "Add your first deals to the Pipeline to unlock weekly coaching insights.",
                "Connect your email to auto-capture new deal opportunities.",
                "Set a goal of 3 qualified deals in pipeline by end of next week.",
            ],
            "generated_at": now.isoformat() + "Z",
        }

    deals_info: list[dict] = []
    for row in rows:
        deal_id, title, company, stage, value, health_score, created_at, stage_changed_at, competitors = row
        ref = stage_changed_at or created_at
        days_in_stage = (now - ref.replace(tzinfo=datetime.timezone.utc)).days if ref else 0
        threshold = _COACHING_STAGE_THRESHOLDS.get(stage, 30)
        overdue = days_in_stage > threshold
        score = float(value or 0) / 1000 + (100 - int(health_score or 50)) + (30 if overdue else 0)
        deals_info.append({
            "deal_id": str(deal_id),
            "title": title or "Untitled",
            "company": company or "",
            "stage": stage,
            "value": float(value or 0),
            "health_score": int(health_score or 0),
            "days_in_stage": days_in_stage,
            "threshold": threshold,
            "competitors": competitors if isinstance(competitors, list) else [],
            "_score": score,
        })

    top3 = sorted(deals_info, key=lambda d: d["_score"], reverse=True)[:3]

    context_lines = ["Weekly sales coaching digest — top deals needing attention:\n"]
    for d in top3:
        comp_str = f", competitors: {', '.join(d['competitors'])}" if d["competitors"] else ""
        context_lines.append(
            f"  deal_id={d['deal_id']} title={d['title']!r} company={d['company']!r} "
            f"stage={d['stage']} value=${d['value']:,.0f} health={d['health_score']} "
            f"days_in_stage={d['days_in_stage']} (threshold {d['threshold']}d){comp_str}"
        )
    context = "\n".join(context_lines)

    def _default_coached_deal(d: dict) -> dict:
        stage = d["stage"]
        if stage == "discovery":
            wtd = "Run a structured discovery call to uncover budget, authority, and timeline. Document findings in the deal notes."
            wta = "Avoid pitching product features before understanding the buyer's pain points."
            points = ["What is your biggest operational challenge right now?", "Who else is involved in this decision?", "What does success look like in 6 months?"]
        elif stage == "qualified":
            wtd = "Send a tailored proposal within 48 hours. Follow up with a call to walk through it together."
            wta = "Do not send a generic proposal — personalise it to the buyer's stated priorities."
            points = ["How does this align with your Q4 priorities?", "Are there any internal approvals needed before we proceed?", "What would make this an easy yes for your team?"]
        elif stage == "proposal":
            wtd = "Follow up within 3 business days if no response. Offer a 30-minute call to address objections."
            wta = "Avoid discounting too early — understand the objection before adjusting price."
            points = ["What questions came up after reviewing the proposal?", "Is the timeline still realistic for your team?", "Can we schedule a technical review call?"]
        else:
            wtd = "Request a verbal commitment and agree on the final contract timeline. Involve legal on both sides."
            wta = "Do not let the deal sit — each week of delay increases the risk of stakeholder change."
            points = ["What is left before you can sign?", "Are there any procurement steps we should be aware of?", "Can we agree on a signature date today?"]
        return {
            "deal_id": d["deal_id"],
            "title": d["title"],
            "stage": stage,
            "value": d["value"],
            "what_to_do": wtd,
            "what_to_avoid": wta,
            "talking_points": points,
        }

    default_coached = [_default_coached_deal(d) for d in top3]

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1200,
            system=_COACHING_DIGEST_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg.content[0].text.strip() if msg.content else "{}"
        data = json.loads(raw)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    coached_deals = data.get("coached_deals", default_coached)
    if not isinstance(coached_deals, list):
        coached_deals = default_coached
    valid_deal_ids = {d["deal_id"] for d in top3}
    cleaned_deals = []
    for cd in coached_deals:
        if not isinstance(cd, dict):
            continue
        if str(cd.get("deal_id", "")) not in valid_deal_ids:
            continue
        tps = cd.get("talking_points", [])
        talking_points = [str(t) for t in (tps if isinstance(tps, list) else [])[:3]]
        while len(talking_points) < 3:
            talking_points.append("What would make this deal move forward this week?")
        cleaned_deals.append({
            "deal_id": str(cd.get("deal_id", "")),
            "title": str(cd.get("title", ""))[:80],
            "stage": str(cd.get("stage", "")),
            "value": float(cd.get("value", 0)),
            "what_to_do": str(cd.get("what_to_do", ""))[:400],
            "what_to_avoid": str(cd.get("what_to_avoid", ""))[:200],
            "talking_points": talking_points,
        })
    if not cleaned_deals:
        cleaned_deals = default_coached

    default_theme = f"This week focus on {top3[0]['title']!r} — your highest-priority deal at ${top3[0]['value']:,.0f}."
    weekly_theme = data.get("weekly_theme", default_theme)
    if not isinstance(weekly_theme, str) or not weekly_theme.strip():
        weekly_theme = default_theme

    default_recs = [
        "Block 30 minutes each morning this week for deal follow-ups — consistency beats intensity.",
        "Update deal health scores after every customer interaction to keep your pipeline accurate.",
        "Schedule a pipeline review meeting with your team to align on priorities and remove blockers.",
    ]
    raw_recs = data.get("recommendations", [])
    recommendations = [str(r) for r in (raw_recs if isinstance(raw_recs, list) else [])[:3]]
    while len(recommendations) < 3:
        recommendations.append(default_recs[len(recommendations) % 3])

    return {
        "coached_deals": cleaned_deals,
        "weekly_theme": weekly_theme,
        "recommendations": recommendations,
        "generated_at": now.isoformat() + "Z",
    }


_QBR_SUMMARY_SYSTEM = """\
You are a senior sales analytics AI generating a Quarterly Business Review (QBR) summary for a sales leader.

Given workspace CRM data for the last 90 days, produce a concise, actionable QBR summary.

Respond with valid JSON only, no prose outside JSON:
{
  "wins_summary": "2-sentence narrative celebrating key wins and total revenue closed",
  "pipeline_status": "2-sentence narrative on current pipeline health, momentum, and areas of concern",
  "strategic_recommendations": ["specific actionable recommendation 1", "specific recommendation 2", "specific recommendation 3"]
}
"""


@router.get("/workspaces/{workspace_id}/ai/deals/qbr-summary")
@limiter.limit("5/minute")
async def get_qbr_summary(
    request: Request,
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if str(current_user.workspace_id) != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    now = datetime.datetime.now(datetime.timezone.utc)
    cutoff_90 = now - datetime.timedelta(days=90)

    won_result = await db.execute(
        select(Deal.id, Deal.title, Deal.company, Deal.value, Deal.stage_changed_at)
        .where(
            Deal.workspace_id == workspace_id,
            Deal.stage == "closed_won",
            Deal.stage_changed_at >= cutoff_90,
        )
        .order_by(Deal.value.desc())
    )
    won_rows = won_result.all()

    lost_result = await db.execute(
        select(func.count())
        .select_from(Deal)
        .where(
            Deal.workspace_id == workspace_id,
            Deal.stage == "closed_lost",
            Deal.stage_changed_at >= cutoff_90,
        )
    )
    lost_count = lost_result.scalar() or 0

    open_result = await db.execute(
        select(Deal.id, Deal.title, Deal.company, Deal.stage, Deal.value, Deal.health_score, Deal.ml_win_probability)
        .where(
            Deal.workspace_id == workspace_id,
            Deal.stage.notin_(["closed_won", "closed_lost"]),
        )
        .order_by(Deal.value.desc())
    )
    open_rows = open_result.all()

    won_count = len(won_rows)
    won_revenue = sum(float(r[3] or 0) for r in won_rows)
    total_closed = won_count + int(lost_count)
    win_rate = round((won_count / total_closed * 100)) if total_closed > 0 else 0

    top_wins = [
        {
            "id": str(r[0]),
            "title": str(r[1] or ""),
            "company": str(r[2] or ""),
            "value": float(r[3] or 0),
            "closed_at": r[4].isoformat() + "Z" if r[4] else None,
        }
        for r in won_rows[:3]
    ]

    open_count = len(open_rows)
    total_pipeline = sum(float(r[4] or 0) for r in open_rows)
    at_risk_rows = [r for r in open_rows if int(r[5] or 50) < 50]
    at_risk_count = len(at_risk_rows)
    avg_prob = (
        round(sum(float(r[6] or 0) for r in open_rows) / open_count)
        if open_count > 0 else 0
    )

    top_risks = [
        {
            "id": str(r[0]),
            "title": str(r[1] or ""),
            "company": str(r[2] or ""),
            "stage": str(r[3] or ""),
            "value": float(r[4] or 0),
            "health_score": int(r[5] or 0),
        }
        for r in sorted(at_risk_rows, key=lambda x: float(x[4] or 0), reverse=True)[:3]
    ]

    stage_breakdown: dict[str, int] = {}
    for r in open_rows:
        s = str(r[3] or "unknown")
        stage_breakdown[s] = stage_breakdown.get(s, 0) + 1

    quarter = (now.month - 1) // 3 + 1
    quarter_label = f"Q{quarter} {now.year}"

    context_lines = [
        f"Quarter: {quarter_label}",
        f"Closed Won (last 90 days): {won_count} deals · ${won_revenue:,.0f} revenue",
        f"Closed Lost (last 90 days): {int(lost_count)} deals",
        f"Win Rate: {win_rate}%",
        f"Open Pipeline: {open_count} deals · ${total_pipeline:,.0f} total value",
        f"At-Risk Deals (health<50): {at_risk_count}",
        f"Avg Win Probability: {avg_prob}%",
        f"Stage Breakdown: " + ", ".join(f"{s}: {c}" for s, c in stage_breakdown.items()),
    ]
    if top_wins:
        context_lines.append("Top Wins: " + "; ".join(f"{w['title']} (${w['value']:,.0f})" for w in top_wins))
    if top_risks:
        context_lines.append("Top At-Risk: " + "; ".join(f"{r['title']} health={r['health_score']}" for r in top_risks))
    context = "\n".join(context_lines)

    default_wins_summary = (
        f"In {quarter_label} the team closed {won_count} deals totalling ${won_revenue:,.0f} in revenue, "
        f"achieving a {win_rate}% win rate against {int(lost_count)} losses."
    )
    default_pipeline_status = (
        f"The pipeline holds {open_count} open deals worth ${total_pipeline:,.0f}, "
        f"with {at_risk_count} deals flagged at-risk and an average win probability of {avg_prob}%."
    )
    default_recs = [
        f"Focus on the {at_risk_count} at-risk deals — schedule a pipeline review before quarter end.",
        "Run a win-loss debrief on last quarter's losses to identify common objection patterns.",
        "Ensure all open deals have a next-action date set — follow-up discipline drives velocity.",
    ]

    metrics = {
        "closed_won_count": won_count,
        "closed_won_revenue": won_revenue,
        "closed_lost_count": int(lost_count),
        "win_rate": win_rate,
        "open_deal_count": open_count,
        "total_pipeline_value": total_pipeline,
        "at_risk_count": at_risk_count,
        "avg_win_probability": avg_prob,
    }

    if won_count == 0 and open_count == 0:
        return {
            "quarter": quarter_label,
            "wins_summary": default_wins_summary,
            "pipeline_status": default_pipeline_status,
            "top_wins": [],
            "top_risks": [],
            "strategic_recommendations": default_recs,
            "metrics": metrics,
            "generated_at": now.isoformat() + "Z",
        }

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            system=_QBR_SUMMARY_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg.content[0].text.strip() if msg.content else "{}"
        data = json.loads(raw)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    wins_summary = data.get("wins_summary", default_wins_summary)
    if not isinstance(wins_summary, str) or not wins_summary.strip():
        wins_summary = default_wins_summary

    pipeline_status = data.get("pipeline_status", default_pipeline_status)
    if not isinstance(pipeline_status, str) or not pipeline_status.strip():
        pipeline_status = default_pipeline_status

    raw_recs = data.get("strategic_recommendations", [])
    strategic_recommendations = [str(r) for r in (raw_recs if isinstance(raw_recs, list) else [])[:3]]
    while len(strategic_recommendations) < 3:
        strategic_recommendations.append(default_recs[len(strategic_recommendations) % 3])

    return {
        "quarter": quarter_label,
        "wins_summary": wins_summary,
        "pipeline_status": pipeline_status,
        "top_wins": top_wins,
        "top_risks": top_risks,
        "strategic_recommendations": strategic_recommendations,
        "metrics": metrics,
        "generated_at": now.isoformat() + "Z",
    }


_CONVERSION_PATH_SYSTEM = """\
You are a senior sales analytics AI analysing deal conversion path patterns.

Given the most common winning stage paths for a workspace, write a short, actionable analysis.

Respond with valid JSON only, no prose outside JSON:
{
  "insight": "2-sentence insight on what the paths reveal about the team's sales process and where leverage is",
  "recommendations": ["specific actionable recommendation 1", "specific recommendation 2", "specific recommendation 3"]
}
"""


@router.get("/workspaces/{workspace_id}/ai/deals/conversion-path")
@limiter.limit("5/minute")
async def get_deal_conversion_paths(
    request: Request,
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if str(current_user.workspace_id) != str(workspace_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    now = datetime.datetime.now(datetime.timezone.utc)
    cutoff_90 = now - datetime.timedelta(days=90)
    cutoff_180 = now - datetime.timedelta(days=180)

    won_result = await db.execute(
        select(Deal.title).where(
            Deal.workspace_id == workspace_id,
            Deal.stage == "closed_won",
            Deal.stage_changed_at >= cutoff_90,
        )
    )
    won_rows = won_result.all()
    won_titles = {row[0] for row in won_rows if row[0]}

    lost_result = await db.execute(
        select(Deal.title).where(
            Deal.workspace_id == workspace_id,
            Deal.stage == "closed_lost",
            Deal.stage_changed_at >= cutoff_90,
        )
    )
    lost_rows = lost_result.all()
    lost_titles = {row[0] for row in lost_rows if row[0]}

    all_closed_titles = won_titles | lost_titles

    import re as _re
    events_result = await db.execute(
        select(ActivityEvent.description, ActivityEvent.created_at)
        .where(
            ActivityEvent.workspace_id == workspace_id,
            ActivityEvent.type == "deal_moved",
            ActivityEvent.created_at >= cutoff_180,
        )
        .order_by(ActivityEvent.created_at.asc())
    )
    event_rows = events_result.all()

    _stage_re = _re.compile(r"→\s*([a-z_]+)")
    _title_re = _re.compile(r"Deal '([^']+)'")

    deal_events: dict[str, list[tuple[str, datetime.datetime]]] = defaultdict(list)
    for desc, ts in event_rows:
        if not desc:
            continue
        title_m = _title_re.search(desc)
        stage_m = _stage_re.search(desc)
        if title_m and stage_m:
            title = title_m.group(1)
            stage = stage_m.group(1)
            tz_ts = ts.replace(tzinfo=datetime.timezone.utc) if not ts.tzinfo else ts
            deal_events[title].append((stage, tz_ts))

    path_data: dict[str, dict] = {}
    for title in all_closed_titles:
        events_list = deal_events.get(title, [])
        if not events_list:
            continue
        stages = [s for s, _ in events_list]
        path_key = " → ".join(stages)
        is_won = title in won_titles
        total_days = 0.0
        if len(events_list) > 1:
            total_days = (events_list[-1][1] - events_list[0][1]).total_seconds() / 86400.0
        if path_key not in path_data:
            path_data[path_key] = {"stages": stages, "won_count": 0, "lost_count": 0, "days_list": []}
        if is_won:
            path_data[path_key]["won_count"] += 1
            path_data[path_key]["days_list"].append(total_days)
        else:
            path_data[path_key]["lost_count"] += 1

    if not path_data:
        return {
            "paths": [],
            "most_common_path": None,
            "fastest_path": None,
            "insight": "No deal conversion path data available for the last 90 days.",
            "recommendations": [
                "Move deals through stages in the CRM to start building conversion path data.",
                "Ensure stage transitions are logged for every deal in the pipeline.",
                "Aim to close at least 3 deals per quarter to generate meaningful path analysis.",
            ],
            "generated_at": now.isoformat() + "Z",
        }

    paths = []
    for pk, d in path_data.items():
        won = d["won_count"]
        lost = d["lost_count"]
        total = won + lost
        win_rate = round(won / total * 100) if total > 0 else 0
        avg_days = round(sum(d["days_list"]) / len(d["days_list"]), 1) if d["days_list"] else 0.0
        paths.append({
            "stages_sequence": d["stages"],
            "deal_count": total,
            "win_rate": win_rate,
            "avg_days": avg_days,
        })

    paths.sort(key=lambda p: (-p["deal_count"], -p["win_rate"]))

    won_paths = [p for p in paths if p["win_rate"] > 0 and p["avg_days"] > 0]
    most_common_path = paths[0]["stages_sequence"] if paths else None
    fastest_path = min(won_paths, key=lambda p: p["avg_days"])["stages_sequence"] if won_paths else most_common_path

    path_context = "\n".join(
        f"- Path: {' → '.join(p['stages_sequence'])} | Deals: {p['deal_count']} | Win Rate: {p['win_rate']}% | Avg days: {p['avg_days']}"
        for p in paths[:8]
    )
    most_common_str = " → ".join(most_common_path) if most_common_path else "N/A"
    fastest_str = " → ".join(fastest_path) if fastest_path else "N/A"
    context = (
        f"Workspace deal conversion paths (last 90 days):\n{path_context}\n\n"
        f"Most common path: {most_common_str}\nFastest path: {fastest_str}"
    )

    default_insight = (
        f"The most common winning path is {most_common_str}. "
        "Focus on replicating this process across the team."
    )
    default_recs = [
        "Train your team to follow the most common winning path consistently.",
        "Identify why deals deviate from winning paths and address those root causes.",
        "Set stage-specific SLAs to keep deals on the fastest winning track.",
    ]

    try:
        client = _anthropic.Anthropic()
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            system=_CONVERSION_PATH_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg.content[0].text.strip() if msg.content else "{}"
        data = json.loads(raw)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    insight = data.get("insight", default_insight)
    if not isinstance(insight, str) or not insight.strip():
        insight = default_insight

    raw_recs = data.get("recommendations", [])
    recommendations = [str(r) for r in (raw_recs if isinstance(raw_recs, list) else [])[:3]]
    while len(recommendations) < 3:
        recommendations.append(default_recs[len(recommendations) % 3])

    return {
        "paths": paths[:8],
        "most_common_path": most_common_path,
        "fastest_path": fastest_path,
        "insight": insight,
        "recommendations": recommendations,
        "generated_at": now.isoformat() + "Z",
    }

# ---------------------------------------------------------------------------
# Phase 17d — AI workspace deal playbook generator
# ---------------------------------------------------------------------------

_PLAYBOOK_SYSTEM = """\
You are a senior sales coaching AI analysing patterns from closed deals.

Given metrics about top-performing deals and stage-level stats, generate a practical deal playbook.

Respond with valid JSON only, no prose outside JSON:
{
  "playbook_title": "short punchy title for this workspace's winning playbook",
  "key_behaviors": ["3 highest-impact behavior from top-performing deals"],
  "stage_playbook": [
    {
      "stage": "discovery",
      "key_actions": ["3 key actions for this stage"],
      "success_signals": ["2 signals a deal is progressing well"],
      "common_mistakes": ["2 common mistakes to avoid"]
    }
  ],
  "recommendations": ["3 actionable recommendations for the sales team"]
}
Provide stage_playbook for stages: discovery, qualified, proposal, negotiation.
"""


@router.get("/workspaces/{workspace_id}/ai/deals/playbook")
@limiter.limit("5/minute")
async def get_deal_playbook(
    request: Request,
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if str(current_user.workspace_id) != str(workspace_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    now = datetime.datetime.now(datetime.timezone.utc)
    cutoff_90 = now - datetime.timedelta(days=90)
    cutoff_180 = now - datetime.timedelta(days=180)

    # Query 1: top-performing closed_won deals (high health, last 90d)
    won_result = await db.execute(
        select(
            Deal.id,
            Deal.title,
            Deal.value,
            Deal.health_score,
            Deal.stage_changed_at,
            Deal.created_at,
        )
        .where(
            Deal.workspace_id == workspace_id,
            Deal.stage == "closed_won",
            Deal.stage_changed_at >= cutoff_90,
        )
        .order_by(Deal.health_score.desc())
    )
    won_rows = won_result.all()

    # Query 2: closed_lost deals (last 90d) for comparison
    lost_result = await db.execute(
        select(Deal.id, Deal.title, Deal.health_score, Deal.stage_changed_at, Deal.created_at)
        .where(
            Deal.workspace_id == workspace_id,
            Deal.stage == "closed_lost",
            Deal.stage_changed_at >= cutoff_90,
        )
    )
    lost_rows = lost_result.all()

    # Query 3: deal_moved events to understand stage sequences
    events_result = await db.execute(
        select(ActivityEvent.description, ActivityEvent.created_at)
        .where(
            ActivityEvent.workspace_id == workspace_id,
            ActivityEvent.type == "deal_moved",
            ActivityEvent.created_at >= cutoff_180,
        )
        .order_by(ActivityEvent.created_at.asc())
    )
    event_rows = events_result.all()

    won_count = len(won_rows)
    lost_count = len(lost_rows)

    default_playbook_title = "Standard Sales Playbook"
    default_key_behaviors = [
        "Qualify deeply before moving to proposal — deals with high health scores spend more time in qualified.",
        "Maintain regular follow-up cadence — top deals average touch every 3-5 days.",
        "Align on success criteria early — winning deals define what success looks like in discovery.",
    ]
    default_stage_playbook = [
        {
            "stage": "discovery",
            "key_actions": [
                "Map the full buying committee and identify the economic buyer.",
                "Document the customer's current pain and quantify the cost of inaction.",
                "Set a clear mutual action plan with agreed next steps.",
            ],
            "success_signals": [
                "Customer shares internal docs or invites additional stakeholders.",
                "Economic buyer is engaged and confirms budget authority.",
            ],
            "common_mistakes": [
                "Rushing to demo before understanding the problem.",
                "Failing to identify blockers or competing priorities.",
            ],
        },
        {
            "stage": "qualified",
            "key_actions": [
                "Confirm BANT: Budget, Authority, Need, Timeline.",
                "Run a tailored demo focused on the customer's top 3 pain points.",
                "Agree on evaluation criteria and decision-making process.",
            ],
            "success_signals": [
                "Customer requests a proposal or pricing discussion.",
                "Champion advocates internally and introduces you to decision maker.",
            ],
            "common_mistakes": [
                "Sending a generic proposal without customisation.",
                "Assuming one stakeholder speaks for the entire buying group.",
            ],
        },
        {
            "stage": "proposal",
            "key_actions": [
                "Present ROI analysis tailored to their stated metrics.",
                "Address top objections proactively in the proposal document.",
                "Set a clear decision date and follow-up schedule.",
            ],
            "success_signals": [
                "Customer shares proposal internally and reports positive feedback.",
                "Legal or procurement team is introduced.",
            ],
            "common_mistakes": [
                "Ignoring competitor mentions instead of directly addressing them.",
                "Failing to create urgency or a compelling event.",
            ],
        },
        {
            "stage": "negotiation",
            "key_actions": [
                "Anchor on value rather than discounting on price.",
                "Understand their constraints before making concessions.",
                "Get verbal commit before sending revised commercial terms.",
            ],
            "success_signals": [
                "Customer requests contract redlines or legal review.",
                "Champion sets an internal signing deadline.",
            ],
            "common_mistakes": [
                "Caving on price without asking for something in return.",
                "Allowing negotiations to stall without a follow-up plan.",
            ],
        },
    ]
    default_recs = [
        f"Review the {won_count} recently closed wins and document the specific objections overcome in each.",
        "Run a monthly pipeline review focused on deal health scores — deals below 50 need immediate attention.",
        "Implement a structured handoff checklist from sales to customer success for every closed deal.",
    ]

    if won_count == 0:
        return {
            "playbook_title": default_playbook_title,
            "winning_profile": {
                "avg_health": 0,
                "avg_cycle_days": 0,
                "won_count": 0,
                "lost_count": lost_count,
                "win_rate": 0,
            },
            "key_behaviors": default_key_behaviors,
            "stage_playbook": default_stage_playbook,
            "recommendations": default_recs,
            "generated_at": now.isoformat() + "Z",
        }

    # Compute winning profile metrics
    health_scores = [float(r[3] or 0) for r in won_rows]
    avg_health = round(sum(health_scores) / len(health_scores)) if health_scores else 0

    cycle_days_list = []
    for row in won_rows:
        closed_at = row[4]
        created_at = row[5]
        if closed_at and created_at:
            ca = closed_at.replace(tzinfo=datetime.timezone.utc) if not closed_at.tzinfo else closed_at
            cr = created_at.replace(tzinfo=datetime.timezone.utc) if not created_at.tzinfo else created_at
            delta = (ca - cr).total_seconds() / 86400.0
            if delta >= 0:
                cycle_days_list.append(delta)
    avg_cycle_days = round(sum(cycle_days_list) / len(cycle_days_list), 1) if cycle_days_list else 0.0

    total_closed = won_count + lost_count
    win_rate = round(won_count / total_closed * 100) if total_closed > 0 else 0

    # Parse stage sequences from activity events for won deals
    import re as _re
    won_titles = {row[1] for row in won_rows if row[1]}
    _stage_re = _re.compile(r"→\s*([a-z_]+)")
    _title_re = _re.compile(r"Deal '([^']+)'")

    deal_stages: dict[str, list[str]] = defaultdict(list)
    for desc, ts in event_rows:
        if not desc:
            continue
        tm = _title_re.search(desc)
        sm = _stage_re.search(desc)
        if tm and sm:
            deal_stages[tm.group(1)].append(sm.group(1))

    stage_counts: dict[str, int] = defaultdict(int)
    for title in won_titles:
        for stage in deal_stages.get(title, []):
            stage_counts[stage] += 1

    top_stages = sorted(stage_counts.keys(), key=lambda s: -stage_counts[s])[:4]

    context_lines = [
        f"Workspace closed {won_count} deals (won) and {lost_count} deals (lost) in the last 90 days.",
        f"Win rate: {win_rate}%",
        f"Average health score of won deals: {avg_health}",
        f"Average cycle time (won): {avg_cycle_days} days",
        f"Most visited stages in winning deals: {', '.join(top_stages) if top_stages else 'unknown'}",
    ]
    context = "\n".join(context_lines)

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1000,
            system=_PLAYBOOK_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg.content[0].text.strip() if msg.content else "{}"
        data = json.loads(raw)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    playbook_title = data.get("playbook_title", default_playbook_title)
    if not isinstance(playbook_title, str) or not playbook_title.strip():
        playbook_title = default_playbook_title

    raw_behaviors = data.get("key_behaviors", [])
    key_behaviors = [str(b) for b in (raw_behaviors if isinstance(raw_behaviors, list) else [])[:3]]
    while len(key_behaviors) < 3:
        key_behaviors.append(default_key_behaviors[len(key_behaviors) % 3])

    raw_stage_playbook = data.get("stage_playbook", [])
    stage_playbook = raw_stage_playbook if isinstance(raw_stage_playbook, list) and len(raw_stage_playbook) > 0 else default_stage_playbook

    raw_recs = data.get("recommendations", [])
    recommendations = [str(r) for r in (raw_recs if isinstance(raw_recs, list) else [])[:3]]
    while len(recommendations) < 3:
        recommendations.append(default_recs[len(recommendations) % 3])

    return {
        "playbook_title": playbook_title,
        "winning_profile": {
            "avg_health": avg_health,
            "avg_cycle_days": avg_cycle_days,
            "won_count": won_count,
            "lost_count": lost_count,
            "win_rate": win_rate,
        },
        "key_behaviors": key_behaviors,
        "stage_playbook": stage_playbook,
        "recommendations": recommendations,
        "generated_at": now.isoformat() + "Z",
    }

# ---------------------------------------------------------------------------
# Phase 17e — AI workspace competitor battle cards
# ---------------------------------------------------------------------------

_BATTLE_CARD_SYSTEM = """\
You are a senior sales strategy AI analysing competitor intelligence from CRM data.

Given competitor encounter data (how often each competitor appears in deals and the win/loss record against them), generate actionable battle cards.

Respond with valid JSON only, no prose outside JSON:
{
  "battle_cards": [
    {
      "competitor": "CompetitorName",
      "key_differentiators": ["3 ways we beat this competitor"],
      "objection_responses": ["3 ready responses to common objections this competitor raises"],
      "positioning": "one-sentence positioning statement when facing this competitor"
    }
  ],
  "recommendations": ["3 strategic recommendations for competing in this market"]
}
"""


@router.get("/workspaces/{workspace_id}/ai/deals/battle-card")
@limiter.limit("5/minute")
async def get_deal_battle_card(
    request: Request,
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if str(current_user.workspace_id) != str(workspace_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    now = datetime.datetime.now(datetime.timezone.utc)
    cutoff_90 = now - datetime.timedelta(days=90)

    # Query 1: open deals with competitors field
    open_result = await db.execute(
        select(Deal.title, Deal.competitors)
        .where(
            Deal.workspace_id == workspace_id,
            Deal.stage.notin_(["closed_won", "closed_lost"]),
            Deal.competitors.isnot(None),
        )
    )
    open_rows = open_result.all()

    # Query 2: closed_won deals with competitors (last 90d)
    won_result = await db.execute(
        select(Deal.title, Deal.competitors)
        .where(
            Deal.workspace_id == workspace_id,
            Deal.stage == "closed_won",
            Deal.stage_changed_at >= cutoff_90,
            Deal.competitors.isnot(None),
        )
    )
    won_rows = won_result.all()

    # Query 3: closed_lost deals with competitors (last 90d)
    lost_result = await db.execute(
        select(Deal.title, Deal.competitors)
        .where(
            Deal.workspace_id == workspace_id,
            Deal.stage == "closed_lost",
            Deal.stage_changed_at >= cutoff_90,
            Deal.competitors.isnot(None),
        )
    )
    lost_rows = lost_result.all()

    # Aggregate competitor encounter counts and win/loss records
    competitor_data: dict[str, dict] = defaultdict(lambda: {"open": 0, "won": 0, "lost": 0})

    def _extract_competitors(rows: list, outcome: str) -> None:
        for title, comps in rows:
            if not comps:
                continue
            names: list[str] = []
            if isinstance(comps, list):
                names = [str(c).strip() for c in comps if c]
            elif isinstance(comps, str):
                names = [c.strip() for c in comps.split(",") if c.strip()]
            for name in names:
                if name:
                    competitor_data[name][outcome] += 1

    _extract_competitors(open_rows, "open")
    _extract_competitors(won_rows, "won")
    _extract_competitors(lost_rows, "lost")

    if not competitor_data:
        return {
            "battle_cards": [],
            "top_competitor": None,
            "recommendations": [
                "Start tracking competitors on deals — add competitor names to the deal record to enable battle-card generation.",
                "Review lost deals from the last quarter and identify which competitors were mentioned.",
                "Set up a win/loss debrief process to capture competitor intelligence systematically.",
            ],
            "generated_at": now.isoformat() + "Z",
        }

    # Build sorted competitor list for context
    competitor_list = []
    for name, counts in competitor_data.items():
        total_closed = counts["won"] + counts["lost"]
        win_rate = round(counts["won"] / total_closed * 100) if total_closed > 0 else None
        encounter_count = counts["open"] + counts["won"] + counts["lost"]
        competitor_list.append({
            "competitor": name,
            "encounter_count": encounter_count,
            "open_count": counts["open"],
            "won_count": counts["won"],
            "lost_count": counts["lost"],
            "win_rate": win_rate,
        })

    competitor_list.sort(key=lambda c: -c["encounter_count"])
    top_competitor = competitor_list[0]["competitor"] if competitor_list else None

    context_lines = [
        "Competitor encounter data from CRM deals (last 90 days):",
    ]
    for c in competitor_list[:6]:
        wr = f"{c['win_rate']}%" if c["win_rate"] is not None else "no closed data"
        context_lines.append(
            f"- {c['competitor']}: {c['encounter_count']} encounters, win rate {wr} "
            f"({c['won_count']} won, {c['lost_count']} lost, {c['open_count']} open)"
        )
    context = "\n".join(context_lines)

    default_battle_cards = [
        {
            "competitor": c["competitor"],
            "encounter_count": c["encounter_count"],
            "win_rate": c["win_rate"],
            "key_differentiators": [
                "Superior integration ecosystem with 200+ native connectors vs limited options.",
                "Dedicated customer success team with guaranteed 2-hour response SLA.",
                "Transparent pricing with no hidden implementation or migration fees.",
            ],
            "objection_responses": [
                "If they claim lower price: our TCO over 3 years is typically 30% lower once implementation costs are factored in.",
                "If they claim more features: our platform focuses on the 20% of features that drive 80% of outcomes — less noise, faster adoption.",
                "If they claim better support: we offer a named CSM from day one; ask them who your point of contact will be post-sale.",
            ],
            "positioning": f"Unlike {c['competitor']}, we focus on outcomes over features — faster time-to-value with lower total cost of ownership.",
        }
        for c in competitor_list[:3]
    ]
    default_recs = [
        f"Prioritise battle card training for {top_competitor} — they appear most frequently in the pipeline.",
        "Run a quarterly win/loss review focused on competitive deals to keep intelligence fresh.",
        "Add competitor tracking as a required field on all deals over $10K to improve data coverage.",
    ]

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1200,
            system=_BATTLE_CARD_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg.content[0].text.strip() if msg.content else "{}"
        data = json.loads(raw)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    raw_cards = data.get("battle_cards", [])
    if not isinstance(raw_cards, list) or len(raw_cards) == 0:
        raw_cards = []

    # Merge AI card content with our computed metrics
    merged_cards = []
    comp_lookup = {c["competitor"]: c for c in competitor_list}
    seen_competitors = set()

    for ai_card in raw_cards[:6]:
        name = str(ai_card.get("competitor", "")).strip()
        if not name or name in seen_competitors:
            continue
        seen_competitors.add(name)
        metrics = comp_lookup.get(name, {"encounter_count": 0, "win_rate": None})
        merged_cards.append({
            "competitor": name,
            "encounter_count": metrics.get("encounter_count", 0),
            "win_rate": metrics.get("win_rate"),
            "key_differentiators": [str(d) for d in (ai_card.get("key_differentiators") or [])[:3]],
            "objection_responses": [str(r) for r in (ai_card.get("objection_responses") or [])[:3]],
            "positioning": str(ai_card.get("positioning", "")),
        })

    # Ensure cards exist for top competitors if AI missed them
    for c in competitor_list[:3]:
        if c["competitor"] not in seen_competitors:
            default = next((d for d in default_battle_cards if d["competitor"] == c["competitor"]), None)
            if default:
                merged_cards.append(default)

    if not merged_cards:
        merged_cards = default_battle_cards

    raw_recs = data.get("recommendations", [])
    recommendations = [str(r) for r in (raw_recs if isinstance(raw_recs, list) else [])[:3]]
    while len(recommendations) < 3:
        recommendations.append(default_recs[len(recommendations) % 3])

    return {
        "battle_cards": merged_cards,
        "top_competitor": top_competitor,
        "recommendations": recommendations,
        "generated_at": now.isoformat() + "Z",
    }

# ---------------------------------------------------------------------------
# Phase 17f — AI workspace deal risk escalation digest
# ---------------------------------------------------------------------------

_RISK_ESCALATION_SYSTEM = """\
You are a senior sales operations AI analysing at-risk deals in a CRM pipeline.

Given a list of at-risk deals with health scores, days stale, and deal metadata, generate a targeted risk escalation digest.

Respond with valid JSON only, no prose outside JSON:
{
  "escalations": [
    {
      "deal_id": "uuid string",
      "suggested_action": "one concrete next action the rep should take today",
      "risk_factors": ["up to 3 specific risk factors for this deal"]
    }
  ],
  "recommendations": ["3 strategic recommendations for the sales manager to address pipeline risk"]
}
The escalations array must be in the same order as the deals provided.
"""


@router.get("/workspaces/{workspace_id}/ai/deals/risk-escalation")
@limiter.limit("5/minute")
async def get_deal_risk_escalation(
    request: Request,
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if str(current_user.workspace_id) != str(workspace_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    now = datetime.datetime.now(datetime.timezone.utc)

    # Query: top 5 at-risk open deals by health score ascending
    result = await db.execute(
        select(
            Deal.id,
            Deal.title,
            Deal.company,
            Deal.stage,
            Deal.value,
            Deal.health_score,
            Deal.ml_win_probability,
            Deal.stage_changed_at,
            Deal.competitors,
        )
        .where(
            Deal.workspace_id == workspace_id,
            Deal.stage.notin_(["closed_won", "closed_lost"]),
            Deal.health_score < 60,
        )
        .order_by(Deal.health_score.asc())
        .limit(5)
    )
    rows = result.all()

    if not rows:
        return {
            "escalations": [],
            "total_at_risk_value": 0.0,
            "recommendations": [
                "All open deals have health scores above 60 — no escalations needed right now.",
                "Schedule a pipeline review next week to maintain deal health before any slip occurs.",
                "Keep monitoring deal activity; health scores below 60 will trigger an escalation alert here.",
            ],
            "generated_at": now.isoformat() + "Z",
        }

    total_at_risk_value = sum(float(r[4] or 0) for r in rows)

    # Compute days_stale for each deal
    deal_context_parts = []
    deal_ids = []
    for r in rows:
        deal_id = str(r[0])
        deal_ids.append(deal_id)
        title = r[1] or "Untitled"
        company = r[2] or "Unknown"
        stage = r[3] or "unknown"
        value = float(r[4] or 0)
        health = int(r[5] or 0)
        win_prob = int(r[6] or 0) if r[6] is not None else 0
        stage_changed_at = r[7]
        competitors = r[8]

        days_stale = 0
        if stage_changed_at:
            sc = stage_changed_at.replace(tzinfo=datetime.timezone.utc) if not stage_changed_at.tzinfo else stage_changed_at
            days_stale = max(0, int((now - sc).total_seconds() / 86400))

        has_competitor = bool(competitors and (
            (isinstance(competitors, list) and len(competitors) > 0) or
            (isinstance(competitors, str) and competitors.strip())
        ))

        deal_context_parts.append(
            f"- deal_id={deal_id}, title=\"{title}\", company={company}, stage={stage}, "
            f"value=${value:,.0f}, health={health}, win_probability={win_prob}%, "
            f"days_stale={days_stale}, competitor_pressure={'yes' if has_competitor else 'no'}"
        )

    context = "At-risk deals (health < 60), sorted worst first:\n" + "\n".join(deal_context_parts)

    default_escalations = []
    for r in rows:
        deal_id = str(r[0])
        health = int(r[5] or 0)
        stage_changed_at = r[7]
        days_stale = 0
        if stage_changed_at:
            sc = stage_changed_at.replace(tzinfo=datetime.timezone.utc) if not stage_changed_at.tzinfo else stage_changed_at
            days_stale = max(0, int((now - sc).total_seconds() / 86400))
        default_escalations.append({
            "deal_id": deal_id,
            "suggested_action": f"Schedule an immediate check-in call — this deal has been stale for {days_stale} days with health score {health}.",
            "risk_factors": [
                f"Health score critically low at {health}/100.",
                f"No stage movement in {days_stale} days — likely stalled.",
                "Win probability below threshold — needs re-qualification.",
            ],
        })

    default_recs = [
        f"Immediately review the {len(rows)} at-risk deals (total value ${total_at_risk_value:,.0f}) in a pipeline call this week.",
        "Require reps to log a next-action date on every deal with health < 60 before end of day.",
        "Consider running a win/loss debrief on recently lost deals to identify patterns that predict health score decline.",
    ]

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1000,
            system=_RISK_ESCALATION_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg.content[0].text.strip() if msg.content else "{}"
        data = json.loads(raw)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    # Merge AI escalations with our computed deal rows
    ai_escalations = data.get("escalations", [])
    if not isinstance(ai_escalations, list):
        ai_escalations = []

    ai_by_id = {str(e.get("deal_id", "")): e for e in ai_escalations if isinstance(e, dict)}

    escalations = []
    for i, r in enumerate(rows):
        deal_id = str(r[0])
        title = r[1] or "Untitled"
        company = r[2] or "Unknown"
        stage = r[3] or "unknown"
        value = float(r[4] or 0)
        health = int(r[5] or 0)
        win_prob = int(r[6] or 0) if r[6] is not None else 0
        stage_changed_at = r[7]
        days_stale = 0
        if stage_changed_at:
            sc = stage_changed_at.replace(tzinfo=datetime.timezone.utc) if not stage_changed_at.tzinfo else stage_changed_at
            days_stale = max(0, int((now - sc).total_seconds() / 86400))

        ai_entry = ai_by_id.get(deal_id, {})
        suggested_action = str(ai_entry.get("suggested_action", default_escalations[i]["suggested_action"])).strip()
        if not suggested_action:
            suggested_action = default_escalations[i]["suggested_action"]
        raw_rf = ai_entry.get("risk_factors", [])
        risk_factors = [str(f) for f in (raw_rf if isinstance(raw_rf, list) else [])[:3]]
        if not risk_factors:
            risk_factors = default_escalations[i]["risk_factors"]

        escalations.append({
            "deal_id": deal_id,
            "title": title,
            "company": company,
            "stage": stage,
            "value": value,
            "health_score": health,
            "win_probability": win_prob,
            "days_stale": days_stale,
            "risk_factors": risk_factors,
            "suggested_action": suggested_action,
        })

    raw_recs = data.get("recommendations", [])
    recommendations = [str(r) for r in (raw_recs if isinstance(raw_recs, list) else [])[:3]]
    while len(recommendations) < 3:
        recommendations.append(default_recs[len(recommendations) % 3])

    return {
        "escalations": escalations,
        "total_at_risk_value": total_at_risk_value,
        "recommendations": recommendations,
        "generated_at": now.isoformat() + "Z",
    }


_MOMENTUM_SYSTEM = """\
You are a senior sales operations AI analysing deal momentum in a CRM pipeline.
Given a list of open deals with velocity scores, stage info, and days since last stage change, classify each into accelerating, decelerating, or stalled, and generate a momentum digest.
Respond with valid JSON only, no prose outside JSON:
{
  "accelerating": [{"deal_id": "uuid", "trend_description": "one sentence"}],
  "decelerating": [{"deal_id": "uuid", "trend_description": "one sentence"}],
  "stalled": [{"deal_id": "uuid", "trend_description": "one sentence"}],
  "momentum_index": 0,
  "insight": "one paragraph insight about pipeline momentum",
  "recommendations": ["rec1", "rec2", "rec3"]
}
momentum_index is 0-100 (100 = all deals accelerating, 0 = all stalled).
"""


@router.get("/workspaces/{workspace_id}/ai/deals/momentum")
@limiter.limit("5/minute")
async def get_deal_momentum(
    request: Request,
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if str(current_user.workspace_id) != str(workspace_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    now = datetime.datetime.now(datetime.timezone.utc)

    result = await db.execute(
        select(
            Deal.id,
            Deal.title,
            Deal.company,
            Deal.stage,
            Deal.value,
            Deal.health_score,
            Deal.ml_win_probability,
            Deal.stage_changed_at,
        )
        .where(
            Deal.workspace_id == workspace_id,
            Deal.stage.notin_(["closed_won", "closed_lost"]),
        )
        .order_by(Deal.stage_changed_at.asc())
    )
    rows = result.all()

    deals_data = []
    for r in rows:
        deal_id = str(r[0])
        title = r[1] or "Untitled"
        company = r[2] or ""
        stage = str(r[3] or "unknown")
        value = float(r[4] or 0)
        health = int(r[5] or 50)
        win_prob = int(r[6] or 50)
        stage_changed_at = r[7]
        if stage_changed_at and stage_changed_at.tzinfo is None:
            stage_changed_at = stage_changed_at.replace(tzinfo=datetime.timezone.utc)
        days_stale = (now - stage_changed_at).days if stage_changed_at else 30

        # velocity score: higher health + higher prob + fewer stale days = higher velocity
        velocity_score = max(0, min(100, int((health + win_prob) / 2 - days_stale * 2)))

        deals_data.append({
            "deal_id": deal_id,
            "title": title,
            "company": company,
            "stage": stage,
            "value": value,
            "health_score": health,
            "win_probability": win_prob,
            "days_stale": days_stale,
            "velocity_score": velocity_score,
        })

    if not deals_data:
        return {
            "accelerating": [],
            "decelerating": [],
            "stalled": [],
            "momentum_index": 0,
            "insight": "No open deals found to analyse momentum.",
            "recommendations": [
                "Add open deals to start tracking pipeline momentum.",
                "Ensure stage-change dates are kept up to date for accurate velocity scoring.",
                "Review your pipeline stages to capture deal progression accurately.",
            ],
            "generated_at": now.isoformat() + "Z",
        }

    # Build default classification by velocity score
    default_accelerating = [d for d in deals_data if d["velocity_score"] >= 60]
    default_decelerating = [d for d in deals_data if 30 <= d["velocity_score"] < 60]
    default_stalled = [d for d in deals_data if d["velocity_score"] < 30]

    total = len(deals_data)
    momentum_index = int((len(default_accelerating) * 100 + len(default_decelerating) * 50) / total) if total else 0

    context_lines = [
        f"Open Deals: {total}",
        f"Momentum Index: {momentum_index}/100",
        f"Accelerating (velocity>=60): {len(default_accelerating)}",
        f"Decelerating (30<=velocity<60): {len(default_decelerating)}",
        f"Stalled (velocity<30): {len(default_stalled)}",
        "Deal Details:",
    ]
    for d in deals_data[:10]:
        context_lines.append(
            f"  {d['deal_id']} | {d['title']} | {d['company']} | {d['stage']} "
            f"| health={d['health_score']} | prob={d['win_probability']}% "
            f"| stale={d['days_stale']}d | velocity={d['velocity_score']}"
        )
    context = "\n".join(context_lines)

    default_insight = (
        f"The pipeline has {total} open deals with a momentum index of {momentum_index}/100. "
        f"{len(default_accelerating)} deals are accelerating, {len(default_decelerating)} decelerating, "
        f"and {len(default_stalled)} stalled."
    )
    default_recs = [
        f"Prioritise the {len(default_stalled)} stalled deal(s) — schedule immediate outreach to revive momentum.",
        "Review decelerating deals weekly and identify blockers before they stall entirely.",
        "Use accelerating deals as templates — understand what's working and replicate those behaviours.",
    ]

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=700,
            system=_MOMENTUM_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg.content[0].text.strip() if msg.content else "{}"
        data = json.loads(raw)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    def _parse_group(key: str, default_list: list[dict]) -> list[dict]:
        raw_list = data.get(key, [])
        if not isinstance(raw_list, list):
            raw_list = []
        out = []
        deal_map = {d["deal_id"]: d for d in deals_data}
        for item in raw_list[:10]:
            if not isinstance(item, dict):
                continue
            did = str(item.get("deal_id", ""))
            trend = str(item.get("trend_description", ""))
            if did in deal_map:
                d = deal_map[did]
                out.append({
                    "deal_id": did,
                    "title": d["title"],
                    "velocity_score": d["velocity_score"],
                    "trend_description": trend or f"Velocity score {d['velocity_score']}",
                })
        if not out:
            out = [{"deal_id": d["deal_id"], "title": d["title"], "velocity_score": d["velocity_score"], "trend_description": f"Velocity score {d['velocity_score']}"} for d in default_list[:3]]
        return out

    accelerating = _parse_group("accelerating", default_accelerating)
    decelerating = _parse_group("decelerating", default_decelerating)
    stalled = _parse_group("stalled", default_stalled)

    ai_index = data.get("momentum_index")
    if isinstance(ai_index, (int, float)) and 0 <= ai_index <= 100:
        momentum_index = int(ai_index)

    insight = data.get("insight", default_insight)
    if not isinstance(insight, str) or not insight.strip():
        insight = default_insight

    raw_recs = data.get("recommendations", [])
    recommendations = [str(r) for r in (raw_recs if isinstance(raw_recs, list) else [])[:3]]
    while len(recommendations) < 3:
        recommendations.append(default_recs[len(recommendations) % 3])

    return {
        "accelerating": accelerating,
        "decelerating": decelerating,
        "stalled": stalled,
        "momentum_index": momentum_index,
        "insight": insight,
        "recommendations": recommendations,
        "generated_at": now.isoformat() + "Z",
    }


_VELOCITY_HEATMAP_SYSTEM = """\
You are a senior sales operations AI analysing pipeline stage transition velocity.
Given a list of stage transitions with median days and deal counts, identify bottlenecks and generate actionable insights.
Respond with valid JSON only, no prose outside JSON:
{
  "bottleneck_stage": "the stage name that causes the most delay",
  "fastest_transition": "from_stage -> to_stage",
  "slowest_transition": "from_stage -> to_stage",
  "insight": "one paragraph insight about the pipeline velocity patterns",
  "recommendations": ["rec1", "rec2", "rec3"]
}
"""


@router.get("/workspaces/{workspace_id}/ai/pipeline/velocity-heatmap")
@limiter.limit("5/minute")
async def get_pipeline_velocity_heatmap(
    request: Request,
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if str(current_user.workspace_id) != str(workspace_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    now = datetime.datetime.now(datetime.timezone.utc)
    cutoff = now - datetime.timedelta(days=180)

    result = await db.execute(
        select(
            ActivityEvent.description,
            ActivityEvent.created_at,
        )
        .where(
            ActivityEvent.workspace_id == workspace_id,
            ActivityEvent.type == "deal_moved",
            ActivityEvent.created_at >= cutoff,
        )
        .order_by(ActivityEvent.created_at.asc())
    )
    events = result.all()

    # Parse "Deal X moved from A to B" patterns and group by (from_stage, to_stage)
    import re as _re
    _stage_pat = _re.compile(r"moved from (\w+) to (\w+)", _re.IGNORECASE)

    transition_days: dict[tuple[str, str], list[int]] = {}
    prev_by_deal: dict[str, tuple[str, datetime.datetime]] = {}

    for desc, created_at in events:
        if not desc:
            continue
        m = _stage_pat.search(str(desc))
        if not m:
            continue
        from_stage = m.group(1).lower()
        to_stage = m.group(2).lower()
        key = (from_stage, to_stage)
        if created_at and created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=datetime.timezone.utc)
        # Use a synthetic deal key based on description prefix
        deal_key = str(desc).split(" moved")[0].strip()
        if deal_key in prev_by_deal and prev_by_deal[deal_key][0] == from_stage:
            days_taken = max(0, (created_at - prev_by_deal[deal_key][1]).days) if created_at and prev_by_deal[deal_key][1] else 7
            transition_days.setdefault(key, []).append(days_taken)
        prev_by_deal[deal_key] = (to_stage, created_at)
        transition_days.setdefault(key, [])

    # Build transitions list with median days
    transitions = []
    for (from_s, to_s), days_list in transition_days.items():
        if not days_list:
            continue
        sorted_days = sorted(days_list)
        mid = len(sorted_days) // 2
        median_days = sorted_days[mid] if len(sorted_days) % 2 else (sorted_days[mid - 1] + sorted_days[mid]) // 2
        transitions.append({
            "from_stage": from_s,
            "to_stage": to_s,
            "median_days": median_days,
            "deal_count": len(days_list),
        })

    transitions.sort(key=lambda t: -t["median_days"])

    default_bottleneck = transitions[0]["from_stage"] if transitions else "proposal"
    default_fastest = f"{transitions[-1]['from_stage']} -> {transitions[-1]['to_stage']}" if len(transitions) > 1 else "discovery -> qualified"
    default_slowest = f"{transitions[0]['from_stage']} -> {transitions[0]['to_stage']}" if transitions else "proposal -> negotiation"
    default_insight = (
        f"Analysed {len(transitions)} stage transitions over the last 180 days. "
        f"The biggest bottleneck is '{default_bottleneck}' with a median of "
        f"{transitions[0]['median_days'] if transitions else 0} days."
    )
    default_recs = [
        f"Focus on reducing time in '{default_bottleneck}' — identify the common blockers and create a stage-exit checklist.",
        "Review deals that took more than 2× the median days in any stage — these outliers hide systemic issues.",
        "Set stage-entry and stage-exit criteria for each stage to ensure consistent deal qualification.",
    ]

    if not transitions:
        return {
            "transitions": [],
            "bottleneck_stage": "unknown",
            "fastest_transition": "n/a",
            "slowest_transition": "n/a",
            "insight": "No stage transition data found for the last 180 days.",
            "recommendations": default_recs,
            "generated_at": now.isoformat() + "Z",
        }

    context_lines = [
        f"Analysed {len(transitions)} stage transitions (last 180 days):",
    ]
    for t in transitions[:10]:
        context_lines.append(
            f"  {t['from_stage']} -> {t['to_stage']}: median {t['median_days']}d, {t['deal_count']} deals"
        )
    context = "\n".join(context_lines)

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            system=_VELOCITY_HEATMAP_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg.content[0].text.strip() if msg.content else "{}"
        data = json.loads(raw)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    bottleneck_stage = data.get("bottleneck_stage", default_bottleneck)
    if not isinstance(bottleneck_stage, str) or not bottleneck_stage.strip():
        bottleneck_stage = default_bottleneck

    fastest_transition = data.get("fastest_transition", default_fastest)
    if not isinstance(fastest_transition, str) or not fastest_transition.strip():
        fastest_transition = default_fastest

    slowest_transition = data.get("slowest_transition", default_slowest)
    if not isinstance(slowest_transition, str) or not slowest_transition.strip():
        slowest_transition = default_slowest

    insight = data.get("insight", default_insight)
    if not isinstance(insight, str) or not insight.strip():
        insight = default_insight

    raw_recs = data.get("recommendations", [])
    recommendations = [str(r) for r in (raw_recs if isinstance(raw_recs, list) else [])[:3]]
    while len(recommendations) < 3:
        recommendations.append(default_recs[len(recommendations) % 3])

    return {
        "transitions": transitions,
        "bottleneck_stage": bottleneck_stage,
        "fastest_transition": fastest_transition,
        "slowest_transition": slowest_transition,
        "insight": insight,
        "recommendations": recommendations,
        "generated_at": now.isoformat() + "Z",
    }


_WIN_LOSS_SYSTEM = """\
You are a senior sales operations AI analysing win/loss patterns in a CRM pipeline.
Given aggregated win/loss deal data including stage win rates, value comparisons, and deal characteristics, generate actionable pattern insights.
Respond with valid JSON only, no prose outside JSON:
{
  "patterns": [
    {"pattern_type": "won", "description": "one insight about winning deals"},
    {"pattern_type": "won", "description": "another winning pattern"},
    {"pattern_type": "lost", "description": "one insight about losing deals"},
    {"pattern_type": "lost", "description": "another loss pattern"}
  ],
  "recommendations": ["rec1", "rec2", "rec3"]
}
Provide exactly 2 won patterns and 2 lost patterns.
"""


@router.get("/workspaces/{workspace_id}/ai/deals/win-loss-summary")
@limiter.limit("5/minute")
async def get_win_loss_summary(
    request: Request,
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if str(current_user.workspace_id) != str(workspace_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    now = datetime.datetime.now(datetime.timezone.utc)
    cutoff = now - datetime.timedelta(days=90)

    result = await db.execute(
        select(
            Deal.id,
            Deal.title,
            Deal.stage,
            Deal.value,
            Deal.health_score,
            Deal.ml_win_probability,
            Deal.created_at,
        )
        .where(
            Deal.workspace_id == workspace_id,
            Deal.stage.in_(["closed_won", "closed_lost"]),
            Deal.created_at >= cutoff,
        )
        .order_by(Deal.created_at.desc())
    )
    rows = result.all()

    won_rows = [r for r in rows if str(r[2]) == "closed_won"]
    lost_rows = [r for r in rows if str(r[2]) == "closed_lost"]

    won_count = len(won_rows)
    lost_count = len(lost_rows)
    total = won_count + lost_count
    win_rate = round(won_count / total * 100) if total else 0

    won_values = [float(r[3] or 0) for r in won_rows]
    lost_values = [float(r[3] or 0) for r in lost_rows]
    avg_won_value = round(sum(won_values) / len(won_values)) if won_values else 0
    avg_lost_value = round(sum(lost_values) / len(lost_values)) if lost_values else 0

    won_healths = [int(r[4] or 50) for r in won_rows]
    lost_healths = [int(r[4] or 50) for r in lost_rows]
    avg_won_health = round(sum(won_healths) / len(won_healths)) if won_healths else 0
    avg_lost_health = round(sum(lost_healths) / len(lost_healths)) if lost_healths else 0

    top_wins = [{"title": r[1], "value": float(r[3] or 0)} for r in sorted(won_rows, key=lambda x: float(x[3] or 0), reverse=True)[:3]]
    top_losses = [{"title": r[1], "value": float(r[3] or 0)} for r in sorted(lost_rows, key=lambda x: float(x[3] or 0), reverse=True)[:3]]

    default_patterns = [
        {"pattern_type": "won", "description": f"Won deals average {avg_won_health} health score vs {avg_lost_health} for losses — health is a strong win predictor."},
        {"pattern_type": "won", "description": f"Average won deal value is ${avg_won_value:,.0f}, suggesting deals in this range are well-qualified."},
        {"pattern_type": "lost", "description": f"Lost deals average ${avg_lost_value:,.0f} in value — review if pricing or scope is misaligned for this segment."},
        {"pattern_type": "lost", "description": f"Lost deals show lower engagement scores — earlier health monitoring could flag at-risk deals sooner."},
    ]
    default_recs = [
        f"Focus on replicating the behaviours of the top {min(3, won_count)} won deals — debrief with the winning reps this week.",
        "Implement a deal health review at every stage gate to catch declining deals before they reach proposal.",
        f"Analyse the top {min(3, lost_count)} lost deals for common objection patterns and build battlecard responses.",
    ]

    if total == 0:
        return {
            "win_rate": 0,
            "avg_won_value": 0,
            "avg_lost_value": 0,
            "won_count": 0,
            "lost_count": 0,
            "avg_won_health": 0,
            "avg_lost_health": 0,
            "top_wins": [],
            "top_losses": [],
            "patterns": [],
            "recommendations": default_recs,
            "generated_at": now.isoformat() + "Z",
        }

    context_lines = [
        f"Last 90 days — Won: {won_count} deals, Lost: {lost_count} deals, Win Rate: {win_rate}%",
        f"Avg Won Value: ${avg_won_value:,.0f}, Avg Lost Value: ${avg_lost_value:,.0f}",
        f"Avg Won Health: {avg_won_health}, Avg Lost Health: {avg_lost_health}",
    ]
    if top_wins:
        context_lines.append("Top Wins: " + ", ".join(f"{w['title']} (${w['value']:,.0f})" for w in top_wins))
    if top_losses:
        context_lines.append("Top Losses: " + ", ".join(f"{l['title']} (${l['value']:,.0f})" for l in top_losses))
    context = "\n".join(context_lines)

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
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    raw_patterns = data.get("patterns", [])
    patterns = []
    for p in (raw_patterns if isinstance(raw_patterns, list) else [])[:4]:
        if isinstance(p, dict):
            pt = str(p.get("pattern_type", "won"))
            desc = str(p.get("description", ""))
            if pt in ("won", "lost") and desc:
                patterns.append({"pattern_type": pt, "description": desc})
    if not patterns:
        patterns = default_patterns

    raw_recs = data.get("recommendations", [])
    recommendations = [str(r) for r in (raw_recs if isinstance(raw_recs, list) else [])[:3]]
    while len(recommendations) < 3:
        recommendations.append(default_recs[len(recommendations) % 3])

    return {
        "win_rate": win_rate,
        "avg_won_value": avg_won_value,
        "avg_lost_value": avg_lost_value,
        "won_count": won_count,
        "lost_count": lost_count,
        "avg_won_health": avg_won_health,
        "avg_lost_health": avg_lost_health,
        "top_wins": top_wins,
        "top_losses": top_losses,
        "patterns": patterns,
        "recommendations": recommendations,
        "generated_at": now.isoformat() + "Z",
    }

_SALES_FORECAST_SYSTEM = """\
You are a senior sales operations AI generating a revenue forecast for a CRM pipeline.
Given the weighted pipeline value, best-case, worst-case, deal count, and stage breakdown, generate a concise forecast narrative and 3 adjustment factors.
Respond with valid JSON only, no prose outside JSON:
{
  "forecast_narrative": "2-3 sentence forecast summary",
  "adjustments": [
    {"factor": "factor name", "impact": "positive", "magnitude": "high"},
    {"factor": "factor name", "impact": "negative", "magnitude": "medium"},
    {"factor": "factor name", "impact": "positive", "magnitude": "low"}
  ]
}
impact must be "positive" or "negative". magnitude must be "high", "medium", or "low".
Provide exactly 3 adjustments.
"""


@router.get("/workspaces/{workspace_id}/ai/deals/sales-forecast")
@limiter.limit("5/minute")
async def get_sales_forecast(
    request: Request,
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if str(current_user.workspace_id) != str(workspace_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    now = datetime.datetime.now(datetime.timezone.utc)

    result = await db.execute(
        select(
            Deal.id,
            Deal.stage,
            Deal.value,
            Deal.health_score,
            Deal.ml_win_probability,
        )
        .where(
            Deal.workspace_id == workspace_id,
            Deal.stage.notin_(["closed_won", "closed_lost"]),
        )
    )
    rows = result.all()

    deal_count = len(rows)

    if deal_count == 0:
        return {
            "weighted_pipeline": 0,
            "best_case": 0,
            "worst_case": 0,
            "deal_count": 0,
            "stage_breakdown": [],
            "forecast_narrative": "No open deals found. Add deals to the pipeline to generate a sales forecast.",
            "adjustments": [
                {"factor": "Pipeline coverage", "impact": "negative", "magnitude": "high"},
                {"factor": "New deal creation", "impact": "positive", "magnitude": "medium"},
                {"factor": "Lead qualification", "impact": "positive", "magnitude": "low"},
            ],
            "generated_at": now.isoformat() + "Z",
        }

    # Compute weighted pipeline, best case, worst case
    weighted_pipeline = 0.0
    best_case = 0.0
    worst_case = 0.0
    stage_totals: dict[str, dict] = {}

    for row in rows:
        value = float(row[2] or 0)
        health = int(row[3] or 50)
        win_prob = float(row[4] or 0.5)
        stage = str(row[1])

        weighted_pipeline += value * win_prob
        if health > 60:
            best_case += value
        if health < 50:
            worst_case += value * 0.5

        if stage not in stage_totals:
            stage_totals[stage] = {"weighted_value": 0.0, "count": 0}
        stage_totals[stage]["weighted_value"] += value * win_prob
        stage_totals[stage]["count"] += 1

    weighted_pipeline = round(weighted_pipeline)
    best_case = round(best_case)
    worst_case = round(worst_case)

    stage_breakdown = [
        {"stage": s, "weighted_value": round(v["weighted_value"]), "count": v["count"]}
        for s, v in sorted(stage_totals.items(), key=lambda x: -x[1]["weighted_value"])
    ]

    context_lines = [
        f"Open deals: {deal_count}",
        f"Weighted pipeline: ${weighted_pipeline:,.0f}",
        f"Best case (health>60): ${best_case:,.0f}",
        f"Worst case (health<50, 50% likely): ${worst_case:,.0f}",
        "Stage breakdown: " + ", ".join(
            f"{b['stage']} ${b['weighted_value']:,.0f} ({b['count']} deals)"
            for b in stage_breakdown
        ),
    ]
    context = "\n".join(context_lines)

    default_narrative = (
        f"Your pipeline holds {deal_count} open deals with a weighted forecast of ${weighted_pipeline:,.0f}. "
        f"Best-case revenue from highly engaged deals is ${best_case:,.0f}, while at-risk deals contribute a worst-case baseline of ${worst_case:,.0f}. "
        "Focus on improving health scores in low-probability stages to close the gap between scenarios."
    )
    default_adjustments = [
        {"factor": "Deal health distribution", "impact": "positive" if best_case > worst_case else "negative", "magnitude": "high"},
        {"factor": "Win probability alignment", "impact": "positive", "magnitude": "medium"},
        {"factor": "Stage concentration risk", "impact": "negative" if len(stage_breakdown) < 3 else "positive", "magnitude": "low"},
    ]

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            system=_SALES_FORECAST_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg.content[0].text.strip() if msg.content else "{}"
        data = json.loads(raw)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    forecast_narrative = str(data.get("forecast_narrative", "")).strip() or default_narrative

    raw_adjs = data.get("adjustments", [])
    adjustments = []
    for a in (raw_adjs if isinstance(raw_adjs, list) else [])[:3]:
        if isinstance(a, dict):
            factor = str(a.get("factor", ""))
            impact = str(a.get("impact", "positive"))
            magnitude = str(a.get("magnitude", "medium"))
            if factor and impact in ("positive", "negative") and magnitude in ("high", "medium", "low"):
                adjustments.append({"factor": factor, "impact": impact, "magnitude": magnitude})
    while len(adjustments) < 3:
        adjustments.append(default_adjustments[len(adjustments) % 3])

    return {
        "weighted_pipeline": weighted_pipeline,
        "best_case": best_case,
        "worst_case": worst_case,
        "deal_count": deal_count,
        "stage_breakdown": stage_breakdown,
        "forecast_narrative": forecast_narrative,
        "adjustments": adjustments,
        "generated_at": now.isoformat() + "Z",
    }

_DEAL_AGE_SYSTEM = """\
You are a senior sales operations AI analysing the age distribution of open CRM deals.
Given deal count and total value per age bucket (<30d, 30-60d, 60-90d, >90d), plus the oldest and newest deal and average pipeline age, generate an aging insight and 3 recommendations.
Respond with valid JSON only, no prose outside JSON:
{
  "aging_insight": "2-3 sentence insight about pipeline aging",
  "recommendations": ["rec1", "rec2", "rec3"]
}
Provide exactly 3 recommendations.
"""


@router.get("/workspaces/{workspace_id}/ai/deals/age-distribution")
@limiter.limit("5/minute")
async def get_deal_age_distribution(
    request: Request,
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if str(current_user.workspace_id) != str(workspace_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    now = datetime.datetime.now(datetime.timezone.utc)

    result = await db.execute(
        select(Deal.id, Deal.title, Deal.value, Deal.created_at)
        .where(
            Deal.workspace_id == workspace_id,
            Deal.stage.notin_(["closed_won", "closed_lost"]),
        )
        .order_by(Deal.created_at.asc())
    )
    rows = result.all()

    if not rows:
        return {
            "buckets": [
                {"label": "<30d", "count": 0, "total_value": 0, "pct_of_pipeline": 0},
                {"label": "30-60d", "count": 0, "total_value": 0, "pct_of_pipeline": 0},
                {"label": "60-90d", "count": 0, "total_value": 0, "pct_of_pipeline": 0},
                {"label": ">90d", "count": 0, "total_value": 0, "pct_of_pipeline": 0},
            ],
            "oldest_deal": None,
            "newest_deal": None,
            "avg_age_days": 0,
            "aging_insight": "No open deals found in the pipeline.",
            "recommendations": [
                "Create new deals in the pipeline to start tracking age distribution.",
                "Import existing opportunities from your CRM or spreadsheet.",
                "Set up inbound lead capture to automatically create deals.",
            ],
            "generated_at": now.isoformat() + "Z",
        }

    bucket_labels = ["<30d", "30-60d", "60-90d", ">90d"]
    bucket_data: dict[str, dict] = {b: {"count": 0, "total_value": 0.0} for b in bucket_labels}

    total_pipeline = 0.0
    ages = []
    oldest = None
    newest = None

    for row in rows:
        title = str(row[1])
        value = float(row[2] or 0)
        created_at = row[3]
        if created_at and created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=datetime.timezone.utc)
        days = (now - created_at).days if created_at else 0
        ages.append(days)
        total_pipeline += value

        if days < 30:
            bucket = "<30d"
        elif days < 60:
            bucket = "30-60d"
        elif days < 90:
            bucket = "60-90d"
        else:
            bucket = ">90d"

        bucket_data[bucket]["count"] += 1
        bucket_data[bucket]["total_value"] += value

        if oldest is None or days > oldest["days"]:
            oldest = {"title": title, "days": days}
        if newest is None or days < newest["days"]:
            newest = {"title": title, "days": days}

    avg_age_days = round(sum(ages) / len(ages)) if ages else 0

    buckets = [
        {
            "label": label,
            "count": bucket_data[label]["count"],
            "total_value": round(bucket_data[label]["total_value"]),
            "pct_of_pipeline": round(bucket_data[label]["total_value"] / total_pipeline * 100) if total_pipeline > 0 else 0,
        }
        for label in bucket_labels
    ]

    default_insight = (
        f"Your pipeline has {len(rows)} open deals with an average age of {avg_age_days} days. "
        f"The oldest deal has been open for {oldest['days']} days — review whether it is still progressing. "
        "Focus on clearing stale deals to keep pipeline accuracy high."
    )
    default_recs = [
        f"Review the {bucket_data['>90d']['count']} deals older than 90 days — close or disqualify those with no recent activity.",
        "Set a maximum pipeline age policy (e.g. 120 days) and automate health-score alerts for deals approaching it.",
        "Run a weekly aging report to identify deals at risk of becoming stale before they miss the quarter.",
    ]

    old_deal_count = bucket_data[">90d"]["count"]
    context_lines = [
        f"Open deals: {len(rows)}, avg age: {avg_age_days} days",
        f"<30d: {bucket_data['<30d']['count']} deals (${bucket_data['<30d']['total_value']:,.0f})",
        f"30-60d: {bucket_data['30-60d']['count']} deals (${bucket_data['30-60d']['total_value']:,.0f})",
        f"60-90d: {bucket_data['60-90d']['count']} deals (${bucket_data['60-90d']['total_value']:,.0f})",
        f">90d: {old_deal_count} deals (${bucket_data['>90d']['total_value']:,.0f})",
        f"Oldest deal: {oldest['title']} at {oldest['days']} days",
        f"Newest deal: {newest['title']} at {newest['days']} days",
    ]
    context = "\n".join(context_lines)

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=350,
            system=_DEAL_AGE_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg.content[0].text.strip() if msg.content else "{}"
        data = json.loads(raw)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    aging_insight = str(data.get("aging_insight", "")).strip() or default_insight
    raw_recs = data.get("recommendations", [])
    recommendations = [str(r) for r in (raw_recs if isinstance(raw_recs, list) else [])[:3]]
    while len(recommendations) < 3:
        recommendations.append(default_recs[len(recommendations) % 3])

    return {
        "buckets": buckets,
        "oldest_deal": oldest,
        "newest_deal": newest,
        "avg_age_days": avg_age_days,
        "aging_insight": aging_insight,
        "recommendations": recommendations,
        "generated_at": now.isoformat() + "Z",
    }

_DEAL_HEALTH_TREND_SYSTEM = """\
You are a senior sales operations AI analysing deal health trends across a CRM pipeline.
Given average health per stage, overall health, trend direction, and at-risk deal count, generate a health narrative and 3 recommendations.
Respond with valid JSON only, no prose outside JSON:
{
  "health_narrative": "2-3 sentence narrative about pipeline health trends",
  "recommendations": ["rec1", "rec2", "rec3"]
}
Provide exactly 3 recommendations.
"""


@router.get("/workspaces/{workspace_id}/ai/deals/health-trend")
@limiter.limit("5/minute")
async def get_deal_health_trend(
    request: Request,
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if str(current_user.workspace_id) != str(workspace_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    now = datetime.datetime.now(datetime.timezone.utc)

    result = await db.execute(
        select(Deal.stage, Deal.health_score)
        .where(
            Deal.workspace_id == workspace_id,
            Deal.stage.notin_(["closed_won", "closed_lost"]),
        )
    )
    rows = result.all()

    if not rows:
        return {
            "stage_health": [],
            "overall_avg_health": 0,
            "trend_direction": "stable",
            "at_risk_count": 0,
            "health_narrative": "No open deals found in the pipeline. Add deals to start tracking health trends.",
            "recommendations": [
                "Create your first deals to begin pipeline health tracking.",
                "Configure deal health scoring to reflect your sales process.",
                "Set up automated health score updates based on deal activity.",
            ],
            "generated_at": now.isoformat() + "Z",
        }

    stage_order = ["discovery", "qualified", "proposal", "negotiation", "closing", "other"]
    stage_buckets: dict[str, list[int]] = {}
    at_risk_count = 0

    for row in rows:
        stage = str(row[0])
        health = int(row[1] or 50)
        if health < 40:
            at_risk_count += 1
        if stage not in stage_buckets:
            stage_buckets[stage] = []
        stage_buckets[stage].append(health)

    stage_health = []
    for stage in stage_order:
        if stage in stage_buckets:
            healths = stage_buckets[stage]
            stage_health.append({
                "stage": stage,
                "avg_health": round(sum(healths) / len(healths)),
                "count": len(healths),
            })
    # Add any stages not in the canonical order
    for stage, healths in stage_buckets.items():
        if stage not in stage_order:
            stage_health.append({
                "stage": stage,
                "avg_health": round(sum(healths) / len(healths)),
                "count": len(healths),
            })

    all_healths = [int(r[1] or 50) for r in rows]
    overall_avg_health = round(sum(all_healths) / len(all_healths))

    # Trend: compare early-pipeline (discovery+qualified) vs late-pipeline (proposal+negotiation)
    early_stages = {"discovery", "qualified"}
    late_stages = {"proposal", "negotiation", "closing"}
    early_healths = [int(r[1] or 50) for r in rows if str(r[0]) in early_stages]
    late_healths = [int(r[1] or 50) for r in rows if str(r[0]) in late_stages]

    early_avg = sum(early_healths) / len(early_healths) if early_healths else None
    late_avg = sum(late_healths) / len(late_healths) if late_healths else None

    if early_avg is not None and late_avg is not None:
        diff = late_avg - early_avg
        trend_direction = "improving" if diff > 5 else "declining" if diff < -5 else "stable"
    else:
        trend_direction = "stable"

    default_narrative = (
        f"Your pipeline has an overall average health score of {overall_avg_health}. "
        f"{at_risk_count} deal{'s are' if at_risk_count != 1 else ' is'} at risk with health below 40. "
        f"Pipeline health is {trend_direction} from early to late stages."
    )
    default_recs = [
        "Schedule a deal health review for all deals below 40 — these are at risk of being lost without immediate action.",
        "Set automated alerts when deal health drops below 50 so reps can intervene before deals stall.",
        "Review the healthiest deals for best practices that can be replicated across the team.",
    ]

    context_lines = [
        f"Open deals: {len(rows)}, overall avg health: {overall_avg_health}, at-risk (<40): {at_risk_count}",
        f"Trend direction (early vs late pipeline): {trend_direction}",
    ]
    for sh in stage_health:
        context_lines.append(f"{sh['stage']}: avg health {sh['avg_health']}, {sh['count']} deals")
    context = "\n".join(context_lines)

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=350,
            system=_DEAL_HEALTH_TREND_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg.content[0].text.strip() if msg.content else "{}"
        data = json.loads(raw)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    health_narrative = str(data.get("health_narrative", "")).strip() or default_narrative
    raw_recs = data.get("recommendations", [])
    recommendations = [str(r) for r in (raw_recs if isinstance(raw_recs, list) else [])[:3]]
    while len(recommendations) < 3:
        recommendations.append(default_recs[len(recommendations) % 3])

    return {
        "stage_health": stage_health,
        "overall_avg_health": overall_avg_health,
        "trend_direction": trend_direction,
        "at_risk_count": at_risk_count,
        "health_narrative": health_narrative,
        "recommendations": recommendations,
        "generated_at": now.isoformat() + "Z",
    }

# ---------------------------------------------------------------------------
# Phase 17m: Deal stagnation detector
# ---------------------------------------------------------------------------

_DEAL_STAGNATION_SYSTEM = """\
You are a senior sales operations AI analysing deal stagnation across a CRM pipeline.
Given information about deals that have been stuck in their current stage beyond the threshold, stage average days, and the most stagnant deal, generate a stagnation narrative and 3 recommendations.
Respond with valid JSON only, no prose outside JSON:
{
  "stagnation_narrative": "2-3 sentence narrative about pipeline stagnation",
  "recommendations": ["rec1", "rec2", "rec3"]
}
Provide exactly 3 recommendations.
"""


@router.get("/workspaces/{workspace_id}/ai/deals/stagnation")
@limiter.limit("5/minute")
async def get_deal_stagnation(
    request: Request,
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if str(current_user.workspace_id) != str(workspace_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    now = datetime.datetime.now(datetime.timezone.utc)
    STAGNANT_THRESHOLD_DAYS = 14

    result = await db.execute(
        select(Deal.id, Deal.title, Deal.stage, Deal.health_score, Deal.stage_changed_at)
        .where(
            Deal.workspace_id == workspace_id,
            Deal.stage.notin_(["closed_won", "closed_lost"]),
        )
    )
    rows = result.all()

    if not rows:
        return {
            "stagnant_deals": [],
            "stage_avg_days": [],
            "total_stagnant_count": 0,
            "most_stagnant": None,
            "stagnation_narrative": "No open deals found in the pipeline.",
            "recommendations": [
                "Add deals to the pipeline to start tracking stagnation.",
                "Set up automated reminders for deals approaching the stagnation threshold.",
                "Define stagnation policies per stage to catch slow deals early.",
            ],
            "generated_at": now.isoformat() + "Z",
        }

    # Compute days in stage for each deal
    stage_days_buckets: dict[str, list[float]] = {}
    deal_infos = []
    for row in rows:
        deal_id, title, stage, health_score, stage_changed_at = row
        if stage_changed_at is None:
            days_in_stage = 0.0
        else:
            if stage_changed_at.tzinfo is None:
                stage_changed_at = stage_changed_at.replace(tzinfo=datetime.timezone.utc)
            days_in_stage = max(0.0, (now - stage_changed_at).total_seconds() / 86400)

        deal_infos.append({
            "id": str(deal_id),
            "title": str(title),
            "stage": str(stage),
            "health_score": int(health_score or 50),
            "days_in_stage": round(days_in_stage),
        })
        stage_days_buckets.setdefault(str(stage), []).append(days_in_stage)

    # Stage average days
    stage_order = ["discovery", "qualified", "proposal", "negotiation", "closing"]
    stage_avg_days = []
    for stage in stage_order:
        if stage in stage_days_buckets:
            days_list = stage_days_buckets[stage]
            stage_avg_days.append({
                "stage": stage,
                "avg_days": round(sum(days_list) / len(days_list)),
                "count": len(days_list),
            })
    for stage, days_list in stage_days_buckets.items():
        if stage not in stage_order:
            stage_avg_days.append({
                "stage": stage,
                "avg_days": round(sum(days_list) / len(days_list)),
                "count": len(days_list),
            })

    # Stagnant deals
    stagnant_deals = [d for d in deal_infos if d["days_in_stage"] > STAGNANT_THRESHOLD_DAYS]
    stagnant_deals.sort(key=lambda d: d["days_in_stage"], reverse=True)
    total_stagnant_count = len(stagnant_deals)

    most_stagnant = (
        {"title": stagnant_deals[0]["title"], "days": stagnant_deals[0]["days_in_stage"]}
        if stagnant_deals else None
    )

    default_narrative = (
        f"{total_stagnant_count} deal{'s are' if total_stagnant_count != 1 else ' is'} stagnant "
        f"(stuck for more than {STAGNANT_THRESHOLD_DAYS} days in the current stage). "
        f"Pipeline has {len(rows)} open deals total."
    )
    default_recs = [
        f"Schedule deal reviews for all {total_stagnant_count} stagnant deals this week — each one needs an action plan or should be disqualified.",
        "Set automated 14-day stage-age alerts so reps receive a nudge before a deal becomes fully stagnant.",
        "Review the stage with the highest average days and adjust qualification criteria to prevent deals from entering unprepared.",
    ]

    context_lines = [
        f"Open deals: {len(rows)}, stagnant (>{STAGNANT_THRESHOLD_DAYS}d in stage): {total_stagnant_count}",
    ]
    if most_stagnant:
        context_lines.append(f"Most stagnant: {most_stagnant['title']} ({most_stagnant['days']} days)")
    for s in stage_avg_days:
        context_lines.append(f"{s['stage']}: avg {s['avg_days']}d, {s['count']} deals")
    context = "\n".join(context_lines)

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=350,
            system=_DEAL_STAGNATION_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg.content[0].text.strip() if msg.content else "{}"
        data = json.loads(raw)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    stagnation_narrative = str(data.get("stagnation_narrative", "")).strip() or default_narrative
    raw_recs = data.get("recommendations", [])
    recommendations = [str(r) for r in (raw_recs if isinstance(raw_recs, list) else [])[:3]]
    while len(recommendations) < 3:
        recommendations.append(default_recs[len(recommendations) % 3])

    return {
        "stagnant_deals": stagnant_deals,
        "stage_avg_days": stage_avg_days,
        "total_stagnant_count": total_stagnant_count,
        "most_stagnant": most_stagnant,
        "stagnation_narrative": stagnation_narrative,
        "recommendations": recommendations,
        "generated_at": now.isoformat() + "Z",
    }

# ---------------------------------------------------------------------------
# Phase 17n: Deal engagement gap analyser
# ---------------------------------------------------------------------------

_DEAL_ENGAGEMENT_GAP_SYSTEM = """\
You are a senior sales operations AI analysing deal engagement gaps across a CRM pipeline.
Given information about deals that have not been updated recently, average days since last activity, and total disengaged count, generate an engagement narrative and 3 recommendations.
Respond with valid JSON only, no prose outside JSON:
{
  "engagement_narrative": "2-3 sentence narrative about deal engagement gaps",
  "recommendations": ["rec1", "rec2", "rec3"]
}
Provide exactly 3 recommendations.
"""


@router.get("/workspaces/{workspace_id}/ai/deals/engagement-gap")
@limiter.limit("5/minute")
async def get_deal_engagement_gap(
    request: Request,
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if str(current_user.workspace_id) != str(workspace_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    now = datetime.datetime.now(datetime.timezone.utc)
    ENGAGEMENT_THRESHOLD_DAYS = 7

    result = await db.execute(
        select(Deal.id, Deal.title, Deal.stage, Deal.health_score, Deal.updated_at)
        .where(
            Deal.workspace_id == workspace_id,
            Deal.stage.notin_(["closed_won", "closed_lost"]),
        )
    )
    rows = result.all()

    if not rows:
        return {
            "disengaged_deals": [],
            "avg_days_since_activity": 0,
            "total_disengaged": 0,
            "top_disengaged": None,
            "engagement_narrative": "No open deals found in the pipeline.",
            "recommendations": [
                "Add deals to the pipeline to start tracking engagement.",
                "Set up a regular cadence of updates so deal records stay current.",
                "Define engagement SLAs per stage to ensure deals receive timely attention.",
            ],
            "generated_at": now.isoformat() + "Z",
        }

    deal_infos = []
    for row in rows:
        deal_id, title, stage, health_score, updated_at = row
        if updated_at is None:
            days_since = 0.0
        else:
            if updated_at.tzinfo is None:
                updated_at = updated_at.replace(tzinfo=datetime.timezone.utc)
            days_since = max(0.0, (now - updated_at).total_seconds() / 86400)
        deal_infos.append({
            "id": str(deal_id),
            "title": str(title),
            "stage": str(stage),
            "health_score": int(health_score or 50),
            "days_since_activity": round(days_since),
        })

    all_days = [d["days_since_activity"] for d in deal_infos]
    avg_days_since_activity = round(sum(all_days) / len(all_days)) if all_days else 0

    disengaged = [d for d in deal_infos if d["days_since_activity"] > ENGAGEMENT_THRESHOLD_DAYS]
    disengaged.sort(key=lambda d: d["days_since_activity"], reverse=True)
    total_disengaged = len(disengaged)

    top_disengaged = (
        {"title": disengaged[0]["title"], "days": disengaged[0]["days_since_activity"]}
        if disengaged else None
    )

    default_narrative = (
        f"{total_disengaged} deal{'s have' if total_disengaged != 1 else ' has'} not been updated "
        f"in more than {ENGAGEMENT_THRESHOLD_DAYS} days. "
        f"The pipeline averages {avg_days_since_activity} days since last activity across {len(rows)} open deals."
    )
    default_recs = [
        f"Review and update all {total_disengaged} disengaged deals this week — add notes, move stage, or disqualify each one.",
        f"Set a {ENGAGEMENT_THRESHOLD_DAYS}-day maximum engagement SLA: any deal without activity triggers an automatic rep alert.",
        "Add next-action dates to every active deal so reps have a clear cadence and deals don't drift without accountability.",
    ]

    context_lines = [
        f"Open deals: {len(rows)}, avg days since last update: {avg_days_since_activity}",
        f"Disengaged (>{ENGAGEMENT_THRESHOLD_DAYS}d without update): {total_disengaged}",
    ]
    if top_disengaged:
        context_lines.append(f"Most disengaged: {top_disengaged['title']} ({top_disengaged['days']} days)")
    for d in disengaged[:5]:
        context_lines.append(f"{d['title']} ({d['stage']}): {d['days_since_activity']}d, health {d['health_score']}")
    context = "\n".join(context_lines)

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=350,
            system=_DEAL_ENGAGEMENT_GAP_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg.content[0].text.strip() if msg.content else "{}"
        data = json.loads(raw)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    engagement_narrative = str(data.get("engagement_narrative", "")).strip() or default_narrative
    raw_recs = data.get("recommendations", [])
    recommendations = [str(r) for r in (raw_recs if isinstance(raw_recs, list) else [])[:3]]
    while len(recommendations) < 3:
        recommendations.append(default_recs[len(recommendations) % 3])

    return {
        "disengaged_deals": disengaged,
        "avg_days_since_activity": avg_days_since_activity,
        "total_disengaged": total_disengaged,
        "top_disengaged": top_disengaged,
        "engagement_narrative": engagement_narrative,
        "recommendations": recommendations,
        "generated_at": now.isoformat() + "Z",
    }

# ---------------------------------------------------------------------------
# Phase 17o: Deal value concentration analyser
# ---------------------------------------------------------------------------

_DEAL_VALUE_CONCENTRATION_SYSTEM = """\
You are a senior sales operations AI analysing pipeline value concentration risk.
Given information about deal values, concentration metrics, and herfindahl index, generate a concentration narrative and 3 recommendations.
Respond with valid JSON only, no prose outside JSON:
{
  "concentration_narrative": "2-3 sentence narrative about pipeline value concentration and risk",
  "recommendations": ["rec1", "rec2", "rec3"]
}
Provide exactly 3 recommendations.
"""


@router.get("/workspaces/{workspace_id}/ai/deals/value-concentration")
@limiter.limit("5/minute")
async def get_deal_value_concentration(
    request: Request,
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if str(current_user.workspace_id) != str(workspace_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    now = datetime.datetime.now(datetime.timezone.utc)

    result = await db.execute(
        select(Deal.id, Deal.title, Deal.stage, Deal.value, Deal.ml_win_probability)
        .where(
            Deal.workspace_id == workspace_id,
            Deal.stage.notin_(["closed_won", "closed_lost"]),
        )
        .order_by(Deal.value.desc())
    )
    rows = result.all()

    if not rows:
        return {
            "deals_ranked": [],
            "total_pipeline": 0,
            "top_deal_pct": 0,
            "top3_pct": 0,
            "concentration_risk": "low",
            "herfindahl_index": 0,
            "concentration_narrative": "No open deals found in the pipeline.",
            "recommendations": [
                "Add deals to the pipeline to start tracking value concentration.",
                "Aim for a diverse pipeline where no single deal exceeds 25% of total value.",
                "Track concentration metrics monthly to catch over-reliance on single deals early.",
            ],
            "generated_at": now.isoformat() + "Z",
        }

    total_pipeline = sum(float(r[3] or 0) for r in rows)

    if total_pipeline == 0:
        deals_ranked = [
            {"id": str(r[0]), "title": str(r[1]), "stage": str(r[2]),
             "value": float(r[3] or 0), "pct_of_pipeline": 0}
            for r in rows
        ]
        return {
            "deals_ranked": deals_ranked,
            "total_pipeline": 0,
            "top_deal_pct": 0,
            "top3_pct": 0,
            "concentration_risk": "low",
            "herfindahl_index": 0,
            "concentration_narrative": "All open deals have zero value — update deal values to see concentration risk.",
            "recommendations": [
                "Set deal values to accurately track your pipeline's financial exposure.",
                "Aim for a diverse pipeline where no single deal exceeds 25% of total value.",
                "Track concentration metrics monthly to catch over-reliance on single deals early.",
            ],
            "generated_at": now.isoformat() + "Z",
        }

    deals_ranked = []
    for r in rows:
        value = float(r[3] or 0)
        pct = round((value / total_pipeline) * 100, 1) if total_pipeline > 0 else 0
        deals_ranked.append({
            "id": str(r[0]),
            "title": str(r[1]),
            "stage": str(r[2]),
            "value": value,
            "pct_of_pipeline": pct,
        })

    top_deal_pct = deals_ranked[0]["pct_of_pipeline"] if deals_ranked else 0
    top3_values = sum(d["value"] for d in deals_ranked[:3])
    top3_pct = round((top3_values / total_pipeline) * 100, 1) if total_pipeline > 0 else 0

    # Herfindahl-Hirschman Index (0–10000 scale)
    herfindahl_index = round(sum((d["value"] / total_pipeline) ** 2 for d in deals_ranked) * 10000)

    if top_deal_pct > 40 or herfindahl_index > 2500:
        concentration_risk = "high"
    elif top_deal_pct > 25 or herfindahl_index > 1500:
        concentration_risk = "medium"
    else:
        concentration_risk = "low"

    default_narrative = (
        f"Your pipeline of ${total_pipeline:,.0f} shows {concentration_risk} concentration risk. "
        f"The largest deal represents {top_deal_pct}% of total pipeline value "
        f"and the top 3 deals account for {top3_pct}%. "
        f"HHI score: {herfindahl_index}/10000."
    )
    default_recs = [
        f"Diversify the pipeline — the top deal at {top_deal_pct}% creates {'critical' if top_deal_pct > 40 else 'elevated'} single-deal risk.",
        "Prioritise adding 3–5 new mid-size deals this month to reduce concentration below the 25% threshold.",
        "Set pipeline health alerts when any single deal exceeds 30% of total value so leadership can act early.",
    ]

    context_lines = [
        f"Total pipeline: ${total_pipeline:,.0f}, deals: {len(rows)}, concentration risk: {concentration_risk}",
        f"Top deal: {top_deal_pct}%, top-3 deals: {top3_pct}%, HHI: {herfindahl_index}",
    ]
    for d in deals_ranked[:5]:
        context_lines.append(f"{d['title']} ({d['stage']}): ${d['value']:,.0f} ({d['pct_of_pipeline']}%)")
    context = "\n".join(context_lines)

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=350,
            system=_DEAL_VALUE_CONCENTRATION_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg.content[0].text.strip() if msg.content else "{}"
        data = json.loads(raw)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    concentration_narrative = str(data.get("concentration_narrative", "")).strip() or default_narrative
    raw_recs = data.get("recommendations", [])
    recommendations = [str(r) for r in (raw_recs if isinstance(raw_recs, list) else [])[:3]]
    while len(recommendations) < 3:
        recommendations.append(default_recs[len(recommendations) % 3])

    return {
        "deals_ranked": deals_ranked,
        "total_pipeline": round(total_pipeline, 2),
        "top_deal_pct": top_deal_pct,
        "top3_pct": top3_pct,
        "concentration_risk": concentration_risk,
        "herfindahl_index": herfindahl_index,
        "concentration_narrative": concentration_narrative,
        "recommendations": recommendations,
        "generated_at": now.isoformat() + "Z",
    }


_DEAL_CLOSE_DATE_ACCURACY_SYSTEM = """\
You are a senior sales operations AI analysing close date accuracy for deals.
Given data about closed deals and their expected vs actual close dates, generate an accuracy narrative and 3 recommendations.
Respond with valid JSON only, no prose outside JSON:
{
  "accuracy_narrative": "2-3 sentence narrative about close date prediction accuracy and its business impact",
  "recommendations": ["rec1", "rec2", "rec3"]
}
Provide exactly 3 recommendations.
"""


@router.get("/workspaces/{workspace_id}/ai/deals/close-date-accuracy")
@limiter.limit("5/minute")
async def get_deal_close_date_accuracy(
    request: Request,
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if str(current_user.workspace_id) != str(workspace_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    now = datetime.datetime.now(datetime.timezone.utc)
    cutoff = now - datetime.timedelta(days=90)

    result = await db.execute(
        select(
            Deal.id,
            Deal.title,
            Deal.stage,
            Deal.expected_close,
            Deal.stage_changed_at,
        )
        .where(
            Deal.workspace_id == workspace_id,
            Deal.stage.in_(["closed_won", "closed_lost"]),
            Deal.stage_changed_at >= cutoff,
        )
        .order_by(Deal.stage_changed_at.desc())
    )
    rows = result.all()

    on_time_count = 0
    late_count = 0
    early_count = 0
    slip_days_list: list[int] = []

    for r in rows:
        expected_close_str = r[3]
        stage_changed_at = r[4]
        if not expected_close_str:
            continue
        try:
            expected_date = datetime.date.fromisoformat(str(expected_close_str))
            if stage_changed_at is None:
                continue
            sc = stage_changed_at
            if sc.tzinfo is None:
                sc = sc.replace(tzinfo=datetime.timezone.utc)
            actual_date = sc.date()
            slip = (actual_date - expected_date).days
            if slip > 7:
                late_count += 1
                slip_days_list.append(slip)
            elif slip < -7:
                early_count += 1
            else:
                on_time_count += 1
        except (ValueError, AttributeError):
            continue

    total_with_expected = on_time_count + late_count + early_count
    accuracy_pct = round(on_time_count / total_with_expected * 100, 1) if total_with_expected > 0 else 100.0
    avg_slip_days = round(sum(slip_days_list) / len(slip_days_list), 1) if slip_days_list else 0.0
    total_closed = len(rows)

    default_narrative = (
        f"{total_closed} deals closed in the last 90 days with a close date accuracy of {accuracy_pct}%. "
        f"{on_time_count} were on time, {late_count} were late (avg {avg_slip_days:.0f}d slip), and {early_count} closed early. "
        f"{'Accuracy is strong — keep up the disciplined forecasting.' if accuracy_pct >= 70 else 'Improving forecast accuracy will help revenue planning and pipeline reliability.'}"
    )
    default_recs = [
        f"Review the {late_count} late-closing deals to identify common causes of slippage — process gaps, buyer delays, or poor qualification.",
        "Set a bi-weekly close-date audit so reps update expected dates before they become stale — stale dates erode forecast trust.",
        f"Celebrate the {on_time_count} on-time closes and share what made them predictable to reinforce accurate forecasting habits.",
    ]

    context_lines = [
        f"Total closed (90d): {total_closed}, with expected close date: {total_with_expected}",
        f"On-time: {on_time_count}, Late: {late_count}, Early: {early_count}",
        f"Accuracy: {accuracy_pct}%, Avg slip for late deals: {avg_slip_days}d",
    ]
    context = "\n".join(context_lines)

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            system=_DEAL_CLOSE_DATE_ACCURACY_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg.content[0].text.strip() if msg.content else "{}"
        data = json.loads(raw)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    accuracy_narrative = str(data.get("accuracy_narrative", "")).strip() or default_narrative
    raw_recs = data.get("recommendations", [])
    recommendations = [str(r) for r in (raw_recs if isinstance(raw_recs, list) else [])[:3]]
    while len(recommendations) < 3:
        recommendations.append(default_recs[len(recommendations) % 3])

    return {
        "total_closed": total_closed,
        "accuracy_pct": accuracy_pct,
        "avg_slip_days": avg_slip_days,
        "on_time_count": on_time_count,
        "late_count": late_count,
        "early_count": early_count,
        "accuracy_narrative": accuracy_narrative,
        "recommendations": recommendations,
        "generated_at": now.isoformat() + "Z",
    }


_REP_PERFORMANCE_SYSTEM = """\
You are a senior sales operations AI analysing sales rep performance data.
Given a leaderboard of reps with their closed deal counts, win rates, and revenue generated in the last 90 days, generate a performance narrative and 3 coaching recommendations.
Respond with valid JSON only, no prose outside JSON:
{
  "performance_narrative": "2-3 sentence narrative about overall rep performance patterns and standouts",
  "recommendations": ["rec1", "rec2", "rec3"]
}
Provide exactly 3 recommendations.
"""


@router.get("/workspaces/{workspace_id}/ai/deals/rep-performance")
@limiter.limit("5/minute")
async def get_rep_performance(
    request: Request,
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if str(current_user.workspace_id) != str(workspace_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    now = datetime.datetime.now(datetime.timezone.utc)
    cutoff = now - datetime.timedelta(days=90)

    result = await db.execute(
        select(
            Deal.id,
            Deal.stage,
            Deal.value,
            Deal.assigned_agent,
        )
        .where(
            Deal.workspace_id == workspace_id,
            Deal.stage.in_(["closed_won", "closed_lost"]),
            Deal.stage_changed_at >= cutoff,
        )
        .order_by(Deal.stage_changed_at.desc())
    )
    rows = result.all()

    # Group by rep name
    rep_map: dict[str, dict] = {}
    for r in rows:
        rep_name = str(r[3]).strip() if r[3] else "Unassigned"
        stage = str(r[1])
        value = float(r[2] or 0)
        if rep_name not in rep_map:
            rep_map[rep_name] = {"won": 0, "lost": 0, "revenue": 0.0}
        if stage == "closed_won":
            rep_map[rep_name]["won"] += 1
            rep_map[rep_name]["revenue"] += value
        else:
            rep_map[rep_name]["lost"] += 1

    reps = []
    for name, stats in rep_map.items():
        total = stats["won"] + stats["lost"]
        win_rate = round(stats["won"] / total * 100) if total > 0 else 0
        avg_deal = round(stats["revenue"] / stats["won"]) if stats["won"] > 0 else 0
        reps.append({
            "name": name,
            "won_count": stats["won"],
            "lost_count": stats["lost"],
            "win_rate": win_rate,
            "total_revenue": round(stats["revenue"], 2),
            "avg_deal_size": avg_deal,
        })

    reps.sort(key=lambda x: x["total_revenue"], reverse=True)
    top_rep = reps[0]["name"] if reps else None
    total_reps = len(reps)

    default_narrative = (
        f"{total_reps} rep{'s' if total_reps != 1 else ''} closed deals in the last 90 days. "
        + (f"{top_rep} leads the team in revenue." if top_rep else "No closed deals found.")
        + " Reviewing individual win rates alongside revenue reveals where coaching will have the highest impact."
    )
    default_recs = [
        "Pair top performers with lower-revenue reps for deal reviews to spread best practices across the team.",
        "Focus coaching on reps with low win rates — improving qualification and objection-handling can unlock significant revenue.",
        "Set individual revenue targets for next quarter based on each rep's 90-day baseline to create clear, motivating benchmarks.",
    ]

    context_lines = [f"Rep performance — last 90 days, {total_reps} rep(s):"]
    for rep in reps[:8]:
        context_lines.append(
            f"{rep['name']}: {rep['won_count']}W/{rep['lost_count']}L, "
            f"win rate {rep['win_rate']}%, revenue ${rep['total_revenue']:,.0f}, avg deal ${rep['avg_deal_size']:,.0f}"
        )
    context = "\n".join(context_lines)

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            system=_REP_PERFORMANCE_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg.content[0].text.strip() if msg.content else "{}"
        data = json.loads(raw)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    performance_narrative = str(data.get("performance_narrative", "")).strip() or default_narrative
    raw_recs = data.get("recommendations", [])
    recommendations = [str(r) for r in (raw_recs if isinstance(raw_recs, list) else [])[:3]]
    while len(recommendations) < 3:
        recommendations.append(default_recs[len(recommendations) % 3])

    return {
        "reps": reps,
        "top_rep": top_rep,
        "total_reps": total_reps,
        "performance_narrative": performance_narrative,
        "recommendations": recommendations,
        "generated_at": now.isoformat() + "Z",
    }


_PIPELINE_CONVERSION_FUNNEL_SYSTEM = """\
You are a senior sales operations AI analysing pipeline conversion funnel data.
Given per-stage deal counts, total values, and stage-to-stage conversion rates, generate a funnel narrative and 3 recommendations.
Respond with valid JSON only, no prose outside JSON:
{
  "funnel_narrative": "2-3 sentence narrative about funnel health, conversion patterns, and where deals are lost",
  "recommendations": ["rec1", "rec2", "rec3"]
}
Provide exactly 3 recommendations.
"""

_FUNNEL_STAGES = ["discovery", "qualified", "proposal", "negotiation"]


@router.get("/workspaces/{workspace_id}/ai/pipeline/conversion-funnel-ai")
@limiter.limit("5/minute")
async def get_pipeline_conversion_funnel_ai(
    request: Request,
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if str(current_user.workspace_id) != str(workspace_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    now = datetime.datetime.now(datetime.timezone.utc)

    result = await db.execute(
        select(Deal.stage, Deal.value)
        .where(
            Deal.workspace_id == workspace_id,
            Deal.stage.in_(_FUNNEL_STAGES),
        )
    )
    rows = result.all()

    counts: dict[str, int] = {s: 0 for s in _FUNNEL_STAGES}
    values: dict[str, float] = {s: 0.0 for s in _FUNNEL_STAGES}
    for r in rows:
        stage = str(r[0])
        if stage in counts:
            counts[stage] += 1
            values[stage] += float(r[1] or 0)

    stages = []
    weakest_stage: str | None = None
    best_stage: str | None = None
    min_rate = 101.0
    max_rate = -1.0

    for i, stage in enumerate(_FUNNEL_STAGES):
        if i < len(_FUNNEL_STAGES) - 1:
            next_stage = _FUNNEL_STAGES[i + 1]
            conversion_rate = (
                round(counts[next_stage] / counts[stage] * 100, 1)
                if counts[stage] > 0
                else None
            )
            if conversion_rate is not None:
                if conversion_rate < min_rate:
                    min_rate = conversion_rate
                    weakest_stage = stage
                if conversion_rate > max_rate:
                    max_rate = conversion_rate
                    best_stage = stage
        else:
            conversion_rate = None

        stages.append({
            "stage": stage,
            "deal_count": counts[stage],
            "total_value": round(values[stage], 2),
            "conversion_rate": conversion_rate,
        })

    context_lines = ["Pipeline conversion funnel (active deals):"]
    for s in stages:
        cr = f"{s['conversion_rate']}% → next" if s["conversion_rate"] is not None else "final stage"
        context_lines.append(f"{s['stage']}: {s['deal_count']} deals, ${s['total_value']:,.0f} value, conversion: {cr}")
    if weakest_stage:
        context_lines.append(f"Weakest conversion: {weakest_stage} ({min_rate}%)")
    if best_stage:
        context_lines.append(f"Best conversion: {best_stage} ({max_rate}%)")
    context = "\n".join(context_lines)

    total = sum(counts.values())
    default_narrative = (
        f"The pipeline has {total} active deals across {len([s for s in stages if s['deal_count'] > 0])} stages. "
        + (f"The weakest conversion point is {weakest_stage} at {min_rate}% — this is where the most deals are being lost." if weakest_stage else "No conversion data available yet.")
        + " Addressing the top bottleneck will have the greatest impact on revenue."
    )
    default_recs = [
        f"Focus coaching on the {weakest_stage} → next-stage transition — this is where the most deals are stalling." if weakest_stage else "Build out each stage with more qualified deals to generate meaningful conversion data.",
        "Review entry criteria for each stage to ensure deals are correctly qualified before advancing — stage pollution skews conversion metrics.",
        "Set conversion rate targets per stage (e.g. ≥60%) and review weekly with the team to create accountability and early alerts.",
    ]

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            system=_PIPELINE_CONVERSION_FUNNEL_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg.content[0].text.strip() if msg.content else "{}"
        data = json.loads(raw)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    funnel_narrative = str(data.get("funnel_narrative", "")).strip() or default_narrative
    raw_recs = data.get("recommendations", [])
    recommendations = [str(r) for r in (raw_recs if isinstance(raw_recs, list) else [])[:3]]
    while len(recommendations) < 3:
        recommendations.append(default_recs[len(recommendations) % 3])

    return {
        "stages": stages,
        "weakest_stage": weakest_stage,
        "best_stage": best_stage,
        "funnel_narrative": funnel_narrative,
        "recommendations": recommendations,
        "generated_at": now.isoformat() + "Z",
    }


_DEAL_SCORE_DISTRIBUTION_SYSTEM = """\
You are a senior sales operations AI analysing deal scoring distribution across a pipeline.
Given win probability bucket counts and health score bucket counts, generate a scoring narrative and 3 recommendations.
Respond with valid JSON only, no prose outside JSON:
{
  "scoring_narrative": "2-3 sentence narrative about the overall deal scoring health and key risk areas",
  "recommendations": ["rec1", "rec2", "rec3"]
}
Provide exactly 3 recommendations.
"""


@router.get("/workspaces/{workspace_id}/ai/deals/score-distribution")
@limiter.limit("5/minute")
async def get_deal_score_distribution(
    request: Request,
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if str(current_user.workspace_id) != str(workspace_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    now = datetime.datetime.now(datetime.timezone.utc)

    closed_stages = {"closed_won", "closed_lost"}
    rows_result = await db.execute(
        select(Deal.ml_win_probability, Deal.health_score).where(
            Deal.workspace_id == workspace_id,
            ~Deal.stage.in_(closed_stages),
        )
    )
    rows = rows_result.all()

    win_prob_ranges = [
        ("0-20", 0, 20),
        ("21-40", 21, 40),
        ("41-60", 41, 60),
        ("61-80", 61, 80),
        ("81-100", 81, 100),
    ]
    win_prob_counts: dict[str, int] = {r[0]: 0 for r in win_prob_ranges}

    health_labels = [
        ("healthy", 70, 101),
        ("at_risk", 40, 70),
        ("critical", 0, 40),
    ]
    health_counts: dict[str, int] = {h[0]: 0 for h in health_labels}

    total_win_prob = 0.0
    total_health = 0.0
    win_prob_n = 0
    health_n = 0
    high_confidence_count = 0
    critical_count = 0

    for win_prob, health in rows:
        wp = float(win_prob) if win_prob is not None else 0.0
        hs = float(health) if health is not None else 0.0

        for label, lo, hi in win_prob_ranges:
            if lo <= wp <= hi:
                win_prob_counts[label] += 1
                break

        for label, lo, hi in health_labels:
            if lo <= hs < hi:
                health_counts[label] += 1
                break

        total_win_prob += wp
        win_prob_n += 1
        total_health += hs
        health_n += 1

        if wp > 70:
            high_confidence_count += 1
        if hs < 40:
            critical_count += 1

    avg_win_prob = round(total_win_prob / win_prob_n, 1) if win_prob_n else 0.0
    avg_health_score = round(total_health / health_n, 1) if health_n else 0.0

    win_prob_buckets = [{"range": r[0], "count": win_prob_counts[r[0]]} for r in win_prob_ranges]
    health_buckets = [{"label": h[0], "count": health_counts[h[0]]} for h in health_labels]

    context_lines = [
        f"Win probability buckets: " + ", ".join(f"{r['range']}%: {r['count']} deals" for r in win_prob_buckets),
        f"Health score buckets: " + ", ".join(f"{h['label']}: {h['count']} deals" for h in health_buckets),
        f"Average win probability: {avg_win_prob}%",
        f"Average health score: {avg_health_score}",
        f"High confidence deals (win_prob>70): {high_confidence_count}",
        f"Critical health deals (health<40): {critical_count}",
    ]
    context = "\n".join(context_lines)

    total_deals = win_prob_n
    default_narrative = (
        f"The pipeline contains {total_deals} open deals with an average win probability of {avg_win_prob}% "
        f"and average health score of {avg_health_score}. "
        + (f"There are {critical_count} critically unhealthy deals that require immediate attention." if critical_count else "Overall deal health is strong.")
    )
    default_recs = [
        f"Prioritise the {critical_count} critical-health deals — low health scores strongly predict churn and loss." if critical_count else "Maintain deal hygiene by reviewing health scores weekly and addressing any drops promptly.",
        f"Nurture the {high_confidence_count} high-confidence deals (win_prob>70%) to close — these represent your most reliable near-term revenue." if high_confidence_count else "Focus on building more deals into the high-confidence tier through disciplined qualification.",
        "Use score distributions to set rep-level targets: aim for fewer than 20% of deals in the 0-20% win probability bucket.",
    ]

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            system=_DEAL_SCORE_DISTRIBUTION_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg.content[0].text.strip() if msg.content else "{}"
        data = json.loads(raw)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    scoring_narrative = str(data.get("scoring_narrative", "")).strip() or default_narrative
    raw_recs = data.get("recommendations", [])
    recommendations = [str(r) for r in (raw_recs if isinstance(raw_recs, list) else [])[:3]]
    while len(recommendations) < 3:
        recommendations.append(default_recs[len(recommendations) % 3])

    return {
        "win_prob_buckets": win_prob_buckets,
        "health_buckets": health_buckets,
        "avg_win_prob": avg_win_prob,
        "avg_health_score": avg_health_score,
        "high_confidence_count": high_confidence_count,
        "critical_count": critical_count,
        "scoring_narrative": scoring_narrative,
        "recommendations": recommendations,
        "generated_at": now.isoformat() + "Z",
    }



_WIN_FACTORS_SYSTEM = """\
You are a senior sales operations AI analysing what drives deal wins and losses.
Given aggregate data about won vs lost deals, generate a win factors narrative and 3 actionable recommendations.
Respond with valid JSON only, no prose outside JSON:
{
  "win_factors_narrative": "2-3 sentence narrative about the key patterns differentiating won deals from lost ones",
  "recommendations": ["rec1", "rec2", "rec3"]
}
Provide exactly 3 recommendations.
"""


@router.get("/workspaces/{workspace_id}/ai/deals/win-factors")
@limiter.limit("5/minute")
async def get_deal_win_factors(
    request: Request,
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if str(current_user.workspace_id) != str(workspace_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    now = datetime.datetime.now(datetime.timezone.utc)
    cutoff = now - datetime.timedelta(days=90)

    rows_result = await db.execute(
        select(Deal.stage, Deal.value, Deal.health_score, Deal.ml_win_probability).where(
            Deal.workspace_id == workspace_id,
            Deal.stage.in_(["closed_won", "closed_lost"]),
            Deal.stage_changed_at >= cutoff,
        )
    )
    rows = rows_result.all()

    won_values: list[float] = []
    lost_values: list[float] = []
    won_health: list[float] = []
    lost_health: list[float] = []
    won_prob: list[float] = []
    lost_prob: list[float] = []

    for stage, value, health, win_prob in rows:
        v = float(value or 0)
        h = float(health or 0)
        p = float(win_prob or 0)
        if stage == "closed_won":
            won_values.append(v)
            won_health.append(h)
            won_prob.append(p)
        else:
            lost_values.append(v)
            lost_health.append(h)
            lost_prob.append(p)

    def avg(lst: list[float]) -> float:
        return round(sum(lst) / len(lst), 1) if lst else 0.0

    won_count = len(won_values)
    lost_count = len(lost_values)
    total = won_count + lost_count
    overall_win_rate = round(won_count / total * 100, 1) if total else 0.0

    avg_won_value = avg(won_values)
    avg_lost_value = avg(lost_values)
    avg_won_health = avg(won_health)
    avg_lost_health = avg(lost_health)
    avg_won_prob = avg(won_prob)
    avg_lost_prob = avg(lost_prob)

    health_delta = round(avg_won_health - avg_lost_health, 1)
    prob_delta = round(avg_won_prob - avg_lost_prob, 1)
    value_delta = round(avg_won_value - avg_lost_value, 2)

    context = (
        f"Last 90 days: {won_count} won, {lost_count} lost, overall win rate {overall_win_rate}%\n"
        f"Won deals — avg value ${avg_won_value:,.0f}, avg health {avg_won_health}, avg win_prob {avg_won_prob}%\n"
        f"Lost deals — avg value ${avg_lost_value:,.0f}, avg health {avg_lost_health}, avg win_prob {avg_lost_prob}%\n"
        f"Health delta (won − lost): {health_delta}, win_prob delta: {prob_delta}%, value delta: ${value_delta:,.0f}"
    )

    default_narrative = (
        f"Over the last 90 days {won_count} deals were won and {lost_count} lost (win rate {overall_win_rate}%). "
        f"Won deals had {'higher' if health_delta >= 0 else 'lower'} health scores by {abs(health_delta)} points "
        f"and {'higher' if prob_delta >= 0 else 'lower'} win probability by {abs(prob_delta)}% compared to lost deals. "
        + ("Improving deal health earlier in the cycle is the clearest lever for better outcomes." if health_delta > 10 else "")
    )
    default_recs = [
        f"Focus on raising health scores early — won deals averaged {avg_won_health} vs {avg_lost_health} for lost deals, a {health_delta}-point gap." if health_delta > 0 else "Work on both health and engagement to build a clearer win profile.",
        f"Target deals where win probability reaches ≥{int(avg_won_prob)}% before advancing to proposal stage — this matches your historical win profile.",
        "Run a post-mortem on each lost deal within 1 week of close to capture fresh insight on what tipped the outcome.",
    ]

    if not rows:
        return {
            "won_count": 0,
            "lost_count": 0,
            "overall_win_rate": 0.0,
            "avg_won_value": 0.0,
            "avg_lost_value": 0.0,
            "avg_won_health": 0.0,
            "avg_lost_health": 0.0,
            "avg_won_prob": 0.0,
            "avg_lost_prob": 0.0,
            "health_delta": 0.0,
            "prob_delta": 0.0,
            "win_factors_narrative": "No closed deals in the last 90 days to analyse.",
            "recommendations": default_recs,
            "generated_at": now.isoformat() + "Z",
        }

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            system=_WIN_FACTORS_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg.content[0].text.strip() if msg.content else "{}"
        data = json.loads(raw)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    win_factors_narrative = str(data.get("win_factors_narrative", "")).strip() or default_narrative
    raw_recs = data.get("recommendations", [])
    recommendations = [str(r) for r in (raw_recs if isinstance(raw_recs, list) else [])[:3]]
    while len(recommendations) < 3:
        recommendations.append(default_recs[len(recommendations) % 3])

    return {
        "won_count": won_count,
        "lost_count": lost_count,
        "overall_win_rate": overall_win_rate,
        "avg_won_value": avg_won_value,
        "avg_lost_value": avg_lost_value,
        "avg_won_health": avg_won_health,
        "avg_lost_health": avg_lost_health,
        "avg_won_prob": avg_won_prob,
        "avg_lost_prob": avg_lost_prob,
        "health_delta": health_delta,
        "prob_delta": prob_delta,
        "win_factors_narrative": win_factors_narrative,
        "recommendations": recommendations,
        "generated_at": now.isoformat() + "Z",
    }

# ---------------------------------------------------------------------------
# Phase 17u – Contact Engagement Heatmap
# ---------------------------------------------------------------------------

_ENGAGEMENT_HEATMAP_SYSTEM = """\
You are a senior sales operations AI analysing contact engagement patterns.
Given hourly and daily activity event counts for the last 90 days, identify
optimal outreach timing windows and engagement trends.
Respond with a JSON object containing exactly two keys:
  "engagement_narrative": one paragraph (2-3 sentences) summarising timing patterns,
  "recommendations": array of exactly 3 actionable strings about optimal outreach timing.
Output only valid JSON with no markdown fences.
"""


@router.get("/workspaces/{workspace_id}/ai/contacts/engagement-heatmap")
@limiter.limit("5/minute")
async def get_contact_engagement_heatmap(
    request: Request,
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if str(current_user.workspace_id) != str(workspace_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    import datetime as _dt
    now = _dt.datetime.now(timezone.utc)
    cutoff = now - _dt.timedelta(days=90)

    result = await db.execute(
        select(ActivityEvent.created_at)
        .where(ActivityEvent.workspace_id == workspace_id)
        .where(ActivityEvent.created_at >= cutoff)
    )
    rows = result.all()

    hour_counts: dict[int, int] = {h: 0 for h in range(24)}
    day_counts: dict[str, int] = {d: 0 for d in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]}
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    for (created_at,) in rows:
        if created_at is None:
            continue
        if hasattr(created_at, "tzinfo") and created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        hour_counts[created_at.hour] += 1
        day_counts[day_names[created_at.weekday()]] += 1

    total_events = sum(hour_counts.values())

    peak_hour = max(hour_counts, key=lambda h: hour_counts[h]) if total_events > 0 else 9
    peak_day = max(day_counts, key=lambda d: day_counts[d]) if total_events > 0 else "Tuesday"

    hour_buckets = [{"hour": h, "count": hour_counts[h]} for h in range(24)]
    day_buckets = [{"day": d, "count": day_counts[d]} for d in day_names]

    default_narrative = (
        f"Peak engagement occurs at hour {peak_hour}:00 UTC on {peak_day}s. "
        "Scheduling outreach during these windows can improve response rates. "
        "Consider aligning automated follow-ups with these high-activity periods."
    )
    default_recs = [
        f"Schedule outreach emails to send at {peak_hour}:00 UTC for maximum engagement.",
        f"Prioritise {peak_day} as your primary outreach day based on activity patterns.",
        "Set automated follow-up sequences to trigger during peak engagement windows.",
    ]

    context = (
        f"Workspace contact engagement over the last 90 days.\n"
        f"Total activity events: {total_events}\n"
        f"Peak hour (UTC): {peak_hour}:00 ({hour_counts[peak_hour]} events)\n"
        f"Peak day: {peak_day} ({day_counts[peak_day]} events)\n"
        f"Hour distribution: {json.dumps(hour_buckets)}\n"
        f"Day distribution: {json.dumps(day_buckets)}\n"
        "Provide an engagement_narrative and 3 recommendations about optimal outreach timing."
    )

    try:
        client = _anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)  # TODO: add real credentials
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            system=_ENGAGEMENT_HEATMAP_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
        raw = msg.content[0].text.strip() if msg.content else "{}"
        data = json.loads(raw)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI unavailable: {exc}",
        ) from exc

    engagement_narrative = str(data.get("engagement_narrative", "")).strip() or default_narrative
    raw_recs = data.get("recommendations", [])
    recommendations = [str(r) for r in (raw_recs if isinstance(raw_recs, list) else [])[:3]]
    while len(recommendations) < 3:
        recommendations.append(default_recs[len(recommendations) % 3])

    return {
        "hour_buckets": hour_buckets,
        "day_buckets": day_buckets,
        "peak_hour": peak_hour,
        "peak_day": peak_day,
        "total_events": total_events,
        "engagement_narrative": engagement_narrative,
        "recommendations": recommendations,
        "generated_at": now.isoformat() + "Z",
    }
