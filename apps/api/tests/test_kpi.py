"""Tests for the kpi router — batch upsert idempotency + list filtering."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient, ASGITransport

from tests.conftest import _make_scalar_result, _make_scalars_result


def _fake_snapshot(workspace_id: uuid.UUID, **kwargs) -> MagicMock:
    snap = MagicMock()
    snap.id = uuid.uuid4()
    snap.workspace_id = workspace_id
    snap.date = kwargs.get("date", date(2026, 6, 5))
    snap.domain = kwargs.get("domain", "engineering")
    snap.metric = kwargs.get("metric", "git_commits")
    snap.value = kwargs.get("value", Decimal("7"))
    snap.meta = kwargs.get("meta", {})
    snap.updated_at = kwargs.get("updated_at", None)
    return snap


# ---------------------------------------------------------------------------
# PUT /workspaces/{wid}/kpi/{date} — batch upsert
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upsert_kpi_inserts_new_rows(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    # Every metric lookup misses -> new rows added.
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.put(
            f"/workspaces/{workspace_id}/kpi/2026-06-05",
            json={
                "snapshots": [
                    {"domain": "engineering", "metric": "git_commits", "value": 7, "meta": {}},
                    {"domain": "knowledge", "metric": "sessions", "value": 3, "meta": {"src": "vault"}},
                ]
            },
        )

    assert resp.status_code == 200
    assert resp.json() == {"upserted": 2, "date": "2026-06-05"}
    assert mock_db.add.call_count == 2
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_upsert_kpi_same_metric_updates_in_place(app_client):
    """Idempotency: re-pushing the same (date, metric) updates value/meta, no new row."""
    fastapi_app, mock_db, workspace_id = app_client
    existing = _fake_snapshot(workspace_id, metric="git_commits", value=Decimal("7"), domain="engineering")
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(existing))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.put(
            f"/workspaces/{workspace_id}/kpi/2026-06-05",
            json={"snapshots": [{"domain": "engineering", "metric": "git_commits", "value": 11, "meta": {"runs": 2}}]},
        )

    assert resp.status_code == 200
    assert resp.json() == {"upserted": 1, "date": "2026-06-05"}
    # Existing row mutated in place — no insert.
    mock_db.add.assert_not_called()
    assert existing.value == 11
    assert existing.meta == {"runs": 2}
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_upsert_kpi_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.put(
            f"/workspaces/{wrong_id}/kpi/2026-06-05",
            json={"snapshots": [{"domain": "life", "metric": "sleep", "value": 8}]},
        )

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/kpi — list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_kpi_returns_rows(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    snap = _fake_snapshot(workspace_id, metric="crm_users", value=Decimal("42"))
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([snap]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/kpi?from_date=2026-06-01&to_date=2026-06-30&domain=engineering")

    assert resp.status_code == 200
    body = resp.json()
    assert body[0]["metric"] == "crm_users"
    # NUMERIC serialized as float.
    assert body[0]["value"] == 42.0


@pytest.mark.asyncio
async def test_list_kpi_wrong_workspace_returns_403(app_client):
    fastapi_app, _, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong_id}/kpi")

    assert resp.status_code == 403
