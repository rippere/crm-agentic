"""Tests for the Outlook / Microsoft 365 connector — mirrors test_gmail_router.py.

Covers the outlook.py router (OAuth URL, callback, not-configured 503, sync), the
OutlookClient (401 refresh, refresh-token rotation, reauth errors, sendMail,
pagination), the Outlook ingest path through the SAME capped _run_sync pipeline
Gmail uses, and the Outlook branch of every outbound send path. All HTTP is
mocked — no Microsoft, no DB, no Anthropic.
"""

from __future__ import annotations

import json
import uuid
from urllib.parse import parse_qs, urlparse
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from httpx import AsyncClient, ASGITransport

from app.services.oauth_state import build_state
from tests.conftest import _make_scalar_result


@pytest.fixture
def ms_configured(monkeypatch):
    monkeypatch.setattr("app.config.settings.MICROSOFT_CLIENT_ID", "test-ms-client-id")
    monkeypatch.setattr("app.config.settings.MICROSOFT_CLIENT_SECRET", "test-ms-client-secret")


@pytest.fixture
def ms_unconfigured(monkeypatch):
    monkeypatch.setattr("app.config.settings.MICROSOFT_CLIENT_ID", "")
    monkeypatch.setattr("app.config.settings.MICROSOFT_CLIENT_SECRET", "")


def _http_cm(client: AsyncMock) -> AsyncMock:
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=client)
    cm.__aexit__ = AsyncMock(return_value=None)
    return cm


def _resp(status_code: int = 200, payload: dict | None = None, url: str = "https://graph.microsoft.com/v1.0/x") -> httpx.Response:
    """A real httpx.Response so raise_for_status behaves like production."""
    return httpx.Response(
        status_code,
        json=payload if payload is not None else {},
        request=httpx.Request("GET", url),
    )


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/connectors/outlook/auth
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_outlook_auth_url_returns_microsoft_url(app_client, ms_configured):
    fastapi_app, mock_db, workspace_id = app_client

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/connectors/outlook/auth")

    assert resp.status_code == 200
    auth_url = resp.json()["auth_url"]
    parsed = urlparse(auth_url)
    assert parsed.netloc == "login.microsoftonline.com"
    assert parsed.path == "/common/oauth2/v2.0/authorize"
    q = parse_qs(parsed.query)
    assert q["client_id"] == ["test-ms-client-id"]
    assert q["response_type"] == ["code"]
    assert q["redirect_uri"] == ["http://localhost:8000/auth/outlook/callback"]
    scopes = q["scope"][0].split()
    for scope in ("offline_access", "openid", "email", "User.Read", "Mail.Read", "Mail.Send"):
        assert scope in scopes
    # The state is the signed, workspace-bound state shared with Gmail/Slack.
    from app.services.oauth_state import verify_state

    assert verify_state(q["state"][0]) == workspace_id


@pytest.mark.asyncio
async def test_outlook_auth_url_wrong_workspace_returns_403(app_client, ms_configured):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong_id}/connectors/outlook/auth")

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_outlook_auth_url_not_configured_returns_503(app_client, ms_unconfigured):
    fastapi_app, mock_db, workspace_id = app_client

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/connectors/outlook/auth")

    assert resp.status_code == 503
    assert resp.json()["detail"] == "Outlook connector not configured"


@pytest.mark.asyncio
async def test_outlook_auth_url_secret_missing_returns_503(app_client, monkeypatch):
    """A client id alone is not enough — the code exchange needs the secret."""
    fastapi_app, mock_db, workspace_id = app_client
    monkeypatch.setattr("app.config.settings.MICROSOFT_CLIENT_ID", "id-only")
    monkeypatch.setattr("app.config.settings.MICROSOFT_CLIENT_SECRET", "")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/connectors/outlook/auth")

    assert resp.status_code == 503


# ---------------------------------------------------------------------------
# GET /auth/outlook/callback
# ---------------------------------------------------------------------------


def _make_ms_http_client(
    token_status: int = 200,
    profile: dict | None = None,
    refresh_token: str | None = "M.refresh",
) -> tuple[AsyncMock, AsyncMock]:
    token_payload = {"access_token": "eyJ.access", "token_type": "Bearer", "expires_in": 3600}
    if refresh_token:
        token_payload["refresh_token"] = refresh_token
    token_resp = MagicMock()
    token_resp.status_code = token_status
    token_resp.json = lambda: token_payload

    profile_resp = MagicMock()
    profile_resp.json = lambda: profile if profile is not None else {"mail": "mike@betson.com"}
    profile_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=token_resp)
    mock_client.get = AsyncMock(return_value=profile_resp)
    return _http_cm(mock_client), mock_client


