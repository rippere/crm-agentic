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
from app.models.deal_note import DealNote
from app.models.message import Message
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
            Deal.expected_close < today,
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
