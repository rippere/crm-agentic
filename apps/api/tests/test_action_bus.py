"""Tests for the action bus (app.services.action_bus) — BUILD-SPEC R10/R11.

Covers:
  * registry reuse — every read tool in ``mcp_server.TOOL_HANDLERS`` is wrapped
    as a NON-actuating ActionSpec (``actuating=False``, ``authority_key=None``),
    and NO write tool leaks into ``mcp_server.TOOLS`` (R10: mcp stays read-only);
  * unknown action → a failed ActionResult, never an exception;
  * resolver wiring / fail-closed — the ONE actuating action (``discover_market``)
    routes through the shared authority clamp; a non-``auto`` resolution yields
    ``needs_confirmation`` and does NOT run the handler; ``auto`` (or an explicit
    confirm) runs it (R11/R12).

Zero DB, zero network: the authority resolution and the discovery dispatch seam
are patched. authority.py is an Increment-2 file, so the bus fails closed to
``ask``; the tests steer it by patching ``action_bus._resolve_authority``.
"""

from __future__ import annotations

import uuid as uuid_mod
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_WS = uuid_mod.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_DISCOVERY_ACTION = "discover_market"


def _user():
    user = MagicMock()
    user.workspace_id = _WS
    return user


def _registry_by_name():
    import app.services.action_bus as bus
    import app.services.actions  # noqa: F401 — self-registers the actuating action

    return {spec.name: spec for spec in bus.all_specs()}


# ---------------------------------------------------------------------------
# registry reuse (R10)
# ---------------------------------------------------------------------------


def test_read_tools_registered_as_non_actuating():
    from app.routers.mcp_server import TOOL_HANDLERS

    registry = _registry_by_name()
    for name in TOOL_HANDLERS:
        assert name in registry, f"read tool {name!r} not wrapped into the action registry"
        spec = registry[name]
        assert spec.actuating is False
        assert spec.authority_key is None


def test_no_write_tool_leaked_into_read_registry():
    """R10/C10 — mcp_server.TOOLS stays read-only; the write action is bus-only."""
    from app.routers.mcp_server import TOOLS

    names = {t["name"] for t in TOOLS}
    assert "discover_market" not in names
    assert "trigger_discovery" not in names


def test_discovery_action_registered_actuating_with_authority_key():
    registry = _registry_by_name()
    assert _DISCOVERY_ACTION in registry
    spec = registry[_DISCOVERY_ACTION]
    assert spec.actuating is True
    assert spec.authority_key == "discovery"
    # Stage-less discovery (R10) — the resolver treats it per its fail-closed default.
    assert spec.stage is None


def test_tool_definitions_include_read_and_actuating():
    import app.services.action_bus as bus
    import app.services.actions  # noqa: F401

    defs = {d["name"] for d in bus.tool_definitions()}
    assert _DISCOVERY_ACTION in defs
    assert "list_contacts" in defs


# ---------------------------------------------------------------------------
# unknown action
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_action_returns_failed_result_not_exception():
    import app.services.action_bus as bus

    result = await bus.dispatch("no_such_action", {}, _WS, AsyncMock(), _user())
    assert result.ok is False
    assert result.error and "Unknown action" in result.error


# ---------------------------------------------------------------------------
# resolver wiring / fail-closed (R11/R12)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_actuating_action_fail_closed_needs_confirmation_and_does_not_run():
    import app.services.action_bus as bus
    import app.services.actions  # noqa: F401

    with patch.object(bus, "_resolve_authority", new=AsyncMock(return_value="ask")), \
         patch("app.services.discovery.dispatch_discovery_run", new=AsyncMock()) as mock_dispatch:
        result = await bus.dispatch(
            _DISCOVERY_ACTION, {"locality": "Burlington, VT"}, _WS, AsyncMock(), _user()
        )

    assert result.needs_confirmation is True
    assert result.actuating is True
    mock_dispatch.assert_not_called()


@pytest.mark.asyncio
async def test_off_kill_switch_refuses_even_when_confirmed():
    import app.services.action_bus as bus
    import app.services.actions  # noqa: F401

    with patch.object(bus, "_resolve_authority", new=AsyncMock(return_value="off")), \
         patch("app.services.discovery.dispatch_discovery_run", new=AsyncMock()) as mock_dispatch:
        result = await bus.dispatch(
            _DISCOVERY_ACTION, {"locality": "Burlington, VT"}, _WS, AsyncMock(), _user(),
            confirmed=True,
        )

    assert result.ok is False
    assert result.authority == "off"
    mock_dispatch.assert_not_called()


@pytest.mark.asyncio
async def test_actuating_action_auto_runs_handler():
    import app.services.action_bus as bus
    import app.services.actions  # noqa: F401

    fake_run = MagicMock(id=uuid_mod.uuid4(), status="queued", job_id="celery-123",
                         locality="Burlington, VT")
    with patch.object(bus, "_resolve_authority", new=AsyncMock(return_value="auto")), \
         patch("app.services.discovery.dispatch_discovery_run",
               new=AsyncMock(return_value=fake_run)) as mock_dispatch:
        result = await bus.dispatch(
            _DISCOVERY_ACTION, {"locality": "Burlington, VT"}, _WS, AsyncMock(), _user()
        )

    mock_dispatch.assert_awaited_once()
    assert result.ok is True
    assert result.needs_confirmation is False
    assert result.job_id == "celery-123"


@pytest.mark.asyncio
async def test_actuating_action_confirmed_runs_even_when_ask():
    import app.services.action_bus as bus
    import app.services.actions  # noqa: F401

    fake_run = MagicMock(id=uuid_mod.uuid4(), status="queued", job_id="celery-9",
                         locality="Burlington, VT")
    with patch.object(bus, "_resolve_authority", new=AsyncMock(return_value="ask")), \
         patch("app.services.discovery.dispatch_discovery_run",
               new=AsyncMock(return_value=fake_run)) as mock_dispatch:
        result = await bus.dispatch(
            _DISCOVERY_ACTION, {"locality": "Burlington, VT"}, _WS, AsyncMock(), _user(),
            confirmed=True,
        )

    mock_dispatch.assert_awaited_once()
    assert result.needs_confirmation is False


@pytest.mark.asyncio
async def test_workspace_id_passed_to_handler_not_model_supplied():
    """The URL-derived workspace_id is threaded to the dispatch seam (R11)."""
    import app.services.action_bus as bus
    import app.services.actions  # noqa: F401

    fake_run = MagicMock(id=uuid_mod.uuid4(), status="queued", job_id="j", locality="X")
    with patch.object(bus, "_resolve_authority", new=AsyncMock(return_value="auto")), \
         patch("app.services.discovery.dispatch_discovery_run",
               new=AsyncMock(return_value=fake_run)) as mock_dispatch:
        # A model-supplied workspace_id in args must be ignored — the handler uses
        # the caller's workspace_id positional argument.
        await bus.dispatch(
            _DISCOVERY_ACTION,
            {"locality": "Burlington, VT"},
            _WS, AsyncMock(), _user(),
        )

    ws_arg = mock_dispatch.await_args.args[0]
    assert ws_arg == _WS


# ---------------------------------------------------------------------------
# read tool dispatch — auto, no stage, no confirmation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_read_tool_resolves_auto_without_confirmation():
    import app.services.action_bus as bus

    # A read tool runs directly; give it a db whose query returns no rows.
    db = AsyncMock()
    empty = MagicMock()
    empty.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(return_value=empty)

    result = await bus.dispatch("list_contacts", {}, _WS, db, _user())
    assert result.actuating is False
    assert result.authority == "auto"
    assert result.needs_confirmation is False
