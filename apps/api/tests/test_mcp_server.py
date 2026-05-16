"""Tests for mcp_server.py — JSON-RPC endpoint and tool handlers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient, ASGITransport

from tests.conftest import _make_scalars_result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_contact(**kwargs) -> MagicMock:
    c = MagicMock()
    c.name = kwargs.get("name", "Alice Smith")
    c.email = kwargs.get("email", "alice@example.com")
    c.company = kwargs.get("company", "Acme Inc")
    c.role = kwargs.get("role", "CEO")
    c.status = kwargs.get("status", "lead")
    c.ml_score = kwargs.get("ml_score", {"value": 85})
    return c


def _fake_deal(**kwargs) -> MagicMock:
    d = MagicMock()
    d.title = kwargs.get("title", "Enterprise Deal")
    d.company = kwargs.get("company", "Acme Inc")
    d.stage = kwargs.get("stage", "discovery")
    d.value = kwargs.get("value", 10000)
    d.ml_win_probability = kwargs.get("ml_win_probability", 65)
    d.health_score = kwargs.get("health_score", 70)
    return d


# ---------------------------------------------------------------------------
# POST /mcp — protocol methods
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mcp_initialize_returns_protocol_info(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})

    assert resp.status_code == 200
    result = resp.json()["result"]
    assert result["protocolVersion"] == "2024-11-05"
    assert result["serverInfo"]["name"] == "NovaCRM"
    assert "tools" in result["capabilities"]


@pytest.mark.asyncio
async def test_mcp_tools_list_returns_all_tools(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})

    assert resp.status_code == 200
    tools = resp.json()["result"]["tools"]
    tool_names = {t["name"] for t in tools}
    assert {"list_contacts", "list_deals", "stale_deals", "pipeline_summary"}.issubset(tool_names)


@pytest.mark.asyncio
async def test_mcp_unknown_method_returns_error(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post("/mcp", json={"jsonrpc": "2.0", "id": 3, "method": "unknown/method"})

    assert resp.status_code == 200
    error = resp.json()["error"]
    assert error["code"] == -32601
    assert "unknown/method" in error["message"]


@pytest.mark.asyncio
async def test_mcp_invalid_json_returns_400(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            "/mcp",
            content=b"not-valid-json",
            headers={"content-type": "application/json"},
        )

    assert resp.status_code == 400
    assert "JSON" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# POST /mcp — tools/call dispatch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mcp_tools_call_unknown_tool_returns_error(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post("/mcp", json={
            "jsonrpc": "2.0", "id": 4, "method": "tools/call",
            "params": {"name": "no_such_tool", "arguments": {}},
        })

    assert resp.status_code == 200
    error = resp.json()["error"]
    assert error["code"] == -32601
    assert "no_such_tool" in error["message"]


@pytest.mark.asyncio
async def test_mcp_tools_call_no_workspace_returns_error(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    from app.dependencies import get_current_user

    no_ws_user = MagicMock()
    no_ws_user.workspace_id = None

    async def _no_ws():
        return no_ws_user

    fastapi_app.dependency_overrides[get_current_user] = _no_ws
    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post("/mcp", json={
            "jsonrpc": "2.0", "id": 5, "method": "tools/call",
            "params": {"name": "list_contacts", "arguments": {}},
        })

    assert resp.status_code == 200
    error = resp.json()["error"]
    assert error["code"] == -32603
    assert "no workspace" in error["message"].lower()


@pytest.mark.asyncio
async def test_mcp_tools_call_handler_exception_returns_error(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(side_effect=Exception("DB connection failed"))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post("/mcp", json={
            "jsonrpc": "2.0", "id": 6, "method": "tools/call",
            "params": {"name": "list_contacts", "arguments": {}},
        })

    assert resp.status_code == 200
    error = resp.json()["error"]
    assert error["code"] == -32603
    assert "DB connection failed" in error["message"]


# ---------------------------------------------------------------------------
# list_contacts tool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mcp_list_contacts_happy_path(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    contact = _fake_contact()
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([contact]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post("/mcp", json={
            "jsonrpc": "2.0", "id": 7, "method": "tools/call",
            "params": {"name": "list_contacts", "arguments": {}},
        })

    assert resp.status_code == 200
    result = resp.json()["result"]
    assert result["isError"] is False
    content = result["content"][0]["text"]
    assert "Alice Smith" in content
    assert "alice@example.com" in content


@pytest.mark.asyncio
async def test_mcp_list_contacts_query_filters_in_memory(app_client):
    """The query arg filters contacts client-side after DB fetch."""
    fastapi_app, mock_db, workspace_id = app_client
    alice = _fake_contact(name="Alice Smith", email="alice@example.com")
    bob = _fake_contact(name="Bob Jones", email="bob@acme.com")
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([alice, bob]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post("/mcp", json={
            "jsonrpc": "2.0", "id": 8, "method": "tools/call",
            "params": {"name": "list_contacts", "arguments": {"query": "bob"}},
        })

    assert resp.status_code == 200
    content = resp.json()["result"]["content"][0]["text"]
    assert "Bob Jones" in content
    assert "Alice Smith" not in content
    assert "Found 1 contact(s)" in content


@pytest.mark.asyncio
async def test_mcp_list_contacts_query_no_matches(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    contact = _fake_contact(name="Alice Smith")
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([contact]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post("/mcp", json={
            "jsonrpc": "2.0", "id": 9, "method": "tools/call",
            "params": {"name": "list_contacts", "arguments": {"query": "nobody"}},
        })

    assert resp.status_code == 200
    content = resp.json()["result"]["content"][0]["text"]
    assert "Found 0 contact(s)" in content


@pytest.mark.asyncio
async def test_mcp_list_contacts_ml_score_none(app_client):
    """ml_score=None falls back to '?' in output."""
    fastapi_app, mock_db, workspace_id = app_client
    contact = _fake_contact(ml_score=None)
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([contact]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post("/mcp", json={
            "jsonrpc": "2.0", "id": 10, "method": "tools/call",
            "params": {"name": "list_contacts", "arguments": {}},
        })

    assert resp.status_code == 200
    content = resp.json()["result"]["content"][0]["text"]
    assert "ML score: ?" in content


# ---------------------------------------------------------------------------
# list_deals tool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mcp_list_deals_happy_path(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    deal = _fake_deal(title="Big Deal", stage="proposal", value=50000)
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([deal]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post("/mcp", json={
            "jsonrpc": "2.0", "id": 11, "method": "tools/call",
            "params": {"name": "list_deals", "arguments": {}},
        })

    assert resp.status_code == 200
    content = resp.json()["result"]["content"][0]["text"]
    assert "Big Deal" in content
    assert "proposal" in content
    assert "50,000" in content


@pytest.mark.asyncio
async def test_mcp_list_contacts_with_status_filter(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    contact = _fake_contact(status="customer")
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([contact]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post("/mcp", json={
            "jsonrpc": "2.0", "id": 17, "method": "tools/call",
            "params": {"name": "list_contacts", "arguments": {"status": "customer"}},
        })

    assert resp.status_code == 200
    content = resp.json()["result"]["content"][0]["text"]
    assert "Alice Smith" in content


@pytest.mark.asyncio
async def test_mcp_list_deals_with_stage_filter(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    deal = _fake_deal(title="Negotiation Deal", stage="negotiation", value=30000)
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([deal]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post("/mcp", json={
            "jsonrpc": "2.0", "id": 18, "method": "tools/call",
            "params": {"name": "list_deals", "arguments": {"stage": "negotiation"}},
        })

    assert resp.status_code == 200
    content = resp.json()["result"]["content"][0]["text"]
    assert "Negotiation Deal" in content
    assert "negotiation" in content


@pytest.mark.asyncio
async def test_mcp_list_deals_empty(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post("/mcp", json={
            "jsonrpc": "2.0", "id": 12, "method": "tools/call",
            "params": {"name": "list_deals", "arguments": {}},
        })

    assert resp.status_code == 200
    content = resp.json()["result"]["content"][0]["text"]
    assert "Found 0 deal(s)" in content


# ---------------------------------------------------------------------------
# stale_deals tool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mcp_stale_deals_returns_at_risk_deals(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    deal = _fake_deal(title="At-Risk Deal", health_score=25, stage="discovery", value=5000)
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([deal]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post("/mcp", json={
            "jsonrpc": "2.0", "id": 13, "method": "tools/call",
            "params": {"name": "stale_deals", "arguments": {"threshold": 40}},
        })

    assert resp.status_code == 200
    content = resp.json()["result"]["content"][0]["text"]
    assert "At-Risk Deal" in content
    assert "Health: 25" in content


@pytest.mark.asyncio
async def test_mcp_stale_deals_no_results_returns_healthy_message(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post("/mcp", json={
            "jsonrpc": "2.0", "id": 14, "method": "tools/call",
            "params": {"name": "stale_deals", "arguments": {}},
        })

    assert resp.status_code == 200
    content = resp.json()["result"]["content"][0]["text"]
    assert "healthy" in content.lower()


# ---------------------------------------------------------------------------
# pipeline_summary tool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mcp_pipeline_summary_computes_win_rate(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    won = _fake_deal(stage="closed_won", value=20000)
    lost = _fake_deal(stage="closed_lost", value=5000)
    active = _fake_deal(stage="discovery", value=15000)
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([won, lost, active]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post("/mcp", json={
            "jsonrpc": "2.0", "id": 15, "method": "tools/call",
            "params": {"name": "pipeline_summary", "arguments": {}},
        })

    assert resp.status_code == 200
    content = resp.json()["result"]["content"][0]["text"]
    assert "Pipeline Summary" in content
    assert "Win rate: 50%" in content
    assert "$15,000" in content
    assert "Total deals: 3" in content


@pytest.mark.asyncio
async def test_mcp_pipeline_summary_empty_pipeline(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post("/mcp", json={
            "jsonrpc": "2.0", "id": 16, "method": "tools/call",
            "params": {"name": "pipeline_summary", "arguments": {}},
        })

    assert resp.status_code == 200
    content = resp.json()["result"]["content"][0]["text"]
    assert "Win rate: 0%" in content
    assert "Total deals: 0" in content
