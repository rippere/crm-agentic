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
# POST /agents/{id}/run — dispatch real Celery tasks, honest job ids
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_pipeline_optimizer_dispatches_real_task(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    agent = _fake_agent(workspace_id, type="pipeline_optimizer", tasks_today=4)
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(agent))

    fake_task = MagicMock()
    fake_task.id = "celery-pipeline-task-id"

    with patch("app.workers.pipeline.optimize_pipeline.delay", return_value=fake_task) as mock_delay, \
         patch("app.routers.agents._mark_job_dispatched") as mock_marker:
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(f"/agents/{agent.id}/run")

    assert resp.status_code == 200
    data = resp.json()
    # The returned job_id is the REAL Celery task id, not a fabricated uuid.
    assert data["job_id"] == "celery-pipeline-task-id"
    assert data["status"] == "processing"
    mock_delay.assert_called_once_with(str(workspace_id))
    mock_marker.assert_called_once_with("celery-pipeline-task-id", str(workspace_id))
    # Agent bookkeeping updated only after successful dispatch.
    assert agent.status == "processing"
    assert agent.tasks_today == 5  # incremented from 4
    assert agent.last_run != "Never"
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_run_pm_agent_dispatches_health_check(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    agent = _fake_agent(workspace_id, type="pm_agent", tasks_today=0)
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(agent))

    fake_task = MagicMock()
    fake_task.id = "celery-pm-task-id"

    with patch("app.workers.pm_agent.run_health_check.delay", return_value=fake_task) as mock_delay, \
         patch("app.routers.agents._mark_job_dispatched"):
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(f"/agents/{agent.id}/run")

    assert resp.status_code == 200
    assert resp.json()["job_id"] == "celery-pm-task-id"
    mock_delay.assert_called_once_with()  # run_health_check takes no args
    assert agent.tasks_today == 1


@pytest.mark.parametrize(
    "unbacked_type",
    ["email_composer", "call_summarizer", "sentiment_analyzer", "semantic_sorter"],
)
@pytest.mark.asyncio
async def test_run_unbacked_type_returns_501(app_client, unbacked_type):
    fastapi_app, mock_db, workspace_id = app_client
    agent = _fake_agent(workspace_id, type=unbacked_type, tasks_today=7)
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(agent))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(f"/agents/{agent.id}/run")

    assert resp.status_code == 501
    assert resp.json()["detail"]  # a non-empty, explanatory message
    # No dispatch ⇒ no bookkeeping side effects and no commit.
    assert agent.status == "idle"
    assert agent.tasks_today == 7
    mock_db.commit.assert_not_awaited()


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
async def test_get_job_status_pending_when_dispatched(app_client):
    """PENDING + a present dispatch marker ⇒ still PENDING (a real in-flight job)."""
    fastapi_app, mock_db, workspace_id = app_client

    mock_result = MagicMock()
    mock_result.state = "PENDING"
    mock_result.result = None

    with patch("app.workers.celery_app.celery_app") as mock_celery, \
         patch("app.routers.agents._job_was_dispatched", return_value=True):
        mock_celery.AsyncResult.return_value = mock_result
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.get("/jobs/pending-job-id")

    assert resp.status_code == 200
    assert resp.json()["state"] == "PENDING"
    assert resp.json()["result"] is None
    assert resp.json()["error"] is None


@pytest.mark.asyncio
async def test_get_job_status_unknown_id_is_terminal(app_client):
    """Celery reports PENDING for ids it never saw — without a dispatch marker we
    must return the terminal 'unknown' state, not PENDING-forever (the trap)."""
    fastapi_app, mock_db, workspace_id = app_client

    mock_result = MagicMock()
    mock_result.state = "PENDING"  # the trap: nonexistent ids look identical to queued
    mock_result.result = None

    with patch("app.workers.celery_app.celery_app") as mock_celery, \
         patch("app.routers.agents._job_was_dispatched", return_value=False):
        mock_celery.AsyncResult.return_value = mock_result
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.get("/jobs/never-dispatched-id")

    assert resp.status_code == 200
    assert resp.json()["state"] == "unknown"
    assert resp.json()["error"] is not None


@pytest.mark.asyncio
async def test_get_job_status_pending_when_redis_unreachable(app_client):
    """If Redis can't be reached (marker check returns None) we keep PENDING rather
    than risk masking a real in-flight job as unknown."""
    fastapi_app, mock_db, workspace_id = app_client

    mock_result = MagicMock()
    mock_result.state = "PENDING"
    mock_result.result = None

    with patch("app.workers.celery_app.celery_app") as mock_celery, \
         patch("app.routers.agents._job_was_dispatched", return_value=None):
        mock_celery.AsyncResult.return_value = mock_result
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.get("/jobs/pending-during-redis-blip")

    assert resp.status_code == 200
    assert resp.json()["state"] == "PENDING"


