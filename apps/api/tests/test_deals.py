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
    deal.win_loss_reason = kwargs.get("win_loss_reason", None)
    deal.next_action = kwargs.get("next_action", None)
    deal.next_action_date = kwargs.get("next_action_date", None)
    deal.competitors = kwargs.get("competitors", [])
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
                     "expected_close", "assigned_agent", "health_score",
                     "competitors", "created_at"):
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
        stage_changed_at=datetime.now(timezone.utc) - timedelta(days=5),
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


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/deals/{id}/timeline-summary — weekly sparkline
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deal_timeline_summary_returns_12_weeks(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    deal = _fake_deal(workspace_id, title="Sparkline Deal")

    # One activity event created 2 weeks ago (falls in week 10 of 12)
    evt = _fake_activity(
        workspace_id,
        description="Deal 'Sparkline Deal' updated → proposal",
        type="deal_moved",
        created_at=datetime.now(timezone.utc) - timedelta(weeks=2),
    )

    call_count = 0

    async def _execute_side_effect(q):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _make_scalar_result(deal)
        return _make_scalars_result([evt])

    mock_db.execute = AsyncMock(side_effect=_execute_side_effect)

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/deals/{deal.id}/timeline-summary")

    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 12
    assert all("week" in b and "events" in b for b in data)
    assert sum(b["events"] for b in data) == 1


@pytest.mark.asyncio
async def test_deal_timeline_summary_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong_id}/deals/{uuid.uuid4()}/timeline-summary")

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Bulk deal operations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bulk_move_stage(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    deal1 = _fake_deal(workspace_id, stage="discovery")
    deal2 = _fake_deal(workspace_id, stage="qualified")

    execute_results = [
        _make_scalars_result([deal1, deal2]),  # SELECT deals
        MagicMock(),  # INSERT activity event
    ]
    mock_db.execute = AsyncMock(side_effect=execute_results)

    payload = {
        "action": "move_stage",
        "deal_ids": [str(deal1.id), str(deal2.id)],
        "stage": "proposal",
    }

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(f"/workspaces/{workspace_id}/deals/bulk", json=payload)

    assert resp.status_code == 200
    data = resp.json()
    assert data["action"] == "move_stage"
    assert data["updated"] == 2
    assert len(data["deal_ids"]) == 2


@pytest.mark.asyncio
async def test_bulk_delete(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    deal = _fake_deal(workspace_id, stage="discovery", title="Kill Me")

    execute_results = [
        _make_scalars_result([deal]),  # SELECT deals
        MagicMock(),  # INSERT activity event
    ]
    mock_db.execute = AsyncMock(side_effect=execute_results)

    payload = {"action": "delete", "deal_ids": [str(deal.id)]}

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(f"/workspaces/{workspace_id}/deals/bulk", json=payload)

    assert resp.status_code == 200
    data = resp.json()
    assert data["action"] == "delete"
    assert data["updated"] == 1


@pytest.mark.asyncio
async def test_bulk_invalid_action_returns_422(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    payload = {"action": "nuke_all", "deal_ids": [str(uuid.uuid4())]}

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(f"/workspaces/{workspace_id}/deals/bulk", json=payload)

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_bulk_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
    payload = {"action": "delete", "deal_ids": [str(uuid.uuid4())]}

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(f"/workspaces/{wrong_id}/deals/bulk", json=payload)

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_bulk_empty_ids_returns_422(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    payload = {"action": "delete", "deal_ids": []}

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(f"/workspaces/{workspace_id}/deals/bulk", json=payload)

    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/deals/{did}/probability-trend
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_probability_trend_returns_list(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    deal = _fake_deal(workspace_id, title="Demo Deal")
    deal.created_at = datetime.now(timezone.utc) - timedelta(days=15)
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(deal))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/deals/{deal.id}/probability-trend")

    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) > 0
    assert "date" in data[0]
    assert "probability" in data[0]
    assert 0 <= data[0]["probability"] <= 100


@pytest.mark.asyncio
async def test_probability_trend_not_found_returns_404(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/deals/{uuid.uuid4()}/probability-trend")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_probability_trend_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong_id}/deals/{uuid.uuid4()}/probability-trend")

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/deals/forecast
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deal_forecast_returns_monthly_buckets(app_client):
    from datetime import date, timedelta
    fastapi_app, mock_db, workspace_id = app_client

    d1 = _fake_deal(workspace_id, stage="discovery", value=50000)
    d1.expected_close = (date.today() + timedelta(days=15)).isoformat()
    d2 = _fake_deal(workspace_id, stage="proposal", value=80000)
    d2.expected_close = (date.today() + timedelta(days=45)).isoformat()
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([d1, d2]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/deals/forecast?months_ahead=3")

    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 3
    # Both deals close within the 3-month window (+15d and +45d), so they must
    # land in the buckets regardless of which calendar day the test runs on.
    assert sum(b["deal_count"] for b in data) == 2


@pytest.mark.asyncio
async def test_deal_forecast_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong_id}/deals/forecast")

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Deal notes — POST / GET /workspaces/{wid}/deals/{did}/notes
# ---------------------------------------------------------------------------


def _fake_note(workspace_id: uuid.UUID, deal_id: uuid.UUID, **kwargs) -> MagicMock:
    note = MagicMock()
    note.id = kwargs.get("id", uuid.uuid4())
    note.workspace_id = workspace_id
    note.deal_id = deal_id
    note.body = kwargs.get("body", "A note body")
    note.author = kwargs.get("author", "user@example.com")
    note.created_at = kwargs.get("created_at", _NOW)
    return note


@pytest.mark.asyncio
async def test_create_deal_note_returns_201(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    deal = _fake_deal(workspace_id, title="Noted Deal")
    note = _fake_note(workspace_id, deal.id, body="First touchpoint summary", author="me@example.com")

    # create_deal_note: one execute (deal lookup) → commit → refresh
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(deal))

    def fake_refresh(obj):
        for attr in ("id", "workspace_id", "deal_id", "body", "author", "created_at"):
            setattr(obj, attr, getattr(note, attr))

    mock_db.refresh.side_effect = fake_refresh

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{workspace_id}/deals/{deal.id}/notes",
            json={"body": "First touchpoint summary", "author": "me@example.com"},
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["body"] == "First touchpoint summary"
    assert data["author"] == "me@example.com"
    assert data["deal_id"] == str(deal.id)
    mock_db.add.assert_called()
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_create_deal_note_empty_body_returns_422(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{workspace_id}/deals/{uuid.uuid4()}/notes",
            json={"body": "   "},
        )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_deal_note_missing_deal_returns_404(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{workspace_id}/deals/{uuid.uuid4()}/notes",
            json={"body": "orphan note"},
        )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_deal_note_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{wrong_id}/deals/{uuid.uuid4()}/notes",
            json={"body": "note"},
        )

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_deal_notes_chronological(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    deal = _fake_deal(workspace_id, title="Threaded Deal")
    n1 = _fake_note(workspace_id, deal.id, body="Oldest", created_at=_NOW - timedelta(days=2))
    n2 = _fake_note(workspace_id, deal.id, body="Newest", created_at=_NOW)

    call_count = 0

    async def _execute_side_effect(q):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _make_scalar_result(deal)  # deal lookup
        return _make_scalars_result([n1, n2])  # notes query (already ordered)

    mock_db.execute = AsyncMock(side_effect=_execute_side_effect)

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/deals/{deal.id}/notes")

    assert resp.status_code == 200
    data = resp.json()
    assert [n["body"] for n in data] == ["Oldest", "Newest"]


@pytest.mark.asyncio
async def test_list_deal_notes_empty(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    deal = _fake_deal(workspace_id)

    call_count = 0

    async def _execute_side_effect(q):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _make_scalar_result(deal)
        return _make_scalars_result([])

    mock_db.execute = AsyncMock(side_effect=_execute_side_effect)

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/deals/{deal.id}/notes")

    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_deal_notes_missing_deal_returns_404(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/deals/{uuid.uuid4()}/notes")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_deal_notes_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong_id}/deals/{uuid.uuid4()}/notes")

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# WS-L: list deals limit/offset pagination
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_deals_with_limit_offset(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    deal = _fake_deal(workspace_id, title="Paged Deal")
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([deal]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/deals?limit=1&offset=2")

    assert resp.status_code == 200
    assert len(resp.json()) == 1


@pytest.mark.asyncio
async def test_list_deals_invalid_limit_returns_422(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/deals?limit=0")

    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/deals/velocity
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deal_velocity_groups_by_stage(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    deals = [
        _fake_deal(workspace_id, stage="discovery", stage_changed_at=_NOW - timedelta(days=10)),
        _fake_deal(workspace_id, stage="discovery", stage_changed_at=_NOW - timedelta(days=20)),
        _fake_deal(workspace_id, stage="proposal",  stage_changed_at=_NOW - timedelta(days=5)),
    ]
    mock_db.execute = AsyncMock(return_value=_make_scalars_result(deals))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/deals/velocity")

    assert resp.status_code == 200
    data = resp.json()
    stages = [row["stage"] for row in data]
    assert "discovery" in stages
    assert "proposal" in stages
    disc = next(r for r in data if r["stage"] == "discovery")
    assert disc["deal_count"] == 2
    assert disc["avg_days"] > 0


@pytest.mark.asyncio
async def test_deal_velocity_empty_workspace(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/deals/velocity")

    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_deal_velocity_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong_id}/deals/velocity")

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/deals/funnel
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deal_funnel_groups_by_stage(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    deals = [
        _fake_deal(workspace_id, stage="discovery"),
        _fake_deal(workspace_id, stage="discovery"),
        _fake_deal(workspace_id, stage="qualified"),
        _fake_deal(workspace_id, stage="proposal"),
    ]
    mock_db.execute = AsyncMock(return_value=_make_scalars_result(deals))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/deals/funnel")

    assert resp.status_code == 200
    data = resp.json()
    disc = next(r for r in data if r["stage"] == "discovery")
    qual = next(r for r in data if r["stage"] == "qualified")
    prop = next(r for r in data if r["stage"] == "proposal")
    assert disc["deal_count"] == 2
    assert disc["conversion_rate"] is None
    assert qual["deal_count"] == 1
    assert qual["conversion_rate"] == 50.0
    assert prop["deal_count"] == 1
    assert prop["conversion_rate"] == 100.0


@pytest.mark.asyncio
async def test_deal_funnel_empty_workspace(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/deals/funnel")

    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 6
    assert all(row["deal_count"] == 0 for row in data)


@pytest.mark.asyncio
async def test_deal_funnel_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong_id}/deals/funnel")

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# PUT /workspaces/{wid}/deals/{did}/outcome — win/loss reason tagging
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_deal_outcome_success(app_client):
    """PUT /outcome sets stage + reason and returns updated deal."""
    fastapi_app, mock_db, workspace_id = app_client
    deal = _fake_deal(workspace_id, stage="negotiation")

    scalar_result = _make_scalar_result(deal)
    mock_db.execute = AsyncMock(return_value=scalar_result)
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()

    # After commit/refresh the deal attributes are updated
    deal.stage = "closed_lost"
    deal.win_loss_reason = "price"

    deal_id = deal.id
    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.put(
            f"/workspaces/{workspace_id}/deals/{deal_id}/outcome",
            json={"stage": "closed_lost", "reason": "price"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["stage"] == "closed_lost"
    assert data["win_loss_reason"] == "price"


@pytest.mark.asyncio
async def test_set_deal_outcome_invalid_reason_returns_422(app_client):
    """PUT /outcome with unknown reason returns 422."""
    fastapi_app, mock_db, workspace_id = app_client
    deal = _fake_deal(workspace_id, stage="proposal")

    mock_db.execute = AsyncMock(return_value=_make_scalar_result(deal))

    deal_id = deal.id
    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.put(
            f"/workspaces/{workspace_id}/deals/{deal_id}/outcome",
            json={"stage": "closed_won", "reason": "not_a_real_reason"},
        )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_outcome_reasons_groups_by_reason(app_client):
    """GET /outcome-reasons groups closed deals by reason × outcome."""
    fastapi_app, mock_db, workspace_id = app_client
    deals = [
        _fake_deal(workspace_id, stage="closed_won", win_loss_reason="price"),
        _fake_deal(workspace_id, stage="closed_won", win_loss_reason="price"),
        _fake_deal(workspace_id, stage="closed_lost", win_loss_reason="price"),
        _fake_deal(workspace_id, stage="closed_lost", win_loss_reason="timing"),
    ]
    mock_db.execute = AsyncMock(return_value=_make_scalars_result(deals))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/deals/outcome-reasons")

    assert resp.status_code == 200
    data = resp.json()
    price_row = next((r for r in data if r["reason"] == "price"), None)
    timing_row = next((r for r in data if r["reason"] == "timing"), None)
    assert price_row is not None
    assert price_row["won"] == 2
    assert price_row["lost"] == 1
    assert timing_row is not None
    assert timing_row["won"] == 0
    assert timing_row["lost"] == 1


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/deals/{did}/activity-heatmap
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deal_activity_heatmap_returns_12_weeks(app_client):
    """GET /deals/{id}/activity-heatmap returns 12 week buckets with expected keys."""
    fastapi_app, mock_db, workspace_id = app_client
    deal = _fake_deal(workspace_id, contact_id=None)  # no contact → skips message query

    # db.execute calls: deal lookup, activity_events, deal_notes
    mock_db.execute = AsyncMock(side_effect=[
        _make_scalar_result(deal),
        _make_scalars_result([]),
        _make_scalars_result([]),
    ])

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/deals/{deal.id}/activity-heatmap")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 12
    assert "week_start" in data[0]
    assert "events" in data[0]
    assert "messages" in data[0]
    assert "notes" in data[0]
    assert "total" in data[0]
    assert all(w["total"] == 0 for w in data)


@pytest.mark.asyncio
async def test_deal_activity_heatmap_not_found_returns_404(app_client):
    """GET /deals/{unknown_id}/activity-heatmap returns 404."""
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/deals/{uuid.uuid4()}/activity-heatmap")

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/deals/{did}/stage-history
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deal_stage_history_no_events_returns_current_stage(app_client):
    """GET /deals/{id}/stage-history with no activity events returns a single-entry history."""
    fastapi_app, mock_db, workspace_id = app_client
    deal = _fake_deal(workspace_id, stage="proposal")

    # Two execute calls: deal lookup + activity events
    mock_db.execute = AsyncMock(side_effect=[
        _make_scalar_result(deal),
        _make_scalars_result([]),
    ])

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/deals/{deal.id}/stage-history")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["stage"] == "proposal"
    assert data[0]["label"] == "Proposal"
    assert data[0]["is_current"] is True
    assert "entered_at" in data[0]
    assert data[0]["days_in_stage"] >= 0


@pytest.mark.asyncio
async def test_deal_stage_history_wrong_workspace_returns_403(app_client):
    """GET /deals/{id}/stage-history returns 403 for a different workspace."""
    fastapi_app, mock_db, workspace_id = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong_id}/deals/{uuid.uuid4()}/stage-history")

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/deals/{did}/competitors
# PUT /workspaces/{wid}/deals/{did}/competitors
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_deal_competitors_returns_list(app_client):
    """GET /deals/{id}/competitors returns the stored competitor list."""
    fastapi_app, mock_db, workspace_id = app_client
    deal = _fake_deal(workspace_id, title="Comp Deal")
    deal.competitors = ["Salesforce", "HubSpot"]
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(deal))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/deals/{deal.id}/competitors")

    assert resp.status_code == 200
    assert resp.json() == {"competitors": ["Salesforce", "HubSpot"]}


@pytest.mark.asyncio
async def test_update_deal_competitors_wrong_workspace_returns_403(app_client):
    """PUT /deals/{id}/competitors returns 403 for a different workspace."""
    fastapi_app, mock_db, workspace_id = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.put(
            f"/workspaces/{wrong_id}/deals/{uuid.uuid4()}/competitors",
            json={"competitors": ["Rival Inc"]},
        )

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/deals/overdue-actions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_overdue_actions_returns_overdue_deals(app_client):
    """Returns deals whose next_action_date is today or past, ordered most-overdue first."""
    from datetime import date

    fastapi_app, mock_db, workspace_id = app_client
    yesterday = date.today() - timedelta(days=1)
    two_days_ago = date.today() - timedelta(days=2)

    d1 = _fake_deal(workspace_id, title="Follow Up", stage="proposal",
                    next_action="Send revised proposal", next_action_date=yesterday)
    d2 = _fake_deal(workspace_id, title="Old Action", stage="qualified",
                    next_action="Call back", next_action_date=two_days_ago)
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([d2, d1]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/deals/overdue-actions")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["title"] == "Old Action"
    assert data[0]["days_overdue"] == 2
    assert data[0]["next_action"] == "Call back"
    assert data[1]["days_overdue"] == 1


@pytest.mark.asyncio
async def test_overdue_actions_empty_workspace(app_client):
    """Returns empty list when no overdue next actions exist."""
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/deals/overdue-actions")

    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_overdue_actions_wrong_workspace_returns_403(app_client):
    """Returns 403 when requesting another workspace's overdue actions."""
    fastapi_app, mock_db, workspace_id = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong_id}/deals/overdue-actions")

    assert resp.status_code == 403


# ─── Phase 12o–13d: new analytics endpoints ──────────────────────────────────

@pytest.mark.asyncio
async def test_at_risk_returns_low_probability_deals(app_client):
    """Deals with ml_win_probability < 30 appear in at-risk list."""
    from datetime import datetime, timezone
    fastapi_app, mock_db, workspace_id = app_client
    now = datetime.now(timezone.utc)
    risky = _fake_deal(workspace_id, title="Risky Deal", ml_win_probability=20, stage="proposal",
                       stage_changed_at=now - timedelta(days=20))
    ok    = _fake_deal(workspace_id, title="OK Deal",    ml_win_probability=70, stage="qualified",
                       stage_changed_at=now - timedelta(days=1))
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([risky, ok]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/deals/at-risk")

    assert resp.status_code == 200
    data = resp.json()
    titles = [d["title"] for d in data]
    assert "Risky Deal" in titles
    assert "OK Deal" not in titles


@pytest.mark.asyncio
async def test_at_risk_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    wrong = uuid.UUID("11111111-1111-1111-1111-111111111111")
    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong}/deals/at-risk")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_close_date_slipped_returns_overdue_deals(app_client):
    """Deals with expected_close in the past are returned."""
    from datetime import date
    fastapi_app, mock_db, workspace_id = app_client
    past  = (date.today() - timedelta(days=10)).isoformat()
    future = (date.today() + timedelta(days=10)).isoformat()
    d_overdue = _fake_deal(workspace_id, title="Overdue", stage="proposal", expected_close=past)
    d_future  = _fake_deal(workspace_id, title="Future",  stage="qualified", expected_close=future)
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([d_overdue, d_future]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/deals/close-date-slipped")

    assert resp.status_code == 200
    data = resp.json()
    assert any(d["title"] == "Overdue" for d in data)
    assert not any(d["title"] == "Future" for d in data)


@pytest.mark.asyncio
async def test_close_date_slipped_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    wrong = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong}/deals/close-date-slipped")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_health_distribution_groups_correctly(app_client):
    """Deals are bucketed into critical/at_risk/healthy by health_score."""
    fastapi_app, mock_db, workspace_id = app_client
    d1 = _fake_deal(workspace_id, health_score=90, value=100000, stage="proposal")
    d2 = _fake_deal(workspace_id, health_score=55, value=50000,  stage="qualified")
    d3 = _fake_deal(workspace_id, health_score=25, value=30000,  stage="discovery")
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([d1, d2, d3]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/deals/health-distribution")

    assert resp.status_code == 200
    by_bucket = {r["bucket"]: r for r in resp.json()}
    assert by_bucket["healthy"]["count"] == 1
    assert by_bucket["at_risk"]["count"] == 1
    assert by_bucket["critical"]["count"] == 1


@pytest.mark.asyncio
async def test_health_distribution_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    wrong = uuid.UUID("cccccccc-1111-cccc-cccc-cccccccccccc")
    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong}/deals/health-distribution")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_deals_by_agent_groups_and_sorts(app_client):
    """Groups open deals by assigned_agent, sorted by count desc."""
    fastapi_app, mock_db, workspace_id = app_client
    d1 = _fake_deal(workspace_id, assigned_agent="Nova", stage="proposal", value=50000)
    d2 = _fake_deal(workspace_id, assigned_agent="Nova", stage="qualified", value=30000)
    d3 = _fake_deal(workspace_id, assigned_agent="Aria", stage="discovery", value=20000)
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([d1, d2, d3]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/deals/by-agent")

    assert resp.status_code == 200
    data = resp.json()
    assert data[0]["agent"] == "Nova"
    assert data[0]["count"] == 2
    assert data[1]["agent"] == "Aria"
    assert data[1]["count"] == 1


@pytest.mark.asyncio
async def test_deals_by_agent_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    wrong = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong}/deals/by-agent")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_revenue_forecast_groups_by_month(app_client):
    """Groups open deals by expected_close month with probability-weighted revenue."""
    from datetime import date
    fastapi_app, mock_db, workspace_id = app_client
    m1 = (date.today().replace(day=28)).isoformat()
    d1 = _fake_deal(workspace_id, stage="proposal", value=100000, ml_win_probability=50, expected_close=m1)
    d2 = _fake_deal(workspace_id, stage="qualified", value=80000, ml_win_probability=25, expected_close=m1)
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([d1, d2]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/deals/revenue-forecast")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["deal_count"] == 2
    assert abs(data[0]["expected_revenue"] - 70000) < 1  # 100k*0.5 + 80k*0.25 = 70k


@pytest.mark.asyncio
async def test_revenue_forecast_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    wrong = uuid.UUID("eeeeeeee-1111-eeee-eeee-eeeeeeeeeeee")
    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong}/deals/revenue-forecast")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_stage_aging_groups_and_sorts(app_client):
    """Returns open deals with days_in_stage, sorted by stage order then oldest-first."""
    fastapi_app, mock_db, workspace_id = app_client
    old = _fake_deal(workspace_id, stage="discovery", value=50000, stage_changed_at=_NOW - timedelta(days=20))
    new = _fake_deal(workspace_id, stage="discovery", value=30000, stage_changed_at=_NOW - timedelta(days=3))
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([old, new]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/deals/stage-aging")

    assert resp.status_code == 200
    data = resp.json()
    assert data[0]["days_in_stage"] > data[1]["days_in_stage"]


@pytest.mark.asyncio
async def test_stage_aging_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    wrong = uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong}/deals/stage-aging")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_win_probability_by_stage_averages_correctly(app_client):
    """Returns average ml_win_probability per stage."""
    fastapi_app, mock_db, workspace_id = app_client
    d1 = _fake_deal(workspace_id, stage="proposal", ml_win_probability=60, value=50000)
    d2 = _fake_deal(workspace_id, stage="proposal", ml_win_probability=40, value=30000)
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([d1, d2]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/deals/win-probability-by-stage")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["stage"] == "proposal"
    assert data[0]["avg_probability"] == 50.0
    assert data[0]["deal_count"] == 2


@pytest.mark.asyncio
async def test_win_probability_by_stage_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    wrong = uuid.UUID("11111111-1111-1111-1111-111111111111")
    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong}/deals/win-probability-by-stage")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_concentration_risk_computes_top3_pct(app_client):
    """Computes top3_pct and risk_level from open deal values."""
    fastapi_app, mock_db, workspace_id = app_client
    deals = [
        _fake_deal(workspace_id, value=100000, stage="proposal"),
        _fake_deal(workspace_id, value=80000,  stage="qualified"),
        _fake_deal(workspace_id, value=60000,  stage="discovery"),
        _fake_deal(workspace_id, value=10000,  stage="discovery"),
    ]
    mock_db.execute = AsyncMock(return_value=_make_scalars_result(deals))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/deals/concentration-risk")

    assert resp.status_code == 200
    data = resp.json()
    # Top 3 = 240k out of 250k total = 96% → high risk
    assert data["top3_pct"] == 96.0
    assert data["risk_level"] == "high"
    assert len(data["top_deals"]) <= 5


@pytest.mark.asyncio
async def test_concentration_risk_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    wrong = uuid.UUID("22222222-2222-2222-2222-222222222222")
    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong}/deals/concentration-risk")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_close_date_accuracy_computes_delta(app_client):
    """Computes days_delta and outcome for closed_won deals."""
    from datetime import date
    fastapi_app, mock_db, workspace_id = app_client
    expected = date.today() - timedelta(days=5)
    actual_close_dt = _NOW  # stage_changed_at = _NOW (5 days after expected if expected is 5 days ago, actual is NOW... wait)
    # expected = today - 5d, actual = _NOW (2026-05-15 as defined in test file)
    # days_delta = actual_date - expected = today's date math
    # Let's set stage_changed_at = NOW and expected_close = now - 10 days → late by 10 days
    expected_close = (_NOW.date() - timedelta(days=10)).isoformat()
    d = _fake_deal(workspace_id, stage="closed_won", expected_close=expected_close,
                   stage_changed_at=_NOW)
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([d]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/deals/close-date-accuracy")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["days_delta"] == 10
    assert data[0]["outcome"] == "late"


@pytest.mark.asyncio
async def test_close_date_accuracy_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    wrong = uuid.UUID("33333333-3333-3333-3333-333333333333")
    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong}/deals/close-date-accuracy")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_velocity_trends_groups_by_month(app_client):
    """Returns 6 monthly buckets with avg_cycle_days for closed_won deals."""
    fastapi_app, mock_db, workspace_id = app_client
    close_date = _NOW
    d = _fake_deal(workspace_id, stage="closed_won", stage_changed_at=close_date,
                   created_at=close_date - timedelta(days=30))
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([d]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/deals/velocity-trends")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 6  # default months=6
    for row in data:
        assert "month" in row
        assert "avg_cycle_days" in row
        assert "deal_count" in row


@pytest.mark.asyncio
async def test_velocity_trends_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    wrong = uuid.UUID("44444444-4444-4444-4444-444444444444")
    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong}/deals/velocity-trends")
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/deals/leaderboard — Phase 13e
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_leaderboard_ranks_by_composite_score(app_client):
    """Deals ranked by ml_win_probability × value descending."""
    fastapi_app, mock_db, workspace_id = app_client

    # Deal A: low probability, moderate value → score = 100 × 20 = 2000
    d_a = _fake_deal(workspace_id, value=100.0, ml_win_probability=20, stage="discovery")
    # Deal B: high probability, moderate value → score = 60 × 80 = 4800 (ranked first)
    d_b = _fake_deal(workspace_id, value=60.0, ml_win_probability=80, stage="qualified")
    # Mock returns only open deals (DB filters closed_won/lost before Python sees them)

    mock_db.execute = AsyncMock(return_value=_make_scalars_result([d_a, d_b]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/deals/leaderboard", params={"limit": 5})

    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 2
    assert rows[0]["rank"] == 1
    assert rows[0]["ml_win_probability"] == 80  # d_b ranked first (score=4800)
    assert rows[1]["rank"] == 2
    assert rows[1]["ml_win_probability"] == 20  # d_a ranked second (score=2000)
    assert "trend" in rows[0]
    assert "score" in rows[0]


@pytest.mark.asyncio
async def test_leaderboard_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    wrong = uuid.UUID("55555555-5555-5555-5555-555555555555")
    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong}/deals/leaderboard")
    assert resp.status_code == 403
