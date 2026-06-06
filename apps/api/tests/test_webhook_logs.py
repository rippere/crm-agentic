"""Tests for webhook_logs router and webhook logging side-effects."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

from tests.conftest import _make_scalar_result, _make_scalars_result


def _make_log(
    workspace_id: uuid.UUID,
    source: str = "gmail",
    event_type: str = "pubsub_push",
    status: str = "queued",
    payload_summary: str = "email=test@example.com",
    job_id: str | None = "celery-abc",
):
    log = MagicMock()
    log.id = uuid.uuid4()
    log.workspace_id = workspace_id
    log.source = source
    log.event_type = event_type
    log.status = status
    log.payload_summary = payload_summary
    log.job_id = job_id
    log.error_detail = None
    log.created_at = datetime.now(tz=timezone.utc)
    return log


# ---------------------------------------------------------------------------
# GET /workspaces/{id}/webhook-logs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_webhook_logs_returns_200(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    log = _make_log(workspace_id)
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([log]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/webhook-logs")

    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["source"] == "gmail"
    assert data[0]["event_type"] == "pubsub_push"
    assert data[0]["status"] == "queued"
    assert data[0]["job_id"] == "celery-abc"


@pytest.mark.asyncio
async def test_list_webhook_logs_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong_id}/webhook-logs")

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_webhook_logs_empty_workspace(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/webhook-logs")

    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_webhook_logs_source_filter_applied(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    slack_log = _make_log(workspace_id, source="slack", event_type="event_callback")
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([slack_log]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/webhook-logs?source=slack")

    assert resp.status_code == 200
    data = resp.json()
    assert data[0]["source"] == "slack"


# ---------------------------------------------------------------------------
# Gmail webhook logging side-effect
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gmail_push_logs_queued_when_connector_found(app_client):
    from app.routers.gmail import _trigger_ingest_for_email
    from app.models.webhook_log import WebhookLog

    _, mock_db, workspace_id = app_client

    connector = MagicMock()
    connector.id = uuid.uuid4()
    connector.workspace_id = workspace_id
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(connector))

    mock_task = MagicMock()
    mock_task.id = "celery-job-123"

    with patch("app.workers.ingest.process_gmail_sync") as mock_ingest:
        mock_ingest.delay.return_value = mock_task
        result = await _trigger_ingest_for_email("user@example.com", mock_db)

    assert result == "celery-job-123"
    # WebhookLog was added with status=queued
    added = mock_db.add.call_args[0][0]
    assert isinstance(added, WebhookLog)
    assert added.status == "queued"
    assert added.source == "gmail"
    assert added.job_id == "celery-job-123"
    assert added.workspace_id == workspace_id


@pytest.mark.asyncio
async def test_gmail_push_logs_received_when_connector_not_found(app_client):
    from app.routers.gmail import _trigger_ingest_for_email
    from app.models.webhook_log import WebhookLog

    _, mock_db, _ = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    result = await _trigger_ingest_for_email("unknown@example.com", mock_db)

    assert result is None
    added = mock_db.add.call_args[0][0]
    assert isinstance(added, WebhookLog)
    assert added.status == "received"
    assert "connector=not_found" in (added.payload_summary or "")


# ---------------------------------------------------------------------------
# Slack webhook logging side-effect
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_slack_ingest_logs_queued_when_connector_found(app_client):
    from app.routers.slack import _trigger_slack_ingest_for_team
    from app.models.webhook_log import WebhookLog

    _, mock_db, workspace_id = app_client

    connector = MagicMock()
    connector.id = uuid.uuid4()
    connector.workspace_id = workspace_id
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(connector))

    mock_task = MagicMock()
    mock_task.id = "celery-slack-456"

    with patch("app.workers.slack_ingest.process_slack_sync") as mock_sync:
        mock_sync.delay.return_value = mock_task
        result = await _trigger_slack_ingest_for_team("T-TEAM123", mock_db)

    assert result == "celery-slack-456"
    added = mock_db.add.call_args[0][0]
    assert isinstance(added, WebhookLog)
    assert added.status == "queued"
    assert added.source == "slack"
    assert added.job_id == "celery-slack-456"


@pytest.mark.asyncio
async def test_slack_ingest_logs_received_when_connector_not_found(app_client):
    from app.routers.slack import _trigger_slack_ingest_for_team
    from app.models.webhook_log import WebhookLog

    _, mock_db, _ = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    result = await _trigger_slack_ingest_for_team("T-UNKNOWN", mock_db)

    assert result is None
    added = mock_db.add.call_args[0][0]
    assert isinstance(added, WebhookLog)
    assert added.status == "received"
    assert "connector=not_found" in (added.payload_summary or "")
