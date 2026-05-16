"""Tests for calls.py router — upload, list, get, delete."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

from tests.conftest import _make_scalar_result, _make_scalars_result


def _fake_call(workspace_id: uuid.UUID, **kwargs) -> MagicMock:
    c = MagicMock()
    c.id = uuid.uuid4()
    c.workspace_id = workspace_id
    c.contact_id = None
    c.title = kwargs.get("title", "Discovery Call")
    c.duration_seconds = kwargs.get("duration_seconds", 900)
    c.summary = kwargs.get("summary", "Discussed product fit.")
    c.action_items = kwargs.get("action_items", [])
    c.participants = kwargs.get("participants", "Alice, Bob")
    c.call_date = kwargs.get("call_date", datetime(2026, 5, 15, 10, 0, tzinfo=timezone.utc))
    c.transcript = kwargs.get("transcript", "Hello, how are you?")
    c.model_used = kwargs.get("model_used", "whisper-1")
    return c


# ---------------------------------------------------------------------------
# POST /workspaces/{wid}/calls/upload
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_call_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{wrong_id}/calls/upload",
            files={"file": ("audio.mp3", b"bytes", "audio/mpeg")},
            data={"title": "Test"},
        )

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_upload_call_invalid_format_returns_422(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{workspace_id}/calls/upload",
            files={"file": ("document.pdf", b"pdf bytes", "application/pdf")},
            data={"title": "Bad Format"},
        )

    assert resp.status_code == 422
    assert "Unsupported" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_upload_call_too_large_returns_413(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    with patch("app.routers.calls.MAX_UPLOAD_MB", 0):
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(
                f"/workspaces/{workspace_id}/calls/upload",
                files={"file": ("audio.mp3", b"any_bytes", "audio/mpeg")},
                data={"title": "Too Big"},
            )

    assert resp.status_code == 413
    assert "MB limit" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_upload_call_with_contact_id(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    call = _fake_call(workspace_id)
    contact_id = str(uuid.uuid4())

    async def fake_refresh(obj):
        obj.id = call.id

    mock_db.refresh.side_effect = fake_refresh

    mock_task = MagicMock()
    mock_task.id = "task-abc"

    with patch("app.workers.transcribe.transcribe_call") as mock_celery:
        mock_celery.delay.return_value = mock_task
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(
                f"/workspaces/{workspace_id}/calls/upload",
                files={"file": ("call.mp3", b"audio", "audio/mpeg")},
                data={"title": "With Contact", "contact_id": contact_id},
            )

    assert resp.status_code == 202


@pytest.mark.asyncio
async def test_upload_call_invalid_contact_id_is_ignored(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    call = _fake_call(workspace_id)

    async def fake_refresh(obj):
        obj.id = call.id

    mock_db.refresh.side_effect = fake_refresh

    mock_task = MagicMock()
    mock_task.id = "task-xyz"

    with patch("app.workers.transcribe.transcribe_call") as mock_celery:
        mock_celery.delay.return_value = mock_task
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(
                f"/workspaces/{workspace_id}/calls/upload",
                files={"file": ("call.mp3", b"audio", "audio/mpeg")},
                data={"title": "Bad Contact", "contact_id": "not-a-uuid"},
            )

    assert resp.status_code == 202


@pytest.mark.asyncio
async def test_upload_call_happy_path_enqueues_task(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    call = _fake_call(workspace_id)

    async def fake_refresh(obj):
        obj.id = call.id

    mock_db.refresh.side_effect = fake_refresh

    mock_task = MagicMock()
    mock_task.id = "celery-job-xyz"

    with patch("app.workers.transcribe.transcribe_call") as mock_celery:
        mock_celery.delay.return_value = mock_task
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(
                f"/workspaces/{workspace_id}/calls/upload",
                files={"file": ("interview.mp3", b"audio_data", "audio/mpeg")},
                data={"title": "Interview"},
            )

    assert resp.status_code == 202
    assert resp.json()["status"] == "processing"
    assert resp.json()["job_id"] == "celery-job-xyz"
    mock_db.commit.assert_awaited()


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/calls
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_calls_empty(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/calls")

    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_calls_returns_data(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    call = _fake_call(workspace_id, title="Sales Call")
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([call]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/calls")

    assert resp.status_code == 200
    assert resp.json()[0]["title"] == "Sales Call"


@pytest.mark.asyncio
async def test_list_calls_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong_id}/calls")

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/calls/{cid}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_call_returns_detail(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    call = _fake_call(workspace_id, title="Discovery Call", summary="Found product fit.")
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(call))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/calls/{call.id}")

    assert resp.status_code == 200
    assert resp.json()["title"] == "Discovery Call"
    assert "transcript" in resp.json()


@pytest.mark.asyncio
async def test_get_call_not_found_returns_404(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/calls/{uuid.uuid4()}")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_call_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong_id}/calls/{uuid.uuid4()}")

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# DELETE /workspaces/{wid}/calls/{cid}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_call_returns_204(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    call = _fake_call(workspace_id)
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(call))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.delete(f"/workspaces/{workspace_id}/calls/{call.id}")

    assert resp.status_code == 204
    mock_db.delete.assert_awaited_with(call)
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_delete_call_not_found_returns_404(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.delete(f"/workspaces/{workspace_id}/calls/{uuid.uuid4()}")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_call_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.delete(f"/workspaces/{wrong_id}/calls/{uuid.uuid4()}")

    assert resp.status_code == 403
