"""Tests for the contacts router — GET/PATCH/DELETE single contact."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
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
    contact.updated_at = None
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
                     "revenue", "deal_count", "last_activity", "created_at",
                     "updated_at"):
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


@pytest.mark.asyncio
async def test_list_contacts_pagination_applies_limit_offset(app_client):
    """limit/offset query params are accepted and forwarded into the SQL statement,
    while the JSON response shape stays a bare list."""
    fastapi_app, mock_db, workspace_id = app_client
    contact = _fake_contact(workspace_id, name="Paged Contact")
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([contact]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/contacts?limit=5&offset=10")

    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert body[0]["name"] == "Paged Contact"

    # The compiled SELECT should carry the LIMIT/OFFSET we asked for.
    stmt = mock_db.execute.call_args.args[0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "LIMIT 5" in compiled
    assert "OFFSET 10" in compiled


@pytest.mark.asyncio
async def test_list_contacts_limit_over_cap_returns_422(app_client):
    """limit above the max cap is rejected by FastAPI validation."""
    fastapi_app, mock_db, workspace_id = app_client

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/contacts?limit=99999")

    assert resp.status_code == 422


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


# ---------------------------------------------------------------------------
# POST /workspaces/{wid}/contacts/{cid}/compose
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compose_email_happy_path(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    contact = _fake_contact(workspace_id)
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(contact))

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text='{"subject": "Hello Alice", "body": "Hi there"}')]
    mock_client_instance = MagicMock()
    mock_client_instance.messages.create.return_value = mock_response

    with patch("anthropic.Anthropic", return_value=mock_client_instance):
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(f"/workspaces/{workspace_id}/contacts/{contact.id}/compose")

    assert resp.status_code == 200
    assert resp.json()["subject"] == "Hello Alice"
    assert resp.json()["body"] == "Hi there"


@pytest.mark.asyncio
async def test_compose_email_contact_not_found_returns_404(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    with patch("app.routers.contacts.get_row", new=AsyncMock(return_value=None)):
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(f"/workspaces/{workspace_id}/contacts/{uuid.uuid4()}/compose")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_compose_email_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(f"/workspaces/{wrong_id}/contacts/{uuid.uuid4()}/compose")

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_compose_email_json_parse_error_returns_500(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    contact = _fake_contact(workspace_id)
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(contact))

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="not valid json at all")]
    mock_client_instance = MagicMock()
    mock_client_instance.messages.create.return_value = mock_response

    with patch("anthropic.Anthropic", return_value=mock_client_instance):
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(f"/workspaces/{workspace_id}/contacts/{contact.id}/compose")

    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# POST /workspaces/{wid}/contacts/{cid}/send-email
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_email_no_connector_returns_404(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{workspace_id}/contacts/{uuid.uuid4()}/send-email",
            json={"to": "alice@example.com", "subject": "Hello", "body": "Hi"},
        )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_send_email_gmail_error_returns_502(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    connector = MagicMock()
    connector.workspace_id = workspace_id
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(connector))

    with patch("app.services.gmail_client.GmailClient") as MockGmailClient:
        mock_gmail = AsyncMock()
        mock_gmail.send_message = AsyncMock(side_effect=Exception("SMTP failure"))
        MockGmailClient.return_value = mock_gmail
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(
                f"/workspaces/{workspace_id}/contacts/{uuid.uuid4()}/send-email",
                json={"to": "alice@example.com", "subject": "Hello", "body": "Hi"},
            )

    assert resp.status_code == 502
    assert "Gmail error" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_send_email_happy_path(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    connector = MagicMock()
    connector.workspace_id = workspace_id
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(connector))

    with patch("app.services.gmail_client.GmailClient") as MockGmailClient:
        mock_gmail = AsyncMock()
        mock_gmail.send_message = AsyncMock(return_value={"id": "msg_abc123"})
        MockGmailClient.return_value = mock_gmail
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(
                f"/workspaces/{workspace_id}/contacts/{uuid.uuid4()}/send-email",
                json={"to": "alice@example.com", "subject": "Hello", "body": "Hi there"},
            )

    assert resp.status_code == 200
    assert resp.json()["status"] == "sent"
    assert resp.json()["to"] == "alice@example.com"
    mock_db.commit.assert_awaited()


# ---------------------------------------------------------------------------
# POST /workspaces/{wid}/contacts/{cid}/brief
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pre_meeting_brief_contact_not_found_returns_404(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(f"/workspaces/{workspace_id}/contacts/{uuid.uuid4()}/brief")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_pre_meeting_brief_happy_path(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    contact = _fake_contact(workspace_id)

    mock_db.execute = AsyncMock(side_effect=[
        _make_scalar_result(contact),  # contact lookup
        _make_scalars_result([]),       # messages
        _make_scalars_result([]),       # calls
        _make_scalars_result([]),       # deals
    ])

    mock_message = MagicMock()
    mock_message.content = [MagicMock(text="This is a brief about Alice Smith.")]
    mock_anthropic_client = AsyncMock()
    mock_anthropic_client.messages.create = AsyncMock(return_value=mock_message)

    with patch("anthropic.AsyncAnthropic", return_value=mock_anthropic_client):
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(f"/workspaces/{workspace_id}/contacts/{contact.id}/brief")

    assert resp.status_code == 200
    data = resp.json()
    assert data["contact_id"] == str(contact.id)
    assert data["contact_name"] == contact.name
    assert "brief" in data
    assert "Alice" in data["brief"]


@pytest.mark.asyncio
async def test_pre_meeting_brief_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(f"/workspaces/{wrong_id}/contacts/{uuid.uuid4()}/brief")

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_pre_meeting_brief_with_context_data(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    contact = _fake_contact(workspace_id)

    msg = MagicMock()
    msg.subject = "Re: Proposal"

    call = MagicMock()
    call.title = "Discovery Call"
    call.summary = "We discussed pricing."

    deal = MagicMock()
    deal.title = "Big Deal"
    deal.stage = "proposal"
    deal.value = 50000.0
    deal.ml_win_probability = 65

    mock_db.execute = AsyncMock(side_effect=[
        _make_scalar_result(contact),
        _make_scalars_result([msg]),
        _make_scalars_result([call]),
        _make_scalars_result([deal]),
    ])

    mock_message = MagicMock()
    mock_message.content = [MagicMock(text="Brief including deal and call context.")]
    mock_anthropic_client = AsyncMock()
    mock_anthropic_client.messages.create = AsyncMock(return_value=mock_message)

    with patch("anthropic.AsyncAnthropic", return_value=mock_anthropic_client):
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(f"/workspaces/{workspace_id}/contacts/{contact.id}/brief")

    assert resp.status_code == 200
    assert "brief" in resp.json()


@pytest.mark.asyncio
async def test_compose_email_strips_markdown_fence(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    contact = _fake_contact(workspace_id)
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(contact))

    fenced = '```json\n{"subject": "Fenced subject", "body": "Fenced body"}\n```'
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=fenced)]
    mock_client_instance = MagicMock()
    mock_client_instance.messages.create.return_value = mock_response

    with patch("anthropic.Anthropic", return_value=mock_client_instance):
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(f"/workspaces/{workspace_id}/contacts/{contact.id}/compose")

    assert resp.status_code == 200
    assert resp.json()["subject"] == "Fenced subject"


@pytest.mark.asyncio
async def test_send_email_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{wrong_id}/contacts/{uuid.uuid4()}/send-email",
            json={"to": "alice@example.com", "subject": "Hello", "body": "Hi"},
        )

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_compose_email_supabase_fallback_path(app_client):
    """When contact not in Postgres, falls back to Supabase REST row to build email."""
    fastapi_app, mock_db, workspace_id = app_client
    contact_id = uuid.uuid4()
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    supabase_row = {
        "name": "Supabase Alice",
        "company": "Remote Corp",
        "role": "CTO",
        "status": "prospect",
        "semantic_tags": ["ai", "enterprise"],
        "revenue": 500000,
    }

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text='{"subject": "Hello Supabase Alice", "body": "Via fallback"}')]
    mock_client_instance = MagicMock()
    mock_client_instance.messages.create.return_value = mock_response

    with patch("app.routers.contacts.get_row", new=AsyncMock(return_value=supabase_row)):
        with patch("anthropic.Anthropic", return_value=mock_client_instance):
            async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
                resp = await ac.post(f"/workspaces/{workspace_id}/contacts/{contact_id}/compose")

    assert resp.status_code == 200
    assert resp.json()["subject"] == "Hello Supabase Alice"
    # Verify the Supabase row fields were used in the prompt
    call_args = mock_client_instance.messages.create.call_args
    user_msg = call_args[1]["messages"][0]["content"]
    assert "Supabase Alice" in user_msg
    assert "Remote Corp" in user_msg


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/contacts/export — CSV download
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_export_contacts_csv_returns_csv(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    contact = MagicMock()
    contact.id = uuid.uuid4()
    contact.workspace_id = workspace_id
    contact.name = "Alice"
    contact.email = "alice@example.com"
    contact.company = "Acme"
    contact.role = "CEO"
    contact.status = "customer"
    contact.ml_score = 80
    contact.revenue = 50000
    contact.created_at = None

    mock_db.execute = AsyncMock(return_value=_make_scalars_result([contact]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/contacts/export")

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    lines = resp.text.strip().splitlines()
    assert lines[0].startswith("id,name,email")
    assert "Alice" in resp.text


@pytest.mark.asyncio
async def test_export_contacts_csv_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong_id}/contacts/export")

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /workspaces/{wid}/contacts/import — CSV import
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_import_contacts_csv_imports_new_contacts(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    # No existing contact found by email → insert
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    csv_content = b"name,email,company,role,status\nAlice,alice@ex.com,Acme,CEO,lead\n"
    from httpx import AsyncClient, ASGITransport
    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{workspace_id}/contacts/import",
            files={"file": ("contacts.csv", csv_content, "text/csv")},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["imported"] == 1
    assert data["skipped"] == 0
    assert data["errors"] == []
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_import_contacts_csv_skips_rows_without_name(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    csv_content = b"name,email\n,missing@ex.com\nBob,bob@ex.com\n"
    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{workspace_id}/contacts/import",
            files={"file": ("contacts.csv", csv_content, "text/csv")},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["skipped"] == 1
    assert len(data["errors"]) == 1
    assert data["imported"] == 1


@pytest.mark.asyncio
async def test_import_contacts_csv_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
    csv_content = b"name,email\nAlice,alice@ex.com\n"
    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{wrong_id}/contacts/import",
            files={"file": ("contacts.csv", csv_content, "text/csv")},
        )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /workspaces/{wid}/contacts/bulk — bulk delete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bulk_delete_contacts_returns_deleted_count(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    c1 = _fake_contact(workspace_id, name="Alice")
    c2 = _fake_contact(workspace_id, name="Bob")
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([c1, c2]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{workspace_id}/contacts/bulk",
            json={"action": "delete", "contact_ids": [str(c1.id), str(c2.id)]},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["action"] == "delete"
    assert data["deleted"] == 2
    assert len(data["contact_ids"]) == 2
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_bulk_delete_contacts_empty_list_returns_422(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{workspace_id}/contacts/bulk",
            json={"action": "delete", "contact_ids": []},
        )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_bulk_delete_contacts_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{wrong_id}/contacts/bulk",
            json={"action": "delete", "contact_ids": [str(uuid.uuid4())]},
        )

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /workspaces/{wid}/contacts/merge
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_merge_contacts_reassigns_and_deletes_duplicate(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    primary   = _fake_contact(workspace_id, name="Alice Smith")
    duplicate = _fake_contact(workspace_id, name="Alice S.")

    # First execute: fetch both contacts
    mock_db.execute = AsyncMock(side_effect=[
        _make_scalars_result([primary, duplicate]),  # select contacts
        MagicMock(rowcount=2),   # update tasks
        MagicMock(rowcount=1),   # update messages
        MagicMock(rowcount=1),   # update deals
    ])

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{workspace_id}/contacts/merge",
            json={"primary_id": str(primary.id), "duplicate_id": str(duplicate.id)},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["primary_id"] == str(primary.id)
    assert data["duplicate_id"] == str(duplicate.id)
    assert data["tasks_reassigned"] == 2
    assert data["messages_reassigned"] == 1
    assert data["deals_reassigned"] == 1
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_merge_contacts_same_ids_returns_422(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    contact_id = uuid.uuid4()

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{workspace_id}/contacts/merge",
            json={"primary_id": str(contact_id), "duplicate_id": str(contact_id)},
        )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_merge_contacts_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{wrong_id}/contacts/merge",
            json={"primary_id": str(uuid.uuid4()), "duplicate_id": str(uuid.uuid4())},
        )

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# PUT /workspaces/{wid}/contacts/{cid}/tags
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_put_tags_updates_semantic_tags(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    contact = _fake_contact(workspace_id)
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(contact))

    tags = [{"label": "enterprise", "confidence": 0.9, "color": "indigo"}]

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.put(
            f"/workspaces/{workspace_id}/contacts/{contact.id}/tags",
            json={"tags": tags},
        )

    assert resp.status_code == 200
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_put_tags_invalid_tag_missing_label_returns_422(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    contact = _fake_contact(workspace_id)
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(contact))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.put(
            f"/workspaces/{workspace_id}/contacts/{contact.id}/tags",
            json={"tags": [{"confidence": 0.5}]},
        )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_put_tags_not_found_returns_404(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.put(
            f"/workspaces/{workspace_id}/contacts/{uuid.uuid4()}/tags",
            json={"tags": [{"label": "test", "confidence": 1.0, "color": "indigo"}]},
        )

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/contacts/{cid}/activity-heatmap
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_activity_heatmap_returns_12_weeks(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    contact = _fake_contact(workspace_id)

    # db.execute is called 3 times: contact lookup, messages query, notes query
    mock_db.execute = AsyncMock(side_effect=[
        _make_scalar_result(contact),
        _make_scalars_result([]),
        _make_scalars_result([]),
    ])

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/contacts/{contact.id}/activity-heatmap")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 12
    assert "week_start" in data[0]
    assert "messages" in data[0]
    assert "notes" in data[0]
    assert "total" in data[0]
    # All counts should be 0 (no mock messages or notes)
    assert all(w["total"] == 0 for w in data)


@pytest.mark.asyncio
async def test_activity_heatmap_contact_not_found_returns_404(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/contacts/{uuid.uuid4()}/activity-heatmap")

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/contacts/{cid}/engagement-score
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_engagement_score_returns_score(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    contact = _fake_contact(workspace_id)

    # db.execute called 4 times: contact lookup, messages, notes, tasks
    mock_db.execute = AsyncMock(side_effect=[
        _make_scalar_result(contact),
        _make_scalars_result([]),
        _make_scalars_result([]),
        _make_scalars_result([]),
    ])

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/contacts/{contact.id}/engagement-score")

    assert resp.status_code == 200
    data = resp.json()
    assert "score" in data
    assert "message_count" in data
    assert "note_count" in data
    assert "tasks_total" in data
    assert "tasks_done" in data
    assert "components" in data
    assert 0 <= data["score"] <= 100
    # With zero activity the score should be 0
    assert data["score"] == 0
    assert data["components"]["messages"] == 0
    assert data["components"]["notes"] == 0
    assert data["components"]["tasks"] == 0


@pytest.mark.asyncio
async def test_engagement_score_contact_not_found_returns_404(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/contacts/{uuid.uuid4()}/engagement-score")

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/contacts/{cid}/timeline/export — CSV download
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_export_contact_timeline_returns_csv(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    contact = _fake_contact(workspace_id, name="Timeline Bob")
    contact_id = contact.id

    # First call: contact lookup; subsequent calls return empty scalars for each source table
    call_count = 0

    def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _make_scalar_result(contact)
        return _make_scalars_result([])

    mock_db.execute = AsyncMock(side_effect=side_effect)

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/contacts/{contact_id}/timeline/export")

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    lines = resp.text.strip().splitlines()
    assert lines[0] == "date,type,title,description,severity"
    assert f"timeline_{contact_id}.csv" in resp.headers.get("content-disposition", "")


@pytest.mark.asyncio
async def test_export_contact_timeline_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong_id}/contacts/{uuid.uuid4()}/timeline/export")

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/contacts/{cid}/deal-summary
# ---------------------------------------------------------------------------


def _fake_deal(workspace_id: uuid.UUID, contact_id: uuid.UUID, stage: str, value: float) -> MagicMock:
    d = MagicMock()
    d.workspace_id = workspace_id
    d.contact_id = contact_id
    d.stage = stage
    d.value = value
    return d


@pytest.mark.asyncio
async def test_contact_deal_summary_returns_aggregates(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    contact = _fake_contact(workspace_id)
    contact_id = contact.id

    deals = [
        _fake_deal(workspace_id, contact_id, "proposal", 50000),
        _fake_deal(workspace_id, contact_id, "negotiation", 80000),
        _fake_deal(workspace_id, contact_id, "closed_won", 60000),
        _fake_deal(workspace_id, contact_id, "closed_lost", 40000),
    ]

    mock_db.execute = AsyncMock(side_effect=[
        _make_scalar_result(contact),
        _make_scalars_result(deals),
    ])

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/contacts/{contact_id}/deal-summary")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_pipeline_value"] == 130000.0   # 50k + 80k (non-closed)
    assert data["closed_won_value"] == 60000.0
    assert data["open_deal_count"] == 2
    # won=1, lost=1, total_closed=2 → win_rate = round(1/2*100) = 50
    assert data["win_rate"] == 50
    assert data["total_deals"] == 4
    assert data["avg_deal_size"] == round((50000 + 80000 + 60000 + 40000) / 4)


@pytest.mark.asyncio
async def test_contact_deal_summary_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong_id}/contacts/{uuid.uuid4()}/deal-summary")

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/contacts/duplicate-candidates
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_duplicate_candidates_returns_pairs(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    # Two contacts with similar names and the same email domain should form a pair
    c1 = _fake_contact(workspace_id, name="John Smith", email="john.smith@acme.com")
    c2 = _fake_contact(workspace_id, name="Jon Smith", email="jon@acme.com")
    # A third contact whose name is completely different should not pair with c1
    c3 = _fake_contact(workspace_id, name="Alice Zhang", email="alice@acme.com")

    mock_db.execute = AsyncMock(return_value=_make_scalars_result([c1, c2, c3]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/contacts/duplicate-candidates")

    assert resp.status_code == 200
    data = resp.json()
    assert "pairs" in data
    # john/jon + same domain → should score >= 0.65
    assert len(data["pairs"]) >= 1
    pair = data["pairs"][0]
    assert pair["similarity_score"] >= 0.65
    assert "reason" in pair
    names_in_pair = {pair["contact_a"]["name"], pair["contact_b"]["name"]}
    assert "John Smith" in names_in_pair or "Jon Smith" in names_in_pair


@pytest.mark.asyncio
async def test_duplicate_candidates_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong_id}/contacts/duplicate-candidates")

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/contacts/going-dark
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_going_dark_returns_contacts_with_no_recent_activity(app_client):
    """Contacts with no messages or notes in the last 30 days are returned."""
    from datetime import timezone

    fastapi_app, mock_db, workspace_id = app_client

    dark = _fake_contact(workspace_id, status="customer")
    active = _fake_contact(workspace_id, status="prospect")

    # Build a fake message for the active contact (received 5 days ago)
    recent_msg = MagicMock()
    recent_msg.contact_id = active.id
    recent_msg.received_at = datetime.now(timezone.utc) - timedelta(days=5)

    # 3 execute calls: contacts, messages, notes
    mock_db.execute = AsyncMock(side_effect=[
        _make_scalars_result([dark, active]),  # contacts query
        _make_scalars_result([recent_msg]),    # messages query
        _make_scalars_result([]),              # notes query
    ])

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/contacts/going-dark")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["id"] == str(dark.id)
    assert data[0]["days_since_last_contact"] == 90
    assert data[0]["status"] == "customer"


@pytest.mark.asyncio
async def test_going_dark_wrong_workspace_returns_403(app_client):
    """Returns 403 when requesting another workspace's going-dark contacts."""
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong_id}/contacts/going-dark")

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/contacts/{cid}/last-touch
# ---------------------------------------------------------------------------