@pytest.mark.asyncio
async def test_outlook_callback_invalid_state_returns_400(app_client, ms_configured):
    fastapi_app, mock_db, _ = app_client

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get("/auth/outlook/callback?code=abc&state=not-base64-json")

    assert resp.status_code == 400
    assert "state" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_outlook_callback_tampered_state_returns_400(app_client, ms_configured):
    fastapi_app, mock_db, workspace_id = app_client
    payload, sig = build_state(workspace_id).split(".", 1)
    forged = f"{payload}.{'A' * len(sig)}"

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/auth/outlook/callback?code=abc&state={forged}")

    assert resp.status_code == 400
    mock_db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_outlook_callback_user_denied_redirects_to_connectors(app_client, ms_configured):
    """Microsoft sends ?error=access_denied (no code) when the user cancels."""
    fastapi_app, mock_db, _ = app_client

    async with AsyncClient(
        transport=ASGITransport(app=fastapi_app), base_url="http://test", follow_redirects=False
    ) as ac:
        resp = await ac.get("/auth/outlook/callback?error=access_denied&error_description=cancelled")

    assert resp.status_code in (301, 302, 307, 308)
    assert resp.headers["location"].endswith("/connectors?error=outlook_oauth_denied")
    mock_db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_outlook_callback_missing_code_returns_400(app_client, ms_configured):
    fastapi_app, mock_db, workspace_id = app_client

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/auth/outlook/callback?state={build_state(workspace_id)}")

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_outlook_callback_not_configured_returns_503(app_client, ms_unconfigured):
    fastapi_app, mock_db, workspace_id = app_client

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/auth/outlook/callback?code=abc&state={build_state(workspace_id)}")

    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_outlook_callback_token_exchange_fails_returns_400(app_client, ms_configured):
    fastapi_app, mock_db, workspace_id = app_client

    mock_cm, _ = _make_ms_http_client(token_status=400)
    state = build_state(workspace_id)

    with patch("app.routers.outlook.httpx.AsyncClient", return_value=mock_cm):
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.get(f"/auth/outlook/callback?code=bad&state={state}")

    assert resp.status_code == 400
    assert "Token exchange" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_outlook_callback_happy_path_new_connector(app_client, ms_configured):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    mock_cm, mock_client = _make_ms_http_client(profile={"mail": "mike@betson.com"})
    state = build_state(workspace_id)

    with patch("app.routers.outlook.httpx.AsyncClient", return_value=mock_cm):
        with patch("app.routers.outlook.encrypt_token", side_effect=lambda t: f"enc:{t}"):
            async with AsyncClient(
                transport=ASGITransport(app=fastapi_app),
                base_url="http://test",
                follow_redirects=False,
            ) as ac:
                resp = await ac.get(f"/auth/outlook/callback?code=code&state={state}")

    assert resp.status_code in (301, 302, 307, 308)
    assert resp.headers["location"].endswith("/connectors?connected=outlook")

    # Token exchange hit the v2 common token endpoint with the Outlook redirect URI.
    token_call = mock_client.post.await_args
    assert token_call.args[0] == "https://login.microsoftonline.com/common/oauth2/v2.0/token"
    data = token_call.kwargs["data"]
    assert data["grant_type"] == "authorization_code"
    assert data["client_secret"] == "test-ms-client-secret"
    assert data["redirect_uri"] == "http://localhost:8000/auth/outlook/callback"
    # Identity came from Graph /me.
    assert mock_client.get.await_args.args[0] == "https://graph.microsoft.com/v1.0/me"

    from app.models.connector import Connector

    added = [c.args[0] for c in mock_db.add.call_args_list if isinstance(c.args[0], Connector)]
    assert len(added) == 1
    connector = added[0]
    assert connector.service == "outlook"
    assert connector.workspace_id == workspace_id
    assert connector.external_email == "mike@betson.com"
    assert connector.encrypted_token == "enc:eyJ.access"
    assert connector.refresh_token == "enc:M.refresh"
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_outlook_callback_falls_back_to_user_principal_name(app_client, ms_configured):
    """`mail` is null for some personal / unlicensed accounts."""
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    mock_cm, _ = _make_ms_http_client(profile={"mail": None, "userPrincipalName": "ben@outlook.com"})

    with patch("app.routers.outlook.httpx.AsyncClient", return_value=mock_cm):
        with patch("app.routers.outlook.encrypt_token", return_value="encrypted"):
            async with AsyncClient(
                transport=ASGITransport(app=fastapi_app), base_url="http://test", follow_redirects=False
            ) as ac:
                resp = await ac.get(f"/auth/outlook/callback?code=code&state={build_state(workspace_id)}")

    assert resp.status_code in (301, 302, 307, 308)
    from app.models.connector import Connector

    added = [c.args[0] for c in mock_db.add.call_args_list if isinstance(c.args[0], Connector)]
    assert added[0].external_email == "ben@outlook.com"


