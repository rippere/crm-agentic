"""Tests for the messages router — enriched list endpoint."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient, ASGITransport

from tests.conftest import _make_scalars_result


def _fake_clarity(score: int = 85, rationale: str = "Clear and concise") -> MagicMock:
    cs = MagicMock()
    cs.score = score
    cs.rationale = rationale
    return cs


def _fake_task(title: str = "Follow up", status: str = "open") -> MagicMock:
    t = MagicMock()
    t.id = uuid.uuid4()
    t.title = title
    t.status = status
    return t


def _fake_message(workspace_id: uuid.UUID, **kwargs) -> MagicMock:
    msg = MagicMock()
    msg.id = uuid.uuid4()
    msg.workspace_id = workspace_id
    msg.external_id = kwargs.get("external_id", "msg-001")
    msg.subject = kwargs.get("subject", "Hello")
    msg.body_plain = kwargs.get("body_plain", "Body text")
    msg.sender_email = kwargs.get("sender_email", "alice@example.com")
    msg.received_at = kwargs.get("received_at", datetime(2026, 1, 1, tzinfo=timezone.utc))
    msg.contact_id = kwargs.get("contact_id", None)
    msg.processed = kwargs.get("processed", False)
    # Eagerly loaded relationships
    msg.clarity_score = kwargs.get("clarity_score", None)
    msg.tasks = kwargs.get("tasks", [])
    return msg


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/messages
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_messages_empty(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/messages")

    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_messages_returns_messages(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    msg = _fake_message(workspace_id, subject="Project update", sender_email="bob@example.com")
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([msg]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/messages")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["subject"] == "Project update"
    assert data[0]["sender_email"] == "bob@example.com"
    assert data[0]["processed"] is False
    assert data[0]["clarity_score"] is None
    assert data[0]["tasks"] == []


@pytest.mark.asyncio
async def test_list_messages_includes_clarity_score(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    cs = _fake_clarity(score=92, rationale="Crystal clear and actionable")
    msg = _fake_message(workspace_id, subject="Action needed", clarity_score=cs)
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([msg]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/messages")

    assert resp.status_code == 200
    data = resp.json()
    assert data[0]["clarity_score"]["score"] == 92
    assert data[0]["clarity_score"]["rationale"] == "Crystal clear and actionable"


@pytest.mark.asyncio
async def test_list_messages_includes_tasks(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    task1 = _fake_task(title="Schedule review", status="open")
    task2 = _fake_task(title="Send report", status="done")
    msg = _fake_message(workspace_id, tasks=[task1, task2])
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([msg]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/messages")

    assert resp.status_code == 200
    data = resp.json()
    tasks = data[0]["tasks"]
    assert len(tasks) == 2
    assert tasks[0]["title"] == "Schedule review"
    assert tasks[0]["status"] == "open"
    assert tasks[1]["status"] == "done"


@pytest.mark.asyncio
async def test_list_messages_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong_id}/messages")

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/messages/volume-trends
# ---------------------------------------------------------------------------


def _fake_msg_with_service(workspace_id: uuid.UUID, received_at: datetime, service: str | None = "gmail") -> tuple:
    """Return a (Message mock, service_string) pair as the JOIN query would yield."""
    msg = MagicMock()
    msg.id = uuid.uuid4()
    msg.workspace_id = workspace_id
    msg.connector_id = uuid.uuid4()
    msg.received_at = received_at
    return (msg, service)


@pytest.mark.asyncio
async def test_message_volume_trends_groups_by_week_and_source(app_client):
    """GET /messages/volume-trends returns 12 weekly rows with correct source counts."""
    from datetime import timedelta
    from unittest.mock import MagicMock

    fastapi_app, mock_db, workspace_id = app_client

    now = datetime.now(tz=timezone.utc)
    # Two messages in the most recent week: one gmail, one slack
    monday = now - timedelta(days=now.weekday())
    monday = monday.replace(hour=12, minute=0, second=0, microsecond=0)
    rows = [
        _fake_msg_with_service(workspace_id, monday, "gmail"),
        _fake_msg_with_service(workspace_id, monday, "slack"),
    ]
    # Endpoint calls execute().all() (not .scalars().all())
    join_result = MagicMock()
    join_result.all.return_value = rows
    mock_db.execute = AsyncMock(return_value=join_result)

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/messages/volume-trends")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 12
    assert "week_start" in data[0]
    assert "gmail" in data[0]
    assert "slack" in data[0]
    assert "teams" in data[0]
    assert "unknown" in data[0]
    assert "total" in data[0]
    # The most recent week should have the 2 messages we injected
    last_week = data[-1]
    assert last_week["gmail"] + last_week["slack"] == 2
    assert last_week["total"] == 2


@pytest.mark.asyncio
async def test_message_volume_trends_wrong_workspace_returns_403(app_client):
    """GET /messages/volume-trends returns 403 for a different workspace."""
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong_id}/messages/volume-trends")

    assert resp.status_code == 403