def _make_first_result(value):
    """Mock for execute().first() returning a single tuple row."""
    r = MagicMock()
    r.first.return_value = value
    return r


@pytest.mark.asyncio
async def test_last_touch_returns_most_recent_touch(app_client):
    """Returns last message/note/activity dates and identifies the most recent type."""
    fastapi_app, mock_db, workspace_id = app_client
    contact = _fake_contact(workspace_id)
    contact_id = contact.id

    msg_dt = datetime.now() - timedelta(days=3)
    note_dt = datetime.now() - timedelta(days=10)
    act_dt = datetime.now() - timedelta(days=20)

    mock_db.execute = AsyncMock(side_effect=[
        _make_scalar_result(contact),              # contact lookup
        _make_first_result((msg_dt, msg_dt)),      # message received_at, created_at
        _make_first_result((note_dt,)),            # note created_at
        _make_first_result((act_dt,)),             # activity created_at
    ])

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/contacts/{contact_id}/last-touch")

    assert resp.status_code == 200
    data = resp.json()
    assert data["most_recent_type"] == "message"
    assert data["days_ago"] is not None and data["days_ago"] <= 4
    assert data["last_message_date"] is not None
    assert data["last_note_date"] is not None
    assert data["last_activity_date"] is not None


@pytest.mark.asyncio
async def test_last_touch_contact_not_found_returns_404(app_client):
    """Returns 404 when contact does not exist."""
    fastapi_app, mock_db, workspace_id = app_client
    missing_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/contacts/{missing_id}/last-touch")

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/contacts/pipeline-contribution (Phase 12x)
# ---------------------------------------------------------------------------


