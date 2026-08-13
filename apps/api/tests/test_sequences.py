"""Tests for the sequences router — CRUD + step builder + auth checks."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient, ASGITransport

from tests.conftest import _make_scalar_result, _make_scalars_result

_NOW = datetime(2026, 5, 15, 12, 0, 0, tzinfo=timezone.utc)


def _fake_sequence(workspace_id: uuid.UUID, **kwargs) -> MagicMock:
    seq = MagicMock()
    seq.id = kwargs.get("id", uuid.uuid4())
    seq.workspace_id = workspace_id
    seq.name = kwargs.get("name", "Welcome Drip")
    seq.description = kwargs.get("description", None)
    seq.channel = kwargs.get("channel", "email")
    seq.status = kwargs.get("status", "draft")
    seq.step_count = kwargs.get("step_count", 0)
    seq.settings = kwargs.get("settings", {})
    seq.created_at = kwargs.get("created_at", _NOW - timedelta(days=1))
    seq.updated_at = kwargs.get("updated_at", _NOW - timedelta(days=1))
    return seq


def _fake_step(workspace_id: uuid.UUID, sequence_id: uuid.UUID, **kwargs) -> MagicMock:
    step = MagicMock()
    step.id = kwargs.get("id", uuid.uuid4())
    step.workspace_id = workspace_id
    step.sequence_id = sequence_id
    step.step_order = kwargs.get("step_order", 0)
    step.channel = kwargs.get("channel", "email")
    step.delay_hours = kwargs.get("delay_hours", 0)
    step.subject = kwargs.get("subject", "Hello")
    step.body_template = kwargs.get("body_template", "Hi {{name}}")
    step.requires_approval = kwargs.get("requires_approval", True)
    step.ai_generate = kwargs.get("ai_generate", False)
    step.created_at = kwargs.get("created_at", _NOW)
    step.updated_at = kwargs.get("updated_at", _NOW)
    return step


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/sequences — list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_sequences_returns_empty(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/sequences")

    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_sequences_returns_sequences(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    seq = _fake_sequence(workspace_id, name="Nurture", status="active")
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([seq]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/sequences?status=active")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "Nurture"
    assert data[0]["status"] == "active"


@pytest.mark.asyncio
async def test_list_sequences_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong_id}/sequences")

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /workspaces/{wid}/sequences — create
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_sequence_returns_201(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    seq = _fake_sequence(workspace_id, name="Cold Outreach", channel="email")

    def fake_refresh(obj):
        for attr in ("id", "workspace_id", "name", "description", "channel",
                     "status", "step_count", "settings", "created_at", "updated_at"):
            setattr(obj, attr, getattr(seq, attr))

    mock_db.refresh.side_effect = fake_refresh

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{workspace_id}/sequences",
            json={"name": "Cold Outreach", "channel": "email"},
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Cold Outreach"
    assert data["step_count"] == 0
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_create_sequence_bad_channel_returns_422(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{workspace_id}/sequences",
            json={"name": "Bad", "channel": "carrier_pigeon"},
        )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_sequence_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(f"/workspaces/{wrong_id}/sequences", json={"name": "x"})

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/sequences/{id} — detail with steps
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_sequence_returns_detail_with_steps(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    seq = _fake_sequence(workspace_id, name="Detail Seq", step_count=2)
    s1 = _fake_step(workspace_id, seq.id, step_order=0, subject="First")
    s2 = _fake_step(workspace_id, seq.id, step_order=1, subject="Second")

    call_count = 0

    async def _execute_side_effect(q):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _make_scalar_result(seq)  # sequence lookup
        return _make_scalars_result([s1, s2])  # ordered steps

    mock_db.execute = AsyncMock(side_effect=_execute_side_effect)

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/sequences/{seq.id}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Detail Seq"
    assert len(data["steps"]) == 2
    assert data["steps"][0]["subject"] == "First"


@pytest.mark.asyncio
async def test_get_sequence_not_found_returns_404(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    # supabase_rest fallback also misses → 404
    from unittest.mock import patch

    with patch("app.routers.sequences.get_row", new=AsyncMock(return_value=None)):
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.get(f"/workspaces/{workspace_id}/sequences/{uuid.uuid4()}")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_sequence_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong_id}/sequences/{uuid.uuid4()}")

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# PATCH /workspaces/{wid}/sequences/{id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patch_sequence_updates_fields(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    seq = _fake_sequence(workspace_id, name="Old", status="draft")
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(seq))
    mock_db.refresh.side_effect = lambda obj: None

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.patch(
            f"/workspaces/{workspace_id}/sequences/{seq.id}",
            json={"name": "New", "status": "active"},
        )

    assert resp.status_code == 200
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_patch_sequence_bad_status_returns_422(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.patch(
            f"/workspaces/{workspace_id}/sequences/{uuid.uuid4()}",
            json={"status": "on_fire"},
        )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_patch_sequence_not_found_returns_404(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.patch(
            f"/workspaces/{workspace_id}/sequences/{uuid.uuid4()}",
            json={"name": "x"},
        )

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /workspaces/{wid}/sequences/{id} — archive
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_sequence_archives_returns_204(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    seq = _fake_sequence(workspace_id)
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(seq))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.delete(f"/workspaces/{workspace_id}/sequences/{seq.id}")

    assert resp.status_code == 204
    assert seq.status == "archived"
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_delete_sequence_not_found_returns_404(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.delete(f"/workspaces/{workspace_id}/sequences/{uuid.uuid4()}")

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PUT /workspaces/{wid}/sequences/{id}/steps — replace ordered list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_put_steps_replaces_and_recomputes_step_count(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    seq = _fake_sequence(workspace_id, name="Builder Seq", step_count=0)
    new_steps = [
        _fake_step(workspace_id, seq.id, step_order=0, subject="Step 1", channel="email"),
        _fake_step(workspace_id, seq.id, step_order=1, subject="Step 2", channel="sms"),
        _fake_step(workspace_id, seq.id, step_order=2, subject="Step 3", channel="email"),
    ]

    call_count = 0

    async def _execute_side_effect(q):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _make_scalar_result(seq)      # sequence lookup
        if call_count == 2:
            return MagicMock()                   # DELETE existing steps
        return _make_scalars_result(new_steps)   # re-query ordered steps

    mock_db.execute = AsyncMock(side_effect=_execute_side_effect)
    mock_db.refresh.side_effect = lambda obj: None

    payload = {
        "steps": [
            {"channel": "email", "delay_hours": 0, "subject": "Step 1", "body_template": "Hi {{name}}"},
            {"channel": "sms", "delay_hours": 24, "body_template": "SMS {{name}}"},
            {"channel": "email", "delay_hours": 48, "subject": "Step 3", "body_template": "Final"},
        ]
    }

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.put(f"/workspaces/{workspace_id}/sequences/{seq.id}/steps", json=payload)

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["steps"]) == 3
    # step_count recomputed to the number of submitted steps
    assert seq.step_count == 3
    assert data["step_count"] == 3
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_put_steps_bad_channel_returns_422(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    # 'mixed' is a valid *sequence* channel but NOT a valid *step* channel.
    payload = {"steps": [{"channel": "mixed", "body_template": "x"}]}

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.put(
            f"/workspaces/{workspace_id}/sequences/{uuid.uuid4()}/steps", json=payload
        )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_put_steps_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.put(
            f"/workspaces/{wrong_id}/sequences/{uuid.uuid4()}/steps",
            json={"steps": []},
        )

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /workspaces/{wid}/sequences/{id}/steps — append
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_append_step_returns_201_and_bumps_count(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    seq = _fake_sequence(workspace_id, step_count=1)
    step = _fake_step(workspace_id, seq.id, step_order=1, subject="Appended")

    call_count = 0

    async def _execute_side_effect(q):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _make_scalar_result(seq)      # sequence lookup
        return _make_scalar_result(0)            # max(step_order) → 0

    mock_db.execute = AsyncMock(side_effect=_execute_side_effect)

    def fake_refresh(obj):
        for attr in ("id", "workspace_id", "sequence_id", "step_order", "channel",
                     "delay_hours", "subject", "body_template", "requires_approval",
                     "ai_generate", "created_at", "updated_at"):
            setattr(obj, attr, getattr(step, attr))

    mock_db.refresh.side_effect = fake_refresh

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{workspace_id}/sequences/{seq.id}/steps",
            json={"channel": "email", "subject": "Appended", "body_template": "Hi"},
        )

    assert resp.status_code == 201
    assert resp.json()["subject"] == "Appended"
    assert seq.step_count == 2


@pytest.mark.asyncio
async def test_append_step_bad_channel_returns_422(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{workspace_id}/sequences/{uuid.uuid4()}/steps",
            json={"channel": "fax", "body_template": "x"},
        )

    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# PATCH / DELETE step
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patch_step_updates_fields(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    seq_id = uuid.uuid4()
    step = _fake_step(workspace_id, seq_id, subject="Old")
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(step))
    mock_db.refresh.side_effect = lambda obj: None

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.patch(
            f"/workspaces/{workspace_id}/sequences/{seq_id}/steps/{step.id}",
            json={"subject": "New", "delay_hours": 12},
        )

    assert resp.status_code == 200
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_patch_step_not_found_returns_404(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.patch(
            f"/workspaces/{workspace_id}/sequences/{uuid.uuid4()}/steps/{uuid.uuid4()}",
            json={"subject": "x"},
        )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_patch_step_bad_channel_returns_422(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.patch(
            f"/workspaces/{workspace_id}/sequences/{uuid.uuid4()}/steps/{uuid.uuid4()}",
            json={"channel": "mixed"},
        )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_delete_step_returns_204_and_decrements_count(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    seq = _fake_sequence(workspace_id, step_count=2)
    step = _fake_step(workspace_id, seq.id)

    call_count = 0

    async def _execute_side_effect(q):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _make_scalar_result(step)  # step lookup
        return _make_scalar_result(seq)       # sequence lookup for count decrement

    mock_db.execute = AsyncMock(side_effect=_execute_side_effect)

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.delete(
            f"/workspaces/{workspace_id}/sequences/{seq.id}/steps/{step.id}"
        )

    assert resp.status_code == 204
    mock_db.delete.assert_awaited_with(step)
    assert seq.step_count == 1


@pytest.mark.asyncio
async def test_delete_step_not_found_returns_404(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.delete(
            f"/workspaces/{workspace_id}/sequences/{uuid.uuid4()}/steps/{uuid.uuid4()}"
        )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_step_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.delete(
            f"/workspaces/{wrong_id}/sequences/{uuid.uuid4()}/steps/{uuid.uuid4()}"
        )

    assert resp.status_code == 403