@pytest.mark.asyncio
async def test_outlook_callback_updates_existing_connector(app_client, ms_configured):
    fastapi_app, mock_db, workspace_id = app_client
    existing = MagicMock()
    existing.refresh_token = "old-refresh"
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(existing))

    mock_cm, _ = _make_ms_http_client()

    with patch("app.routers.outlook.httpx.AsyncClient", return_value=mock_cm):
        with patch("app.routers.outlook.encrypt_token", return_value="new_encrypted"):
            async with AsyncClient(
                transport=ASGITransport(app=fastapi_app), base_url="http://test", follow_redirects=False
            ) as ac:
                resp = await ac.get(f"/auth/outlook/callback?code=code&state={build_state(workspace_id)}")

    assert resp.status_code in (301, 302, 307, 308)
    assert existing.encrypted_token == "new_encrypted"
    assert existing.refresh_token == "new_encrypted"


# ---------------------------------------------------------------------------
# POST /workspaces/{wid}/connectors/outlook/sync
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_outlook_sync_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(f"/workspaces/{wrong_id}/connectors/outlook/sync")

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_outlook_sync_no_connector_returns_404(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(f"/workspaces/{workspace_id}/connectors/outlook/sync")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_outlook_sync_happy_path(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    connector = MagicMock()
    connector.id = uuid.uuid4()
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(connector))

    mock_task = MagicMock()
    mock_task.id = "outlook-sync-job"

    with patch("app.workers.ingest.process_outlook_sync") as mock_celery:
        mock_celery.delay.return_value = mock_task
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(f"/workspaces/{workspace_id}/connectors/outlook/sync")

    assert resp.status_code == 200
    assert resp.json()["job_id"] == "outlook-sync-job"
    mock_celery.delay.assert_called_once_with(str(connector.id))


def test_outlook_sync_task_is_registered():
    from app.workers.celery_app import celery_app

    assert "app.workers.ingest.process_outlook_sync" in celery_app.tasks


# ---------------------------------------------------------------------------
# OutlookClient — refresh, rotation, reauth, send, list
# ---------------------------------------------------------------------------


def _client_connector() -> MagicMock:
    connector = MagicMock()
    connector.encrypted_token = "enc-access"
    connector.refresh_token = "enc-refresh"
    return connector


def _outlook_client(connector: MagicMock, db: AsyncMock | None = None):
    from app.services.outlook_client import OutlookClient

    db = db or AsyncMock()
    db.add = MagicMock()
    return OutlookClient(connector, db, "cid", "csecret"), db


@pytest.mark.asyncio
async def test_outlook_client_refresh_persists_rotated_refresh_token():
    """Microsoft returns a NEW refresh token on every refresh — it must be stored,
    or the connector dies once the original one ages out."""
    connector = _client_connector()
    client, db = _outlook_client(connector)

    http = AsyncMock()
    http.post = AsyncMock(return_value=_resp(200, {
        "access_token": "new-access", "refresh_token": "rotated-refresh", "expires_in": 3600,
    }))

    with patch("app.services.outlook_client.httpx.AsyncClient", return_value=_http_cm(http)), \
         patch("app.services.outlook_client.decrypt_token", return_value="plain-refresh"), \
         patch("app.services.outlook_client.encrypt_token", side_effect=lambda t: f"enc:{t}"):
        token = await client._refresh_access_token()

    assert token == "new-access"
    assert connector.encrypted_token == "enc:new-access"
    assert connector.refresh_token == "enc:rotated-refresh"
    data = http.post.await_args.kwargs["data"]
    assert http.post.await_args.args[0] == "https://login.microsoftonline.com/common/oauth2/v2.0/token"
    assert data["grant_type"] == "refresh_token"
    assert data["refresh_token"] == "plain-refresh"
    assert "offline_access" in data["scope"]
    db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_outlook_client_refresh_keeps_old_refresh_token_if_none_returned():
    connector = _client_connector()
    client, _ = _outlook_client(connector)

    http = AsyncMock()
    http.post = AsyncMock(return_value=_resp(200, {"access_token": "new-access"}))

    with patch("app.services.outlook_client.httpx.AsyncClient", return_value=_http_cm(http)), \
         patch("app.services.outlook_client.decrypt_token", return_value="plain-refresh"), \
         patch("app.services.outlook_client.encrypt_token", side_effect=lambda t: f"enc:{t}"):
        await client._refresh_access_token()

    assert connector.refresh_token == "enc-refresh"


@pytest.mark.asyncio
@pytest.mark.parametrize("error_code", ["invalid_grant", "interaction_required"])
async def test_outlook_client_refresh_reauth_errors_raise_reauth_required(error_code):
    from app.services.outlook_client import OutlookReauthRequired

    client, _ = _outlook_client(_client_connector())
    http = AsyncMock()
    http.post = AsyncMock(return_value=_resp(400, {"error": error_code}))

    with patch("app.services.outlook_client.httpx.AsyncClient", return_value=_http_cm(http)), \
         patch("app.services.outlook_client.decrypt_token", return_value="plain-refresh"):
        with pytest.raises(OutlookReauthRequired) as exc_info:
            await client._refresh_access_token()

    assert exc_info.value.code == error_code


@pytest.mark.asyncio
async def test_outlook_client_refresh_config_error_is_not_reauth():
    """invalid_client (bad MICROSOFT_CLIENT_SECRET) is a server bug, not a reconnect:
    it surfaces as an HTTP error (logged), never as OutlookReauthRequired."""
    client, _ = _outlook_client(_client_connector())
    http = AsyncMock()
    http.post = AsyncMock(return_value=_resp(401, {"error": "invalid_client"}))

    with patch("app.services.outlook_client.httpx.AsyncClient", return_value=_http_cm(http)), \
         patch("app.services.outlook_client.decrypt_token", return_value="plain-refresh"):
        with pytest.raises(httpx.HTTPStatusError):
            await client._refresh_access_token()


@pytest.mark.asyncio
async def test_outlook_client_no_refresh_token_raises_reauth():
    from app.services.outlook_client import OutlookReauthRequired

    connector = _client_connector()
    connector.refresh_token = None
    client, _ = _outlook_client(connector)

    with pytest.raises(OutlookReauthRequired) as exc_info:
        await client._refresh_access_token()
    assert exc_info.value.code == "no_refresh_token"


@pytest.mark.asyncio
async def test_outlook_client_401_triggers_refresh_and_retry():
    client, _ = _outlook_client(_client_connector())

    http = AsyncMock()
    http.request = AsyncMock(side_effect=[
        _resp(401, {"error": {"code": "InvalidAuthenticationToken"}}),
        _resp(200, {"mail": "mike@betson.com"}),
    ])

    with patch("app.services.outlook_client.httpx.AsyncClient", return_value=_http_cm(http)), \
         patch("app.services.outlook_client.decrypt_token", return_value="stale-access"), \
         patch.object(client, "_refresh_access_token", AsyncMock(return_value="fresh-access")) as refresh:
        profile = await client.get_profile()

    assert profile == {"mail": "mike@betson.com"}
    refresh.assert_awaited_once()
    first, second = http.request.await_args_list
    assert first.kwargs["headers"]["Authorization"] == "Bearer stale-access"
    assert second.kwargs["headers"]["Authorization"] == "Bearer fresh-access"


@pytest.mark.asyncio
async def test_outlook_client_send_message_posts_sendmail():
    client, _ = _outlook_client(_client_connector())

    http = AsyncMock()
    # Graph answers sendMail with 202 Accepted and an empty body.
    http.request = AsyncMock(return_value=httpx.Response(
        202, request=httpx.Request("POST", "https://graph.microsoft.com/v1.0/me/sendMail")
    ))

    with patch("app.services.outlook_client.httpx.AsyncClient", return_value=_http_cm(http)), \
         patch("app.services.outlook_client.decrypt_token", return_value="access"):
        result = await client.send_message(to="lead@acme.com", subject="Hello", body="Hi there")

    method, url = http.request.await_args.args
    assert method == "POST"
    assert url == "https://graph.microsoft.com/v1.0/me/sendMail"
    payload = http.request.await_args.kwargs["json"]
    assert payload["message"]["subject"] == "Hello"
    assert payload["message"]["body"] == {"contentType": "Text", "content": "Hi there"}
    assert payload["message"]["toRecipients"] == [{"emailAddress": {"address": "lead@acme.com"}}]
    assert payload["saveToSentItems"] is True
    assert result["id"] is None and result["status"] == "accepted"


@pytest.mark.asyncio
async def test_outlook_client_list_messages_params_and_next_link():
    from datetime import datetime, timezone

    client, _ = _outlook_client(_client_connector())
    http = AsyncMock()
    http.request = AsyncMock(return_value=_resp(200, {"value": []}))
    next_link = "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages?$skip=100"

    with patch("app.services.outlook_client.httpx.AsyncClient", return_value=_http_cm(http)), \
         patch("app.services.outlook_client.decrypt_token", return_value="access"):
        await client.list_messages(
            folder="sentitems", top=100, since=datetime(2026, 8, 29, tzinfo=timezone.utc)
        )
        await client.list_messages(next_link=next_link)

    first, second = http.request.await_args_list
    assert first.args[1] == "https://graph.microsoft.com/v1.0/me/mailFolders/sentitems/messages"
    params = first.kwargs["params"]
    assert params["$top"] == 100
    assert params["$orderby"] == "receivedDateTime desc"
    assert params["$filter"] == "receivedDateTime ge 2026-08-29T00:00:00Z"
    assert 'outlook.body-content-type="text"' in first.kwargs["headers"]["Prefer"]
    assert 'IdType="ImmutableId"' in first.kwargs["headers"]["Prefer"]
    # nextLink is followed verbatim — it already encodes filter/order/page size.
    assert second.args[1] == next_link
    assert "params" not in second.kwargs


# ---------------------------------------------------------------------------
# Outlook ingest — same capped _run_sync pipeline as Gmail
# ---------------------------------------------------------------------------

WS = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
CONNECTOR_ID = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")


def _graph_message(
    msg_id: str,
    *,
    sender: str,
    to: str = "mike@betson.com",
    cc: str | None = None,
    received: str = "2026-09-20T09:00:00Z",
    body: str = "Following up on the quote.",
) -> dict:
    msg = {
        "id": msg_id,
        "conversationId": f"conv-{msg_id}",
        "internetMessageId": f"<{msg_id}@betson.com>",
        "internetMessageHeaders": [{"name": "In-Reply-To", "value": "<parent@betson.com>"}],
        "subject": "Quote for Q4",
        "from": {"emailAddress": {"name": "Sender Name", "address": sender}},
        "toRecipients": [{"emailAddress": {"name": "To Name", "address": to}}],
        "ccRecipients": [],
        "receivedDateTime": received,
        "sentDateTime": received,
        "bodyPreview": body[:40],
        "body": {"contentType": "text", "content": body},
    }
    if cc:
        msg["ccRecipients"] = [{"emailAddress": {"name": "", "address": cc}}]
    return msg


def _ingest_db() -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()

    connector = MagicMock()
    connector.id = CONNECTOR_ID
    connector.workspace_id = WS
    connector.service = "outlook"
    connector.message_count = 0

    def _execute(stmt, *a, **kw):
        result = MagicMock()
        text = str(stmt)
        result.scalar_one_or_none.return_value = connector if "FROM connectors" in text else None
        result.scalars.return_value.all.return_value = []
        return result

    db.execute = AsyncMock(side_effect=_execute)
    return db


def _session_factory(db: AsyncMock):
    factory = MagicMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=db)
    ctx.__aexit__ = AsyncMock(return_value=False)
    factory.return_value = ctx
    return factory


