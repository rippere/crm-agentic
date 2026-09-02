"""Tests for the outreach router — HITL approval queue + inbound engagement webhook.

Mirrors the style of tests/test_deals.py: mocked async session via app_client,
_make_scalar_result / _make_scalars_result helpers, ASGITransport client.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

from tests.conftest import _make_scalar_result, _make_scalars_result

_SECRET = "test-engagement-secret"


def _fake_enrollment(workspace_id: uuid.UUID, **kwargs) -> MagicMock:
    enr = MagicMock()
    enr.id = kwargs.get("id", uuid.uuid4())
    enr.workspace_id = workspace_id
    enr.campaign_id = kwargs.get("campaign_id", uuid.uuid4())
    enr.sequence_id = kwargs.get("sequence_id", uuid.uuid4())
    enr.lead_id = kwargs.get("lead_id", uuid.uuid4())
    enr.current_step = kwargs.get("current_step", 0)
    enr.status = kwargs.get("status", "waiting")
    enr.next_run_at = kwargs.get("next_run_at", None)
    return enr


def _fake_step(workspace_id: uuid.UUID, **kwargs) -> MagicMock:
    step = MagicMock()
    step.id = kwargs.get("id", uuid.uuid4())
    step.workspace_id = workspace_id
    step.sequence_id = kwargs.get("sequence_id", uuid.uuid4())
    step.step_order = kwargs.get("step_order", 0)
    step.channel = kwargs.get("channel", "email")
    step.subject = kwargs.get("subject", "Hi {{name}}")
    step.body_template = kwargs.get("body_template", "Hello {{name}} at {{company}}")
    step.requires_approval = kwargs.get("requires_approval", True)
    step.ai_generate = kwargs.get("ai_generate", False)
    return step


def _fake_lead(workspace_id: uuid.UUID, **kwargs) -> MagicMock:
    lead = MagicMock()
    lead.id = kwargs.get("id", uuid.uuid4())
    lead.workspace_id = workspace_id
    lead.name = kwargs.get("name", "Zach")
    lead.email = kwargs.get("email", "zach@photobooth.com")
    lead.company = kwargs.get("company", "PhotoBooth Co")
    lead.title = kwargs.get("title", "Owner")
    return lead


def _sign(body: bytes) -> str:
    return "sha256=" + hmac.new(_SECRET.encode(), body, hashlib.sha256).hexdigest()


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/outreach/pending
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pending_returns_empty(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/outreach/pending")

    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_pending_returns_rendered_draft(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    enr = _fake_enrollment(workspace_id, current_step=0)
    step = _fake_step(workspace_id, sequence_id=enr.sequence_id, step_order=0)
    lead = _fake_lead(workspace_id, name="Zach", company="PhotoBooth Co")

    call_count = 0

    async def _execute_side_effect(q):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _make_scalars_result([enr])  # waiting enrollments
        if call_count == 2:
            return _make_scalar_result(step)  # current step
        return _make_scalar_result(lead)  # lead

    mock_db.execute = AsyncMock(side_effect=_execute_side_effect)

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/outreach/pending")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["enrollment_id"] == str(enr.id)
    assert data[0]["body"] == "Hello Zach at PhotoBooth Co"
    assert data[0]["subject"] == "Hi {{name}}"


@pytest.mark.asyncio
async def test_pending_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong_id}/outreach/pending")

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /workspaces/{wid}/outreach/{enrollment_id}/draft
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_draft_renders_template(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    enr = _fake_enrollment(workspace_id, current_step=0)
    step = _fake_step(workspace_id, sequence_id=enr.sequence_id, step_order=0, ai_generate=False)
    lead = _fake_lead(workspace_id, name="Zach", company="PhotoBooth Co")

    call_count = 0

    async def _execute_side_effect(q):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _make_scalar_result(enr)  # enrollment
        if call_count == 2:
            return _make_scalar_result(step)  # step
        return _make_scalar_result(lead)  # lead

    mock_db.execute = AsyncMock(side_effect=_execute_side_effect)

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(f"/workspaces/{workspace_id}/outreach/{enr.id}/draft")

    assert resp.status_code == 200
    data = resp.json()
    assert data["body"] == "Hello Zach at PhotoBooth Co"
    assert data["ai_generated"] is False


@pytest.mark.asyncio
async def test_draft_not_found_returns_404(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    with patch("app.routers.outreach.get_row", new=AsyncMock(return_value=None)):
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(f"/workspaces/{workspace_id}/outreach/{uuid.uuid4()}/draft")

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /workspaces/{wid}/outreach/{enrollment_id}/approve  (key domain action)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_approve_returns_202_and_writes_approved_event(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    enr = _fake_enrollment(workspace_id, status="waiting")
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(enr))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{workspace_id}/outreach/{enr.id}/approve",
            json={"subject": "Edited subject", "body": "Edited body"},
        )

    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "approved"
    assert data["enrollment_id"] == str(enr.id)
    # enrollment flipped send-ready + engagement_event(type='approved') written
    assert enr.status == "active"
    mock_db.commit.assert_awaited()

    from app.models.engagement_event import EngagementEvent
    added = [c.args[0] for c in mock_db.add.call_args_list]
    assert any(isinstance(o, EngagementEvent) and o.type == "approved" for o in added)


@pytest.mark.asyncio
async def test_approve_not_found_returns_404(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    with patch("app.routers.outreach.get_row", new=AsyncMock(return_value=None)):
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(f"/workspaces/{workspace_id}/outreach/{uuid.uuid4()}/approve", json={})

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_approve_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(f"/workspaces/{wrong_id}/outreach/{uuid.uuid4()}/approve", json={})

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /workspaces/{wid}/outreach/{enrollment_id}/reject
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reject_stops_enrollment_and_writes_event(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    enr = _fake_enrollment(workspace_id, status="waiting")
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(enr))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{workspace_id}/outreach/{enr.id}/reject",
            json={"reason": "off-brand"},
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"
    assert enr.status == "stopped"

    from app.models.engagement_event import EngagementEvent
    added = [c.args[0] for c in mock_db.add.call_args_list]
    assert any(isinstance(o, EngagementEvent) and o.type == "rejected" for o in added)


# ---------------------------------------------------------------------------
# POST /workspaces/{wid}/webhooks/engagement  (HMAC-verified, no auth)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_webhook_appends_engagement_event(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    lead_id = uuid.uuid4()
    payload = {"lead_id": str(lead_id), "type": "opened", "channel": "email"}
    body = json.dumps(payload).encode()

    with patch("app.routers.outreach._engagement_secret", return_value=_SECRET):
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(
                f"/workspaces/{workspace_id}/webhooks/engagement",
                content=body,
                headers={"X-Engagement-Signature": _sign(body), "content-type": "application/json"},
            )

    assert resp.status_code == 202
    assert resp.json()["status"] == "accepted"
    assert resp.json()["type"] == "opened"

    from app.models.engagement_event import EngagementEvent
    added = [c.args[0] for c in mock_db.add.call_args_list]
    ev = next((o for o in added if isinstance(o, EngagementEvent)), None)
    assert ev is not None
    assert ev.type == "opened"
    assert ev.weight == 5
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_webhook_bad_type_returns_422(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    payload = {"lead_id": str(uuid.uuid4()), "type": "not_a_real_type"}
    body = json.dumps(payload).encode()

    with patch("app.routers.outreach._engagement_secret", return_value=_SECRET):
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(
                f"/workspaces/{workspace_id}/webhooks/engagement",
                content=body,
                headers={"X-Engagement-Signature": _sign(body), "content-type": "application/json"},
            )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_webhook_invalid_signature_returns_401(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    payload = {"lead_id": str(uuid.uuid4()), "type": "opened"}
    body = json.dumps(payload).encode()

    with patch("app.routers.outreach._engagement_secret", return_value=_SECRET):
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(
                f"/workspaces/{workspace_id}/webhooks/engagement",
                content=body,
                headers={"X-Engagement-Signature": "sha256=deadbeef", "content-type": "application/json"},
            )

    assert resp.status_code == 401
