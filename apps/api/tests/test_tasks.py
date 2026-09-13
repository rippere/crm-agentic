"""Tests for the tasks router — list, create, update, delete."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient, ASGITransport

from tests.conftest import _make_scalar_result, _make_scalars_result


def _fake_task(workspace_id: uuid.UUID, **kwargs) -> MagicMock:
    task = MagicMock()
    task.id = uuid.uuid4()
    task.workspace_id = workspace_id
    task.title = kwargs.get("title", "Follow up with Alice")
    task.description = kwargs.get("description", "")
    task.status = kwargs.get("status", "open")
    task.due_date = kwargs.get("due_date", None)
    task.external_id = kwargs.get("external_id", None)
    task.message_id = kwargs.get("message_id", None)
    task.contact_id = kwargs.get("contact_id", None)
    task.deal_id = kwargs.get("deal_id", None)
    task.project_id = kwargs.get("project_id", None)
    task.updated_at = kwargs.get("updated_at", None)
    return task


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/tasks — list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_tasks_empty(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/tasks")

    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_tasks_returns_tasks(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    task = _fake_task(workspace_id, title="Call Bob")
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([task]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/tasks")

    assert resp.status_code == 200
    assert resp.json()[0]["title"] == "Call Bob"


@pytest.mark.asyncio
async def test_list_tasks_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong_id}/tasks")

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /workspaces/{wid}/tasks — create
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_task_returns_201(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    task = _fake_task(workspace_id, title="Send proposal")

    def fake_refresh(obj):
        for attr in ("id", "workspace_id", "title", "description", "status", "due_date", "message_id", "contact_id"):
            setattr(obj, attr, getattr(task, attr))

    mock_db.refresh.side_effect = fake_refresh

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{workspace_id}/tasks",
            json={"title": "Send proposal", "status": "open"},
        )

    assert resp.status_code == 201
    assert resp.json()["title"] == "Send proposal"
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_create_task_missing_title_returns_422(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(f"/workspaces/{workspace_id}/tasks", json={})

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_task_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(f"/workspaces/{wrong_id}/tasks", json={"title": "x"})

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# PUT /workspaces/{wid}/tasks/by-external/{external_id} — upsert
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upsert_cc_task_defaults_due_date_when_omitted(app_client):
    """A cc:-namespaced follow-up created with no due_date gets a default so
    carry-forward logic has something to sort on."""
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))
    created = _fake_task(workspace_id, external_id="cc:session-abc123", title="Follow up on X")

    def fake_refresh(obj):
        for attr in ("id", "workspace_id", "external_id", "title", "description",
                     "status", "due_date", "project_id", "contact_id", "deal_id"):
            if getattr(obj, attr, None) is None and hasattr(created, attr):
                setattr(obj, attr, getattr(created, attr))

    mock_db.refresh.side_effect = fake_refresh

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.put(
            f"/workspaces/{workspace_id}/tasks/by-external/cc:session-abc123",
            json={"title": "Follow up on X"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["due_date"] is not None
    expected = date.today() + timedelta(days=7)
    assert body["due_date"] == expected.isoformat()
    mock_db.add.assert_called_once()


@pytest.mark.asyncio
async def test_upsert_cc_task_respects_explicit_due_date(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))
    created = _fake_task(
        workspace_id,
        external_id="cc:session-xyz789",
        title="Follow up on Y",
        due_date=date(2026, 12, 25),
    )

    def fake_refresh(obj):
        for attr in ("id", "workspace_id", "external_id", "title", "description",
                     "status", "due_date", "project_id", "contact_id", "deal_id"):
            if getattr(obj, attr, None) is None and hasattr(created, attr):
                setattr(obj, attr, getattr(created, attr))

    mock_db.refresh.side_effect = fake_refresh

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.put(
            f"/workspaces/{workspace_id}/tasks/by-external/cc:session-xyz789",
            json={"title": "Follow up on Y", "due_date": "2026-12-25"},
        )

    assert resp.status_code == 200
    assert resp.json()["due_date"] == "2026-12-25"


@pytest.mark.asyncio
async def test_upsert_non_cc_task_leaves_due_date_none_when_omitted(app_client):
    """Non-cc: tasks (e.g. the sync- namespace) keep today's no-default behavior."""
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))
    created = _fake_task(workspace_id, external_id="sync-42", title="Regular sync task")

    def fake_refresh(obj):
        for attr in ("id", "workspace_id", "external_id", "title", "description",
                     "status", "due_date", "project_id", "contact_id", "deal_id"):
            if getattr(obj, attr, None) is None and hasattr(created, attr):
                setattr(obj, attr, getattr(created, attr))

    mock_db.refresh.side_effect = fake_refresh

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.put(
            f"/workspaces/{workspace_id}/tasks/by-external/sync-42",
            json={"title": "Regular sync task"},
        )

    assert resp.status_code == 200
    assert resp.json()["due_date"] is None


@pytest.mark.asyncio
async def test_upsert_cc_task_updates_existing_without_overwriting_due_date_logic(app_client):
    """Updating an existing cc: task goes through the normal update path — the
    default only applies at creation, never clobbering an existing row's due_date."""
    fastapi_app, mock_db, workspace_id = app_client
    existing = _fake_task(
        workspace_id, external_id="cc:session-existing", title="Old title", due_date=None
    )
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(existing))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.put(
            f"/workspaces/{workspace_id}/tasks/by-external/cc:session-existing",
            json={"title": "New title"},
        )

    assert resp.status_code == 200
    # Update path passes body.due_date through as-is (None here) — no
    # creation-time default is applied on update.
    assert existing.due_date is None


# ---------------------------------------------------------------------------
# PUT /workspaces/{wid}/tasks/{tid} — update
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_task_commits(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    task = _fake_task(workspace_id, status="open")
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(task))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.put(
            f"/workspaces/{workspace_id}/tasks/{task.id}",
            json={"status": "done"},
        )

    assert resp.status_code == 200
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_update_task_not_found_returns_404(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.put(
            f"/workspaces/{workspace_id}/tasks/{uuid.uuid4()}",
            json={"status": "done"},
        )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_task_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.put(f"/workspaces/{wrong_id}/tasks/{uuid.uuid4()}", json={})

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_update_task_all_fields(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    task = _fake_task(workspace_id, title="Old title", description="Old desc", status="open")
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(task))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.put(
            f"/workspaces/{workspace_id}/tasks/{task.id}",
            json={"title": "New title", "description": "New desc", "status": "done", "due_date": "2026-06-01"},
        )

    assert resp.status_code == 200
    assert task.title == "New title"
    assert task.description == "New desc"
    assert task.status == "done"
    assert task.due_date == date(2026, 6, 1)
    mock_db.commit.assert_awaited()


# ---------------------------------------------------------------------------
# DELETE /workspaces/{wid}/tasks/{tid}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_task_returns_204(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    task = _fake_task(workspace_id)
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(task))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.delete(f"/workspaces/{workspace_id}/tasks/{task.id}")

    assert resp.status_code == 204
    mock_db.delete.assert_awaited_with(task)
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_delete_task_not_found_returns_404(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.delete(f"/workspaces/{workspace_id}/tasks/{uuid.uuid4()}")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_task_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.delete(f"/workspaces/{wrong_id}/tasks/{uuid.uuid4()}")

    assert resp.status_code == 403