def _folder_pages(folders: dict[str, list[list[dict]]]):
    """list_messages stub serving `folders[folder]` as successive pages linked by
    fake @odata.nextLink values."""
    def _list(folder="inbox", top=100, since=None, next_link=None):
        if next_link:
            folder, idx = next_link.split("|")
            idx = int(idx)
        else:
            idx = 0
        pages = folders.get(folder, [])
        page = {"value": pages[idx] if idx < len(pages) else []}
        if idx + 1 < len(pages):
            page["@odata.nextLink"] = f"{folder}|{idx + 1}"
        return page

    return AsyncMock(side_effect=_list)


async def _run_outlook(folders: dict[str, list[list[dict]]], relevance, db: AsyncMock):
    outlook = MagicMock()
    outlook.list_messages = _folder_pages(folders)
    relevance_mock = AsyncMock(side_effect=relevance)

    with patch("app.workers.ingest._get_async_session", return_value=_session_factory(db)), \
         patch("app.services.outlook_client.OutlookClient", return_value=outlook), \
         patch("app.services.gmail_client.GmailClient", side_effect=AssertionError("Gmail used for Outlook")), \
         patch("app.workers.ingest._is_deal_relevant_async", relevance_mock), \
         patch("app.workers.ingest.enrich_message") as enrich:
        enrich.delay = MagicMock()
        from app.workers.ingest import _run_sync

        result = await _run_sync(str(CONNECTOR_ID))
    return result, outlook, relevance_mock, enrich


