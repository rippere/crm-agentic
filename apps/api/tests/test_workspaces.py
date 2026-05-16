"""Tests for the workspaces router — GET, PATCH, auth checks."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient, ASGITransport

from tests.conftest import _make_scalar_result


def _fake_workspace(workspace_id: uuid.UUID, **kwargs) -> MagicMock:
    ws = MagicMock()
    ws.id = workspace_id
    ws.name = kwargs.get("name", "Acme Workspace")
    ws.slug = kwargs.get("slug", "acme")
    ws.mode = kwargs.get("mode", "sales")
    return ws


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_workspace_returns_workspace(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    ws = _fake_workspace(workspace_id, name="Acme Corp")
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(ws))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}")

    assert resp.status_code == 200
    assert resp.json()["name"] == "Acme Corp"
    assert resp.json()["mode"] == "sales"


@pytest.mark.asyncio
async def test_get_workspace_not_found_returns_404(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_workspace_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong_id}")

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# PATCH /workspaces/{wid}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patch_workspace_updates_name(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    ws = _fake_workspace(workspace_id, name="Old Name", mode="sales")

    def fake_refresh(obj):
        obj.id = ws.id
        obj.name = "New Name"
        obj.slug = ws.slug
        obj.mode = ws.mode

    mock_db.execute = AsyncMock(return_value=_make_scalar_result(ws))
    mock_db.refresh.side_effect = fake_refresh

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.patch(
            f"/workspaces/{workspace_id}",
            json={"name": "New Name"},
        )

    assert resp.status_code == 200
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_patch_workspace_updates_mode(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    ws = _fake_workspace(workspace_id, mode="sales")

    def fake_refresh(obj):
        obj.id = ws.id
        obj.name = ws.name
        obj.slug = ws.slug
        obj.mode = "pm"

    mock_db.execute = AsyncMock(return_value=_make_scalar_result(ws))
    mock_db.refresh.side_effect = fake_refresh

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.patch(
            f"/workspaces/{workspace_id}",
            json={"mode": "pm"},
        )

    assert resp.status_code == 200
    assert ws.mode == "pm"
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_patch_workspace_not_found_returns_404(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.patch(
            f"/workspaces/{workspace_id}",
            json={"name": "New Name"},
        )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_patch_workspace_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.patch(
            f"/workspaces/{wrong_id}",
            json={"name": "Hacked"},
        )

    assert resp.status_code == 403
