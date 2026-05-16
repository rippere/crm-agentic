"""Tests for the deals router — CRUD + auth checks."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

from tests.conftest import _make_scalar_result, _make_scalars_result


def _fake_deal(workspace_id: uuid.UUID, **kwargs) -> MagicMock:
    deal = MagicMock()
    deal.id = uuid.uuid4()
    deal.workspace_id = workspace_id
    deal.title = kwargs.get("title", "Test Deal")
    deal.company = kwargs.get("company", "Acme")
    deal.contact_name = kwargs.get("contact_name", None)
    deal.contact_id = kwargs.get("contact_id", None)
    deal.value = kwargs.get("value", 10000.0)
    deal.stage = kwargs.get("stage", "discovery")
    deal.ml_win_probability = kwargs.get("ml_win_probability", 50)
    deal.expected_close = kwargs.get("expected_close", None)
    deal.assigned_agent = kwargs.get("assigned_agent", None)
    deal.health_score = kwargs.get("health_score", 100)
    deal.notes = kwargs.get("notes", None)
    deal.created_at = kwargs.get("created_at", None)
    return deal


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/deals — list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_deals_returns_empty(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/deals")

    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_deals_returns_deals(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    deal = _fake_deal(workspace_id, title="Big Deal", value=50000.0)
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([deal]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/deals")

    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["title"] == "Big Deal"


@pytest.mark.asyncio
async def test_list_deals_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong_id}/deals")

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /workspaces/{wid}/deals — create
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_deal_returns_201(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    deal = _fake_deal(workspace_id, title="New Deal", stage="proposal")

    def fake_refresh(obj):
        for attr in ("id", "workspace_id", "title", "company", "contact_name",
                     "contact_id", "value", "stage", "ml_win_probability",
                     "expected_close", "assigned_agent", "health_score"):
            setattr(obj, attr, getattr(deal, attr))

    mock_db.refresh.side_effect = fake_refresh

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{workspace_id}/deals",
            json={"title": "New Deal", "stage": "proposal", "value": 25000.0},
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["stage"] == "proposal"


@pytest.mark.asyncio
async def test_create_deal_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(f"/workspaces/{wrong_id}/deals", json={"title": "x"})

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/deals/{did} — single
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_deal_returns_deal(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    deal = _fake_deal(workspace_id, title="Single Deal")
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(deal))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/deals/{deal.id}")

    assert resp.status_code == 200
    assert resp.json()["title"] == "Single Deal"


@pytest.mark.asyncio
async def test_get_deal_not_found_returns_404(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/deals/{uuid.uuid4()}")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_deal_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong_id}/deals/{uuid.uuid4()}")

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# PATCH /workspaces/{wid}/deals/{did} — update
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patch_deal_updates_fields(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    deal = _fake_deal(workspace_id, title="Old Title", stage="discovery")

    def fake_refresh(obj):
        pass

    mock_db.execute = AsyncMock(return_value=_make_scalar_result(deal))
    mock_db.refresh.side_effect = fake_refresh

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.patch(
            f"/workspaces/{workspace_id}/deals/{deal.id}",
            json={"title": "New Title", "stage": "proposal"},
        )

    assert resp.status_code == 200
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_patch_deal_not_found_returns_404(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.patch(
            f"/workspaces/{workspace_id}/deals/{uuid.uuid4()}",
            json={"title": "x"},
        )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_patch_deal_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.patch(f"/workspaces/{wrong_id}/deals/{uuid.uuid4()}", json={})

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# DELETE /workspaces/{wid}/deals/{did}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_deal_returns_204(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    deal = _fake_deal(workspace_id)
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(deal))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.delete(f"/workspaces/{workspace_id}/deals/{deal.id}")

    assert resp.status_code == 204
    mock_db.delete.assert_awaited_with(deal)
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_delete_deal_not_found_returns_404(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.delete(f"/workspaces/{workspace_id}/deals/{uuid.uuid4()}")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_deal_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.delete(f"/workspaces/{wrong_id}/deals/{uuid.uuid4()}")

    assert resp.status_code == 403