def _stored(db: AsyncMock) -> list:
    from app.models.message import Message

    return [c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], Message)]


@pytest.mark.asyncio
async def test_outlook_ingest_stores_inbox_and_sent_with_headers():
    db = _ingest_db()
    inbound = _graph_message("in-1", sender="lead@acme.com", cc="boss@acme.com")
    outbound = _graph_message(
        "out-1", sender="mike@betson.com", to="lead@acme.com", received="2026-09-21T09:00:00Z"
    )

    result, outlook, _, enrich = await _run_outlook(
        {"inbox": [[inbound]], "sentitems": [[outbound]]}, [True, True], db
    )

    stored = {m.external_id: m for m in _stored(db)}
    assert set(stored) == {"in-1", "out-1"}
    assert stored["in-1"].direction == "inbound"
    assert stored["out-1"].direction == "outbound"
    assert stored["in-1"].sender_email == "Sender Name <lead@acme.com>"
    assert stored["in-1"].to_emails == ["mike@betson.com"]
    assert stored["in-1"].cc_emails == ["boss@acme.com"]
    assert stored["in-1"].thread_id == "conv-in-1"
    assert stored["in-1"].rfc_message_id == "<in-1@betson.com>"
    assert stored["in-1"].in_reply_to == "<parent@betson.com>"
    assert stored["in-1"].body_plain == "Following up on the quote."
    assert stored["in-1"].connector_id == CONNECTOR_ID
    assert result["new_messages"] == 2
    assert enrich.delay.call_count == 2
    # Recency window is applied (INGEST_SINCE_DAYS), to both folders.
    folders_called = [c.kwargs["folder"] for c in outlook.list_messages.await_args_list]
    assert folders_called == ["inbox", "sentitems"]
    assert all(c.kwargs["since"] is not None for c in outlook.list_messages.await_args_list)


