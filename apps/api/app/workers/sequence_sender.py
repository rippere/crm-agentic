"""
Celery task: the sequence scheduler/sender — the beat-driven heart of the
outbound engine (leads -> campaigns -> sequences -> email/SMS with a bot->human
HITL gate).

tick_sequences_all()
  Beat dispatcher (crontab every 5 min). Enumerates workspace ids and fans out
  tick_sequences.delay(ws) per workspace — the bare tick task needs a
  workspace_id that beat cannot supply.

tick_sequences(workspace_id)
  Select sequence_enrollments where status IN ('active','waiting') AND
  next_run_at <= NOW() AND the parent campaign status='active'. For each, load
  the sequence_step at current_step and:
    * step is None (walked off the end)        -> status='completed'
    * sequence.settings.stop_on_reply and the
      lead has replied                         -> status='stopped'
    * inside sequence.settings.quiet_hours      -> skip this tick, retry later
    * step.requires_approval and NO approved
      draft exists                              -> produce a pending draft
      (Claude when ai_generate, else render body_template tokens), write
      engagement_event(type='queued'), park enrollment status='waiting' so it
      surfaces on /outreach/pending. DO NOT send.
    * approved (an 'approved' engagement_event newer than last_sent_at) OR the
      step needs no approval                    -> SEND via the guarded Gmail /
      SMS boundary, write engagement_event(type='sent'), advance current_step,
      set next_run_at = NOW() + next_step.delay_hours and last_sent_at=NOW();
      no next step -> status='completed'.

Copies the score_contact.py / followup_sequences.py worker house shape: sync
@celery_app.task(..., bind=True) wrapper delegating to asyncio.run(_async(...));
own _get_async_session() reusing PGBOUNCER_CONNECT_ARGS; primitive args cast to
UUID inside; results written to Postgres + an ActivityEvent; a *_all beat
dispatcher fanning out over workspaces. Every external send (Gmail / Claude /
SMS) sits behind a guarded, patchable boundary so the unit tests run with no
credentials and no network.
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.database import PGBOUNCER_CONNECT_ARGS

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def _get_async_session() -> async_sessionmaker[AsyncSession]:
    # Prefer DATABASE_URL (already asyncpg-formatted) over SUPABASE_URL
    url = os.getenv("DATABASE_URL", "") or os.getenv("SUPABASE_URL", "")
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://") and "+asyncpg" not in url:
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    engine = create_async_engine(url, echo=False, connect_args=PGBOUNCER_CONNECT_ARGS)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# ─── Pure helpers (no DB) ─────────────────────────────────────────────────────

def _render_template(template: str | None, lead: Any) -> str:
    """Substitute ``{{name}}``/``{{company}}``/``{{email}}``/``{{title}}`` tokens.

    Mirrors routers/outreach.py::_render_template so the sender delivers exactly
    what the approval queue previewed.
    """
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


def _in_quiet_hours(now: datetime, settings: dict[str, Any] | None) -> bool:
    """True when ``now`` (its UTC hour) falls inside the sequence's quiet window.

    Pure. Accepts ``quiet_hours`` as a 2-element ``[start, end]`` list/tuple or a
    ``{"start": h, "end": h}`` dict of integer hours (0-23). ``start < end`` is a
    same-day window; ``start > end`` wraps past midnight. Anything malformed or
    absent means "not quiet" (send freely).
    """
    qh = (settings or {}).get("quiet_hours")
    if not qh:
        return False
    if isinstance(qh, dict):
        start, end = qh.get("start"), qh.get("end")
    elif isinstance(qh, (list, tuple)) and len(qh) == 2:
        start, end = qh[0], qh[1]
    else:
        return False
    try:
        start, end = int(start), int(end)
    except (TypeError, ValueError):
        return False
    if start == end:
        return False
    hour = now.hour
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end  # wraps midnight


# ─── Guarded external-send boundary (patchable in tests) ──────────────────────

async def _draft_body(step: Any, lead: Any) -> tuple[str, bool]:
    """Return ``(body, ai_generated)`` for a step.

    Claude only fires when ``step.ai_generate`` is True AND an ANTHROPIC_API_KEY
    is present; any failure falls back to the deterministic template render — so
    tests exercise this with no key and no network. Mirrors
    routers/outreach.py::_draft_for_step.
    """
    if step is None:
        return "", False
    rendered = _render_template(getattr(step, "body_template", ""), lead)
    if not getattr(step, "ai_generate", False):
        return rendered, False

    from app.config import settings as _settings

    api_key = getattr(_settings, "ANTHROPIC_API_KEY", "") or ""
    if not api_key:
        return rendered, False
    try:
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=api_key)
        prompt = (
            "You are a sales assistant. Personalise this outreach message for the "
            f"lead {getattr(lead, 'name', None) or 'there'} at "
            f"{getattr(lead, 'company', None) or 'their company'}. "
            "Keep it under 120 words. Base template:\n\n"
            f"{rendered}"
        )
        message = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        body = message.content[0].text if message.content else rendered
        return (body or rendered), True
    except Exception as exc:  # noqa: BLE001 — guard: fall back to the template
        logger.warning("sequence_sender ai_draft_failed step_id=%s exc=%s", getattr(step, "id", None), exc)
        return rendered, False


async def _deliver(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    step: Any,
    lead: Any,
    subject: str | None,
    body: str,
) -> dict[str, Any]:
    """Actually deliver a step. The single external boundary — fully guarded.

    email -> the same Gmail path followup_sequences.py uses (GmailClient over the
    workspace 'gmail' Connector). sms -> a stub connector for the Zach demo (log +
    return a stub result). Never raises: a missing connector, missing recipient,
    or provider error is logged and returned as ``{"delivered": False}`` so a tick
    never crashes on one bad send. Patched wholesale in the unit tests, so it runs
    with no credentials.
    """
    channel = getattr(step, "channel", "email") or "email"

    if channel == "sms":
        phone = getattr(lead, "phone", None)
        # SMS is a stub connector for the demo — log the intent, no provider wired.
        logger.info(
            "sequence_sender sms_stub workspace=%s to=%s body=%r",
            workspace_id, phone, (body or "")[:80],
        )
        return {"delivered": bool(phone), "channel": "sms", "stub": True, "to": phone}

    # email
    to = getattr(lead, "email", None)
    if not to:
        logger.info("sequence_sender email_skip_no_recipient workspace=%s", workspace_id)
        return {"delivered": False, "channel": "email", "reason": "no recipient"}

    try:
        from app.models.connector import Connector
        from app.services.gmail_client import GmailClient
        from app.config import settings as _settings

        result = await db.execute(
            select(Connector).where(
                Connector.workspace_id == workspace_id,
                Connector.service == "gmail",
            )
        )
        connector = result.scalar_one_or_none()
        if connector is None:
            logger.info("sequence_sender email_skip_no_connector workspace=%s", workspace_id)
            return {"delivered": False, "channel": "email", "reason": "no gmail connector"}

        client = GmailClient(
            connector,
            db,
            google_client_id=_settings.GOOGLE_CLIENT_ID,
            google_client_secret=_settings.GOOGLE_CLIENT_SECRET,
        )
        resp = await client.send_message(to=to, subject=subject or "", body=body or "")
        return {"delivered": True, "channel": "email", "to": to, "message_id": resp.get("id")}
    except Exception as exc:  # noqa: BLE001 — guard: one bad send never fails the tick
        logger.warning("sequence_sender email_send_failed workspace=%s to=%s exc=%s", workspace_id, to, exc)
        return {"delivered": False, "channel": "email", "reason": str(exc)}


# ─── DB loaders (thin, patchable so _run_tick tests need no query plumbing) ────

async def _due_enrollments(db: AsyncSession, workspace_id: uuid.UUID, now: datetime) -> list[Any]:
    """Enrollments due to advance: active/waiting, past next_run_at, parent campaign active."""
    from app.models.sequence_enrollment import SequenceEnrollment
    from app.models.campaign import Campaign

    result = await db.execute(
        select(SequenceEnrollment)
        .join(Campaign, Campaign.id == SequenceEnrollment.campaign_id)
        .where(
            SequenceEnrollment.workspace_id == workspace_id,
            SequenceEnrollment.status.in_(["active", "waiting"]),
            SequenceEnrollment.next_run_at <= now,
            Campaign.status == "active",
        )
        .order_by(SequenceEnrollment.next_run_at)
    )
    return list(result.scalars().all())


async def _load_sequence(db: AsyncSession, workspace_id: uuid.UUID, sequence_id: uuid.UUID) -> Any:
    from app.models.sequence import Sequence

    result = await db.execute(
        select(Sequence).where(
            Sequence.id == sequence_id,
            Sequence.workspace_id == workspace_id,
        )
    )
    return result.scalar_one_or_none()


async def _load_step(
    db: AsyncSession, workspace_id: uuid.UUID, sequence_id: uuid.UUID, step_order: int
) -> Any:
    from app.models.sequence_step import SequenceStep

    result = await db.execute(
        select(SequenceStep).where(
            SequenceStep.workspace_id == workspace_id,
            SequenceStep.sequence_id == sequence_id,
            SequenceStep.step_order == step_order,
        )
    )
    return result.scalar_one_or_none()


async def _load_lead(db: AsyncSession, workspace_id: uuid.UUID, lead_id: uuid.UUID) -> Any:
    from app.models.lead import Lead

    result = await db.execute(
        select(Lead).where(
            Lead.id == lead_id,
            Lead.workspace_id == workspace_id,
        )
    )
    return result.scalar_one_or_none()


async def _has_event_after_last_send(
    db: AsyncSession, workspace_id: uuid.UUID, enrollment: Any, event_type: str
) -> bool:
    """True if an engagement_event of ``event_type`` for this enrollment is newer
    than its ``last_sent_at`` (or any such event when nothing has been sent yet).

    This is how an *approval* is detected: routers/outreach.py::approve_outreach
    writes engagement_event(type='approved', enrollment_id=...) and flips the
    enrollment back to 'active'. Since we stamp last_sent_at on every send, an
    approval for the current step is always newer than the previous send — and a
    'replied' event drives stop_on_reply the same way.
    """
    from app.models.engagement_event import EngagementEvent

    conds = [
        EngagementEvent.workspace_id == workspace_id,
        EngagementEvent.enrollment_id == enrollment.id,
        EngagementEvent.type == event_type,
    ]
    last_sent = getattr(enrollment, "last_sent_at", None)
    if last_sent is not None:
        conds.append(EngagementEvent.occurred_at > last_sent)
    result = await db.execute(select(EngagementEvent.id).where(*conds).limit(1))
    return result.first() is not None


# ─── Core tick ────────────────────────────────────────────────────────────────

async def _run_tick(workspace_id: str) -> dict[str, Any]:
    from app.models.engagement_event import EngagementEvent
    from app.models.activity_event import ActivityEvent

    ws_uuid = uuid.UUID(workspace_id)
    now = datetime.now(timezone.utc)

    sent = queued = completed = stopped = skipped = 0

    SessionFactory = _get_async_session()
    async with SessionFactory() as db:
        enrollments = await _due_enrollments(db, ws_uuid, now)

        for enr in enrollments:
            seq = await _load_sequence(db, ws_uuid, enr.sequence_id)
            settings = (getattr(seq, "settings", None) or {}) if seq is not None else {}

            step = await _load_step(db, ws_uuid, enr.sequence_id, enr.current_step)
            if step is None:
                # Walked off the end of the sequence — nothing left to send.
                enr.status = "completed"
                db.add(enr)
                completed += 1
                continue

            # stop_on_reply (default on): a reply since the last send halts the drip.
            if bool(settings.get("stop_on_reply", True)) and await _has_event_after_last_send(
                db, ws_uuid, enr, "replied"
            ):
                enr.status = "stopped"
                db.add(enr)
                stopped += 1
                continue

            # Quiet hours: leave the row untouched and retry on a later tick.
            if _in_quiet_hours(now, settings):
                skipped += 1
                continue

            lead = await _load_lead(db, ws_uuid, enr.lead_id)

            # HITL gate — a step that requires approval only sends once approved.
            if getattr(step, "requires_approval", True) and not await _has_event_after_last_send(
                db, ws_uuid, enr, "approved"
            ):
                if enr.status != "waiting":
                    # First encounter → produce a pending draft and park it.
                    body, ai_generated = await _draft_body(step, lead)
                    db.add(EngagementEvent(
                        workspace_id=ws_uuid,
                        lead_id=enr.lead_id,
                        campaign_id=enr.campaign_id,
                        enrollment_id=enr.id,
                        step_id=step.id,
                        type="queued",
                        channel=getattr(step, "channel", None),
                        weight=0,
                        metadata_={
                            "subject": getattr(step, "subject", None),
                            "body": body,
                            "ai_generated": ai_generated,
                        },
                    ))
                    enr.status = "waiting"
                    db.add(enr)
                    queued += 1
                # else: already waiting on the human — leave it on /outreach/pending.
                continue

            # ── SEND ────────────────────────────────────────────────────────────
            subject = getattr(step, "subject", None)
            body, ai_generated = await _draft_body(step, lead)
            delivery = await _deliver(db, ws_uuid, step, lead, subject, body)

            db.add(EngagementEvent(
                workspace_id=ws_uuid,
                lead_id=enr.lead_id,
                campaign_id=enr.campaign_id,
                enrollment_id=enr.id,
                step_id=step.id,
                type="sent",
                channel=getattr(step, "channel", None),
                weight=0,
                metadata_={
                    "subject": subject,
                    "body": body,
                    "ai_generated": ai_generated,
                    "delivery": delivery,
                },
            ))

            # Advance the enrollment past the step we just sent.
            next_order = enr.current_step + 1
            next_step = await _load_step(db, ws_uuid, enr.sequence_id, next_order)
            enr.current_step = next_order
            enr.last_sent_at = now
            if next_step is None:
                enr.status = "completed"
                completed += 1
            else:
                enr.status = "active"
                enr.next_run_at = now + timedelta(hours=int(getattr(next_step, "delay_hours", 0) or 0))
            db.add(enr)
            sent += 1

            # Best-effort: re-score the lead off the fresh 'sent' signal.
            try:
                from app.workers.engagement_score import score_lead_engagement

                score_lead_engagement.delay(workspace_id, str(enr.lead_id))
            except Exception as exc:  # noqa: BLE001 — scoring is best-effort
                logger.warning("sequence_sender score_enqueue_failed lead_id=%s exc=%s", enr.lead_id, exc)

        if sent or queued or completed or stopped:
            db.add(ActivityEvent(
                workspace_id=ws_uuid,
                type="sequence_tick",
                agent_name="Sequence Sender",
                description=(
                    f"Sequence tick: {sent} sent, {queued} queued for approval, "
                    f"{completed} completed, {stopped} stopped"
                ),
                severity="info",
            ))
        await db.commit()

    return {
        "workspace_id": workspace_id,
        "sent": sent,
        "queued": queued,
        "completed": completed,
        "stopped": stopped,
        "skipped": skipped,
    }


async def _enumerate_workspace_ids() -> list[str]:
    """Return every workspace id in the DB as a string (sync-land safe)."""
    from app.models.workspace import Workspace

    SessionFactory = _get_async_session()
    async with SessionFactory() as db:
        result = await db.execute(select(Workspace.id))
        return [str(ws_id) for ws_id in result.scalars().all()]


# ─── Celery tasks ─────────────────────────────────────────────────────────────

@celery_app.task(name="app.workers.sequence_sender.tick_sequences", bind=True)
def tick_sequences(self: Any, workspace_id: str) -> dict[str, Any]:
    """Celery task: advance every due enrollment in one workspace (send / gate)."""
    return asyncio.run(_run_tick(workspace_id))


@celery_app.task(name="app.workers.sequence_sender.tick_sequences_all", bind=True)
def tick_sequences_all(self: Any) -> dict[str, Any]:
    """Beat dispatcher (every 5 min): fan tick_sequences out per workspace.

    tick_sequences requires a workspace_id, which celery beat cannot supply. This
    no-arg task enumerates all workspaces and enqueues one tick child per.
    """
    workspace_ids = asyncio.run(_enumerate_workspace_ids())
    for ws_id in workspace_ids:
        tick_sequences.delay(ws_id)
    return {"dispatched": len(workspace_ids), "workspace_ids": workspace_ids}