def _fake_deal_for_contact(workspace_id: uuid.UUID, contact_id: uuid.UUID, **kwargs) -> MagicMock:
    d = MagicMock()
    d.id = uuid.uuid4()
    d.workspace_id = workspace_id
    d.contact_id = contact_id
    d.value = kwargs.get("value", 50000.0)
    d.stage = kwargs.get("stage", "discovery")
    return d


@pytest.mark.asyncio
async def test_pipeline_contribution_aggregates_correctly(app_client):
    """pipeline-contribution aggregates open pipeline + won value per contact."""
    fastapi_app, mock_db, workspace_id = app_client
    cid = uuid.uuid4()
    deal_open = _fake_deal_for_contact(workspace_id, cid, value=100000.0, stage="proposal")
    deal_won  = _fake_deal_for_contact(workspace_id, cid, value=50000.0,  stage="closed_won")
    deal_lost = _fake_deal_for_contact(workspace_id, cid, value=30000.0,  stage="closed_lost")
    contact = _fake_contact(workspace_id, name="Pipeline Person")
    contact.id = cid

    mock_db.execute = AsyncMock(side_effect=[
        _make_scalars_result([deal_open, deal_won, deal_lost]),
        _make_scalars_result([contact]),
    ])

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/contacts/pipeline-contribution")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    row = data[0]
    assert row["pipeline_value"] == 100000.0
    assert row["closed_won_value"] == 50000.0
    assert row["deal_count"] == 3
    assert row["win_rate"] == pytest.approx(33.3, abs=0.2)


