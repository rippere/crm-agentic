"""Tests for the operator chat endpoint POST /workspaces/{ws}/ai/chat (BUILD-SPEC
§2.1.9, V10).

Covers the three V10 gates:
  * tool loop — a stubbed model emits a tool_use for the discovery action; the
    bounded loop routes it through the action bus to ``dispatch_discovery_run``;
  * 403 — a cross-workspace path is rejected on the first-line guard before any
    model call;
  * needs_confirmation — a fail-closed authority resolution (``ask`` / master
    switch off) surfaces ``needs_confirmation`` and does NOT dispatch.

Uses the shared ``app_client`` fixture (auth + DB overridden). The shared LLM
client and the authority resolver are patched; ``workspace_id`` always comes
from the URL + 403 guard, never from the model (R11).
"""

from __future__ import annotations

import contextlib
import uuid as uuid_mod
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


# ---------------------------------------------------------------------------
# fake anthropic client + patch helpers
# ---------------------------------------------------------------------------


def _tool_use_response(action_name: str, args: dict):
    block = MagicMock()
    block.type = "tool_use"
    block.name = action_name
    block.input = args
    block.id = "toolu_1"
    resp = MagicMock()
    resp.stop_reason = "tool_use"
    resp.content = [block]
    return resp


def _text_response(text: str):
    block = MagicMock()
    block.type = "text"
    block.text = text
    resp = MagicMock()
    resp.stop_reason = "end_turn"
    resp.content = [block]
    return resp


def _fake_client(responses):
    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(side_effect=list(responses))
    return client


@contextlib.contextmanager
def _patch_llm(client):
    """Patch the shared LLM client getter + stub the workspace snapshot.

    ``run_agent_turn`` resolves ``get_async_anthropic_client`` from
    ``app.services.llm`` at call time, so patching the module attribute is what
    takes effect. It also builds a live workspace snapshot from the DB before the
    first model call; with the mock session that would churn meaningless queries,
    so the snapshot builder is stubbed to a constant string.
    """
    import app.services.llm as llm
    import app.routers.ai as ai

    with patch.object(llm, "get_async_anthropic_client", return_value=client), \
         patch.object(ai, "_build_workspace_snapshot",
                      new=AsyncMock(return_value="(workspace snapshot)")):
        yield


@contextlib.contextmanager
def _patch_resolver(mode: str):
    """Force the bus authority clamp to a fixed mode.

    The bus consults its own ``_resolve_authority`` seam (delegating to the
    Increment-2 ``app/services/authority.py`` when present, failing closed to
    ``ask`` while absent). Patching that seam keeps the test independent of
    whether ``authority.py`` has landed.
    """
    import app.services.action_bus as bus

    with patch.object(bus, "_resolve_authority", new=AsyncMock(return_value=mode)):
        yield


def _discovery_action_name() -> str:
    import app.services.action_bus as bus
    import app.services.actions  # noqa: F401 — self-registers

    for spec in bus.all_specs():
        if spec.actuating and spec.authority_key == "discovery":
            return spec.name
    raise AssertionError("no discovery action registered")


async def _post_chat(app, workspace_id, body):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post(f"/workspaces/{workspace_id}/ai/chat", json=body)


# ---------------------------------------------------------------------------
# 403 — cross-workspace guard (deterministic, no model call)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_cross_workspace_is_403(app_client):
    app, _db, _ws = app_client
    other_ws = uuid_mod.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    resp = await _post_chat(app, other_ws, {"messages": [{"role": "user", "content": "hi"}]})
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# tool loop — discover action → dispatch_discovery_run
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_tool_loop_dispatches_discovery(app_client):
    app, _db, ws = app_client
    action = _discovery_action_name()
    client = _fake_client([
        _tool_use_response(action, {"locality": "Burlington, VT"}),
        _text_response("Kicked off discovery for Burlington, VT."),
    ])
    fake_run = MagicMock(id=uuid_mod.uuid4(), job_id="celery-abc", locality="Burlington, VT")

    with _patch_llm(client), _patch_resolver("auto"), \
         patch("app.services.discovery.dispatch_discovery_run",
               new=AsyncMock(return_value=fake_run)) as mock_dispatch:
        resp = await _post_chat(
            app, ws, {"messages": [{"role": "user", "content": "find leads in Burlington, begin GTM"}]}
        )

    assert resp.status_code == 200
    mock_dispatch.assert_awaited()
    # the model must never supply workspace_id — it comes from the URL guard.
    ws_arg = mock_dispatch.await_args.args[0] if mock_dispatch.await_args.args else \
        mock_dispatch.await_args.kwargs.get("workspace_id")
    assert str(ws_arg) == str(ws)


# ---------------------------------------------------------------------------
# needs_confirmation — fail-closed authority, no dispatch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_fail_closed_surfaces_needs_confirmation(app_client):
    app, _db, ws = app_client
    action = _discovery_action_name()
    client = _fake_client([
        _tool_use_response(action, {"locality": "Burlington, VT"}),
        _text_response("I need your confirmation before running discovery."),
    ])

    with _patch_llm(client), _patch_resolver("ask"), \
         patch("app.services.discovery.dispatch_discovery_run",
               new=AsyncMock()) as mock_dispatch:
        resp = await _post_chat(
            app, ws, {"messages": [{"role": "user", "content": "find leads in Burlington"}]}
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data.get("needs_confirmation") is True
    mock_dispatch.assert_not_called()
