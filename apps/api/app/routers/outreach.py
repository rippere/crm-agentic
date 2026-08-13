"""Outreach router — the bot→human HITL handoff surface for the outbound engine.

Copies the HITL idiom proven in ``workers/followup_sequences.py`` (draft via Claude
→ post for human approval → resolve) but scoped to sequence sends. A sequence step
with ``requires_approval=True`` produces a **pending draft** that a human approves
before the sender actually delivers.

House conventions (mirrors ``routers/deals.py`` / ``routers/contacts.py``):
  * module-level ``router = APIRouter()`` — no prefix/tags (main.py supplies tags)
  * full paths include ``/workspaces/{workspace_id}/...``
  * first line of every authed handler is the workspace guard → 403
  * every query filters ``.where(Model.workspace_id == workspace_id)``
  * inline Pydantic schemas; enum-ish fields validated against the same literal
    sets as the SQL CHECK constraints → 422
  * ``ActivityEvent`` audit rows on writes
  * ORM-first with ``supabase_rest.get_row`` fallback before 404
  * static sub-paths declared BEFORE ``/{enrollment_id}`` routes

The inbound provider webhook (``POST /webhooks/engagement``) carries NO auth
dependency — it is HMAC-verified instead, mirroring the fail-closed signature
check in ``routers/slack.py`` / ``routers/webhook_logs.py``. It is rate-limited and
appends an ``engagement_event`` fact row, then enqueues re-scoring.
"""

import hashlib
import hmac
import logging
import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.limiter import limiter
from app.models.user import User
from app.models.lead import Lead
from app.models.campaign import Campaign
from app.models.sequence import Sequence
from app.models.sequence_step import SequenceStep
from app.models.sequence_enrollment import SequenceEnrollment
from app.models.engagement_event import EngagementEvent
from app.models.activity_event import ActivityEvent
from app.services.supabase_rest import get_row

logger = logging.getLogger(__name__)

router = APIRouter()


# ─── Literal sets — mirror the SQL CHECK constraints in 023_outbound_engagement ──
ENGAGEMENT_TYPES = (
    "queued", "sent", "delivered", "opened", "clicked", "replied",
    "bounced", "unsubscribed", "converted", "approved", "rejected",
)
ENGAGEMENT_CHANNELS = ("email", "sms")

# Scoring contribution per event type (mirrors workers/engagement_score weights).
ENGAGEMENT_WEIGHTS = {
    "opened": 5,
    "clicked": 15,
    "replied": 30,
    "converted": 40,
    "bounced": -20,
    "unsubscribed": -30,
}


# ─── Schemas ────────────────────────────────────────────────────────────────────

class PendingOutreachResponse(BaseModel):
    enrollment_id: uuid.UUID
    lead_id: uuid.UUID
    campaign_id: uuid.UUID | None = None
    sequence_id: uuid.UUID | None = None
    current_step: int
    status: str
    subject: str | None = None
    body: str = ""


class OutreachDraftResponse(BaseModel):
    enrollment_id: uuid.UUID
    subject: str | None = None
    body: str = ""
    ai_generated: bool = False


class ApproveOutreachRequest(BaseModel):
    # Optional human edits to the draft before it goes send-ready.
    subject: str | None = None
    body: str | None = None


class RejectOutreachRequest(BaseModel):
    reason: str | None = None


class EngagementWebhookRequest(BaseModel):
    lead_id: uuid.UUID
    type: str
    channel: str | None = None
    campaign_id: uuid.UUID | None = None
    enrollment_id: uuid.UUID | None = None
    step_id: uuid.UUID | None = None
    metadata: dict = {}


# ─── Helpers ─────────────────────────────────────────────────────────────────────

def _render_template(template: str | None, lead: Lead | None) -> str:
    """Substitute ``{{name}}``/``{{company}}``/``{{email}}``/``{{title}}`` tokens."""
    text = template or ""
    if lead is None:
        return text
    tokens = {
        "name": getattr(lead, "name", None) or "there",
        "company": getattr(lead, "company", None) or "",
        "email": getattr(lead, "email", None) or "",
        "title": getattr(lead, "title", None) or "",
    }
    for key, val in tokens.items():
        text = text.replace("{{%s}}" % key, str(val))
    return text


async def _draft_for_step(step: SequenceStep | None, lead: Lead | None) -> tuple[str | None, bool]:
    """Return ``(rendered_or_ai_body, ai_generated)`` for a step.

    The Claude call is fully guarded: it only fires when ``step.ai_generate`` is
    True AND an API key is present, and any failure falls back to the deterministic
    template render — so tests exercise this path with no API key and no network.
    """
    if step is None:
        return "", False
    rendered = _render_template(step.body_template, lead)
    if not getattr(step, "ai_generate", False):
        return rendered, False
    return await _ai_draft_body(step, lead, rendered)


