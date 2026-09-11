"""Tests for the escalation control-plane router (app/routers/escalation.py, R15).

Uses the shared app_client fixture (auth + DB overridden). db.execute is stubbed
per-endpoint so the router logic (403/422/upsert/queue/call-outcome) is exercised
with no real database.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient, ASGITransport


def _scalars(objs):
    r = MagicMock()
    r.scalars.return_value.all.return_value = objs
    return r


def _scalar(obj):
    r = MagicMock()
    r.scalar_one_or_none.return_value = obj
    return r


@pytest.mark.asyncio
async def test_get_controls_returns_six_stages_with_defaults(app_client):
    app, mock_db, ws = app_client
    mock_db.execute = AsyncMock(return_value=_scalars([]))  # no stored rows
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{ws}/escalation/controls")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 6
    assert {r["stage"] for r in body} == {
        "new", "contacted", "engaged", "qualified", "converted", "lost"
    }
    assert all(r["mode"] == "ask" for r in body)  # R12 fail-closed default


@pytest.mark.asyncio
async def test_controls_403_cross_workspace(app_client):
    app, mock_db, ws = app_client
    other = uuid.uuid4()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{other}/escalation/controls")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_put_control_valid(app_client):
    app, mock_db, ws = app_client
    mock_db.execute = AsyncMock(return_value=MagicMock())
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.put(
            f"/workspaces/{ws}/escalation/controls/contacted", json={"mode": "auto"}
        )
    assert resp.status_code == 200
    assert resp.json()["mode"] == "auto"
    assert resp.json()["stage"] == "contacted"
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_put_control_422_bad_mode(app_client):
    app, mock_db, ws = app_client
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.put(
            f"/workspaces/{ws}/escalation/controls/contacted", json={"mode": "yolo"}
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_put_control_422_bad_stage(app_client):
    app, mock_db, ws = app_client
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.put(
            f"/workspaces/{ws}/escalation/controls/bogus", json={"mode": "auto"}
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_autonomy_get_default_false(app_client):
    app, mock_db, ws = app_client
    mock_db.execute = AsyncMock(return_value=_scalar(None))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{ws}/escalation/autonomy")
    assert resp.status_code == 200
    assert resp.json()["autonomy_enabled"] is False


@pytest.mark.asyncio
async def test_autonomy_put_toggles_on(app_client):
    app, mock_db, ws = app_client
    mock_db.execute = AsyncMock(return_value=MagicMock())
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.put(
            f"/workspaces/{ws}/escalation/autonomy", json={"autonomy_enabled": True}
        )
    assert resp.status_code == 200
    assert resp.json()["autonomy_enabled"] is True
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_queue_marks_needs_judgment_on_escalate(app_client):
    app, mock_db, ws = app_client

    enr = MagicMock()
    enr.id = uuid.uuid4()
    enr.lead_id = uuid.uuid4()
    enr.status = "waiting"

    lead = MagicMock()
    lead.name = "Zach"
    lead.company = "Photo Booth Co"
    lead.stage = "engaged"

    decision = MagicMock()
    decision.proposed_action = "escalate"
    decision.final_action = "escalate"
    decision.mode = "auto"
    decision.sentiment = "negative"
    decision.score = 55
    decision.reason = "propose=escalate"
    decision.occurred_at = None

    # execute() sequence: waiting-enrollments, then per-enr lead + newest decision.
    mock_db.execute = AsyncMock(side_effect=[_scalars([enr]), _scalar(lead), _scalar(decision)])
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{ws}/escalation/queue")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["needs_judgment"] is True
    assert body[0]["final_action"] == "escalate"
    assert body[0]["lead_name"] == "Zach"


@pytest.mark.asyncio
async def test_call_outcome_converted_emits_and_moves(app_client):
    app, mock_db, ws = app_client
    lead_id = uuid.uuid4()

    lead = MagicMock()
    lead.name = "Zach"
    lead.stage = "engaged"
    lead.score = 40

    enrollment = MagicMock()
    enrollment.id = uuid.uuid4()
    enrollment.status = "waiting"

    # lead lookup, then live-enrollment lookup.
    mock_db.execute = AsyncMock(side_effect=[_scalar(lead), _scalar(enrollment)])

    # Real refresh stamps a PK id; emulate it so the response model validates.
    async def _refresh(obj):
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()

    mock_db.refresh = AsyncMock(side_effect=_refresh)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{ws}/escalation/leads/{lead_id}/call-outcome",
            json={"outcome": "converted", "notes": "closed on the call"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["converted_emitted"] is True
    assert body["stage"] == "converted"
    assert body["enrollment_status"] == "completed"
    assert lead.stage == "converted"
    assert enrollment.status == "completed"


@pytest.mark.asyncio
async def test_call_outcome_422_bad_outcome(app_client):
    app, mock_db, ws = app_client
    lead_id = uuid.uuid4()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{ws}/escalation/leads/{lead_id}/call-outcome",
            json={"outcome": "nope"},
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_call_outcome_404_lead_not_found(app_client):
    app, mock_db, ws = app_client
    lead_id = uuid.uuid4()
    mock_db.execute = AsyncMock(return_value=_scalar(None))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{ws}/escalation/leads/{lead_id}/call-outcome",
            json={"outcome": "callback"},
        )
    assert resp.status_code == 404
