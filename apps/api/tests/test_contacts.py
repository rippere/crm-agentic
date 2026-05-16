"""Tests for the contacts router — GET/PATCH/DELETE single contact."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient, ASGITransport

from tests.conftest import _make_scalar_result


def _fake_contact(workspace_id: uuid.UUID, **kwargs) -> MagicMock:
    contact = MagicMock()
    contact.id = uuid.uuid4()
    contact.workspace_id = workspace_id
    contact.name = kwargs.get("name", "Alice Smith")
    contact.email = kwargs.get("email", "alice@example.com")
    contact.company = kwargs.get("company", "Acme")
    contact.role = kwargs.get("role", "VP Sales")
    contact.status = kwargs.get("status", "lead")
    contact.avatar = kwargs.get("avatar", None)
    contact.ml_score = {"value": 70, "label": "warm", "trend": "stable", "signals": []}
    contact.semantic_tags = []
    contact.revenue = 0.0
    contact.deal_count = 0
    contact.last_activity = "Never"
    contact.created_at = None
    return contact


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/contacts/{cid}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_contact_returns_contact(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    contact = _fake_contact(workspace_id, name="Bob Jones")
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(contact))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/contacts/{contact.id}")

    assert resp.status_code == 200
    assert resp.json()["name"] == "Bob Jones"


@pytest.mark.asyncio
async def test_get_contact_not_found_returns_404(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/contacts/{uuid.uuid4()}")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_contact_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong_id}/contacts/{uuid.uuid4()}")

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# PATCH /workspaces/{wid}/contacts/{cid}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patch_contact_updates_name(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    contact = _fake_contact(workspace_id, name="Old Name")
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(contact))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.patch(
            f"/workspaces/{workspace_id}/contacts/{contact.id}",
            json={"name": "New Name"},
        )

    assert resp.status_code == 200
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_patch_contact_invalid_status_returns_422(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    contact = _fake_contact(workspace_id)
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(contact))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.patch(
            f"/workspaces/{workspace_id}/contacts/{contact.id}",
            json={"status": "invalid_status"},
        )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_patch_contact_not_found_returns_404(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.patch(
            f"/workspaces/{workspace_id}/contacts/{uuid.uuid4()}",
            json={"name": "x"},
        )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_patch_contact_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.patch(
            f"/workspaces/{wrong_id}/contacts/{uuid.uuid4()}",
            json={"name": "x"},
        )

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# DELETE /workspaces/{wid}/contacts/{cid}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_contact_returns_204(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    contact = _fake_contact(workspace_id)
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(contact))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.delete(f"/workspaces/{workspace_id}/contacts/{contact.id}")

    assert resp.status_code == 204
    mock_db.delete.assert_awaited_with(contact)
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_delete_contact_not_found_returns_404(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.delete(f"/workspaces/{workspace_id}/contacts/{uuid.uuid4()}")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_contact_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.delete(f"/workspaces/{wrong_id}/contacts/{uuid.uuid4()}")

    assert resp.status_code == 403
