"""
Action bus — the single dispatch choke point for chatbot-driven tool calls.

The agentic chat loop (``app/routers/ai.py::run_agent_turn``) never calls a tool
handler directly. It calls :func:`dispatch`, which is the ONE place that:

1. Looks a tool/action up in a shared registry (:data:`_REGISTRY`).
2. For an **actuating** action (one with real-world side effects — a send, a
   discovery run), consults the shared authority resolver
   (``app/services/authority.py::resolve_authority``) BEFORE running the handler,
   so the operator's per-stage ``auto``/``ask``/``off`` clamp governs every
   outward action routed through the bus — closing the clamp-bypass hole the
   build spec called out (R11/C11). The action_bus's old independent permissive
   ``resolve_authority`` stub is intentionally NOT built here.
3. For a **read** action (the NovaCRM MCP tools — ``list_contacts``,
   ``list_deals``, ``stale_deals``, ``pipeline_summary``, ``ask_crm``), resolves
   to ``auto`` with no stage and runs the handler directly.

Every read tool exposed by ``app/routers/mcp_server.py`` (``TOOLS`` /
``TOOL_HANDLERS``) is wrapped here at import time as a **non-actuating**
``ActionSpec`` (``actuating=False``, ``authority_key=None``). ``mcp_server.TOOLS``
stays strictly READ-ONLY — no write tool is ever appended to it (R10/C10); the
one actuating action (``discover_market``) is registered ONLY through this bus by
``app/services/actions/discovery.py``.

Fail-closed on a missing resolver (R12): ``authority.py`` lands with Increment 2.
Until then :func:`_resolve_authority` imports it defensively and, when absent,
returns ``'ask'`` for any actuating action — never ``'auto'`` — so the master
switch effectively defaults off and no autonomous outward action fires without
explicit operator confirmation.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# A handler is an async callable ``(args, workspace_id, db, current_user) -> Any``.
# The return value is coerced to text for the model's tool_result; a handler may
# also return a dict (e.g. {"job_id": ...}) which :func:`dispatch` inspects for a
# ``job_id`` to surface to the browser poller.
ActionHandler = Callable[[dict, uuid.UUID, AsyncSession, Any], Awaitable[Any]]


@dataclass(frozen=True)
class ActionSpec:
    """A registered action the chatbot may invoke through the bus.

    ``actuating`` marks an action with real side effects (an outward send, a
    discovery run): such actions are gated by :func:`_resolve_authority` before
    the handler runs. ``authority_key`` names the action for the resolver;
    ``stage`` is the funnel stage the resolver clamps against (``None`` for a
    stage-less action such as discovery, which the resolver treats per its
    fail-closed default). Read tools set ``actuating=False`` and no key.
    """

    name: str
    description: str
    input_schema: dict
    handler: ActionHandler
    actuating: bool = False
    authority_key: str | None = None
    stage: str | None = None


@dataclass
class ActionResult:
    """Outcome of a :func:`dispatch` call.

    ``needs_confirmation`` is set when an actuating action resolved to ``'ask'``
    and the caller did not pass ``confirmed=True`` — the handler did NOT run and
    the chat surface should render a Confirm button that re-dispatches with
    confirmation. ``authority`` records the resolved clamp for an actuating
    action (``'auto'``/``'ask'``/``'off'``); it is ``'auto'`` for read tools.
    ``job_id`` carries a dispatched Celery job id when the handler produced one.
    """

    ok: bool
    action: str
    actuating: bool
    authority: str | None = None
    needs_confirmation: bool = False
    output: Any = None
    job_id: str | None = None
    error: str | None = None

    def as_text(self) -> str:
        """Render this result as the ``tool_result`` content string for the model."""
        if self.error:
            return f"Action '{self.action}' failed: {self.error}"
        if self.needs_confirmation:
            return (
                f"Action '{self.action}' requires operator confirmation before it "
                f"can run (authority='{self.authority}'). Awaiting confirmation."
            )
        if isinstance(self.output, str):
            return self.output
        if self.output is None:
            return f"Action '{self.action}' completed."
        return str(self.output)


# ── Registry ──────────────────────────────────────────────────────────────────
# Keyed by action name so a re-import (e.g. actions/__init__ imported twice)
# overwrites rather than duplicates. ``registry`` is the PUBLIC handle on the same
# dict object (``register()`` mutates it in place, so the alias stays live); the
# ``_REGISTRY`` name is kept for internal readability. ``ACTIONS`` is an additional
# alias for callers that prefer the shoutier name.
_REGISTRY: dict[str, ActionSpec] = {}
registry: dict[str, ActionSpec] = _REGISTRY
ACTIONS: dict[str, ActionSpec] = _REGISTRY


def register(spec: ActionSpec) -> None:
    """Register (or replace) an action spec by name."""
    _REGISTRY[spec.name] = spec


def get(name: str) -> ActionSpec | None:
    """Return the registered spec for ``name``, or ``None``."""
    return _REGISTRY.get(name)


def all_specs() -> list[ActionSpec]:
    """Return every registered action spec (read tools + actuating actions)."""
    return list(_REGISTRY.values())


def tool_definitions() -> list[dict]:
    """Return the Anthropic tool-use definitions for every registered action.

    Shape: ``[{"name", "description", "input_schema"}, ...]`` — the format the
    Messages API ``tools=`` parameter expects. Both read tools and actuating
    actions are advertised to the model; the authority clamp is enforced at
    dispatch, not by hiding the tool.
    """
    return [
        {
            "name": spec.name,
            "description": spec.description,
            "input_schema": spec.input_schema,
        }
        for spec in _REGISTRY.values()
    ]


# ── Authority (defensive / fail-closed — R11/R12) ──────────────────────────────
async def _resolve_authority(
    workspace_id: uuid.UUID, stage: str | None, action: str, db: AsyncSession
) -> str:
    """Resolve the authority clamp for an actuating action, fail-closed.

    Delegates to the shared ``app/services/authority.py::resolve_authority`` — the
    SAME resolver ``sequence_sender._run_tick`` calls, so a send routed through
    the bus resolves against the same ``stage_controls`` table as the tick (R11).

    ``authority.py`` is an Increment-2 file. Until it lands this imports it
    defensively and, when absent, returns ``'ask'`` — never ``'auto'`` — for an
    actuating action (R12 fail-closed: the workspace master switch defaults off,
    so no autonomous outward action fires without explicit confirmation).
    """
    try:
        from app.services.authority import resolve_authority
    except ImportError:
        logger.debug(
            "action_bus authority resolver absent (Inc-2); failing closed to 'ask' "
            "for action=%s",
            action,
        )
        return "ask"

    try:
        return await resolve_authority(workspace_id, stage or "", action, db)
    except Exception as exc:  # noqa: BLE001 — resolver must never widen access
        logger.warning("action_bus resolve_authority raised action=%s exc=%s", action, exc)
        return "ask"


async def dispatch(
    name: str,
    args: dict,
    workspace_id: uuid.UUID,
    db: AsyncSession,
    current_user: Any,
    *,
    confirmed: bool = False,
) -> ActionResult:
    """Dispatch a chatbot tool/action call through the authority clamp.

    - Unknown action -> ``ok=False`` with an error (the model can recover).
    - Non-actuating (read) action -> runs the handler directly, ``authority='auto'``.
    - Actuating action -> resolves authority FIRST:
        * ``'off'``  -> refused (the kill switch wins even over ``confirmed``).
        * ``'ask'`` and not ``confirmed`` -> ``needs_confirmation=True``, handler
          NOT run (the chat surfaces a Confirm button).
        * ``'auto'``, or ``'ask'`` with ``confirmed=True`` -> runs the handler.

    ``workspace_id`` is supplied by the caller (the URL + 403 guard in
    ``ai.py``), never by the model, and is passed into the handler as-is.
    """
    spec = _REGISTRY.get(name)
    if spec is None:
        return ActionResult(
            ok=False, action=name, actuating=False, error=f"Unknown action: {name}"
        )

    if not spec.actuating:
        try:
            output = await spec.handler(args, workspace_id, db, current_user)
        except Exception as exc:  # noqa: BLE001 — a tool failure is reported, not fatal
            logger.warning("action_bus read handler failed action=%s exc=%s", name, exc)
            return ActionResult(
                ok=False, action=name, actuating=False, authority="auto", error=str(exc)
            )
        return ActionResult(
            ok=True, action=name, actuating=False, authority="auto", output=output
        )

    # Actuating: consult the shared resolver before running anything.
    authority = await _resolve_authority(workspace_id, spec.stage, spec.authority_key or name, db)

    if authority == "off":
        return ActionResult(
            ok=False,
            action=name,
            actuating=True,
            authority="off",
            error="Action is disabled for this workspace (authority=off).",
        )

    if authority != "auto" and not confirmed:
        # 'ask' (or any non-auto that isn't the hard 'off' kill switch): require
        # explicit operator confirmation before the handler runs.
        return ActionResult(
            ok=True,
            action=name,
            actuating=True,
            authority=authority,
            needs_confirmation=True,
        )

    try:
        output = await spec.handler(args, workspace_id, db, current_user)
    except Exception as exc:  # noqa: BLE001
        logger.warning("action_bus actuating handler failed action=%s exc=%s", name, exc)
        return ActionResult(
            ok=False, action=name, actuating=True, authority=authority, error=str(exc)
        )

    job_id = output.get("job_id") if isinstance(output, dict) else None
    return ActionResult(
        ok=True,
        action=name,
        actuating=True,
        authority=authority,
        output=output,
        job_id=job_id,
    )


# ── Wrap the read-only MCP tools as non-actuating actions (R10) ────────────────
def _wrap_read_handler(
    fn: Callable[[dict, uuid.UUID, AsyncSession], Awaitable[Any]]
) -> ActionHandler:
    """Adapt an mcp_server handler ``(args, ws, db)`` to the bus 4-arg signature."""

    async def _handler(
        args: dict, workspace_id: uuid.UUID, db: AsyncSession, current_user: Any
    ) -> Any:
        return await fn(args, workspace_id, db)

    return _handler


def _register_read_tools() -> None:
    """Register every read-only MCP tool from ``mcp_server`` as a non-actuating spec.

    ``mcp_server.TOOLS`` stays READ-ONLY (R10): this only *reads* that registry to
    expose the same tools to the chat loop; it never appends a write tool to it.
    """
    try:
        from app.routers import mcp_server
    except Exception as exc:  # noqa: BLE001 — never let this break importing the bus
        logger.warning("action_bus could not import mcp_server read tools: %s", exc)
        return

    handlers = getattr(mcp_server, "TOOL_HANDLERS", {})
    for tool in getattr(mcp_server, "TOOLS", []):
        tool_name = tool.get("name")
        handler = handlers.get(tool_name)
        if not tool_name or handler is None:
            continue
        register(
            ActionSpec(
                name=tool_name,
                description=tool.get("description", ""),
                input_schema=tool.get("inputSchema", {"type": "object", "properties": {}}),
                handler=_wrap_read_handler(handler),
                actuating=False,
                authority_key=None,
            )
        )


_register_read_tools()
