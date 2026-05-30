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
# Module-level auto-fixture: bypass Slack signature verification for all
# endpoint tests except the one that specifically tests the 403 rejection path.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _auto_bypass_slack_sig(request):
    # Skip patching for unit tests that directly test _verify_slack_signature
    # and for the endpoint test that specifically validates the 403 path.
    no_patch = ("verify_signature", "invalid_signature")
    if any(s in request.node.name for s in no_patch):
        yield
    else:
        with patch("app.routers.slack_interactions._verify_slack_signature", return_value=True):
            yield


# ---------------------------------------------------------------------------
# _verify_slack_signature (pure function)
# ---------------------------------------------------------------------------


def test_verify_signature_no_signing_secret_returns_false():
    """Fail-closed: with no signing secret configured, verification must reject
    (not allow) requests, so the endpoint 403s instead of accepting forged POSTs."""
    from app.routers.slack_interactions import _verify_slack_signature

    with patch("app.routers.slack_interactions.settings") as mock_settings:
        mock_settings.SLACK_SIGNING_SECRET = ""
        result = _verify_slack_signature(b"body", "12345", "v0=whatever")

    assert result is False


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

    payload = {"actions": [{"action_id": "hitl_approve", "value": str(uuid.uuid4())}]}
    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post("/slack/interactions", data={"payload": json.dumps(payload)})

    assert resp.status_code == 200
    assert resp.json()["ok"] is True


@pytest.mark.asyncio
async def test_slack_interactions_hitl_dismiss(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    hitl_id = str(uuid.uuid4())
    event = MagicMock()
    event.meta = json.dumps({"hitl_id": hitl_id, "workspace_id": str(workspace_id)})
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(event))

    payload = {"actions": [{"action_id": "hitl_dismiss", "value": hitl_id}]}
    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post("/slack/interactions", data={"payload": json.dumps(payload)})

    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert event.type == "hitl_dismissed"
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_slack_interactions_hitl_approve_no_connector(app_client):
    """When no Gmail connector exists the endpoint still acks Slack immediately
    ({"ok": True}) and the background task marks the event as hitl_error."""
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
        _make_scalar_result(event),    # HITL event lookup (endpoint)
        _make_scalar_result(None),     # connector lookup → none (background task)
    ])

    payload = {"actions": [{"action_id": "hitl_approve", "value": hitl_id}]}
    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post("/slack/interactions", data={"payload": json.dumps(payload)})

    # Slack ack is always 200 ok — errors are handled in the background task
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    # Background task commits once (marking hitl_error)
    mock_db.commit.assert_awaited()


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

    with patch("app.routers.slack_interactions.GmailClient") as MockGmail:
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
    """When Gmail send fails the endpoint still acks Slack immediately and the
    background task marks the event as hitl_error (not hitl_approved)."""
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
        _make_scalar_result(event),    # HITL event lookup (endpoint)
        _make_scalar_result(connector),  # connector lookup (background task)
    ])

    payload = {"actions": [{"action_id": "hitl_approve", "value": hitl_id}]}

    with patch("app.routers.slack_interactions.GmailClient") as MockGmail:
        mock_gmail = AsyncMock()
        mock_gmail.send_message = AsyncMock(side_effect=Exception("SMTP error"))
        MockGmail.return_value = mock_gmail
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post("/slack/interactions", data={"payload": json.dumps(payload)})

    # Slack ack is always 200 ok — the error surfaces in the background task
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    # Background task marks the event as an error, not approved
    assert event.type == "hitl_error"
    mock_db.commit.assert_awaited()


# ---------------------------------------------------------------------------
# New behavior: response_url ack / Slack message replacement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_slack_interactions_dismiss_posts_to_response_url(app_client):
    """Dismiss should call SlackClient.ack_response_url with the payload's response_url."""
    fastapi_app, mock_db, workspace_id = app_client

    hitl_id = str(uuid.uuid4())
    event = MagicMock()
    event.meta = json.dumps({"hitl_id": hitl_id, "workspace_id": str(workspace_id)})
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(event))

    payload = {
        "actions": [{"action_id": "hitl_dismiss", "value": hitl_id}],
        "response_url": "https://hooks.slack.com/actions/fake/url",
    }

    with patch("app.routers.slack_interactions.SlackClient.ack_response_url", new_callable=AsyncMock) as mock_ack:
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post("/slack/interactions", data={"payload": json.dumps(payload)})

    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    mock_ack.assert_awaited_once()
    call_kwargs = mock_ack.await_args
    assert "https://hooks.slack.com/actions/fake/url" in call_kwargs.args
    assert "dismissed" in call_kwargs.kwargs.get("text", "") or "dismissed" in (call_kwargs.args[1] if len(call_kwargs.args) > 1 else "")