@pytest.mark.asyncio
async def test_pipeline_contribution_wrong_workspace_returns_403(app_client):
    """Returns 403 when requesting another workspace's pipeline contribution."""
    fastapi_app, mock_db, workspace_id = app_client
    wrong_id = uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong_id}/contacts/pipeline-contribution")
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/contacts/reengagement-summary — Phase 13b
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reengagement_summary_counts_contacts_after_dark_period(app_client):
    """Returns 12 weekly buckets; counts a reengagement when gap between touches > 30 days."""
    from datetime import timezone

    fastapi_app, mock_db, workspace_id = app_client

    contact_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    # First message: 50 days ago (beyond the dark threshold)
    old_msg = MagicMock()
    old_msg.contact_id = contact_id
    old_msg.received_at = now - timedelta(days=50)

    # Second message: 2 days ago (within last 12 weeks, gap of 48 days — triggers reengagement)
    new_msg = MagicMock()
    new_msg.contact_id = contact_id
    new_msg.received_at = now - timedelta(days=2)

    mock_db.execute = AsyncMock(side_effect=[
        _make_scalars_result([old_msg, new_msg]),  # messages query
        _make_scalars_result([]),                   # notes query
    ])

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/contacts/reengagement-summary?weeks=12")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 12
    # Exactly one reengagement total across all weeks
    total = sum(row["reengaged"] for row in data)
    assert total == 1
    # Reengagement lands in the correct week bucket for the new_msg date
    from datetime import timezone
    new_date = (now - timedelta(days=2)).date()
    new_monday = new_date - timedelta(days=new_date.weekday())
    matching = [r for r in data if r["week_start"] == new_monday.isoformat()]
    assert len(matching) == 1 and matching[0]["reengaged"] == 1


