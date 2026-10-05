"""Shared authority resolver — the ONE choke point for every outward send (R11).

Autonomous Lead Engine, Increment 2 (§2.2.3 / §3.2). Reads the single
``stage_controls`` table plus the ``workspace_autonomy`` master switch and returns
the clamp mode (``'auto'`` / ``'ask'`` / ``'off'``) for a stage.

BOTH callers resolve against this same function so a send can never bypass the
operator's cap (closing collision C11):

- ``sequence_sender._run_tick`` — before proposing/clamping any per-enrollment send.
- ``action_bus.dispatch``       — before running any actuating chatbot action.

The action_bus's old independent permissive stub is deleted; ``action_bus`` imports
this resolver (defensively, since it shipped in Inc 1 before this module existed).

Fail-closed contract (R11/R12) — the resolver NEVER widens what a caller can do,
it only narrows:

- ``workspace_autonomy.autonomy_enabled`` FALSE (the default, and the state when no
  row exists) forces every stage to ``'ask'`` — except a stage explicitly set to
  ``'off'``, which stays ``'off'``. So no ``'auto'`` is ever returned until an
  operator flips the master switch on.
- With the master switch on, the per-stage ``stage_controls.mode`` governs,
  falling back to ``escalation.DEFAULT_STAGE_MODE[stage]`` (``'ask'``) when the
  workspace has no row for that stage.

The ``action`` argument is accepted for the shared signature (and audit/logging)
but does not currently change the resolution — the per-stage cap governs. A future
per-action override would narrow further, never widen.
"""
from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.escalation import DEFAULT_STAGE_MODE

logger = logging.getLogger(__name__)


async def _autonomy_enabled(workspace_id: uuid.UUID, db: AsyncSession) -> bool:
    """True iff this workspace has flipped the autonomy master switch on (R12).

    No row (the common case for a fresh workspace) => FALSE => fail-closed.
    """
    from app.models.workspace_autonomy import WorkspaceAutonomy

    result = await db.execute(
        select(WorkspaceAutonomy.autonomy_enabled).where(
            WorkspaceAutonomy.workspace_id == workspace_id
        )
    )
    row = result.first()
    return bool(row[0]) if row is not None else False


async def _stage_mode(workspace_id: uuid.UUID, stage: str, db: AsyncSession) -> str:
    """The per-stage cap from ``stage_controls``, or the fail-closed default.

    Falls back to ``DEFAULT_STAGE_MODE[stage]`` (``'ask'``) when the workspace has
    no row for the stage; an unknown stage also fails closed to ``'ask'``.
    """
    from app.models.stage_control import StageControl

    result = await db.execute(
        select(StageControl.mode).where(
            StageControl.workspace_id == workspace_id,
            StageControl.stage == stage,
        )
    )
    row = result.first()
    if row is not None and row[0]:
        return str(row[0])
    return DEFAULT_STAGE_MODE.get(stage, "ask")


async def resolve_authority(
    workspace_id: uuid.UUID, stage: str, action: str, db: AsyncSession
) -> str:
    """Resolve the clamp mode (``'auto'`` / ``'ask'`` / ``'off'``) for a stage.

    See the module docstring for the fail-closed contract. Never raises for a
    missing row; a genuinely broken query propagates (the action_bus wraps this
    call in its own defensive guard so a resolver fault fails closed to ``'ask'``).
    """
    mode = await _stage_mode(workspace_id, stage, db)

    if not await _autonomy_enabled(workspace_id, db):
        # Master switch off: 'off' stays 'off' (kill switch), everything else is
        # narrowed to 'ask' — 'auto' is never reachable until the switch is on.
        return "off" if mode == "off" else "ask"

    return mode
