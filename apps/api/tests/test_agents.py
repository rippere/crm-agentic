"""Tests for the agents router — list, run, PATCH status."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

from tests.conftest import _make_scalar_result, _make_scalars_result


def _fake_agent(workspace_id: uuid.UUID, **kwargs) -> MagicMock:
    agent = MagicMock()
    agent.id = uuid.uuid4()
    agent.workspace_id = workspace_id
    agent.name = kwargs.get("name", "TestAgent")
    agent.type = kwargs.get("type", "gmail")
    agent.description = kwargs.get("description", None)
    agent.model = kwargs.get("model", None)
    agent.status = kwargs.get("status", "idle")
    agent.accuracy = kwargs.get("accuracy", 0.95)
    agent.tasks_today = kwargs.get("tasks_today", 0)
    agent.last_run = kwargs.get("last_run", "Never")
    return agent


# ---------------------------------------------------------------------------
# GET /agents
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_agents_returns_empty(app_client):
    fastapi_app, mock_db, _ = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get("/agents")

    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_agents_returns_agents(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    agent = _fake_agent(workspace_id, name="Gmail Agent")
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([agent]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get("/agents")

    assert resp.status_code == 200
    assert resp.json()[0]["name"] == "Gmail Agent"


# ---------------------------------------------------------------------------
# POST /agents/{id}/run
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_agent_returns_job_id(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    agent = _fake_agent(workspace_id)
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(agent))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(f"/agents/{agent.id}/run")

    assert resp.status_code == 200
    data = resp.json()
    assert "job_id" in data
    assert data["status"] == "processing"
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_run_agent_not_found_returns_404(app_client):
    fastapi_app, mock_db, _ = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(f"/agents/{uuid.uuid4()}/run")

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /agents/{id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patch_agent_updates_status(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    agent = _fake_agent(workspace_id, status="idle")
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(agent))
    mock_db.refresh = AsyncMock()

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.patch(f"/agents/{agent.id}", json={"status": "processing"})

    assert resp.status_code == 200
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_patch_agent_not_found_returns_404(app_client):
    fastapi_app, mock_db, _ = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.patch(f"/agents/{uuid.uuid4()}", json={"status": "idle"})

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_patch_agent_none_status_is_noop(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    agent = _fake_agent(workspace_id, status="idle")
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(agent))
    mock_db.refresh = AsyncMock()

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.patch(f"/agents/{agent.id}", json={})

    assert resp.status_code == 200
    assert agent.status == "idle"


# ---------------------------------------------------------------------------
# GET /jobs/{job_id} — Celery job status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_job_status_success(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    mock_result = MagicMock()
    mock_result.state = "SUCCESS"
    mock_result.result = {"output": "done"}

    with patch("app.workers.celery_app.celery_app") as mock_celery:
        mock_celery.AsyncResult.return_value = mock_result
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.get("/jobs/test-job-id-123")

    assert resp.status_code == 200
    data = resp.json()
    assert data["state"] == "SUCCESS"
    assert data["result"] == {"output": "done"}
    assert data["error"] is None


@pytest.mark.asyncio
async def test_get_job_status_failure(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    mock_result = MagicMock()
    mock_result.state = "FAILURE"
    mock_result.result = Exception("something went wrong")

    with patch("app.workers.celery_app.celery_app") as mock_celery:
        mock_celery.AsyncResult.return_value = mock_result
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.get("/jobs/failing-job-id")

    assert resp.status_code == 200
    data = resp.json()
    assert data["state"] == "FAILURE"
    assert data["error"] is not None
    assert data["result"] is None


@pytest.mark.asyncio
async def test_get_job_status_pending(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    mock_result = MagicMock()
    mock_result.state = "PENDING"
    mock_result.result = None

    with patch("app.workers.celery_app.celery_app") as mock_celery:
        mock_celery.AsyncResult.return_value = mock_result
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.get("/jobs/pending-job-id")

    assert resp.status_code == 200
    assert resp.json()["state"] == "PENDING"
    assert resp.json()["result"] is None
    assert resp.json()["error"] is None