@pytest.mark.asyncio
async def test_outlook_ingest_respects_hard_message_cap(monkeypatch):
    """The guard that stopped the Gmail token-cost runaway applies to Outlook too:
    with INGEST_MAX_MESSAGES=3 and 16 messages across both folders, the shared
    budget lists exactly three (Inbox ceil(3/2)=2, Sent the remaining 1), so three
    are stored and relevance-checked, and truncated is set."""
    monkeypatch.setattr("app.config.settings.INGEST_MAX_MESSAGES", 3)
    db = _ingest_db()

    inbox = [
        _graph_message(f"in-{i}", sender=f"lead{i}@acme.com", received=f"2026-09-{10 + i:02d}T09:00:00Z")
        for i in range(8)
    ]
    sent = [
        _graph_message(f"out-{i}", sender="mike@betson.com", to=f"lead{i}@acme.com",
                       received=f"2026-09-{10 + i:02d}T12:00:00Z")
        for i in range(8)
    ]
    # Newest first, as Graph returns them ($orderby=receivedDateTime desc).
    inbox.reverse()
    sent.reverse()

    result, _, relevance_mock, _ = await _run_outlook(
        {"inbox": [inbox[:4], inbox[4:]], "sentitems": [sent[:4], sent[4:]]}, [True] * 16, db
    )

    stored = _stored(db)
    assert len(stored) == 3, "must persist no more than the hard message cap"
    assert relevance_mock.await_count == 3, "at most cap-many Claude relevance calls"
    assert result["truncated"] is True
    assert [m.external_id for m in stored] == ["out-7", "in-7", "in-6"], "newest per folder share, merged newest-first"


