"""Tests for ai.py — Nova AI assistant endpoint."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient, ASGITransport


def _fake_deal_row(**kwargs) -> MagicMock:
    row = MagicMock()
    row.stage = kwargs.get("stage", "proposal")
    row.title = kwargs.get("title", "Test Deal")
    row.company = kwargs.get("company", "Acme")
    row.value = kwargs.get("value", 15000.0)
    row.health_score = kwargs.get("health_score", 85)
    return row


def _fake_event_row(**kwargs) -> MagicMock:
    row = MagicMock()
    row.type = kwargs.get("type", "contact_created")
    row.description = kwargs.get("description", "New contact added")
    row.agent_name = kwargs.get("agent_name", "System")
    return row


def _make_execute_result(rows: list) -> MagicMock:
    result = MagicMock()
    result.all.return_value = rows
    return result


# ---------------------------------------------------------------------------
# POST /workspaces/{wid}/ai/query
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ai_query_empty_body_returns_400(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{workspace_id}/ai/query",
            json={"query": "   "},
        )

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_ai_query_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{wrong_id}/ai/query",
            json={"query": "How is my pipeline?"},
        )

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_ai_query_returns_claude_answer(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    deal = _fake_deal_row(stage="proposal", value=25000.0, health_score=90)
    event = _fake_event_row(description="Deal moved to proposal")

    # scalar() calls: contact_count=5, open_tasks=3
    mock_db.scalar = AsyncMock(side_effect=[5, 3])
    # execute() calls: deals, events
    mock_db.execute = AsyncMock(side_effect=[
        _make_execute_result([deal]),
        _make_execute_result([event]),
    ])

    mock_claude_response = MagicMock()
    mock_claude_response.content = [MagicMock(text="Your pipeline looks strong.")]

    with patch("app.routers.ai._anthropic.Anthropic") as mock_anthropic_cls:
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.return_value = mock_claude_response

        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(
                f"/workspaces/{workspace_id}/ai/query",
                json={"query": "How is my pipeline doing?"},
            )

    assert resp.status_code == 200
    assert resp.json()["answer"] == "Your pipeline looks strong."


@pytest.mark.asyncio
async def test_ai_query_claude_unavailable_returns_503(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    mock_db.scalar = AsyncMock(side_effect=[0, 0])
    mock_db.execute = AsyncMock(side_effect=[
        _make_execute_result([]),
        _make_execute_result([]),
    ])

    with patch("app.routers.ai._anthropic.Anthropic") as mock_anthropic_cls:
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.side_effect = Exception("Connection timeout")

        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(
                f"/workspaces/{workspace_id}/ai/query",
                json={"query": "What should I focus on today?"},
            )

    assert resp.status_code == 503
    assert "AI unavailable" in resp.json()["detail"]
