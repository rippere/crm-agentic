"""Tests for the campaigns router — CRUD + schedule/launch/pause/resume + auth."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

from tests.conftest import _make_scalar_result, _make_scalars_result

_NOW = datetime(2026, 5, 15, 12, 0, 0, tzinfo=timezone.utc)
_WRONG_WS = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")


@pytest.fixture(autouse=True)
def _stub_supabase_rest():
    """ORM-miss paths fall through to the Supabase REST fallback before 404.
    Stub it to None so tests never make a live network call."""
    with patch("app.routers.campaigns.get_row", new=AsyncMock(return_value=None)):
        yield


def _fake_campaign(workspace_id: uuid.UUID, **kwargs) -> MagicMock:
    c = MagicMock()
    c.id = kwargs.get("id", uuid.uuid4())
    c.workspace_id = workspace_id
    c.segment_id = kwargs.get("segment_id", None)
    c.sequence_id = kwargs.get("sequence_id", None)
    c.name = kwargs.get("name", "Spring Blast")
    c.status = kwargs.get("status", "draft")
    c.channel = kwargs.get("channel", "email")
    c.scheduled_at = kwargs.get("scheduled_at", None)
    c.started_at = kwargs.get("started_at", None)
    c.completed_at = kwargs.get("completed_at", None)
    c.stats = kwargs.get("stats", {})
    c.settings = kwargs.get("settings", {})
    c.created_at = kwargs.get("created_at", _NOW - timedelta(days=1))
    c.updated_at = kwargs.get("updated_at", _NOW - timedelta(days=1))
    return c


def _fake_enrollment(workspace_id: uuid.UUID, campaign_id: uuid.UUID, **kwargs) -> MagicMock:
    e = MagicMock()
    e.id = uuid.uuid4()
    e.workspace_id = workspace_id
    e.campaign_id = campaign_id
    e.sequence_id = kwargs.get("sequence_id", uuid.uuid4())
    e.lead_id = kwargs.get("lead_id", uuid.uuid4())
    e.current_step = kwargs.get("current_step", 0)
    e.status = kwargs.get("status", "active")
    e.next_run_at = kwargs.get("next_run_at", None)
    e.last_sent_at = kwargs.get("last_sent_at", None)
    e.created_at = kwargs.get("created_at", _NOW)
    e.updated_at = kwargs.get("updated_at", _NOW)
    return e


def _fake_event(workspace_id: uuid.UUID, campaign_id: uuid.UUID, **kwargs) -> MagicMock:
    ev = MagicMock()
    ev.id = uuid.uuid4()
    ev.workspace_id = workspace_id
    ev.campaign_id = campaign_id
    ev.type = kwargs.get("type", "sent")
    return ev


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/campaigns — list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_campaigns_returns_empty(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/campaigns")

    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_campaigns_returns_campaigns(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    c = _fake_campaign(workspace_id, name="Q3 Nurture", status="active")
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([c]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/campaigns?status=active")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "Q3 Nurture"
    assert data[0]["status"] == "active"


@pytest.mark.asyncio
async def test_list_campaigns_wrong_workspace_returns_403(app_client):
    fastapi_app, _, _ = app_client

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{_WRONG_WS}/campaigns")

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /workspaces/{wid}/campaigns — create (binds segment + sequence)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_campaign_returns_201_binds_segment_and_sequence(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    segment_id = uuid.uuid4()
    sequence_id = uuid.uuid4()
    c = _fake_campaign(
        workspace_id, name="Launch Wave", segment_id=segment_id, sequence_id=sequence_id
    )

    def fake_refresh(obj):
        for attr in (
            "id", "workspace_id", "segment_id", "sequence_id", "name", "status",
            "channel", "scheduled_at", "started_at", "completed_at", "stats",
            "settings", "created_at", "updated_at",
        ):
            setattr(obj, attr, getattr(c, attr))

    mock_db.refresh.side_effect = fake_refresh

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{workspace_id}/campaigns",
            json={
                "name": "Launch Wave",
                "segment_id": str(segment_id),
                "sequence_id": str(sequence_id),
                "channel": "email",
            },
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "draft"
    assert data["segment_id"] == str(segment_id)
    assert data["sequence_id"] == str(sequence_id)
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_create_campaign_bad_channel_returns_422(app_client):
    fastapi_app, _, workspace_id = app_client

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{workspace_id}/campaigns",
            json={"name": "Bad Channel", "channel": "carrier_pigeon"},
        )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_campaign_wrong_workspace_returns_403(app_client):
    fastapi_app, _, _ = app_client

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(f"/workspaces/{_WRONG_WS}/campaigns", json={"name": "x"})

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/campaigns/{id} — detail
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_campaign_returns_campaign(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    c = _fake_campaign(workspace_id, name="Detail Campaign")
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(c))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/campaigns/{c.id}")

    assert resp.status_code == 200
    assert resp.json()["name"] == "Detail Campaign"


@pytest.mark.asyncio
async def test_get_campaign_not_found_returns_404(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/campaigns/{uuid.uuid4()}")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_campaign_wrong_workspace_returns_403(app_client):
    fastapi_app, _, _ = app_client

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{_WRONG_WS}/campaigns/{uuid.uuid4()}")

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# PATCH /workspaces/{wid}/campaigns/{id} — update
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patch_campaign_updates_fields(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    c = _fake_campaign(workspace_id, name="Old Name")
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(c))
    mock_db.refresh.side_effect = lambda obj: None

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.patch(
            f"/workspaces/{workspace_id}/campaigns/{c.id}",
            json={"name": "New Name", "channel": "mixed"},
        )

    assert resp.status_code == 200
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_patch_campaign_bad_channel_returns_422(app_client):
    fastapi_app, _, workspace_id = app_client

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.patch(
            f"/workspaces/{workspace_id}/campaigns/{uuid.uuid4()}",
            json={"channel": "smoke_signal"},
        )

    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /workspaces/{wid}/campaigns/{id}/schedule
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_schedule_campaign_sets_status_scheduled(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    c = _fake_campaign(workspace_id, status="draft")

    def fake_refresh(obj):
        obj.status = "scheduled"

    mock_db.execute = AsyncMock(return_value=_make_scalar_result(c))
    mock_db.refresh.side_effect = fake_refresh

    when = (_NOW + timedelta(days=2)).isoformat()
    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{workspace_id}/campaigns/{c.id}/schedule",
            json={"scheduled_at": when},
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "scheduled"


@pytest.mark.asyncio
async def test_schedule_campaign_not_found_returns_404(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{workspace_id}/campaigns/{uuid.uuid4()}/schedule",
            json={"scheduled_at": _NOW.isoformat()},
        )

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /workspaces/{wid}/campaigns/{id}/launch — 202 + job_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_launch_campaign_returns_202_with_job_id(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    c = _fake_campaign(workspace_id, status="scheduled")
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(c))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(f"/workspaces/{workspace_id}/campaigns/{c.id}/launch")

    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "queued"
    assert data["campaign_id"] == str(c.id)
    assert data["job_id"]  # guarded-import fallback still yields a job id
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_launch_campaign_not_found_returns_404(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(f"/workspaces/{workspace_id}/campaigns/{uuid.uuid4()}/launch")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_launch_campaign_wrong_workspace_returns_403(app_client):
    fastapi_app, _, _ = app_client

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(f"/workspaces/{_WRONG_WS}/campaigns/{uuid.uuid4()}/launch")

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /pause + /resume — status transitions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pause_campaign_sets_status_paused(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    c = _fake_campaign(workspace_id, status="active")

    def fake_refresh(obj):
        obj.status = "paused"

    mock_db.execute = AsyncMock(return_value=_make_scalar_result(c))
    mock_db.refresh.side_effect = fake_refresh

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(f"/workspaces/{workspace_id}/campaigns/{c.id}/pause")

    assert resp.status_code == 200
    assert resp.json()["status"] == "paused"


@pytest.mark.asyncio
async def test_resume_campaign_sets_status_active(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    c = _fake_campaign(workspace_id, status="paused")

    def fake_refresh(obj):
        obj.status = "active"

    mock_db.execute = AsyncMock(return_value=_make_scalar_result(c))
    mock_db.refresh.side_effect = fake_refresh

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(f"/workspaces/{workspace_id}/campaigns/{c.id}/resume")

    assert resp.status_code == 200
    assert resp.json()["status"] == "active"


# ---------------------------------------------------------------------------
# GET /enrollments + /stats
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_enrollments_returns_rows(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    campaign_id = uuid.uuid4()
    enr = _fake_enrollment(workspace_id, campaign_id, status="active")
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([enr]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/campaigns/{campaign_id}/enrollments")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["status"] == "active"
    assert data[0]["campaign_id"] == str(campaign_id)


@pytest.mark.asyncio
async def test_campaign_stats_aggregates_events(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    c = _fake_campaign(workspace_id, status="active", stats={"enrolled": 3})

    call_count = 0

    async def _side_effect(q):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _make_scalar_result(c)  # campaign load
        # stats now issues a GROUP BY aggregate returning (type, count) rows.
        agg = MagicMock()
        agg.all.return_value = [("sent", 2), ("opened", 1)]
        return agg

    mock_db.execute = AsyncMock(side_effect=_side_effect)

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/campaigns/{c.id}/stats")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_events"] == 3
    assert data["events_by_type"]["sent"] == 2
    assert data["events_by_type"]["opened"] == 1
    assert data["stats"]["enrolled"] == 3


@pytest.mark.asyncio
async def test_campaign_stats_not_found_returns_404(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/campaigns/{uuid.uuid4()}/stats")

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /workspaces/{wid}/campaigns/{id} — archive
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_archive_campaign_sets_status_archived(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    c = _fake_campaign(workspace_id, status="completed")

    def fake_refresh(obj):
        obj.status = "archived"

    mock_db.execute = AsyncMock(return_value=_make_scalar_result(c))
    mock_db.refresh.side_effect = fake_refresh

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.delete(f"/workspaces/{workspace_id}/campaigns/{c.id}")

    assert resp.status_code == 200
    assert resp.json()["status"] == "archived"


@pytest.mark.asyncio
async def test_archive_campaign_not_found_returns_404(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.delete(f"/workspaces/{workspace_id}/campaigns/{uuid.uuid4()}")

    assert resp.status_code == 404