async def _ai_draft_body(step: SequenceStep, lead: Lead | None, fallback: str) -> tuple[str, bool]:
    """Isolated, patchable Claude draft. Guarded — never raises to the caller."""
    from app.config import settings

    api_key = getattr(settings, "ANTHROPIC_API_KEY", "") or ""
    if not api_key:
        return fallback, False
    try:
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=api_key)
        prompt = (
            "You are a sales assistant. Personalise this outreach message for the "
            f"lead {getattr(lead, 'name', None) or 'there'} at "
            f"{getattr(lead, 'company', None) or 'their company'}. "
            "Keep it under 120 words. Base template:\n\n"
            f"{fallback}"
        )
        message = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        body = message.content[0].text if message.content else fallback
        return (body or fallback), True
    except Exception as exc:  # noqa: BLE001 — guard: fall back to the template
        logger.warning("outreach ai_draft_failed step_id=%s exc=%s", getattr(step, "id", None), exc)
        return fallback, False


async def _load_enrollment(
    db: AsyncSession, workspace_id: uuid.UUID, enrollment_id: uuid.UUID
) -> SequenceEnrollment | None:
    result = await db.execute(
        select(SequenceEnrollment).where(
            SequenceEnrollment.id == enrollment_id,
            SequenceEnrollment.workspace_id == workspace_id,
        )
    )
    return result.scalar_one_or_none()


async def _load_lead(
    db: AsyncSession, workspace_id: uuid.UUID, lead_id: uuid.UUID
) -> Lead | None:
    result = await db.execute(
        select(Lead).where(
            Lead.id == lead_id,
            Lead.workspace_id == workspace_id,
        )
    )
    return result.scalar_one_or_none()


async def _load_campaign(
    db: AsyncSession, workspace_id: uuid.UUID, campaign_id: uuid.UUID
) -> Campaign | None:
    result = await db.execute(
        select(Campaign).where(
            Campaign.id == campaign_id,
            Campaign.workspace_id == workspace_id,
        )
    )
    return result.scalar_one_or_none()


def _engagement_secret() -> str:
    """Shared HMAC secret for the inbound engagement webhook.

    Read from the environment (patchable in tests) — the router never defines a
    new config field. Empty means "no secret configured" → fail closed.
    """
    return os.getenv("ENGAGEMENT_WEBHOOK_SECRET", "")


def _verify_engagement_signature(body: bytes, signature: str | None) -> bool:
    """HMAC-SHA256 verify, fail-closed — mirrors ``routers/slack.py``.

    Accepts ``sha256=<hex>`` or a bare ``<hex>`` signature header. Returns False
    when no secret is configured (cannot authenticate → reject).
    """
    secret = _engagement_secret()
    if not secret:
        return False  # fail closed — no secret means we cannot verify
    if not signature:
        return False
    provided = signature.split("=", 1)[1] if signature.startswith("sha256=") else signature
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    try:
        return hmac.compare_digest(expected, provided)
    except TypeError:
        return False  # non-ASCII signature → mismatch, never a 500


# ─── Static sub-paths (declared BEFORE /{enrollment_id} routes) ──────────────────