@pytest.mark.asyncio
async def test_reengagement_summary_wrong_workspace_returns_403(app_client):
    """Returns 403 when requesting another workspace's reengagement summary."""
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")
    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong_id}/contacts/reengagement-summary")
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/contacts/{cid}/response-time — Phase 13e
# ---------------------------------------------------------------------------


def _make_all_result(rows):
    """Mock for execute().all() returning a list of tuples (column-level select)."""
    r = MagicMock()
    r.all.return_value = rows
    return r


@pytest.mark.asyncio
async def test_response_time_computes_avg_p50_p90(app_client):
    """Returns avg/p50/p90 response hours based on inbound→outbound message pairs."""
    fastapi_app, mock_db, workspace_id = app_client
    contact = _fake_contact(workspace_id, email="alice@example.com")
    contact_id = contact.id

    now = datetime.utcnow()
    # 3 inbound messages from contact, each followed by an outbound reply
    # Reply times: 1h, 2h, 3h
    messages = [
        ("alice@example.com", now - timedelta(hours=10), now - timedelta(hours=10)),
        ("rep@company.com",   now - timedelta(hours=9),  now - timedelta(hours=9)),
        ("alice@example.com", now - timedelta(hours=6),  now - timedelta(hours=6)),
        ("rep@company.com",   now - timedelta(hours=4),  now - timedelta(hours=4)),
        ("alice@example.com", now - timedelta(hours=3),  now - timedelta(hours=3)),
        ("rep@company.com",   now - timedelta(hours=0),  now - timedelta(hours=0)),
    ]

    mock_db.execute = AsyncMock(side_effect=[
        _make_scalar_result(contact),
        _make_all_result(messages),
    ])

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/contacts/{contact_id}/response-time")

    assert resp.status_code == 200
    data = resp.json()
    assert data["message_pairs_count"] == 3
    assert data["avg_response_hours"] == pytest.approx(2.0, abs=0.2)
    assert data["p50_response_hours"] is not None
    assert data["p90_response_hours"] is not None