@pytest.mark.asyncio
async def test_outlook_ingest_shared_budget_gives_unused_inbox_share_to_sent(monkeypatch):
    """One budget across both folders: a sparse Inbox leaves its unused share to
    Sent Items, and the total listed never exceeds INGEST_MAX_MESSAGES."""
    monkeypatch.setattr("app.config.settings.INGEST_MAX_MESSAGES", 4)
    db = _ingest_db()
    inbox = [_graph_message("in-0", sender="lead@acme.com", received="2026-09-25T09:00:00Z")]
    sent = [
        _graph_message(f"out-{i}", sender="mike@betson.com", to=f"lead{i}@acme.com",
                       received=f"2026-09-{20 - i:02d}T12:00:00Z")
        for i in range(10)
    ]

    result, _, relevance_mock, _ = await _run_outlook(
        {"inbox": [inbox], "sentitems": [sent]}, [True] * 10, db
    )

    stored = [m.external_id for m in _stored(db)]
    assert stored == ["in-0", "out-0", "out-1", "out-2"]
    assert relevance_mock.await_count == 4
    assert result["truncated"] is True


@pytest.mark.asyncio
async def test_outlook_ingest_respects_page_cap(monkeypatch):
    monkeypatch.setattr("app.workers.ingest._MAX_INGEST_PAGES", 2)
    db = _ingest_db()
    pages = [[_graph_message(f"p{p}-{i}", sender=f"x{p}{i}@acme.com")] for p in range(5) for i in range(1)]

    result, outlook, _, _ = await _run_outlook({"inbox": pages, "sentitems": []}, [True] * 5, db)

    inbox_calls = [c for c in outlook.list_messages.await_args_list
                   if c.kwargs.get("folder") == "inbox" or (c.kwargs.get("next_link") or "").startswith("inbox")]
    assert len(inbox_calls) == 2, "page walk stops at the page cap"
    assert len(_stored(db)) == 2
    assert result["truncated"] is True


@pytest.mark.asyncio
async def test_outlook_ingest_llm_budget_caps_enrich_fanout(monkeypatch):
    """INGEST_MAX_LLM_CALLS bounds relevance + 3×enrich for Outlook exactly as for
    Gmail: budget 5 with 4 relevant messages -> 4 relevance calls, 0 enrich (1//3)."""
    monkeypatch.setattr("app.config.settings.INGEST_MAX_LLM_CALLS", 5)
    db = _ingest_db()
    msgs = [_graph_message(f"m{i}", sender=f"lead{i}@acme.com") for i in range(4)]

    result, _, relevance_mock, enrich = await _run_outlook(
        {"inbox": [msgs], "sentitems": []}, [True] * 4, db
    )

    assert relevance_mock.await_count == 4
    assert enrich.delay.call_count == 0
    assert result["truncated"] is True


@pytest.mark.asyncio
async def test_outlook_ingest_skips_automated_and_irrelevant_is_metadata_only():
    db = _ingest_db()
    msgs = [
        _graph_message("bot", sender="noreply@microsoft.com"),
        _graph_message("keep", sender="jane@acme.com"),
        _graph_message("meta", sender="friend@example.com"),
    ]

    result, _, relevance_mock, enrich = await _run_outlook(
        {"inbox": [msgs], "sentitems": []}, [True, False], db
    )

    stored = {m.external_id: m for m in _stored(db)}
    assert "bot" not in stored
    assert result["skipped_automated"] == 1
    assert stored["meta"].graph_only is True and stored["meta"].body_plain == ""
    assert stored["keep"].graph_only is False
    assert relevance_mock.await_count == 2
    assert enrich.delay.call_count == 1


@pytest.mark.asyncio
async def test_outlook_ingest_dedupes_already_ingested():
    db = _ingest_db()
    connector_result = db.execute.side_effect

    def _execute(stmt, *a, **kw):
        result = connector_result(stmt, *a, **kw)
        if "FROM messages" in str(stmt):
            result.scalar_one_or_none.return_value = MagicMock()  # already stored
        return result

    db.execute = AsyncMock(side_effect=_execute)
    msgs = [_graph_message("old", sender="lead@acme.com")]

    result, _, relevance_mock, _ = await _run_outlook({"inbox": [msgs], "sentitems": []}, [True], db)

    assert _stored(db) == []
    assert relevance_mock.await_count == 0
    assert result["new_messages"] == 0


def test_graph_body_text_strips_html_fallback():
    from app.workers.ingest import _graph_body_text

    html_body = {"contentType": "html", "content": "<html><style>p{}</style><p>Hi &amp; bye</p></html>"}
    assert _graph_body_text(html_body) == "Hi & bye"
    assert _graph_body_text({"contentType": "text", "content": "plain"}) == "plain"
    assert _graph_body_text(None) == ""


