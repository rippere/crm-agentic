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