@pytest.mark.asyncio
async def test_response_time_contact_not_found_returns_404(app_client):
    """Returns 404 when contact does not exist in the workspace."""
    fastapi_app, mock_db, workspace_id = app_client
    missing_id = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/contacts/{missing_id}/response-time")

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/contacts/{cid}/sentiment-trend — Phase 13g
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sentiment_trend_returns_weekly_scores(app_client):
    """Returns per-week sentiment scores bucketed from messages in last 12 weeks."""
    fastapi_app, mock_db, workspace_id = app_client
    contact = _fake_contact(workspace_id)

    now = datetime.utcnow()
    # Two messages in week A, one in week B (different ISO weeks)
    week_a_ts = now - timedelta(days=14)
    week_b_ts = now - timedelta(days=7)
    messages = [
        ("Great progress on the deal!", week_a_ts),
        ("Looking forward to our call.", week_a_ts + timedelta(hours=2)),
        ("Let me know if you have questions.", week_b_ts),
    ]

    mock_db.execute = AsyncMock(side_effect=[
        _make_scalar_result(contact),
        _make_all_result(messages),
    ])

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text='[{"week": "2026-W26", "score": 0.7}, {"week": "2026-W27", "score": 0.4}]')]
    mock_client_instance = MagicMock()
    mock_client_instance.messages.create.return_value = mock_response

    with patch("anthropic.Anthropic", return_value=mock_client_instance):
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.get(f"/workspaces/{workspace_id}/contacts/{contact.id}/sentiment-trend")

    assert resp.status_code == 200
    data = resp.json()
    assert "weeks" in data
    assert len(data["weeks"]) == 2
    assert all("week" in w and "score" in w and "message_count" in w for w in data["weeks"])
    assert all(-1.0 <= w["score"] <= 1.0 for w in data["weeks"])


