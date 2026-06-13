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


@pytest.mark.asyncio
async def test_delete_contact_erases_linked_pii(app_client):
    """GDPR right-to-erasure (finding F7): deleting a contact must destroy the
    PII carried in its linked rows — messages (sender_email + body_plain) and
    call summaries (transcript + summary) hard-deleted, deals/tasks scrubbed of
    the contact link — NOT leave them orphaned with PII intact.

    The DB is mocked, so we assert the *erasure operations* the handler emits in
    the same transaction: a DELETE against ``messages`` and ``call_summaries``
    (each scoped by workspace_id + contact_id), a scrubbing UPDATE against
    ``deals`` (nulling contact_id/contact_name/company) and ``tasks`` (nulling
    contact_id), the contact itself deleted, and a single commit.
    """
    from sqlalchemy.sql import Delete, Update

    fastapi_app, mock_db, workspace_id = app_client
    contact = _fake_contact(workspace_id, name="Erase Me", email="erase@example.com")

    # Capture every statement passed to db.execute so we can introspect them.
    executed: list = []

    async def _capture_execute(stmt, *args, **kwargs):
        executed.append(stmt)
        # First call is the contact SELECT → must yield the contact; the rest
        # are DELETE/UPDATE statements whose result the handler does not read.
        if len(executed) == 1:
            return _make_scalar_result(contact)
        return MagicMock(rowcount=1)

    mock_db.execute = AsyncMock(side_effect=_capture_execute)

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.delete(f"/workspaces/{workspace_id}/contacts/{contact.id}")

    assert resp.status_code == 204

    # --- Index the emitted DELETE / UPDATE statements by target table. -------
    deletes = {
        s.table.name: s for s in executed if isinstance(s, Delete)
    }
    updates = {
        s.table.name: s for s in executed if isinstance(s, Update)
    }

    # 1. PII-bearing children are HARD-DELETED, not orphaned.
    assert "messages" in deletes, "messages (sender_email/body_plain) not deleted"
    assert "call_summaries" in deletes, "call_summaries (transcript/summary) not deleted"

    # 2. Each erasure is scoped by BOTH workspace_id and contact_id (no
    #    cross-tenant / unscoped wipe). Verify via the compiled WHERE clause.
    for table, stmt in list(deletes.items()) + list(updates.items()):
        sql = str(stmt.compile(compile_kwargs={"literal_binds": False}))
        assert f"{table}.workspace_id" in sql, f"{table} erasure not scoped by workspace_id"
        assert f"{table}.contact_id" in sql, f"{table} erasure not scoped by contact_id"

    # 3. Deals survive but are scrubbed of personal data + the contact link.
    assert "deals" in updates, "deals not scrubbed"
    deal_set_cols = {c.name for c in updates["deals"]._values}
    assert {"contact_id", "contact_name", "company"} <= deal_set_cols, (
        f"deal scrub must null contact_id/contact_name/company, got {deal_set_cols}"
    )

    # 4. Tasks survive but lose the contact link.
    assert "tasks" in updates, "tasks not unlinked"
    assert "contact_id" in {c.name for c in updates["tasks"]._values}

    # 5. The contact row itself is deleted, exactly once, in one committed txn.
    mock_db.delete.assert_awaited_once_with(contact)
    mock_db.commit.assert_awaited_once()


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

    # First execute: fetch both contacts; then one UPDATE per reassigned child
    # table (tasks, messages, deals, call_summaries, contact_notes, projects).
    mock_db.execute = AsyncMock(side_effect=[
        _make_scalars_result([primary, duplicate]),  # select contacts
        MagicMock(rowcount=2),   # update tasks
        MagicMock(rowcount=1),   # update messages
        MagicMock(rowcount=1),   # update deals
        MagicMock(rowcount=1),   # update call_summaries
        MagicMock(rowcount=1),   # update contact_notes
        MagicMock(rowcount=1),   # update projects
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
    assert data["call_summaries_reassigned"] == 1
    assert data["contact_notes_reassigned"] == 1
    assert data["projects_reassigned"] == 1
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
# PII-erasure coverage for the sibling deletion paths (bulk delete + merge).
# Mirrors test_delete_contact_erases_linked_pii: the DB is mocked, so we assert
# the *statements the handler emits* against each child table.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bulk_delete_erases_linked_pii_per_contact(app_client):
    """Bulk delete must erase EACH contact's PII children, not orphan them.

    For every contact in the batch the handler must, scoped by
    workspace_id + that contact_id, HARD-DELETE messages (sender_email +
    body_plain) and call_summaries (transcript + summary), and scrub/unlink
    deals + tasks — the same erasure semantics as single delete. We introspect
    the emitted DELETE/UPDATE statements and confirm one of each per contact,
    each correctly scoped, and that both contacts are deleted in one txn.
    """
    from sqlalchemy.sql import Delete, Update

    fastapi_app, mock_db, workspace_id = app_client
    c1 = _fake_contact(workspace_id, name="Alice", email="alice@example.com")
    c2 = _fake_contact(workspace_id, name="Bob", email="bob@example.com")

    executed: list = []

    async def _capture_execute(stmt, *args, **kwargs):
        executed.append(stmt)
        # First call is the bulk contact SELECT → yield both contacts; the rest
        # are the per-contact erasure DELETE/UPDATE statements.
        if len(executed) == 1:
            return _make_scalars_result([c1, c2])
        return MagicMock(rowcount=1)

    mock_db.execute = AsyncMock(side_effect=_capture_execute)

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{workspace_id}/contacts/bulk",
            json={"action": "delete", "contact_ids": [str(c1.id), str(c2.id)]},
        )

    assert resp.status_code == 200
    assert resp.json()["deleted"] == 2

    # Collect erasure statements per target table, with their compiled SQL so we
    # can check both contact ids were targeted.
    def _sql(stmt) -> str:
        return str(stmt.compile(compile_kwargs={"literal_binds": True}))

    msg_deletes = [s for s in executed if isinstance(s, Delete) and s.table.name == "messages"]
    call_deletes = [s for s in executed if isinstance(s, Delete) and s.table.name == "call_summaries"]
    deal_updates = [s for s in executed if isinstance(s, Update) and s.table.name == "deals"]
    task_updates = [s for s in executed if isinstance(s, Update) and s.table.name == "tasks"]

    # One erasure statement per contact, per PII table.
    assert len(msg_deletes) == 2, "messages must be hard-deleted once per contact"
    assert len(call_deletes) == 2, "call_summaries must be hard-deleted once per contact"
    assert len(deal_updates) == 2, "deals must be scrubbed once per contact"
    assert len(task_updates) == 2, "tasks must be unlinked once per contact"

    # Every erasure scoped by workspace_id, and across the batch BOTH contact
    # ids are covered (no contact left with orphaned PII). The PG UUID literal
    # binds render without dashes, so match on the bare hex form.
    for stmt in msg_deletes + call_deletes + deal_updates + task_updates:
        sql = _sql(stmt)
        assert workspace_id.hex in sql, "erasure not scoped by workspace_id"

    for table_stmts, label in (
        (msg_deletes, "messages"),
        (call_deletes, "call_summaries"),
    ):
        covered = " ".join(_sql(s) for s in table_stmts)
        assert c1.id.hex in covered, f"{label} for contact 1 not erased"
        assert c2.id.hex in covered, f"{label} for contact 2 not erased"

    # Deal scrub nulls the personal fields; task scrub nulls the link.
    assert {"contact_id", "contact_name", "company"} <= {c.name for c in deal_updates[0]._values}
    assert "contact_id" in {c.name for c in task_updates[0]._values}

    # No DELETE against the messages/call_summaries tables should be UNscoped,
    # and both contacts themselves are deleted in a single committed txn.
    assert mock_db.delete.await_count == 2
    deleted_objs = {call.args[0] for call in mock_db.delete.await_args_list}
    assert deleted_objs == {c1, c2}
    mock_db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_merge_reassigns_call_summaries_and_notes_no_pii_loss(app_client):
    """Merge is COMBINE, not erase: the duplicate's PII children must be MOVED
    to the primary, never deleted/orphaned.

    Regression guard for the call_summaries gap — previously merge reassigned
    tasks/messages/deals but NOT call_summaries, so a duplicate's transcripts
    were orphaned (FK SET NULL) when the duplicate row was deleted. Here we
    assert the handler emits an UPDATE ... SET contact_id=<primary> WHERE
    contact_id=<duplicate> for call_summaries (and contact_notes, which CASCADE
    and would otherwise be destroyed, and projects), emits NO DELETE against any
    PII table, and deletes only the duplicate contact row.
    """
    from sqlalchemy.sql import Delete, Update

    fastapi_app, mock_db, workspace_id = app_client
    primary = _fake_contact(workspace_id, name="Alice Smith")
    duplicate = _fake_contact(workspace_id, name="Alice S.")

    executed: list = []

    async def _capture_execute(stmt, *args, **kwargs):
        executed.append(stmt)
        if len(executed) == 1:
            return _make_scalars_result([primary, duplicate])
        return MagicMock(rowcount=1)

    mock_db.execute = AsyncMock(side_effect=_capture_execute)

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{workspace_id}/contacts/merge",
            json={"primary_id": str(primary.id), "duplicate_id": str(duplicate.id)},
        )

    assert resp.status_code == 200

    updates = {s.table.name: s for s in executed if isinstance(s, Update)}

    # Every PII-bearing / linked child table is reassigned via UPDATE.
    for table in ("tasks", "messages", "deals", "call_summaries", "contact_notes", "projects"):
        assert table in updates, f"{table} was not reassigned on merge"

    # The transcript-bearing call_summaries reassignment moves the link to the
    # primary and is scoped to the duplicate (so we move exactly its rows).
    call_stmt = updates["call_summaries"]
    assert "contact_id" in {c.name for c in call_stmt._values}, "call_summaries contact_id not reassigned"
    # The PG UUID literal binds render without dashes → match on bare hex. The
    # SET target is the primary id; the WHERE scope is the duplicate id +
    # workspace — i.e. UPDATE ... SET contact_id=<primary> WHERE contact_id=<dup>.
    call_sql = str(call_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert primary.id.hex in call_sql, "call_summaries not reassigned TO the primary"
    assert duplicate.id.hex in call_sql, "call_summaries reassignment not scoped to the duplicate"
    assert workspace_id.hex in call_sql, "call_summaries reassignment not scoped by workspace_id"

    # contact_notes CASCADE on the contacts FK — they MUST be moved, not left to
    # be destroyed when the duplicate is deleted.
    note_sql = str(updates["contact_notes"].compile(compile_kwargs={"literal_binds": True}))
    assert duplicate.id.hex in note_sql

    # NOTHING is erased: no DELETE statement targets any PII-bearing child.
    deleted_tables = {s.table.name for s in executed if isinstance(s, Delete)}
    assert not ({"messages", "call_summaries", "contact_notes"} & deleted_tables), (
        f"merge must not DELETE PII children, but deleted: {deleted_tables}"
    )

    # Only the duplicate CONTACT row itself is deleted (the children survive,
    # reassigned to the primary).
    mock_db.delete.assert_awaited_once_with(duplicate)
    mock_db.commit.assert_awaited_once()

    # Response surfaces the reassignment counts (proof nothing was silently lost).
    data = resp.json()
    assert data["call_summaries_reassigned"] == 1
    assert data["contact_notes_reassigned"] == 1
    assert data["projects_reassigned"] == 1


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
