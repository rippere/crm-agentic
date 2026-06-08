"""Tests for gmail.py router — OAuth URL, callback, sync, list, delete."""

from __future__ import annotations

import base64
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

from app.services.oauth_state import build_state
from tests.conftest import _make_scalar_result, _make_scalars_result


def _make_state(workspace_id: uuid.UUID) -> str:
    return build_state(workspace_id)


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/connectors/gmail/auth
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gmail_auth_url_returns_google_url(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/connectors/gmail/auth")

    assert resp.status_code == 200
    assert "auth_url" in resp.json()
    assert "accounts.google.com" in resp.json()["auth_url"]


@pytest.mark.asyncio
async def test_gmail_auth_url_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong_id}/connectors/gmail/auth")

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /auth/gmail/callback
# ---------------------------------------------------------------------------


def _make_gmail_http_client(token_status: int = 200, email: str = "user@gmail.com") -> AsyncMock:
    token_resp = MagicMock()
    token_resp.status_code = token_status
    token_resp.json = lambda: {
        "access_token": "ya29.access",
        "refresh_token": "1//refresh",
        "token_type": "Bearer",
    }

    profile_resp = MagicMock()
    profile_resp.json = lambda: {"emailAddress": email}
    profile_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=token_resp)
    mock_client.get = AsyncMock(return_value=profile_resp)

    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
    mock_cm.__aexit__ = AsyncMock(return_value=None)
    return mock_cm


