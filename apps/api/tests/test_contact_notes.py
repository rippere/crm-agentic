"""Tests for contact notes endpoints — GET and POST /contacts/{id}/notes."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient, ASGITransport

from tests.conftest import _make_scalar_result, _make_scalars_result

_NOW = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)


def _fake_contact(workspace_id: uuid.UUID, **kwargs) -> MagicMock:
    c = MagicMock()
    c.id = uuid.uuid4()
    c.workspace_id = workspace_id
    c.name = kwargs.get("name", "Alice Smith")
    c.email = kwargs.get("email", "alice@example.com")
    c.company = kwargs.get("company", "Acme")
    c.role = kwargs.get("role", "VP Sales")
    c.status = "lead"
    c.avatar = None
    c.ml_score = {"value": 70, "label": "warm", "trend": "stable", "signals": []}
    c.semantic_tags = []
    c.revenue = 0.0
    c.deal_count = 0
    c.last_activity = "Never"
    c.created_at = None
    c.updated_at = None
    return c


def _fake_note(workspace_id: uuid.UUID, contact_id: uuid.UUID, **kwargs) -> MagicMock:
    note = MagicMock()
    note.id = uuid.uuid4()
    note.workspace_id = workspace_id
    note.contact_id = contact_id
    note.body = kwargs.get("body", "Test note body")
    note.author = kwargs.get("author", "tester@example.com")
    note.created_at = kwargs.get("created_at", _NOW)
    return note


# ---------------------------------------------------------------------------
# POST /workspaces/{wid}/contacts/{cid}/notes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_contact_note_returns_201(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    contact = _fake_contact(workspace_id, name="Alice Smith")
    note = _fake_note(workspace_id, contact.id, body="First call recap", author="me@example.com")

    mock_db.execute = AsyncMock(return_value=_make_scalar_result(contact))

    def fake_refresh(obj):
        for attr in ("id", "workspace_id", "contact_id", "body", "author", "created_at"):
            setattr(obj, attr, getattr(note, attr))

    mock_db.refresh.side_effect = fake_refresh

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{workspace_id}/contacts/{contact.id}/notes",
            json={"body": "First call recap", "author": "me@example.com"},
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["body"] == "First call recap"
    assert data["author"] == "me@example.com"
    assert data["contact_id"] == str(contact.id)
    mock_db.add.assert_called()
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_create_contact_note_empty_body_returns_422(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{workspace_id}/contacts/{uuid.uuid4()}/notes",
            json={"body": "   "},
        )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_contact_note_missing_contact_returns_404(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{workspace_id}/contacts/{uuid.uuid4()}/notes",
            json={"body": "orphan note"},
        )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_contact_note_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{wrong_id}/contacts/{uuid.uuid4()}/notes",
            json={"body": "note"},
        )

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/contacts/{cid}/notes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_contact_notes_chronological(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    contact = _fake_contact(workspace_id, name="Bob Jones")
    n1 = _fake_note(workspace_id, contact.id, body="Oldest", created_at=_NOW - timedelta(days=2))
    n2 = _fake_note(workspace_id, contact.id, body="Newest", created_at=_NOW)

    call_count = 0

    async def _execute_side_effect(q):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _make_scalar_result(contact)   # contact lookup
        return _make_scalars_result([n1, n2])      # notes query (oldest-first)

    mock_db.execute = AsyncMock(side_effect=_execute_side_effect)

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/contacts/{contact.id}/notes")

    assert resp.status_code == 200
    data = resp.json()
    assert [n["body"] for n in data] == ["Oldest", "Newest"]


@pytest.mark.asyncio
async def test_list_contact_notes_empty(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    contact = _fake_contact(workspace_id)

    call_count = 0

    async def _execute_side_effect(q):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _make_scalar_result(contact)
        return _make_scalars_result([])

    mock_db.execute = AsyncMock(side_effect=_execute_side_effect)

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/contacts/{contact.id}/notes")

    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_contact_notes_missing_contact_returns_404(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/contacts/{uuid.uuid4()}/notes")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_contact_notes_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong_id}/contacts/{uuid.uuid4()}/notes")

    assert resp.status_code == 403