# ---------------------------------------------------------------------------
# GET /jobs/{job_id} — tenant isolation (IDOR fix): a job's result is only
# visible to the workspace that dispatched it.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_job_status_foreign_workspace_returns_404(app_client):
    """A job owned by another workspace must look like it does not exist (404),
    and its result body must never be leaked cross-tenant."""
    fastapi_app, mock_db, workspace_id = app_client

    mock_result = MagicMock()
    mock_result.state = "SUCCESS"
    mock_result.result = {"workspace_id": "ffffffff-ffff-ffff-ffff-ffffffffffff", "deals_updated": 9}

    with patch("app.workers.celery_app.celery_app") as mock_celery, \
         patch("app.routers.agents._job_owner_workspace",
               return_value="ffffffff-ffff-ffff-ffff-ffffffffffff"):
        mock_celery.AsyncResult.return_value = mock_result
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.get("/jobs/victim-job-id")

    assert resp.status_code == 404
    assert "deals_updated" not in resp.text  # result never leaked to a foreign tenant


@pytest.mark.asyncio
async def test_get_job_status_own_workspace_returns_result(app_client):
    """The owning workspace still gets its result unchanged."""
    fastapi_app, mock_db, workspace_id = app_client

    mock_result = MagicMock()
    mock_result.state = "SUCCESS"
    mock_result.result = {"workspace_id": str(workspace_id), "deals_updated": 3}

    with patch("app.workers.celery_app.celery_app") as mock_celery, \
         patch("app.routers.agents._job_owner_workspace", return_value=str(workspace_id)):
        mock_celery.AsyncResult.return_value = mock_result
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.get("/jobs/own-job-id")

    assert resp.status_code == 200
    assert resp.json()["result"]["deals_updated"] == 3


@pytest.mark.asyncio
async def test_get_job_status_unknown_owner_preserves_behavior(app_client):
    """Marker missing/expired or Redis down (_job_owner_workspace -> None) must NOT
    404: the rightful caller still gets the result and a Redis blip cannot mask a
    real job."""
    fastapi_app, mock_db, workspace_id = app_client

    mock_result = MagicMock()
    mock_result.state = "SUCCESS"
    mock_result.result = {"output": "ok"}

    with patch("app.workers.celery_app.celery_app") as mock_celery, \
         patch("app.routers.agents._job_owner_workspace", return_value=None):
        mock_celery.AsyncResult.return_value = mock_result
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.get("/jobs/marker-missing-id")

    assert resp.status_code == 200
    assert resp.json()["result"] == {"output": "ok"}


# ---------------------------------------------------------------------------
# GET /workspaces/{workspace_id}/agents/run-stats
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_run_stats_groups_by_agent_name(app_client):
    """Groups last-30-day events by agent_name, counting success vs failure."""
    fastapi_app, mock_db, workspace_id = app_client

    def _fake_event(name: str, severity: str) -> MagicMock:
        e = MagicMock()
        e.agent_name = name
        e.severity = severity
        return e

    events = [
        _fake_event("Lead Scorer", "info"),
        _fake_event("Lead Scorer", "info"),
        _fake_event("Lead Scorer", "error"),
        _fake_event("Email Composer", "info"),
    ]
    mock_db.execute = AsyncMock(return_value=_make_scalars_result(events))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/agents/run-stats")

    assert resp.status_code == 200
    data = resp.json()
    email = next(r for r in data if r["agent_name"] == "Email Composer")
    scorer = next(r for r in data if r["agent_name"] == "Lead Scorer")
    assert email == {"agent_name": "Email Composer", "success": 1, "failure": 0}
    assert scorer == {"agent_name": "Lead Scorer", "success": 2, "failure": 1}


@pytest.mark.asyncio
async def test_agent_run_stats_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    other = uuid.uuid4()

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{other}/agents/run-stats")

    assert resp.status_code == 403


def test_mark_job_dispatched_stores_workspace_not_constant():
    """The dispatch marker stores the owning workspace id (so ownership can be
    enforced), never the legacy constant '1'."""
    captured = {}
    fake_client = MagicMock()
    fake_client.set = lambda *a, **k: captured.update(args=a, kwargs=k)

    with patch("redis.Redis.from_url", return_value=fake_client):
        from app.routers.agents import _mark_job_dispatched

        _mark_job_dispatched("task-xyz", "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

    assert captured["args"][0] == "crm:job:task-xyz"
    assert captured["args"][1] == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"  # not "1"