@pytest.mark.asyncio
async def test_gmail_callback_invalid_state_returns_400(app_client):
    fastapi_app, mock_db, _ = app_client

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get("/auth/gmail/callback?code=abc&state=not-base64-json")

    assert resp.status_code == 400
    assert "state" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_gmail_callback_token_exchange_fails_returns_400(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    mock_cm = _make_gmail_http_client(token_status=400)
    state = _make_state(workspace_id)

    with patch("app.routers.gmail.httpx.AsyncClient", return_value=mock_cm):
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.get(f"/auth/gmail/callback?code=bad&state={state}")

    assert resp.status_code == 400
    assert "Token exchange" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_gmail_callback_happy_path_new_connector(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    mock_cm = _make_gmail_http_client(token_status=200, email="user@gmail.com")
    state = _make_state(workspace_id)

    with patch("app.routers.gmail.httpx.AsyncClient", return_value=mock_cm):
        with patch("app.routers.gmail.encrypt_token", return_value="encrypted"):
            async with AsyncClient(
                transport=ASGITransport(app=fastapi_app),
                base_url="http://test",
                follow_redirects=False,
            ) as ac:
                resp = await ac.get(f"/auth/gmail/callback?code=code&state={state}")

    assert resp.status_code in (301, 302, 307, 308)
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_gmail_callback_updates_existing_connector(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    existing = MagicMock()
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(existing))

    mock_cm = _make_gmail_http_client(token_status=200, email="user@gmail.com")
    state = _make_state(workspace_id)

    with patch("app.routers.gmail.httpx.AsyncClient", return_value=mock_cm):
        with patch("app.routers.gmail.encrypt_token", return_value="new_encrypted"):
            async with AsyncClient(
                transport=ASGITransport(app=fastapi_app),
                base_url="http://test",
                follow_redirects=False,
            ) as ac:
                resp = await ac.get(f"/auth/gmail/callback?code=code&state={state}")

    assert resp.status_code in (301, 302, 307, 308)
    assert existing.encrypted_token == "new_encrypted"


# ---------------------------------------------------------------------------
# POST /workspaces/{wid}/connectors/gmail/sync
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gmail_sync_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(f"/workspaces/{wrong_id}/connectors/gmail/sync")

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_gmail_sync_no_connector_returns_404(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(f"/workspaces/{workspace_id}/connectors/gmail/sync")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_gmail_sync_happy_path(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    connector = MagicMock()
    connector.id = uuid.uuid4()
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(connector))

    mock_task = MagicMock()
    mock_task.id = "gmail-sync-job"

    with patch("app.workers.ingest.process_gmail_sync") as mock_celery:
        mock_celery.delay.return_value = mock_task
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(f"/workspaces/{workspace_id}/connectors/gmail/sync")

    assert resp.status_code == 200
    assert resp.json()["job_id"] == "gmail-sync-job"


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/connectors
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_connectors_empty(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/connectors")

    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_connectors_returns_data(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    connector = MagicMock()
    connector.id = uuid.uuid4()
    connector.service = "gmail"
    connector.last_sync = None
    connector.message_count = 42
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([connector]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/connectors")

    assert resp.status_code == 200
    assert resp.json()[0]["service"] == "gmail"
    assert resp.json()[0]["message_count"] == 42


@pytest.mark.asyncio
async def test_list_connectors_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong_id}/connectors")

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# DELETE /workspaces/{wid}/connectors/{cid}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_connector_returns_204(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    connector = MagicMock()
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(connector))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.delete(f"/workspaces/{workspace_id}/connectors/{uuid.uuid4()}")

    assert resp.status_code == 204
    mock_db.delete.assert_awaited_with(connector)
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_delete_connector_not_found_returns_404(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.delete(f"/workspaces/{workspace_id}/connectors/{uuid.uuid4()}")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_connector_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.delete(f"/workspaces/{wrong_id}/connectors/{uuid.uuid4()}")

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /workspaces/{wid}/connectors/gmail/subscribe
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gmail_subscribe_no_topic_returns_503(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    with patch("app.routers.gmail.settings") as mock_settings:
        mock_settings.GMAIL_PUBSUB_TOPIC = ""
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(f"/workspaces/{workspace_id}/connectors/gmail/subscribe")

    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_gmail_subscribe_no_connector_returns_404(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    with patch("app.routers.gmail.settings") as mock_settings:
        mock_settings.GMAIL_PUBSUB_TOPIC = "projects/test/topics/gmail"
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(f"/workspaces/{workspace_id}/connectors/gmail/subscribe")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_gmail_subscribe_happy_path(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    connector = MagicMock()
    connector.id = uuid.uuid4()
    connector.encrypted_token = "encrypted"
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(connector))

    watch_resp = MagicMock()
    watch_resp.status_code = 200
    watch_resp.json = lambda: {"historyId": "12345", "expiration": "9999999999000"}

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=watch_resp)
    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
    mock_cm.__aexit__ = AsyncMock(return_value=None)

    with patch("app.routers.gmail.settings") as mock_settings:
        mock_settings.GMAIL_PUBSUB_TOPIC = "projects/test/topics/gmail"
        with patch("app.routers.gmail.decrypt_token", return_value="access_token"):
            with patch("app.routers.gmail.httpx.AsyncClient", return_value=mock_cm):
                async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
                    resp = await ac.post(f"/workspaces/{workspace_id}/connectors/gmail/subscribe")

    assert resp.status_code == 200
    data = resp.json()
    assert data["history_id"] == "12345"
    assert "expiration" in data


@pytest.mark.asyncio
async def test_gmail_subscribe_watch_fails_returns_502(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    connector = MagicMock()
    connector.id = uuid.uuid4()
    connector.encrypted_token = "encrypted"
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(connector))

    watch_resp = MagicMock()
    watch_resp.status_code = 403
    watch_resp.text = "Forbidden"

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=watch_resp)
    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
    mock_cm.__aexit__ = AsyncMock(return_value=None)

    with patch("app.routers.gmail.settings") as mock_settings:
        mock_settings.GMAIL_PUBSUB_TOPIC = "projects/test/topics/gmail"
        with patch("app.routers.gmail.decrypt_token", return_value="access_token"):
            with patch("app.routers.gmail.httpx.AsyncClient", return_value=mock_cm):
                async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
                    resp = await ac.post(f"/workspaces/{workspace_id}/connectors/gmail/subscribe")

    assert resp.status_code == 502


# ---------------------------------------------------------------------------
# POST /webhooks/gmail/push
# ---------------------------------------------------------------------------


def _make_pubsub_body(email: str = "user@gmail.com", history_id: str = "12345") -> dict:
    payload = json.dumps({"emailAddress": email, "historyId": history_id})
    encoded = base64.urlsafe_b64encode(payload.encode()).decode()
    return {
        "message": {"data": encoded, "messageId": "abc", "publishTime": "2026-01-01T00:00:00Z"},
        "subscription": "projects/test/subscriptions/gmail-sub",
    }


@pytest.mark.asyncio
async def test_gmail_push_invalid_secret_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client

    with patch("app.routers.gmail.settings") as mock_settings:
        mock_settings.GMAIL_WEBHOOK_SECRET = "real-secret"
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(
                "/webhooks/gmail/push?secret=wrong-secret",
                json=_make_pubsub_body(),
            )

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_gmail_push_no_secret_configured_rejects(app_client):
    """Fail closed: when GMAIL_WEBHOOK_SECRET is empty we cannot authenticate the
    push, so every request is rejected (an unauthenticated push would otherwise
    force a Gmail sync for any connector)."""
    fastapi_app, mock_db, _ = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    with patch("app.routers.gmail.settings") as mock_settings:
        mock_settings.GMAIL_WEBHOOK_SECRET = ""
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post("/webhooks/gmail/push", json=_make_pubsub_body())

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_gmail_push_malformed_body_returns_204(app_client):
    """Malformed Pub/Sub body should return 204 (not retry)."""
    fastapi_app, mock_db, _ = app_client

    with patch("app.routers.gmail.settings") as mock_settings:
        mock_settings.GMAIL_WEBHOOK_SECRET = "real-secret"
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post("/webhooks/gmail/push?secret=real-secret", json={"not": "a-pubsub-message"})

    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_gmail_push_no_connector_still_returns_204(app_client):
    """If no connector matches the email, we still return 204 (not retry)."""
    fastapi_app, mock_db, _ = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    with patch("app.routers.gmail.settings") as mock_settings:
        mock_settings.GMAIL_WEBHOOK_SECRET = "real-secret"
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post("/webhooks/gmail/push?secret=real-secret", json=_make_pubsub_body("unknown@example.com"))

    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_gmail_push_triggers_ingest(app_client):
    """Happy path: matching connector found → ingest task enqueued."""
    fastapi_app, mock_db, _ = app_client
    connector = MagicMock()
    connector.id = uuid.uuid4()
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(connector))

    mock_task = MagicMock()
    mock_task.id = "push-job-id"

    with patch("app.routers.gmail.settings") as mock_settings:
        mock_settings.GMAIL_WEBHOOK_SECRET = "real-secret"
        with patch("app.workers.ingest.process_gmail_sync") as mock_celery:
            mock_celery.delay.return_value = mock_task
            async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
                resp = await ac.post(
                    "/webhooks/gmail/push?secret=real-secret",
                    json=_make_pubsub_body("user@gmail.com"),
                )

    assert resp.status_code == 204
