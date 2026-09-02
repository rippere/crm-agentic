"""Tests for the leads router — CRUD + funnel + stage/promote/score + auth checks."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

from tests.conftest import _make_scalar_result, _make_scalars_result

_NOW = datetime(2026, 5, 15, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _stub_supabase_rest():
    """ORM-miss paths fall through to the Supabase REST fallback before 404.
    Stub it to None so tests never make a live network call."""
    with patch("app.routers.leads.get_row", new=AsyncMock(return_value=None)):
        yield


def _fake_lead(workspace_id: uuid.UUID, **kwargs) -> MagicMock:
    lead = MagicMock()
    lead.id = kwargs.get("id", uuid.uuid4())
    lead.workspace_id = workspace_id
    lead.contact_id = kwargs.get("contact_id", None)
    lead.name = kwargs.get("name", "Test Lead")
    lead.email = kwargs.get("email", "lead@example.com")
    lead.phone = kwargs.get("phone", None)
    lead.company = kwargs.get("company", "Acme")
    lead.title = kwargs.get("title", None)
    lead.source = kwargs.get("source", "import")
    lead.stage = kwargs.get("stage", "new")
    lead.score = kwargs.get("score", 0)
    lead.score_detail = kwargs.get("score_detail", {})
    lead.owner_id = kwargs.get("owner_id", None)
    lead.custom_fields = kwargs.get("custom_fields", {})
    lead.external_id = kwargs.get("external_id", None)
    lead.last_engaged_at = kwargs.get("last_engaged_at", None)
    lead.created_at = kwargs.get("created_at", _NOW - timedelta(days=3))
    lead.updated_at = kwargs.get("updated_at", _NOW - timedelta(days=3))
    return lead


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/leads — list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_leads_returns_empty(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/leads")

    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_leads_returns_leads(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    lead = _fake_lead(workspace_id, name="Hot Lead", stage="engaged")
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([lead]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/leads?stage=engaged&min_score=0")

    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["name"] == "Hot Lead"


@pytest.mark.asyncio
async def test_list_leads_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong_id}/leads")

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/leads/funnel
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lead_funnel_groups_by_stage(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    # The funnel handler now issues a GROUP BY aggregate returning
    # (stage, count, sum(score)) rows rather than loading every Lead row.
    agg_rows = [
        ("new", 2, 0),
        ("engaged", 1, 40),
        ("converted", 1, 90),
    ]
    result = MagicMock()
    result.all.return_value = agg_rows
    mock_db.execute = AsyncMock(return_value=result)

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/leads/funnel")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 6
    new_row = next(r for r in data if r["stage"] == "new")
    assert new_row["count"] == 2
    engaged_row = next(r for r in data if r["stage"] == "engaged")
    assert engaged_row["value"] == 40


@pytest.mark.asyncio
async def test_lead_funnel_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong_id}/leads/funnel")

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /workspaces/{wid}/leads — create
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_lead_returns_201(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    lead = _fake_lead(workspace_id, name="New Lead", stage="new", source="web")

    def fake_refresh(obj):
        for attr in (
            "id", "workspace_id", "contact_id", "name", "email", "phone",
            "company", "title", "source", "stage", "score", "score_detail",
            "owner_id", "custom_fields", "external_id", "last_engaged_at",
            "created_at", "updated_at",
        ):
            setattr(obj, attr, getattr(lead, attr))

    mock_db.refresh.side_effect = fake_refresh

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{workspace_id}/leads",
            json={"name": "New Lead", "source": "web", "stage": "new"},
        )

    assert resp.status_code == 201
    assert resp.json()["stage"] == "new"


@pytest.mark.asyncio
async def test_create_lead_bad_source_returns_422(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{workspace_id}/leads",
            json={"name": "Bad", "source": "not_a_source"},
        )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_lead_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(f"/workspaces/{wrong_id}/leads", json={"name": "x"})

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/leads/{lid}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_lead_returns_lead(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    lead = _fake_lead(workspace_id, name="Single Lead")
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(lead))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/leads/{lead.id}")

    assert resp.status_code == 200
    assert resp.json()["name"] == "Single Lead"


@pytest.mark.asyncio
async def test_get_lead_not_found_returns_404(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/leads/{uuid.uuid4()}")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_lead_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong_id}/leads/{uuid.uuid4()}")

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# PATCH /workspaces/{wid}/leads/{lid}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patch_lead_updates_fields(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    lead = _fake_lead(workspace_id, name="Old", stage="new")
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(lead))
    mock_db.refresh.side_effect = lambda obj: None

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.patch(
            f"/workspaces/{workspace_id}/leads/{lead.id}",
            json={"name": "New", "stage": "contacted"},
        )

    assert resp.status_code == 200
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_patch_lead_bad_stage_returns_422(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.patch(
            f"/workspaces/{workspace_id}/leads/{uuid.uuid4()}",
            json={"stage": "bogus_stage"},
        )

    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /workspaces/{wid}/leads/{lid}/stage — funnel transition
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stage_transition_success(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    lead = _fake_lead(workspace_id, stage="engaged")
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(lead))
    mock_db.refresh.side_effect = lambda obj: None

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{workspace_id}/leads/{lead.id}/stage",
            json={"stage": "qualified"},
        )

    assert resp.status_code == 200
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_stage_transition_to_converted_writes_engagement_event(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    lead = _fake_lead(workspace_id, stage="qualified")
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(lead))
    mock_db.refresh.side_effect = lambda obj: None

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{workspace_id}/leads/{lead.id}/stage",
            json={"stage": "converted"},
        )

    assert resp.status_code == 200
    # ActivityEvent + EngagementEvent added (plus the lead itself)
    from app.models.engagement_event import EngagementEvent
    added = [c.args[0] for c in mock_db.add.call_args_list]
    assert any(isinstance(o, EngagementEvent) for o in added)


@pytest.mark.asyncio
async def test_stage_transition_bad_stage_returns_422(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{workspace_id}/leads/{uuid.uuid4()}/stage",
            json={"stage": "not_real"},
        )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_stage_transition_not_found_returns_404(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{workspace_id}/leads/{uuid.uuid4()}/stage",
            json={"stage": "contacted"},
        )

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /workspaces/{wid}/leads/{lid}/promote — bot→human close handoff
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_promote_lead_creates_contact(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    lead = _fake_lead(workspace_id, name="Promote Me", email="promote@example.com")

    call_count = 0

    async def _execute_side_effect(q):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _make_scalar_result(lead)  # lead lookup
        return _make_scalar_result(None)  # contact-by-email lookup → none

    mock_db.execute = AsyncMock(side_effect=_execute_side_effect)
    mock_db.refresh.side_effect = lambda obj: None

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{workspace_id}/leads/{lead.id}/promote",
            json={"create_deal": False},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["contact_id"] is not None
    assert data["deal_id"] is None


@pytest.mark.asyncio
async def test_promote_lead_with_deal(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    lead = _fake_lead(workspace_id, name="Deal Lead", email="deal@example.com")

    call_count = 0

    async def _execute_side_effect(q):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _make_scalar_result(lead)
        return _make_scalar_result(None)

    mock_db.execute = AsyncMock(side_effect=_execute_side_effect)
    mock_db.refresh.side_effect = lambda obj: None

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{workspace_id}/leads/{lead.id}/promote",
            json={"create_deal": True},
        )

    assert resp.status_code == 200
    assert resp.json()["deal_id"] is not None


@pytest.mark.asyncio
async def test_promote_lead_not_found_returns_404(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{workspace_id}/leads/{uuid.uuid4()}/promote",
            json={"create_deal": False},
        )

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /workspaces/{wid}/leads/import — Celery enqueue (guarded)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_import_leads_returns_202(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        with patch(
            "app.workers.import_leads.process_lead_import.delay",
            return_value=MagicMock(id="test-job-id"),
        ):
            resp = await ac.post(
                f"/workspaces/{workspace_id}/leads/import",
                json={"rows": [{"email": "a@b.com"}], "mapping": {}, "dedupe_on": "email"},
            )

    assert resp.status_code == 202
    assert resp.json()["status"] == "queued"
    assert "job_id" in resp.json()


@pytest.mark.asyncio
async def test_import_leads_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(f"/workspaces/{wrong_id}/leads/import", json={"rows": []})

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /workspaces/{wid}/leads/{lid}/score — Celery enqueue (guarded)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_score_lead_returns_202(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    lead = _fake_lead(workspace_id)
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(lead))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        with patch(
            "app.workers.engagement_score.score_lead_engagement.delay",
            return_value=MagicMock(id="test-job-id"),
        ):
            resp = await ac.post(f"/workspaces/{workspace_id}/leads/{lead.id}/score")

    assert resp.status_code == 202
    assert resp.json()["status"] == "queued"


@pytest.mark.asyncio
async def test_score_lead_not_found_returns_404(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(f"/workspaces/{workspace_id}/leads/{uuid.uuid4()}/score")

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /workspaces/{wid}/leads/export — CSV
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_export_leads_csv(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    lead = _fake_lead(workspace_id, name="Export Lead")
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([lead]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(f"/workspaces/{workspace_id}/leads/export")

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "Export Lead" in resp.text


# ---------------------------------------------------------------------------
# DELETE /workspaces/{wid}/leads/{lid}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_lead_returns_204(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    lead = _fake_lead(workspace_id)
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(lead))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.delete(f"/workspaces/{workspace_id}/leads/{lead.id}")

    assert resp.status_code == 204
    mock_db.delete.assert_awaited_with(lead)
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_delete_lead_not_found_returns_404(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.delete(f"/workspaces/{workspace_id}/leads/{uuid.uuid4()}")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_lead_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.delete(f"/workspaces/{wrong_id}/leads/{uuid.uuid4()}")

    assert resp.status_code == 403
