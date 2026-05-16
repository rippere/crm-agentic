"""Tests for the messages router — list endpoint."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient, ASGITransport

from tests.conftest import _make_scalars_result


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


@pytest.mark.asyncio
async def test_list_messages_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong_id}/messages")

    assert resp.status_code == 403
