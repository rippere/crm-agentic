"""
The ONE actuating chatbot action for Increment 1 — market discovery.

Registered through the action_bus (NOT ``mcp_server.TOOLS``, which stays
read-only — R10/C10) as ``actuating=True`` with ``authority_key="discovery"``,
so every invocation passes through the shared authority clamp before it runs. The
handler is a thin adapter over the ONE dispatch seam
``app/services/discovery.py::dispatch_discovery_run`` (R2) — the same seam the
``POST /discovery/runs`` router calls. There is no phantom
``run_discovery(ws, locality, criteria)`` variant.

This collapses the drafts' ``discover_market`` and ``trigger_discovery`` into a
single tool with one argument schema ``{locality, categories?, max_venues?}``
(R10/C10). In Increment 1 discovery is inbound R&D with no outward comms; the
shared resolver treats this stage-less actuating action per its fail-closed
default (master switch off -> ``'ask'`` unless the operator has enabled
autonomy), so the chat surfaces a Confirm button via ``needs_confirmation``.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.action_bus import ActionSpec

logger = logging.getLogger(__name__)


async def _handle_discovery(
    args: dict, workspace_id: uuid.UUID, db: AsyncSession, current_user: Any
) -> dict:
    """Kick off a market-discovery run and return a small pollable summary.

    Imports are local to avoid an import cycle
    (``routers.discovery`` <-> ``services.discovery`` <-> this module) and so the
    package imports clean even before the sibling ``services/discovery.py`` seam
    lands. ``workspace_id`` comes from the caller (URL + 403 guard), never the
    model. Returns ``{run_id, status, job_id, locality}`` — the ``job_id`` the
    action_bus surfaces so the browser poller can track the run via
    ``GET /jobs/{job_id}``.
    """
    # Local imports: the dispatch seam + request schema are owned by sibling
    # modules; importing them at module top would risk a cycle and would make
    # this package fail to import before those land.
    from app.routers.discovery import DiscoveryRunRequest
    from app.services.discovery import dispatch_discovery_run

    request = DiscoveryRunRequest(**args)
    run = await dispatch_discovery_run(workspace_id, request, db)
    return {
        "run_id": str(run.id),
        "status": run.status,
        "job_id": run.job_id,
        "locality": run.locality,
    }


# The single argument schema (R10/C10) advertised to the model.
SPEC = ActionSpec(
    name="discover_market",
    description=(
        "Discover and rubric-score prospective venues in a locality (a city or "
        "region), loading the scored venues into the CRM as leads. Long-running: "
        "returns a job_id the UI polls for progress. Use when the operator asks to "
        "find leads/prospects/venues in a place or to 'begin GTM' there."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "locality": {
                "type": "string",
                "description": "City/region to search, e.g. 'Burlington, VT'.",
            },
            "categories": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional venue categories to focus on (e.g. brewery, museum).",
            },
            "max_venues": {
                "type": "integer",
                "description": "Maximum venues to discover (default 60).",
            },
        },
        "required": ["locality"],
    },
    handler=_handle_discovery,
    actuating=True,
    authority_key="discovery",
    stage=None,
)
