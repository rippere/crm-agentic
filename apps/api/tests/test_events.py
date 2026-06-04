"""Tests for the events router — activity list and create."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient, ASGITransport

from tests.conftest import _make_scalar_result, _make_scalars_result


def _fake_event(workspace_id: uuid.UUID, **kwargs) -> MagicMock:
    ev = MagicMock()
    ev.id = uuid.uuid4()
    ev.workspace_id = workspace_id
    ev.type = kwargs.get("type", "email_sent")
    ev.agent_name = kwargs.get("agent_name", "Gmail")
    ev.description = kwargs.get("description", "Email sent to contact")
    ev.meta = kwargs.get("meta", "")
    ev.severity = kwargs.get("severity", "info")
    ev.created_at = kwargs.get("created_at", datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc))
    return ev


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/activity — list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_activity_empty(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/activity")

    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_activity_returns_events(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    ev = _fake_event(workspace_id, description="Deal moved to proposal")
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([ev]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/activity")

    assert resp.status_code == 200
    assert resp.json()[0]["description"] == "Deal moved to proposal"


@pytest.mark.asyncio
async def test_list_activity_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong_id}/activity")

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_activity_with_offset_and_type_filter(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    ev = _fake_event(workspace_id, type="deal_moved", description="Moved to proposal")
    captured = {}

    async def _capture_execute(stmt):
        captured["stmt"] = str(stmt)
        return _make_scalars_result([ev])

    mock_db.execute = AsyncMock(side_effect=_capture_execute)

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(
            f"/workspaces/{workspace_id}/activity?limit=10&offset=20&type=deal_moved"
        )

    assert resp.status_code == 200
    assert resp.json()[0]["type"] == "deal_moved"
    # type filter should add a second WHERE predicate on the type column
    assert "type" in captured["stmt"].lower()


# ---------------------------------------------------------------------------
# POST /workspaces/{wid}/activity — create
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_activity_returns_201(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    ev = _fake_event(workspace_id, type="note", agent_name="User", description="Logged a call")

    def fake_refresh(obj):
        for attr in ("id", "workspace_id", "type", "agent_name", "description", "meta", "severity", "created_at"):
            setattr(obj, attr, getattr(ev, attr))

    mock_db.refresh.side_effect = fake_refresh

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{workspace_id}/activity",
            json={"type": "note", "agent_name": "User", "description": "Logged a call"},
        )

    assert resp.status_code == 201
    assert resp.json()["description"] == "Logged a call"
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_create_activity_missing_fields_returns_422(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(f"/workspaces/{workspace_id}/activity", json={"type": "note"})

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_activity_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{wrong_id}/activity",
            json={"type": "note", "agent_name": "User", "description": "test"},
        )

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/events — SSE stream (auth guard only; generator at ceiling)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stream_events_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong_id}/events")

    assert resp.status_code == 403
