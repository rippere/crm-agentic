"""Escalation control-plane router — the operator surface for the control graph.

Autonomous Lead Engine, Increment 2 (§2.2.6, R15). Follows the shipped house
conventions verbatim (see routers/discovery.py, routers/leads.py): a bare
module-level ``router = APIRouter()`` (tags attached in ``main.py``); every path
under ``/workspaces/{workspace_id}/...``; a first-line 403 workspace-auth guard on
every handler; every query scoped by ``workspace_id``; inline Pydantic schemas
(``from_attributes``); literal-tuple validation -> 422; ``ActivityEvent`` audit on
writes; STATIC sub-paths declared BEFORE ``/{param}`` routes.

Surfaces:
- ``GET/PUT  /escalation/controls`` + ``PUT /escalation/controls/{stage}`` — the
  per-stage auto/ask/off cap the shared authority resolver reads (R11/R12).
- ``GET/PUT  /escalation/autonomy`` — the workspace autonomy master switch (R12).
- ``GET      /escalation/queue`` — waiting enrollments joined to their newest
  decision; ``needs_judgment`` is True when the newest decision escalated.
- ``POST     /escalation/leads/{lead_id}/call-outcome`` — a human-fed post-call
  outcome re-enters the graph event-sourced: it emits a ``converted`` engagement
  event where applicable, moves stage/enrollment per :data:`_OUTCOME_MAP`, writes a
  human ``escalation_decisions`` row, and enqueues a re-score.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.activity_event import ActivityEvent
from app.models.engagement_event import EngagementEvent
from app.models.escalation_decision import EscalationDecision
from app.models.lead import Lead
from app.models.sequence_enrollment import SequenceEnrollment
from app.models.stage_control import StageControl
from app.models.user import User
from app.models.workspace_autonomy import WorkspaceAutonomy
from app.services.escalation import DEFAULT_STAGE_MODE, STAGE_MODES

logger = logging.getLogger(__name__)

router = APIRouter()

# Literal sets — mirror the 025 CHECK constraints.
ESCALATION_STAGES = ("new", "contacted", "engaged", "qualified", "converted", "lost")

# Post-call outcome → (new stage | None, enrollment status | None, emit converted).
# The vocab a human selects on the call-outcome form; each maps deterministically
# back into the event-sourced graph.
_OUTCOME_MAP: dict[str, dict] = {
    "converted":      {"stage": "converted", "enrollment_status": "completed", "emit_converted": True},
    "booked":         {"stage": "qualified", "enrollment_status": "waiting",   "emit_converted": False},
    "callback":       {"stage": "engaged",   "enrollment_status": "active",    "emit_converted": False},
    "not_interested": {"stage": "lost",      "enrollment_status": "stopped",   "emit_converted": False},
    "no_answer":      {"stage": None,         "enrollment_status": "active",    "emit_converted": False},
}
CALL_OUTCOMES = tuple(_OUTCOME_MAP.keys())


# ─── Schemas ───────────────────────────────────────────────────────────────────
class StageControlOut(BaseModel):
    stage: str
    mode: str
    config: dict = {}


class StageControlUpdate(BaseModel):
    mode: str
    config: dict | None = None


class AutonomyOut(BaseModel):
    autonomy_enabled: bool
    settings: dict = {}


class AutonomyUpdate(BaseModel):
    autonomy_enabled: bool
    settings: dict | None = None


class QueueItem(BaseModel):
    enrollment_id: uuid.UUID
    lead_id: uuid.UUID
    lead_name: str | None = None
    lead_company: str | None = None
    stage: str | None = None
    status: str
    proposed_action: str | None = None
    final_action: str | None = None
    mode: str | None = None
    sentiment: str | None = None
    score: int | None = None
    reason: str | None = None
    needs_judgment: bool = False
    occurred_at: datetime | None = None


class CallOutcomeRequest(BaseModel):
    outcome: str
    notes: str | None = None


class CallOutcomeResponse(BaseModel):
    lead_id: uuid.UUID
    stage: str | None = None
    enrollment_status: str | None = None
    converted_emitted: bool = False
    decision_id: uuid.UUID


def _guard(current_user: User, workspace_id: uuid.UUID) -> None:
    if current_user.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


# ─── Stage controls (static paths) ─────────────────────────────────────────────
@router.get(
    "/workspaces/{workspace_id}/escalation/controls",
    response_model=list[StageControlOut],
)
async def list_stage_controls(
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[StageControlOut]:
    """Return the cap for every stage — a stored row, or the fail-closed default.

    A workspace with no row for a stage falls back to ``DEFAULT_STAGE_MODE`` (``ask``,
    R12), so the operator always sees all six stages with their effective mode.
    """
    _guard(current_user, workspace_id)

    result = await db.execute(
        select(StageControl).where(StageControl.workspace_id == workspace_id)
    )
    stored = {row.stage: row for row in result.scalars().all()}

    out: list[StageControlOut] = []
    for stage in ESCALATION_STAGES:
        row = stored.get(stage)
        if row is not None:
            out.append(StageControlOut(stage=stage, mode=row.mode, config=row.config or {}))
        else:
            out.append(StageControlOut(stage=stage, mode=DEFAULT_STAGE_MODE[stage], config={}))
    return out


@router.put(
    "/workspaces/{workspace_id}/escalation/controls/{stage}",
    response_model=StageControlOut,
)
async def upsert_stage_control(
    workspace_id: uuid.UUID,
    stage: str,
    body: StageControlUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StageControlOut:
    """Upsert the per-stage cap (auto/ask/off). 422 on a bad stage or mode."""
    _guard(current_user, workspace_id)

    if stage not in ESCALATION_STAGES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"stage must be one of {list(ESCALATION_STAGES)}",
        )
    if body.mode not in STAGE_MODES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"mode must be one of {list(STAGE_MODES)}",
        )

    values = {
        "workspace_id": workspace_id,
        "stage": stage,
        "mode": body.mode,
        "config": body.config if body.config is not None else {},
    }
    set_ = {"mode": body.mode, "updated_at": datetime.utcnow()}
    if body.config is not None:
        set_["config"] = body.config
    stmt = (
        pg_insert(StageControl)
        .values(**values)
        .on_conflict_do_update(
            index_elements=[StageControl.workspace_id, StageControl.stage],
            set_=set_,
        )
    )
    await db.execute(stmt)
    db.add(ActivityEvent(
        workspace_id=workspace_id,
        type="stage_control_updated",
        agent_name="Operator",
        description=f"Stage '{stage}' cap set to '{body.mode}'",
        severity="info",
        meta=json.dumps({"stage": stage, "mode": body.mode}),
    ))
    await db.commit()
    return StageControlOut(stage=stage, mode=body.mode, config=values["config"])


# ─── Autonomy master switch ─────────────────────────────────────────────────────
@router.get(
    "/workspaces/{workspace_id}/escalation/autonomy",
    response_model=AutonomyOut,
)
async def get_autonomy(
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AutonomyOut:
    """Return the workspace autonomy master switch (defaults FALSE, R12)."""
    _guard(current_user, workspace_id)

    result = await db.execute(
        select(WorkspaceAutonomy).where(WorkspaceAutonomy.workspace_id == workspace_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return AutonomyOut(autonomy_enabled=False, settings={})
    return AutonomyOut(autonomy_enabled=bool(row.autonomy_enabled), settings=row.settings or {})


@router.put(
    "/workspaces/{workspace_id}/escalation/autonomy",
    response_model=AutonomyOut,
)
async def set_autonomy(
    workspace_id: uuid.UUID,
    body: AutonomyUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AutonomyOut:
    """Toggle the autonomy master switch (R12). Upsert on ``workspace_id``."""
    _guard(current_user, workspace_id)

    values = {
        "workspace_id": workspace_id,
        "autonomy_enabled": body.autonomy_enabled,
        "settings": body.settings if body.settings is not None else {},
    }
    set_ = {"autonomy_enabled": body.autonomy_enabled, "updated_at": datetime.utcnow()}
    if body.settings is not None:
        set_["settings"] = body.settings
    stmt = (
        pg_insert(WorkspaceAutonomy)
        .values(**values)
        .on_conflict_do_update(
            index_elements=[WorkspaceAutonomy.workspace_id],
            set_=set_,
        )
    )
    await db.execute(stmt)
    db.add(ActivityEvent(
        workspace_id=workspace_id,
        type="autonomy_toggled",
        agent_name="Operator",
        description=f"Autonomy master switch set to {body.autonomy_enabled}",
        severity="info",
        meta=json.dumps({"autonomy_enabled": body.autonomy_enabled}),
    ))
    await db.commit()
    return AutonomyOut(autonomy_enabled=body.autonomy_enabled, settings=values["settings"])


# ─── Escalation queue ────────────────────────────────────────────────────────────
@router.get(
    "/workspaces/{workspace_id}/escalation/queue",
    response_model=list[QueueItem],
)
async def escalation_queue(
    workspace_id: uuid.UUID,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[QueueItem]:
    """Waiting enrollments joined to their newest escalation decision.

    ``needs_judgment`` is True when the newest decision for the enrollment escalated
    (``final_action == 'escalate'``) — those want a human, vs a plain ``park`` that
    only wants an approval. Ordered newest-decision-first.
    """
    _guard(current_user, workspace_id)

    enr_result = await db.execute(
        select(SequenceEnrollment)
        .where(
            SequenceEnrollment.workspace_id == workspace_id,
            SequenceEnrollment.status == "waiting",
        )
        .order_by(SequenceEnrollment.updated_at.desc())
        .offset(offset)
        .limit(limit)
    )
    enrollments = list(enr_result.scalars().all())

    items: list[QueueItem] = []
    for enr in enrollments:
        lead_result = await db.execute(
            select(Lead).where(Lead.id == enr.lead_id, Lead.workspace_id == workspace_id)
        )
        lead = lead_result.scalar_one_or_none()

        dec_result = await db.execute(
            select(EscalationDecision)
            .where(
                EscalationDecision.workspace_id == workspace_id,
                EscalationDecision.enrollment_id == enr.id,
            )
            .order_by(EscalationDecision.occurred_at.desc())
            .limit(1)
        )
        decision = dec_result.scalar_one_or_none()

        items.append(QueueItem(
            enrollment_id=enr.id,
            lead_id=enr.lead_id,
            lead_name=getattr(lead, "name", None),
            lead_company=getattr(lead, "company", None),
            stage=getattr(lead, "stage", None),
            status=enr.status,
            proposed_action=getattr(decision, "proposed_action", None),
            final_action=getattr(decision, "final_action", None),
            mode=getattr(decision, "mode", None),
            sentiment=getattr(decision, "sentiment", None),
            score=getattr(decision, "score", None),
            reason=getattr(decision, "reason", None),
            needs_judgment=(getattr(decision, "final_action", None) == "escalate"),
            occurred_at=getattr(decision, "occurred_at", None),
        ))
    return items


# ─── Post-call outcome ──────────────────────────────────────────────────────────
@router.post(
    "/workspaces/{workspace_id}/escalation/leads/{lead_id}/call-outcome",
    response_model=CallOutcomeResponse,
)
async def record_call_outcome(
    workspace_id: uuid.UUID,
    lead_id: uuid.UUID,
    body: CallOutcomeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CallOutcomeResponse:
    """Feed a human post-call outcome back into the event-sourced graph.

    Emits a ``converted`` engagement_event where the outcome warrants it, moves the
    lead stage + its enrollment per :data:`_OUTCOME_MAP`, writes a human-decided
    ``escalation_decisions`` row (``decided_by='human'``), and enqueues a re-score
    (guarded). 422 on an unknown outcome; 404 when the lead is not in this workspace.
    """
    _guard(current_user, workspace_id)

    if body.outcome not in _OUTCOME_MAP:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"outcome must be one of {list(CALL_OUTCOMES)}",
        )

    lead_result = await db.execute(
        select(Lead).where(Lead.id == lead_id, Lead.workspace_id == workspace_id)
    )
    lead = lead_result.scalar_one_or_none()
    if lead is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")

    mapping = _OUTCOME_MAP[body.outcome]

    # Find the lead's live enrollment (waiting/active) to move, if any.
    enr_result = await db.execute(
        select(SequenceEnrollment)
        .where(
            SequenceEnrollment.workspace_id == workspace_id,
            SequenceEnrollment.lead_id == lead_id,
            SequenceEnrollment.status.in_(["waiting", "active"]),
        )
        .order_by(SequenceEnrollment.updated_at.desc())
        .limit(1)
    )
    enrollment = enr_result.scalar_one_or_none()

    # Emit a converted engagement_event where the outcome warrants it (feeds the
    # channel-agnostic engagement scorer).
    converted_emitted = False
    if mapping["emit_converted"]:
        db.add(EngagementEvent(
            workspace_id=workspace_id,
            lead_id=lead_id,
            enrollment_id=getattr(enrollment, "id", None),
            type="converted",
            weight=0,
            metadata_={"source": "call_outcome", "notes": body.notes},
        ))
        converted_emitted = True

    # Move stage + enrollment per the outcome map.
    if mapping["stage"] is not None:
        lead.stage = mapping["stage"]
        db.add(lead)
    if enrollment is not None and mapping["enrollment_status"] is not None:
        enrollment.status = mapping["enrollment_status"]
        db.add(enrollment)

    # Record the human decision (append-only audit; decided_by='human').
    final_status = mapping["enrollment_status"]
    if final_status in ("completed", "stopped"):
        final_action = "stop"
    elif final_status == "waiting":
        final_action = "escalate"
    else:
        final_action = "hold"
    decision = EscalationDecision(
        workspace_id=workspace_id,
        lead_id=lead_id,
        enrollment_id=getattr(enrollment, "id", None),
        stage=mapping["stage"] or (getattr(lead, "stage", None) or "new"),
        proposed_action="escalate",
        final_action=final_action,
        mode="ask",
        score=int(getattr(lead, "score", 0) or 0),
        sentiment=None,
        reason=f"call-outcome:{body.outcome}",
        decided_by="human",
        metadata_={"notes": body.notes} if body.notes else {},
    )
    db.add(decision)
    db.add(ActivityEvent(
        workspace_id=workspace_id,
        type="call_outcome_recorded",
        agent_name="Operator",
        description=f"Call outcome '{body.outcome}' for lead {lead.name or lead_id}",
        severity="info",
        meta=json.dumps({"outcome": body.outcome}),
    ))
    await db.commit()
    await db.refresh(decision)

    # Best-effort re-score off the fresh signal (guarded — a missing worker never 500s).
    try:
        from app.workers.engagement_score import score_lead_engagement

        score_lead_engagement.delay(str(workspace_id), str(lead_id))
    except Exception as exc:  # noqa: BLE001 — scoring is best-effort
        logger.warning("call_outcome score_enqueue_failed lead_id=%s exc=%s", lead_id, exc)

    return CallOutcomeResponse(
        lead_id=lead_id,
        stage=getattr(lead, "stage", None),
        enrollment_status=getattr(enrollment, "status", None),
        converted_emitted=converted_emitted,
        decision_id=decision.id,
    )