# ---------------------------------------------------------------------------
# Outbound send paths use Outlook when the workspace mailbox is Outlook
# ---------------------------------------------------------------------------


def _outlook_connector(workspace_id: uuid.UUID) -> MagicMock:
    connector = MagicMock()
    connector.id = uuid.uuid4()
    connector.workspace_id = workspace_id
    connector.service = "outlook"
    connector.external_email = "mike@betson.com"
    return connector


@pytest.mark.asyncio
async def test_send_email_uses_outlook_when_connected(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(_outlook_connector(workspace_id)))

    outlook = AsyncMock()
    outlook.send_message = AsyncMock(return_value={"id": None, "status": "accepted"})

    with patch("app.services.outlook_client.OutlookClient", return_value=outlook), \
         patch("app.services.gmail_client.GmailClient", side_effect=AssertionError("Gmail used for Outlook")):
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(
                f"/workspaces/{workspace_id}/contacts/{uuid.uuid4()}/send-email",
                json={"to": "lead@acme.com", "subject": "Hello", "body": "Hi there"},
            )

    assert resp.status_code == 200
    assert resp.json()["status"] == "sent"
    outlook.send_message.assert_awaited_once_with(to="lead@acme.com", subject="Hello", body="Hi there")


@pytest.mark.asyncio
async def test_send_email_outlook_reauth_returns_409(app_client):
    from app.services.outlook_client import OutlookReauthRequired

    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(_outlook_connector(workspace_id)))

    outlook = AsyncMock()
    outlook.send_message = AsyncMock(side_effect=OutlookReauthRequired("expired", code="invalid_grant"))

    with patch("app.services.outlook_client.OutlookClient", return_value=outlook):
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(
                f"/workspaces/{workspace_id}/contacts/{uuid.uuid4()}/send-email",
                json={"to": "lead@acme.com", "subject": "Hello", "body": "Hi"},
            )

    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "outlook_reauth_required"


@pytest.mark.asyncio
async def test_send_email_outlook_error_returns_502(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(_outlook_connector(workspace_id)))

    outlook = AsyncMock()
    outlook.send_message = AsyncMock(side_effect=Exception("ErrorAccessDenied"))

    with patch("app.services.outlook_client.OutlookClient", return_value=outlook):
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(
                f"/workspaces/{workspace_id}/contacts/{uuid.uuid4()}/send-email",
                json={"to": "lead@acme.com", "subject": "Hello", "body": "Hi"},
            )

    assert resp.status_code == 502
    assert "Outlook error" in resp.json()["detail"]


def test_sequence_deliver_uses_outlook_when_connected():
    import asyncio

    import app.workers.sequence_sender as mod

    db = AsyncMock()
    res = MagicMock()
    res.scalar_one_or_none.return_value = _outlook_connector(WS)
    db.execute = AsyncMock(return_value=res)
    step = MagicMock()
    step.channel = "email"
    lead = MagicMock()
    lead.email = "lead@acme.com"

    outlook = AsyncMock()
    outlook.send_message = AsyncMock(return_value={"id": None, "status": "accepted"})

    with patch("app.services.outlook_client.OutlookClient", return_value=outlook), \
         patch("app.services.gmail_client.GmailClient", side_effect=AssertionError("Gmail used for Outlook")):
        out = asyncio.run(mod._deliver(db, WS, step, lead, "Subj", "Body"))

    assert out["delivered"] is True
    outlook.send_message.assert_awaited_once_with(to="lead@acme.com", subject="Subj", body="Body")


@pytest.mark.asyncio
async def test_slack_hitl_approve_sends_via_outlook(app_client):
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
    mock_db.execute = AsyncMock(side_effect=[
        _make_scalar_result(event),
        _make_scalar_result(_outlook_connector(workspace_id)),
    ])

    outlook = AsyncMock()
    outlook.send_message = AsyncMock(return_value={"id": None, "threadId": None, "status": "accepted"})
    payload = {"actions": [{"action_id": "hitl_approve", "value": hitl_id}]}

    with patch("app.services.outlook_client.OutlookClient", return_value=outlook), \
         patch("app.routers.slack_interactions._verify_slack_signature", return_value=True), \
         patch("app.routers.slack_interactions.GmailClient", side_effect=AssertionError("Gmail used for Outlook")):
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post("/slack/interactions", data={"payload": json.dumps(payload)})

    assert resp.status_code == 200
    assert event.type == "hitl_approved"
    outlook.send_message.assert_awaited_once()