@pytest.mark.asyncio
async def test_slack_interactions_approve_posts_success_to_response_url(app_client):
    """Successful approve should replace the Slack message via response_url."""
    fastapi_app, mock_db, workspace_id = app_client

    hitl_id = str(uuid.uuid4())
    event = MagicMock()
    contact_id = str(uuid.uuid4())
    event.meta = json.dumps({
        "hitl_id": hitl_id,
        "workspace_id": str(workspace_id),
        "to": "lead@example.com",
        "subject": "Checking in",
        "body": "Hey there!",
        "contact_id": contact_id,
    })
    connector = MagicMock()
    contact = MagicMock()
    mock_db.execute = AsyncMock(side_effect=[
        _make_scalar_result(event),      # HITL lookup (endpoint)
        _make_scalar_result(connector),  # Gmail connector lookup (bg task)
        _make_scalar_result(contact),    # Contact lookup (bg task)
    ])

    payload = {
        "actions": [{"action_id": "hitl_approve", "value": hitl_id}],
        "response_url": "https://hooks.slack.com/actions/fake/url",
    }

    with patch("app.routers.slack_interactions.GmailClient") as MockGmail, \
         patch("app.routers.slack_interactions.SlackClient.ack_response_url", new_callable=AsyncMock) as mock_ack:
        mock_gmail = AsyncMock()
        mock_gmail.send_message = AsyncMock(return_value={"id": "sent-123"})
        MockGmail.return_value = mock_gmail

        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post("/slack/interactions", data={"payload": json.dumps(payload)})

    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert event.type == "hitl_approved"
    # Contact last_activity should be stamped
    assert contact.last_activity is not None
    # Slack message should be replaced with a success notice
    mock_ack.assert_awaited_once()
    ack_text = mock_ack.await_args.args[1] if len(mock_ack.await_args.args) > 1 else mock_ack.await_args.kwargs.get("text", "")
    assert "lead@example.com" in ack_text


@pytest.mark.asyncio
async def test_slack_interactions_approve_updates_contact_last_activity(app_client):
    """Approving a HITL should stamp contact.last_activity with the send date."""
    fastapi_app, mock_db, workspace_id = app_client

    hitl_id = str(uuid.uuid4())
    contact_id = str(uuid.uuid4())
    event = MagicMock()
    event.meta = json.dumps({
        "hitl_id": hitl_id,
        "workspace_id": str(workspace_id),
        "to": "cto@acme.com",
        "subject": "Q3 Follow-up",
        "body": "Just checking in.",
        "contact_id": contact_id,
    })
    connector = MagicMock()
    contact = MagicMock()
    contact.last_activity = "Never"

    mock_db.execute = AsyncMock(side_effect=[
        _make_scalar_result(event),
        _make_scalar_result(connector),
        _make_scalar_result(contact),
    ])

    payload = {"actions": [{"action_id": "hitl_approve", "value": hitl_id}]}

    with patch("app.routers.slack_interactions.GmailClient") as MockGmail, \
         patch("app.routers.slack_interactions.SlackClient.ack_response_url", new_callable=AsyncMock):
        mock_gmail = AsyncMock()
        mock_gmail.send_message = AsyncMock(return_value={"id": "ok"})
        MockGmail.return_value = mock_gmail

        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post("/slack/interactions", data={"payload": json.dumps(payload)})

    assert resp.status_code == 200
    # last_activity should have been updated away from "Never"
    assert contact.last_activity != "Never"
    assert "Email sent" in contact.last_activity


# ---------------------------------------------------------------------------
# SlackClient — new update_message and ack_response_url methods
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_slack_client_update_message_calls_chat_update():
    """SlackClient.update_message should POST to chat.update with channel+ts."""
    from app.services.slack_client import SlackClient

    connector = MagicMock()
    connector.encrypted_token = "enc_token"

    with patch("app.services.slack_client.decrypt_token", return_value="xoxp-test-token"), \
         patch("httpx.AsyncClient") as MockHTTP:
        mock_response = MagicMock()
        mock_response.json.return_value = {"ok": True, "ts": "12345.678"}
        mock_http_instance = AsyncMock()
        mock_http_instance.post = AsyncMock(return_value=mock_response)
        mock_http_instance.__aenter__ = AsyncMock(return_value=mock_http_instance)
        mock_http_instance.__aexit__ = AsyncMock(return_value=False)
        MockHTTP.return_value = mock_http_instance

        client = SlackClient(connector)
        result = await client.update_message(
            channel="C123",
            ts="12345.678",
            text="Updated text",
            blocks=[{"type": "section", "text": {"type": "mrkdwn", "text": "done"}}],
        )

    assert result["ok"] is True
    call_args = mock_http_instance.post.call_args
    assert "chat.update" in call_args.args[0]
    sent_json = call_args.kwargs["json"]
    assert sent_json["channel"] == "C123"
    assert sent_json["ts"] == "12345.678"


@pytest.mark.asyncio
async def test_slack_client_ack_response_url_posts_json():
    """SlackClient.ack_response_url should POST the text to the response_url."""
    from app.services.slack_client import SlackClient

    response_url = "https://hooks.slack.com/actions/TOKEN/12345"

    with patch("httpx.AsyncClient") as MockHTTP:
        mock_response = MagicMock()
        mock_http_instance = AsyncMock()
        mock_http_instance.post = AsyncMock(return_value=mock_response)
        mock_http_instance.__aenter__ = AsyncMock(return_value=mock_http_instance)
        mock_http_instance.__aexit__ = AsyncMock(return_value=False)
        MockHTTP.return_value = mock_http_instance

        await SlackClient.ack_response_url(response_url, text="Done!", replace_original=True)

    call_args = mock_http_instance.post.call_args
    assert call_args.args[0] == response_url
    body = call_args.kwargs["json"]
    assert body["text"] == "Done!"
    assert body["replace_original"] is True