@pytest.mark.asyncio
async def test_sentiment_trend_contact_not_found_returns_404(app_client):
    """Returns 404 when contact does not exist in the workspace."""
    fastapi_app, mock_db, workspace_id = app_client
    missing_id = uuid.UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/contacts/{missing_id}/sentiment-trend")

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/contacts/{cid}/win-rate-trend — Phase 13i
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_win_rate_trend_groups_deals_by_quarter(app_client):
    """Groups closed deals by calendar quarter and computes per-quarter win rate."""
    fastapi_app, mock_db, workspace_id = app_client
    contact = _fake_contact(workspace_id)

    # Q1 2026: 2 won, 1 lost → 66.7%; Q2 2026: 1 won, 1 lost → 50%
    q1_ts = datetime(2026, 2, 15)
    q2_ts = datetime(2026, 5, 10)
    deals = [
        ("closed_won",  q1_ts,                         q1_ts),
        ("closed_won",  q1_ts + timedelta(days=5),     q1_ts + timedelta(days=5)),
        ("closed_lost", q1_ts + timedelta(days=10),    q1_ts + timedelta(days=10)),
        ("closed_won",  q2_ts,                         q2_ts),
        ("closed_lost", q2_ts + timedelta(days=3),     q2_ts + timedelta(days=3)),
    ]

    mock_db.execute = AsyncMock(side_effect=[
        _make_scalar_result(contact),
        _make_all_result(deals),
    ])

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/contacts/{contact.id}/win-rate-trend")

    assert resp.status_code == 200
    data = resp.json()
    assert "quarters" in data
    quarters = {q["quarter"]: q for q in data["quarters"]}

    assert "2026-Q1" in quarters
    assert quarters["2026-Q1"]["won"] == 2
    assert quarters["2026-Q1"]["total"] == 3
    assert quarters["2026-Q1"]["win_rate"] == pytest.approx(66.7, abs=0.2)

    assert "2026-Q2" in quarters
    assert quarters["2026-Q2"]["won"] == 1
    assert quarters["2026-Q2"]["total"] == 2
    assert quarters["2026-Q2"]["win_rate"] == pytest.approx(50.0, abs=0.2)