@router.get(
    "/workspaces/{workspace_id}/outreach/pending",
    response_model=list[PendingOutreachResponse],
)
async def list_pending_outreach(
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[PendingOutreachResponse]:
    """Queue of drafts awaiting human approval.

    A draft is pending when its enrollment is in ``status='waiting'`` (parked by the
    sender because the current step ``requires_approval``). Each row carries the
    rendered subject/body the human reviews before approving.
    """
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    result = await db.execute(
        select(SequenceEnrollment)
        .where(
            SequenceEnrollment.workspace_id == workspace_id,
            SequenceEnrollment.status == "waiting",
        )
        .order_by(SequenceEnrollment.next_run_at)
    )
    enrollments = result.scalars().all()

    out: list[PendingOutreachResponse] = []
    for enr in enrollments:
        step_result = await db.execute(
            select(SequenceStep).where(
                SequenceStep.workspace_id == workspace_id,
                SequenceStep.sequence_id == enr.sequence_id,
                SequenceStep.step_order == enr.current_step,
            )
        )
        step = step_result.scalar_one_or_none()

        lead_result = await db.execute(
            select(Lead).where(
                Lead.id == enr.lead_id,
                Lead.workspace_id == workspace_id,
            )
        )
        lead = lead_result.scalar_one_or_none()

        body = _render_template(step.body_template if step else "", lead)
        out.append(
            PendingOutreachResponse(
                enrollment_id=enr.id,
                lead_id=enr.lead_id,
                campaign_id=enr.campaign_id,
                sequence_id=enr.sequence_id,
                current_step=enr.current_step,
                status=enr.status,
                subject=step.subject if step else None,
                body=body,
            )
        )
    return out


# ─── /{enrollment_id} action routes ──────────────────────────────────────────────

@router.post(
    "/workspaces/{workspace_id}/outreach/{enrollment_id}/draft",
    response_model=OutreachDraftResponse,
)
async def draft_outreach(
    workspace_id: uuid.UUID,
    enrollment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> OutreachDraftResponse:
    """(Re)generate the current step's draft — Claude when ``ai_generate``, else render.

    The Claude call is guarded (see ``_ai_draft_body``) so this works with no API
    key. Returns an editable subject/body the human can tweak before approving.
    """
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    enr = await _load_enrollment(db, workspace_id, enrollment_id)
    if enr is None:
        row = await get_row(
            "sequence_enrollments",
            {"id": str(enrollment_id), "workspace_id": str(workspace_id)},
        )
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Enrollment not found")
        # Fallback path: enrollment exists only in Supabase — no step/lead context.
        return OutreachDraftResponse(enrollment_id=enrollment_id, subject=None, body="", ai_generated=False)

    step_result = await db.execute(
        select(SequenceStep).where(
            SequenceStep.workspace_id == workspace_id,
            SequenceStep.sequence_id == enr.sequence_id,
            SequenceStep.step_order == enr.current_step,
        )
    )
    step = step_result.scalar_one_or_none()

    lead_result = await db.execute(
        select(Lead).where(
            Lead.id == enr.lead_id,
            Lead.workspace_id == workspace_id,
        )
    )
    lead = lead_result.scalar_one_or_none()

    body, ai_generated = await _draft_for_step(step, lead)
    return OutreachDraftResponse(
        enrollment_id=enrollment_id,
        subject=step.subject if step else None,
        body=body or "",
        ai_generated=ai_generated,
    )


@router.post(
    "/workspaces/{workspace_id}/outreach/{enrollment_id}/approve",
    status_code=status.HTTP_202_ACCEPTED,
)
async def approve_outreach(
    workspace_id: uuid.UUID,
    enrollment_id: uuid.UUID,
    body: ApproveOutreachRequest = ApproveOutreachRequest(),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Approve (optionally edited) draft → mark send-ready + write an ``approved`` event.

    Flips the parked enrollment back to ``active`` so the sender delivers it, and
    appends an ``engagement_event(type='approved')`` for the audit/scoring trail.
    """
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    enr = await _load_enrollment(db, workspace_id, enrollment_id)
    lead_id: uuid.UUID | None = None
    campaign_id: uuid.UUID | None = None
    if enr is None:
        row = await get_row(
            "sequence_enrollments",
            {"id": str(enrollment_id), "workspace_id": str(workspace_id)},
        )
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Enrollment not found")
        lead_id = uuid.UUID(str(row["lead_id"])) if row.get("lead_id") else None
        campaign_id = uuid.UUID(str(row["campaign_id"])) if row.get("campaign_id") else None
    else:
        lead_id = enr.lead_id
        campaign_id = enr.campaign_id
        enr.status = "active"  # send-ready — sender picks it up on next tick
        db.add(enr)

    if lead_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Enrollment not found")

    event = EngagementEvent(
        workspace_id=workspace_id,
        lead_id=lead_id,
        campaign_id=campaign_id,
        enrollment_id=enrollment_id,
        type="approved",
        weight=ENGAGEMENT_WEIGHTS.get("approved", 0),
        metadata_={
            "subject": body.subject,
            "body": body.body,
            "approved_by": getattr(current_user, "email", None),
        },
    )
    db.add(event)
    db.add(ActivityEvent(
        workspace_id=workspace_id,
        type="outreach_approved",
        agent_name="System",
        description=f"Outreach approved for enrollment {enrollment_id}",
        severity="info",
    ))
    await db.commit()

    return {"status": "approved", "enrollment_id": str(enrollment_id)}


@router.post("/workspaces/{workspace_id}/outreach/{enrollment_id}/reject")
async def reject_outreach(
    workspace_id: uuid.UUID,
    enrollment_id: uuid.UUID,
    body: RejectOutreachRequest = RejectOutreachRequest(),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Reject the draft → stop the step + write a ``rejected`` event."""
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    enr = await _load_enrollment(db, workspace_id, enrollment_id)
    lead_id: uuid.UUID | None = None
    campaign_id: uuid.UUID | None = None
    if enr is None:
        row = await get_row(
            "sequence_enrollments",
            {"id": str(enrollment_id), "workspace_id": str(workspace_id)},
        )
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Enrollment not found")
        lead_id = uuid.UUID(str(row["lead_id"])) if row.get("lead_id") else None
        campaign_id = uuid.UUID(str(row["campaign_id"])) if row.get("campaign_id") else None
    else:
        lead_id = enr.lead_id
        campaign_id = enr.campaign_id
        enr.status = "stopped"  # skip/stop the step
        db.add(enr)

    if lead_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Enrollment not found")

    event = EngagementEvent(
        workspace_id=workspace_id,
        lead_id=lead_id,
        campaign_id=campaign_id,
        enrollment_id=enrollment_id,
        type="rejected",
        weight=ENGAGEMENT_WEIGHTS.get("rejected", 0),
        metadata_={"reason": body.reason, "rejected_by": getattr(current_user, "email", None)},
    )
    db.add(event)
    db.add(ActivityEvent(
        workspace_id=workspace_id,
        type="outreach_rejected",
        agent_name="System",
        description=f"Outreach rejected for enrollment {enrollment_id}",
        severity="warning",
    ))
    await db.commit()

    return {"status": "rejected", "enrollment_id": str(enrollment_id)}


# ─── Inbound provider webhook (no auth — HMAC-verified) ──────────────────────────

@router.post("/workspaces/{workspace_id}/webhooks/engagement", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("120/minute")
async def engagement_webhook(
    request: Request,
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Inbound provider webhook (open/click/reply/bounce/unsub/…).

    NO auth dependency — the payload is HMAC-verified instead (fail closed,
    mirrors ``routers/slack.py``). Appends an ``engagement_event`` fact row,
    honours ``stop_on_reply`` on the enrollment, and enqueues re-scoring.
    """
    raw_body = await request.body()
    signature = request.headers.get("x-engagement-signature") or request.headers.get("X-Engagement-Signature")
    if not _verify_engagement_signature(raw_body, signature):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")

    try:
        payload = EngagementWebhookRequest.model_validate_json(raw_body)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid payload")

    if payload.type not in ENGAGEMENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"type must be one of {ENGAGEMENT_TYPES}",
        )
    if payload.channel is not None and payload.channel not in ENGAGEMENT_CHANNELS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"channel must be one of {ENGAGEMENT_CHANNELS}",
        )

    # ─── Cross-tenant guard ──────────────────────────────────────────────────
    # The webhook authenticates with a single global HMAC secret, so the caller
    # can be ANY workspace. Reject payloads whose referenced rows do not belong
    # to the URL workspace_id, or a cross-tenant write lands here undetected.
    lead = await _load_lead(db, workspace_id, payload.lead_id)
    if lead is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="lead_id does not belong to this workspace",
        )
    if payload.campaign_id is not None:
        campaign = await _load_campaign(db, workspace_id, payload.campaign_id)
        if campaign is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="campaign_id does not belong to this workspace",
            )
    if payload.enrollment_id is not None:
        enrollment = await _load_enrollment(db, workspace_id, payload.enrollment_id)
        if enrollment is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="enrollment_id does not belong to this workspace",
            )

    event = EngagementEvent(
        workspace_id=workspace_id,
        lead_id=payload.lead_id,
        campaign_id=payload.campaign_id,
        enrollment_id=payload.enrollment_id,
        step_id=payload.step_id,
        type=payload.type,
        channel=payload.channel,
        weight=ENGAGEMENT_WEIGHTS.get(payload.type, 0),
        metadata_=payload.metadata or {},
    )
    db.add(event)

    # stop_on_reply / bounce / unsubscribe → halt the enrollment when we can find it.
    if payload.enrollment_id is not None and payload.type in ("replied", "bounced", "unsubscribed"):
        enr = await _load_enrollment(db, workspace_id, payload.enrollment_id)
        if enr is not None:
            stop_on_reply = True
            seq_result = await db.execute(
                select(Sequence).where(
                    Sequence.id == enr.sequence_id,
                    Sequence.workspace_id == workspace_id,
                )
            )
            seq = seq_result.scalar_one_or_none()
            if seq is not None:
                stop_on_reply = bool((seq.settings or {}).get("stop_on_reply", True))
            if payload.type == "bounced":
                enr.status = "bounced"
                db.add(enr)
            elif stop_on_reply:
                enr.status = "stopped"
                db.add(enr)

    await db.commit()

    # Enqueue re-scoring — guarded so a missing worker never 500s the webhook.
    job_id: str | None = None
    try:
        from app.workers.engagement_score import score_lead_engagement
        from app.routers.agents import _mark_job_dispatched

        task = score_lead_engagement.delay(str(workspace_id), str(payload.lead_id))
        _mark_job_dispatched(task.id, str(workspace_id))
        job_id = task.id
    except Exception as exc:  # noqa: BLE001 — scoring is best-effort
        logger.warning("engagement_webhook score_enqueue_failed lead_id=%s exc=%s", payload.lead_id, exc)

    return {"status": "accepted", "type": payload.type, "job_id": job_id}
