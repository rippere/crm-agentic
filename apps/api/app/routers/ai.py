import datetime
import json
import uuid
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