@pytest.mark.asyncio
async def test_win_rate_trend_wrong_workspace_returns_403(app_client):
    """Returns 403 when the contact belongs to a different workspace."""
    fastapi_app, mock_db, workspace_id = app_client
    other_workspace_id = uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
    contact = _fake_contact(other_workspace_id)
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(contact))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{other_workspace_id}/contacts/{contact.id}/win-rate-trend")

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/contacts/{cid}/deal-stage-progression — Phase 13n
# ---------------------------------------------------------------------------


def _fake_deal_for_contact(workspace_id, contact_id, stage="proposal", **kwargs):
    d = MagicMock()
    d.id = uuid.uuid4()
    d.workspace_id = workspace_id
    d.contact_id = contact_id
    d.title = kwargs.get("title", "Acme Deal")
    d.stage = stage
    d.value = kwargs.get("value", 25000.0)
    d.created_at = datetime(2026, 1, 1)
    d.stage_changed_at = kwargs.get("stage_changed_at", datetime(2026, 3, 15))
    return d


@pytest.mark.asyncio
async def test_deal_stage_progression_returns_stages(app_client):
    """Returns a deal list with reconstructed stage history up to current stage."""
    fastapi_app, mock_db, workspace_id = app_client
    contact = _fake_contact(workspace_id)
    deal = _fake_deal_for_contact(workspace_id, contact.id, stage="proposal")

    mock_db.execute = AsyncMock(side_effect=[
        _make_scalar_result(contact),
        _make_scalars_result([deal]),
    ])

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(
            f"/workspaces/{workspace_id}/contacts/{contact.id}/deal-stage-progression"
        )

    assert resp.status_code == 200
    data = resp.json()
    assert "deals" in data
    assert len(data["deals"]) == 1
    deal_data = data["deals"][0]
    assert deal_data["stage"] == "proposal"
    stages = deal_data["stages"]
    stage_names = [s["stage"] for s in stages]
    assert "discovery" in stage_names
    assert "qualified" in stage_names
    assert "proposal" in stage_names
    # Should NOT include stages after current
    assert "negotiation" not in stage_names
    # Exactly one stage marked current
    assert sum(1 for s in stages if s["is_current"]) == 1


@pytest.mark.asyncio
async def test_deal_stage_progression_wrong_workspace_returns_403(app_client):
    """Returns 403 when requesting a contact that belongs to a different workspace."""
    fastapi_app, mock_db, workspace_id = app_client
    other_workspace_id = uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
    contact = _fake_contact(other_workspace_id)
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(contact))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(
            f"/workspaces/{other_workspace_id}/contacts/{contact.id}/deal-stage-progression"
        )

    assert resp.status_code == 403
