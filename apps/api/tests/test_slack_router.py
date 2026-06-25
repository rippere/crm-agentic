"""Tests for slack.py router — OAuth URL, callback, sync."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

from app.services.oauth_state import build_state
from tests.conftest import _make_scalar_result


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/connectors/slack/auth
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_slack_auth_url_returns_url(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/connectors/slack/auth")

    assert resp.status_code == 200
    assert "auth_url" in resp.json()
    assert "slack.com" in resp.json()["auth_url"]


@pytest.mark.asyncio
async def test_slack_auth_url_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong_id}/connectors/slack/auth")

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /auth/slack/callback
# ---------------------------------------------------------------------------


def _make_token_client(ok: bool = True, user_token: str = "xoxp-token", email: str = "slack@example.com") -> AsyncMock:
    """Build a mock async context manager for the token-exchange httpx call."""
    token_data = {
        "ok": ok,
        "authed_user": {"access_token": user_token, "id": "U123"},
        "team": {"id": "T456"},
    }
    if not ok:
        token_data["error"] = "invalid_code"

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=MagicMock(json=lambda: token_data))

    profile_data = {"ok": True, "user": {"profile": {"email": email}}}
    mock_client.get = AsyncMock(return_value=MagicMock(json=lambda: profile_data))

    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
    mock_cm.__aexit__ = AsyncMock(return_value=None)
    return mock_cm


@pytest.mark.asyncio
async def test_slack_callback_invalid_state_returns_400(app_client):
    fastapi_app, mock_db, _ = app_client

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get("/auth/slack/callback?code=abc&state=not-a-uuid")

    assert resp.status_code == 400
    assert "state" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_slack_callback_token_exchange_fails_returns_400(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    mock_cm = _make_token_client(ok=False)

    with patch("app.routers.slack.httpx.AsyncClient", return_value=mock_cm):
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.get(f"/auth/slack/callback?code=bad_code&state={build_state(workspace_id)}")

    assert resp.status_code == 400
    assert "token exchange" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_slack_callback_no_user_token_returns_400(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    mock_cm = _make_token_client(ok=True, user_token="")  # empty access_token

    with patch("app.routers.slack.httpx.AsyncClient", return_value=mock_cm):
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.get(f"/auth/slack/callback?code=code123&state={build_state(workspace_id)}")

    assert resp.status_code == 400
    assert "token" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_slack_callback_happy_path_new_connector(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    mock_cm = _make_token_client(ok=True, user_token="xoxp-real", email="user@slack.com")

    with patch("app.routers.slack.httpx.AsyncClient", return_value=mock_cm):
        with patch("app.routers.slack.encrypt_token", return_value="encrypted"):
            async with AsyncClient(
                transport=ASGITransport(app=fastapi_app),
                base_url="http://test",
                follow_redirects=False,
            ) as ac:
                resp = await ac.get(f"/auth/slack/callback?code=code123&state={build_state(workspace_id)}")

    assert resp.status_code in (301, 302, 307, 308)
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_slack_callback_updates_existing_connector(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    existing_connector = MagicMock()
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(existing_connector))

    mock_cm = _make_token_client(ok=True, user_token="xoxp-new", email="user@slack.com")

    with patch("app.routers.slack.httpx.AsyncClient", return_value=mock_cm):
        with patch("app.routers.slack.encrypt_token", return_value="new_encrypted"):
            async with AsyncClient(
                transport=ASGITransport(app=fastapi_app),
                base_url="http://test",
                follow_redirects=False,
            ) as ac:
                resp = await ac.get(f"/auth/slack/callback?code=code123&state={build_state(workspace_id)}")

    assert resp.status_code in (301, 302, 307, 308)
    assert existing_connector.encrypted_token == "new_encrypted"


@pytest.mark.asyncio
async def test_slack_callback_no_profile_email_uses_fallback(app_client):
    """When Slack profile lookup fails, external_email falls back to team_id:user_id."""
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    token_data = {
        "ok": True,
        "authed_user": {"access_token": "xoxp-token", "id": "U999"},
        "team": {"id": "T999"},
    }
    profile_data = {"ok": False}  # profile lookup fails → fallback email

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=MagicMock(json=lambda: token_data))
    mock_client.get = AsyncMock(return_value=MagicMock(json=lambda: profile_data))
    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
    mock_cm.__aexit__ = AsyncMock(return_value=None)

    with patch("app.routers.slack.httpx.AsyncClient", return_value=mock_cm):
        with patch("app.routers.slack.encrypt_token", return_value="enc"):
            async with AsyncClient(
                transport=ASGITransport(app=fastapi_app),
                base_url="http://test",
                follow_redirects=False,
            ) as ac:
                resp = await ac.get(f"/auth/slack/callback?code=code&state={build_state(workspace_id)}")

    assert resp.status_code in (301, 302, 307, 308)
    mock_db.commit.assert_awaited()


# ---------------------------------------------------------------------------
# POST /workspaces/{wid}/connectors/slack/sync
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_slack_sync_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(f"/workspaces/{wrong_id}/connectors/slack/sync")

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_slack_sync_no_connector_returns_404(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(f"/workspaces/{workspace_id}/connectors/slack/sync")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_slack_sync_happy_path(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    connector = MagicMock()
    connector.id = uuid.uuid4()
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(connector))

    mock_task = MagicMock()
    mock_task.id = "slack-sync-job"

    with patch("app.workers.slack_ingest.process_slack_sync") as mock_celery:
        mock_celery.delay.return_value = mock_task
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(f"/workspaces/{workspace_id}/connectors/slack/sync")

    assert resp.status_code == 200
    assert resp.json()["job_id"] == "slack-sync-job"


# ---------------------------------------------------------------------------
# POST /webhooks/slack/events — Events API webhook
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_slack_events_url_verification_challenge(app_client):
    """Slack url_verification challenge must be echoed back."""
    fastapi_app, mock_db, _ = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    payload = {"type": "url_verification", "challenge": "3eZbrw1aBm2rZgRNFdxV2595E9CY3gmdALWMmHkvFXO7tYXAYM8P"}

    with patch("app.routers.slack._verify_slack_signature", return_value=True):
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(
                "/webhooks/slack/events",
                json=payload,
            )

    assert resp.status_code == 200
    assert resp.json()["challenge"] == payload["challenge"]


@pytest.mark.asyncio
async def test_slack_events_event_callback_triggers_ingest(app_client):
    """event_callback with a known team_id enqueues a Celery sync job."""
    fastapi_app, mock_db, _ = app_client

    connector = MagicMock()
    connector.id = uuid.uuid4()
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(connector))

    mock_task = MagicMock()
    mock_task.id = "slack-event-job"

    with patch("app.routers.slack._verify_slack_signature", return_value=True):
        with patch("app.workers.slack_ingest.process_slack_sync") as mock_celery:
            mock_celery.delay.return_value = mock_task
            async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
                resp = await ac.post(
                    "/webhooks/slack/events",
                    json={
                        "type": "event_callback",
                        "team_id": "T0TESTTEAM",
                        "event": {"type": "message", "text": "hello"},
                    },
                )

    assert resp.status_code == 200
    assert resp.json()["ok"] is True


@pytest.mark.asyncio
async def test_slack_events_bad_signature_returns_401(app_client):
    """Invalid signature must be rejected with 401."""
    fastapi_app, mock_db, _ = app_client

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            "/webhooks/slack/events",
            json={"type": "url_verification", "challenge": "abc"},
            headers={
                "x-slack-request-timestamp": "1000000000",
                "x-slack-signature": "v0=invalid",
            },
        )

    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_slack_events_no_secret_configured_rejects(app_client):
    """Fail closed: with SLACK_SIGNING_SECRET unset, the events webhook rejects every
    request. (An unauthenticated event_callback would otherwise trigger a Slack sync
    for any team_id — a zero-credential amplification vector.)"""
    fastapi_app, mock_db, _ = app_client

    with patch("app.routers.slack.settings") as mock_settings:
        mock_settings.SLACK_SIGNING_SECRET = ""
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(
                "/webhooks/slack/events",
                json={"type": "event_callback", "team_id": "T0TESTTEAM", "event": {"type": "message"}},
            )

    assert resp.status_code == 401
