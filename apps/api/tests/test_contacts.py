"""Tests for the contacts router — GET/PATCH/DELETE single contact."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

from tests.conftest import _make_scalar_result, _make_scalars_result


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


# ---------------------------------------------------------------------------
# POST /workspaces/{wid}/contacts — create
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_contact_returns_201(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    seeded = _fake_contact(workspace_id, name="Carol Lee", email="carol@example.com")

    def fake_refresh(obj):
        for attr in ("id", "workspace_id", "name", "email", "company", "role",
                     "avatar", "status", "ml_score", "semantic_tags",
                     "revenue", "deal_count", "last_activity", "created_at"):
            setattr(obj, attr, getattr(seeded, attr))

    mock_db.refresh.side_effect = fake_refresh

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{workspace_id}/contacts",
            json={"name": "Carol Lee", "email": "carol@example.com", "status": "lead"},
        )

    assert resp.status_code == 201
    assert resp.json()["name"] == "Carol Lee"
    mock_db.flush.assert_awaited()
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_create_contact_invalid_status_returns_422(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{workspace_id}/contacts",
            json={"name": "Bad Status", "status": "invalidstatus"},
        )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_contact_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{wrong_id}/contacts",
            json={"name": "x", "status": "lead"},
        )

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/contacts — list with filters
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_contacts_empty(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/contacts")

    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_contacts_with_status_filter(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    contact = _fake_contact(workspace_id, status="customer")
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([contact]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/contacts?status=customer")

    assert resp.status_code == 200
    assert resp.json()[0]["status"] == "customer"


@pytest.mark.asyncio
async def test_list_contacts_with_q_filter(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    contact = _fake_contact(workspace_id, name="Dave Evans")
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([contact]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/contacts?q=Dave")

    assert resp.status_code == 200
    assert resp.json()[0]["name"] == "Dave Evans"


@pytest.mark.asyncio
async def test_list_contacts_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong_id}/contacts")

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /workspaces/{wid}/contacts/{cid}/score
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_score_contact_enqueues_job(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    contact = _fake_contact(workspace_id)
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(contact))

    mock_task = MagicMock()
    mock_task.id = "score-job-abc"

    with patch("app.workers.score_contact.score_lead") as mock_celery:
        mock_celery.delay.return_value = mock_task
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(f"/workspaces/{workspace_id}/contacts/{contact.id}/score")

    assert resp.status_code == 200
    assert resp.json()["status"] == "queued"
    assert resp.json()["job_id"] == "score-job-abc"


@pytest.mark.asyncio
async def test_score_contact_not_found_returns_404(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(f"/workspaces/{workspace_id}/contacts/{uuid.uuid4()}/score")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_score_contact_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(f"/workspaces/{wrong_id}/contacts/{uuid.uuid4()}/score")

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /workspaces/{wid}/contacts/{cid}/enrich
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enrich_contact_enqueues_job(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    contact = _fake_contact(workspace_id)
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(contact))

    mock_task = MagicMock()
    mock_task.id = "enrich-job-xyz"

    with patch("app.workers.enrich_contact.enrich_contact") as mock_celery:
        mock_celery.delay.return_value = mock_task
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(f"/workspaces/{workspace_id}/contacts/{contact.id}/enrich")

    assert resp.status_code == 202
    assert resp.json()["status"] == "queued"
    assert resp.json()["job_id"] == "enrich-job-xyz"


@pytest.mark.asyncio
async def test_enrich_contact_not_found_returns_404(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    with patch("app.routers.contacts.get_row", return_value=None):
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(f"/workspaces/{workspace_id}/contacts/{uuid.uuid4()}/enrich")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_enrich_contact_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(f"/workspaces/{wrong_id}/contacts/{uuid.uuid4()}/enrich")

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# PATCH /workspaces/{wid}/contacts/{cid}/status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_contact_status_returns_updated(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    contact = _fake_contact(workspace_id, status="lead")
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(contact))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.patch(
            f"/workspaces/{workspace_id}/contacts/{contact.id}/status",
            json={"status": "customer"},
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "customer"
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_update_contact_status_invalid_returns_422(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.patch(
            f"/workspaces/{workspace_id}/contacts/{uuid.uuid4()}/status",
            json={"status": "not_a_real_status"},
        )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_update_contact_status_not_found_returns_404(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.patch(
            f"/workspaces/{workspace_id}/contacts/{uuid.uuid4()}/status",
            json={"status": "customer"},
        )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_contact_status_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.patch(
            f"/workspaces/{wrong_id}/contacts/{uuid.uuid4()}/status",
            json={"status": "customer"},
        )

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/contacts/{cid}/timeline
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_contact_timeline_empty(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    # timeline makes 4 separate db.execute() calls (messages, calls, deals, events)
    mock_db.execute = AsyncMock(side_effect=[
        _make_scalars_result([]),  # messages
        _make_scalars_result([]),  # call summaries
        _make_scalars_result([]),  # deals
        _make_scalars_result([]),  # activity events
    ])

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/contacts/{uuid.uuid4()}/timeline")

    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_contact_timeline_with_data(app_client):
    from datetime import datetime, timezone
    fastapi_app, mock_db, workspace_id = app_client
    contact_id = uuid.uuid4()

    # Fake message
    msg = MagicMock()
    msg.id = uuid.uuid4()
    msg.subject = "Hello there"
    msg.body_plain = "Body content"
    msg.received_at = datetime(2026, 5, 10, tzinfo=timezone.utc)
    msg.created_at = datetime(2026, 5, 10, tzinfo=timezone.utc)
    msg.sender_email = "sender@example.com"

    # Fake call summary
    call = MagicMock()
    call.id = uuid.uuid4()
    call.title = "Discovery Call"
    call.summary = "Discussed needs."
    call.call_date = datetime(2026, 5, 11, tzinfo=timezone.utc)
    call.duration_seconds = 900
    call.participants = "Alice, Bob"

    # Fake deal
    deal = MagicMock()
    deal.id = uuid.uuid4()
    deal.title = "Big Deal"
    deal.stage = "proposal"
    deal.value = 25000
    deal.stage_changed_at = datetime(2026, 5, 12, tzinfo=timezone.utc)
    deal.created_at = datetime(2026, 5, 12, tzinfo=timezone.utc)

    # Fake activity event
    evt = MagicMock()
    evt.id = uuid.uuid4()
    evt.type = "note"
    evt.description = "Left a voicemail"
    evt.created_at = datetime(2026, 5, 13, tzinfo=timezone.utc)
    evt.agent_name = "System"
    evt.severity = "info"

    mock_db.execute = AsyncMock(side_effect=[
        _make_scalars_result([msg]),
        _make_scalars_result([call]),
        _make_scalars_result([deal]),
        _make_scalars_result([evt]),
    ])

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/contacts/{contact_id}/timeline")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 4
    types = {item["type"] for item in data}
    assert "message" in types
    assert "call" in types
    assert "deal_stage" in types
    assert "activity" in types


@pytest.mark.asyncio
async def test_contact_timeline_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong_id}/contacts/{uuid.uuid4()}/timeline")

    assert resp.status_code == 403
