"""Tests for the deals router — CRUD + auth checks."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

from tests.conftest import _make_scalar_result, _make_scalars_result

_NOW = datetime(2026, 5, 15, 12, 0, 0, tzinfo=timezone.utc)


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
    deal.created_at = kwargs.get("created_at", _NOW - timedelta(days=5))
    deal.updated_at = kwargs.get("updated_at", _NOW - timedelta(days=5))
    deal.stage_changed_at = kwargs.get("stage_changed_at", _NOW - timedelta(days=5))
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


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/deals?stage= — filter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_deals_with_stage_filter(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    deal = _fake_deal(workspace_id, stage="proposal")
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([deal]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/deals?stage=proposal")

    assert resp.status_code == 200
    assert resp.json()[0]["stage"] == "proposal"


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/deals/stale
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stale_deals_returns_unhealthy_deals(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    deal = _fake_deal(
        workspace_id,
        title="Cold Lead",
        stage="discovery",
        health_score=30,
        stage_changed_at=_NOW - timedelta(days=25),
    )
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([deal]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/deals/stale")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["title"] == "Cold Lead"
    assert "signals" in data[0]


@pytest.mark.asyncio
async def test_stale_deals_empty(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/deals/stale")

    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_stale_deals_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong_id}/deals/stale")

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/deals/history
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deals_history_returns_monthly_buckets(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    deal = _fake_deal(
        workspace_id,
        stage="closed_won",
        value=25000.0,
        updated_at=_NOW - timedelta(days=10),
    )
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([deal]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/deals/history?months=3")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 3
    assert all("month" in row and "revenue" in row for row in data)


@pytest.mark.asyncio
async def test_deals_history_empty_no_closed_won(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/deals/history")

    assert resp.status_code == 200
    data = resp.json()
    assert all(row["revenue"] == 0 for row in data)


@pytest.mark.asyncio
async def test_deals_history_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong_id}/deals/history")

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/pipeline/suggestions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pipeline_suggestions_returns_stale_follow_up(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    deal = _fake_deal(
        workspace_id,
        stage="proposal",
        title="Stale Deal",
        value=15000.0,
        stage_changed_at=_NOW - timedelta(days=35),
        ml_win_probability=60,
    )
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([deal]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/pipeline/suggestions")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert data[0]["action"] == "follow_up"
    assert data[0]["priority"] == "high"


@pytest.mark.asyncio
async def test_pipeline_suggestions_low_probability_review(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    deal = _fake_deal(
        workspace_id,
        stage="negotiation",
        title="Long Shot",
        value=5000.0,
        stage_changed_at=_NOW - timedelta(days=5),
        ml_win_probability=20,
    )
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([deal]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/pipeline/suggestions")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert data[0]["action"] == "review"


@pytest.mark.asyncio
async def test_pipeline_suggestions_empty(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/pipeline/suggestions")

    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_pipeline_suggestions_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong_id}/pipeline/suggestions")

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Naive datetime branches (tzinfo=None handling)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deals_history_naive_datetime_handled(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    deal = _fake_deal(
        workspace_id,
        stage="closed_won",
        value=10000.0,
        updated_at=datetime(2026, 5, 10, 12, 0, 0),  # naive — no tzinfo
    )
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([deal]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/deals/history?months=3")

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_pipeline_suggestions_naive_stage_changed_at(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    deal = _fake_deal(
        workspace_id,
        stage="proposal",
        title="Naive Deal",
        value=8000.0,
        stage_changed_at=datetime(2026, 4, 1, 12, 0, 0),  # naive — no tzinfo, >21 days ago
        ml_win_probability=60,
    )
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([deal]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/pipeline/suggestions")

    assert resp.status_code == 200
    assert resp.json()[0]["action"] == "follow_up"


# ---------------------------------------------------------------------------
# POST /workspaces/{wid}/deals/health — Celery enqueue
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trigger_deal_health_enqueues_job(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    mock_task = MagicMock()
    mock_task.id = "job-abc-123"

    with patch("app.workers.deal_health_worker.compute_deal_health") as mock_celery:
        mock_celery.delay.return_value = mock_task
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(f"/workspaces/{workspace_id}/deals/health")

    assert resp.status_code == 202
    assert resp.json()["status"] == "queued"
    assert resp.json()["job_id"] == "job-abc-123"


@pytest.mark.asyncio
async def test_trigger_deal_health_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(f"/workspaces/{wrong_id}/deals/health")

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /workspaces/{wid}/pipeline/optimize — Celery enqueue
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trigger_pipeline_optimize_enqueues_job(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    mock_task = MagicMock()
    mock_task.id = "opt-job-456"

    with patch("app.workers.pipeline.optimize_pipeline") as mock_celery:
        mock_celery.delay.return_value = mock_task
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(f"/workspaces/{workspace_id}/pipeline/optimize")

    assert resp.status_code == 202
    assert resp.json()["job_id"] == "opt-job-456"


@pytest.mark.asyncio
async def test_trigger_pipeline_optimize_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(f"/workspaces/{wrong_id}/pipeline/optimize")

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/deals/{deal_id}/timeline
# ---------------------------------------------------------------------------


def _fake_activity(workspace_id: uuid.UUID, **kwargs) -> MagicMock:
    from app.models.activity_event import ActivityEvent
    evt = MagicMock(spec=ActivityEvent)
    evt.id = uuid.uuid4()
    evt.workspace_id = workspace_id
    evt.type = kwargs.get("type", "activity")
    evt.agent_name = kwargs.get("agent_name", "System")
    evt.description = kwargs.get("description", "Some event")
    evt.severity = kwargs.get("severity", "info")
    evt.created_at = kwargs.get("created_at", _NOW)
    return evt


@pytest.mark.asyncio
async def test_deal_timeline_returns_events(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    deal = _fake_deal(workspace_id, title="Test Deal Alpha")
    evt = _fake_activity(workspace_id, description="Deal 'Test Deal Alpha' updated → proposal", type="deal_moved")

    call_count = 0

    async def _execute_side_effect(q):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _make_scalar_result(deal)
        return _make_scalars_result([evt])

    mock_db.execute = AsyncMock(side_effect=_execute_side_effect)

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/deals/{deal.id}/timeline")

    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["type"] == "deal_moved"
    assert data[0]["body"] == "Deal 'Test Deal Alpha' updated → proposal"


@pytest.mark.asyncio
async def test_deal_timeline_returns_404_for_missing_deal(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/deals/{uuid.uuid4()}/timeline")

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/deals/export — CSV download
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_export_deals_csv_returns_csv(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    deal = _fake_deal(workspace_id, title="Big Deal Export", value=99000.0, stage="negotiation")

    mock_db.execute = AsyncMock(return_value=_make_scalars_result([deal]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/deals/export")

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    lines = resp.text.strip().splitlines()
    assert lines[0].startswith("id,title,company")
    assert "Big Deal Export" in resp.text


@pytest.mark.asyncio
async def test_export_deals_csv_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong_id}/deals/export")

    assert resp.status_code == 403
