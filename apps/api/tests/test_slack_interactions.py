"""Tests for slack_interactions.py — HITL approval handler and signature verifier."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

from tests.conftest import _make_scalar_result


# ---------------------------------------------------------------------------
# _verify_slack_signature (pure function)
# ---------------------------------------------------------------------------


def test_verify_signature_no_signing_secret_returns_true():
    from app.routers.slack_interactions import _verify_slack_signature

    with patch("app.routers.slack_interactions.settings") as mock_settings:
        mock_settings.SLACK_SIGNING_SECRET = ""
        result = _verify_slack_signature(b"body", "12345", "v0=whatever")

    assert result is True


def test_verify_signature_stale_timestamp_returns_false():
    from app.routers.slack_interactions import _verify_slack_signature

    stale = str(int(time.time()) - 400)  # 400 seconds old
    with patch("app.routers.slack_interactions.settings") as mock_settings:
        mock_settings.SLACK_SIGNING_SECRET = "test_secret"
        result = _verify_slack_signature(b"body", stale, "v0=whatever")

    assert result is False


def test_verify_signature_valid_hmac():
    from app.routers.slack_interactions import _verify_slack_signature

    secret = "test_secret_key"
    body = b"test body content"
    ts = str(int(time.time()))
    base = f"v0:{ts}:{body.decode()}"
    sig = "v0=" + hmac.new(
        key=secret.encode(),
        msg=base.encode(),
        digestmod=hashlib.sha256,
    ).hexdigest()

    with patch("app.routers.slack_interactions.settings") as mock_settings:
        mock_settings.SLACK_SIGNING_SECRET = secret
        result = _verify_slack_signature(body, ts, sig)

    assert result is True


# ---------------------------------------------------------------------------
# POST /slack/interactions — endpoint paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_slack_interactions_invalid_signature_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client

    with patch("app.routers.slack_interactions.settings") as mock_settings:
        mock_settings.SLACK_SIGNING_SECRET = "real_secret"
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(
                "/slack/interactions",
                data={"payload": "{}"},
                headers={
                    "x-slack-request-timestamp": "0",  # stale
                    "x-slack-signature": "v0=wrong",
                },
            )

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_slack_interactions_empty_payload_returns_ok(app_client):
    fastapi_app, mock_db, _ = app_client

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post("/slack/interactions", data={})

    assert resp.status_code == 200
    assert resp.json()["ok"] is True


@pytest.mark.asyncio
async def test_slack_interactions_no_actions_returns_ok(app_client):
    fastapi_app, mock_db, _ = app_client

    payload = {"actions": []}
    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post("/slack/interactions", data={"payload": json.dumps(payload)})

    assert resp.status_code == 200
    assert resp.json()["ok"] is True


@pytest.mark.asyncio
async def test_slack_interactions_unknown_action_returns_ok(app_client):
    fastapi_app, mock_db, _ = app_client

    payload = {"actions": [{"action_id": "unknown_action", "value": "xyz"}]}
    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post("/slack/interactions", data={"payload": json.dumps(payload)})

    assert resp.status_code == 200
    assert resp.json()["ok"] is True


@pytest.mark.asyncio
async def test_slack_interactions_event_not_found_returns_ok(app_client):
    fastapi_app, mock_db, _ = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    payload = {"actions": [{"action_id": "hitl_approve", "value": "no-such-id"}]}
    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post("/slack/interactions", data={"payload": json.dumps(payload)})

    assert resp.status_code == 200
    assert resp.json()["ok"] is True


@pytest.mark.asyncio
async def test_slack_interactions_hitl_dismiss(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    event = MagicMock()
    event.meta = json.dumps({"hitl_id": "hitl-abc", "workspace_id": str(workspace_id)})
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(event))

    payload = {"actions": [{"action_id": "hitl_dismiss", "value": "hitl-abc"}]}
    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post("/slack/interactions", data={"payload": json.dumps(payload)})

    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert event.type == "hitl_dismissed"
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_slack_interactions_hitl_approve_no_connector(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    hitl_id = str(uuid.uuid4())
    event = MagicMock()
    event.meta = json.dumps({
        "hitl_id": hitl_id,
        "workspace_id": str(workspace_id),
        "to": "contact@example.com",
        "subject": "Follow up",
        "body": "Hello!",
        "contact_id": str(uuid.uuid4()),
    })
    mock_db.execute = AsyncMock(side_effect=[
        _make_scalar_result(event),    # HITL event lookup
        _make_scalar_result(None),     # connector lookup → none
    ])

    payload = {"actions": [{"action_id": "hitl_approve", "value": hitl_id}]}
    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post("/slack/interactions", data={"payload": json.dumps(payload)})

    assert resp.status_code == 200
    assert resp.json()["error"] == "no_gmail_connector"


@pytest.mark.asyncio
async def test_slack_interactions_hitl_approve_happy_path(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    hitl_id = str(uuid.uuid4())
    event = MagicMock()
    event.meta = json.dumps({
        "hitl_id": hitl_id,
        "workspace_id": str(workspace_id),
        "to": "contact@example.com",
        "subject": "Follow up",
        "body": "Hello there!",
        "contact_id": str(uuid.uuid4()),
    })
    connector = MagicMock()
    mock_db.execute = AsyncMock(side_effect=[
        _make_scalar_result(event),
        _make_scalar_result(connector),
    ])

    payload = {"actions": [{"action_id": "hitl_approve", "value": hitl_id}]}

    with patch("app.services.gmail_client.GmailClient") as MockGmail:
        mock_gmail = AsyncMock()
        mock_gmail.send_message = AsyncMock(return_value={"id": "msg-sent"})
        MockGmail.return_value = mock_gmail
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post("/slack/interactions", data={"payload": json.dumps(payload)})

    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert event.type == "hitl_approved"
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_slack_interactions_hitl_approve_gmail_error(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    hitl_id = str(uuid.uuid4())
    event = MagicMock()
    event.meta = json.dumps({
        "hitl_id": hitl_id,
        "workspace_id": str(workspace_id),
        "to": "contact@example.com",
        "subject": "Follow up",
        "body": "Hello!",
        "contact_id": str(uuid.uuid4()),
    })
    connector = MagicMock()
    mock_db.execute = AsyncMock(side_effect=[
        _make_scalar_result(event),
        _make_scalar_result(connector),
    ])

    payload = {"actions": [{"action_id": "hitl_approve", "value": hitl_id}]}

    with patch("app.services.gmail_client.GmailClient") as MockGmail:
        mock_gmail = AsyncMock()
        mock_gmail.send_message = AsyncMock(side_effect=Exception("SMTP error"))
        MockGmail.return_value = mock_gmail
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post("/slack/interactions", data={"payload": json.dumps(payload)})

    assert resp.status_code == 200
    assert resp.json()["ok"] is False
    assert "SMTP error" in resp.json()["error"]
