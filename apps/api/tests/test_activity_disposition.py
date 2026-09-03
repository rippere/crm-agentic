"""Tests for the call-disposition contract on create_activity (B5).

Exercises POST /workspaces/{wid}/activity, reusing the shared mocked-session
fixtures in conftest.py (same harness as test_events.py). Covers the 422 guards,
disposition persistence, and the 'dead' side effects (churn the contact + lose only
its single most-recent lead).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient, ASGITransport

from app.models.task import Task
from tests.conftest import _make_scalar_result


def fake_refresh(obj) -> None:
    """Populate the server-assigned columns a mocked session never fills (id,
    created_at) so ActivityEventResponse.model_validate(event) succeeds."""
    if getattr(obj, "id", None) is None:
        obj.id = uuid.uuid4()
    if getattr(obj, "created_at", None) is None:
        obj.created_at = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)


async def _post(app, workspace_id: uuid.UUID, body: dict):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        return await ac.post(f"/workspaces/{workspace_id}/activity", json=body)


# ---------------------------------------------------------------------------
# 422 guards
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_call_without_disposition_returns_422(app_client):
    """A call must close with a next-step disposition."""
    app, mock_db, workspace_id = app_client
    resp = await _post(
        app, workspace_id,
        {"type": "call", "agent_name": "User", "description": "Rang the venue"},
    )
    assert resp.status_code == 422
    mock_db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_call_invalid_disposition_returns_422(app_client):
    """An out-of-set disposition on a call is rejected (mirrors LEAD_STAGES)."""
    app, mock_db, workspace_id = app_client
    resp = await _post(
        app, workspace_id,
        {"type": "call", "agent_name": "User", "description": "x", "disposition": "maybe_later"},
    )
    assert resp.status_code == 422
    mock_db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_note_with_invalid_disposition_returns_422(app_client):
    """Any activity that carries a disposition must carry a valid one — even a note,
    so the DB CHECK can never be hit with a bad value (would be a 500, not a 422)."""
    app, mock_db, workspace_id = app_client
    resp = await _post(
        app, workspace_id,
        {"type": "note", "agent_name": "User", "description": "x", "disposition": "nope"},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_valid_disposition_persists_and_echoes(app_client):
    """A valid call disposition persists and round-trips in the response."""
    app, mock_db, workspace_id = app_client
    mock_db.refresh.side_effect = fake_refresh
    resp = await _post(
        app, workspace_id,
        {"type": "call", "agent_name": "User", "description": "Booked a follow-up", "disposition": "follow_up_1mo"},
    )
    assert resp.status_code == 201
    assert resp.json()["disposition"] == "follow_up_1mo"
    mock_db.commit.assert_awaited()
    # No side effects for a non-'dead' disposition -> no contact/lead lookups.
    mock_db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_note_without_disposition_still_201(app_client):
    """Non-call activities are unaffected: no disposition, still created."""
    app, mock_db, workspace_id = app_client
    mock_db.refresh.side_effect = fake_refresh
    resp = await _post(
        app, workspace_id,
        {"type": "note", "agent_name": "User", "description": "Just a note"},
    )
    assert resp.status_code == 201
    assert resp.json()["disposition"] is None
    mock_db.execute.assert_not_awaited()


# ---------------------------------------------------------------------------
# follow-up side effects — a marked Task with the right due date
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_follow_up_1mo_creates_task_due_30d(app_client):
    """follow_up_1mo -> a follow-up Task due +30d, marked disp:<activity_id>,
    linked to the contact and titled with the contact name."""
    app, mock_db, workspace_id = app_client
    contact = MagicMock(); contact.name = "Riverside Events"
    mock_db.execute = AsyncMock(side_effect=[_make_scalar_result(contact)])  # name lookup
    mock_db.refresh.side_effect = fake_refresh
    contact_id = str(uuid.uuid4())

    resp = await _post(
        app, workspace_id,
        {"type": "call", "agent_name": "User", "description": "Great chat",
         "disposition": "follow_up_1mo", "contact_id": contact_id},
    )

    assert resp.status_code == 201
    activity_id = resp.json()["id"]
    tasks = [c.args[0] for c in mock_db.add.call_args_list if isinstance(c.args[0], Task)]
    assert len(tasks) == 1
    task = tasks[0]
    assert task.due_date == date.today() + timedelta(days=30)
    assert task.external_id == f"disp:{activity_id}"  # marker points back at the activity
    assert str(task.contact_id) == contact_id
    assert task.title == "Follow up: Riverside Events"
    assert task.status == "open"
    mock_db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_follow_up_6mo_creates_task_due_180d(app_client):
    """follow_up_6mo -> a follow-up Task due +180d, same marker convention."""
    app, mock_db, workspace_id = app_client
    contact = MagicMock(); contact.name = "Lakeside Hall"
    mock_db.execute = AsyncMock(side_effect=[_make_scalar_result(contact)])
    mock_db.refresh.side_effect = fake_refresh
    contact_id = str(uuid.uuid4())

    resp = await _post(
        app, workspace_id,
        {"type": "call", "agent_name": "User", "description": "Revisit next season",
         "disposition": "follow_up_6mo", "contact_id": contact_id},
    )

    assert resp.status_code == 201
    activity_id = resp.json()["id"]
    tasks = [c.args[0] for c in mock_db.add.call_args_list if isinstance(c.args[0], Task)]
    assert len(tasks) == 1
    assert tasks[0].due_date == date.today() + timedelta(days=180)
    assert tasks[0].external_id == f"disp:{activity_id}"
    assert str(tasks[0].contact_id) == contact_id


# ---------------------------------------------------------------------------
# 'dead' side effects — churn contact + lose ONLY the most-recent lead
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dead_churns_contact_and_loses_most_recent_lead(app_client):
    app, mock_db, workspace_id = app_client
    contact = MagicMock(); contact.status = "active"
    recent_lead = MagicMock(); recent_lead.stage = "qualified"
    # execute() is called twice: contact lookup, then the ORDER BY created_at DESC
    # LIMIT 1 lead lookup (which yields only the most-recent lead).
    mock_db.execute = AsyncMock(side_effect=[
        _make_scalar_result(contact),
        _make_scalar_result(recent_lead),
    ])
    mock_db.refresh.side_effect = fake_refresh

    resp = await _post(
        app, workspace_id,
        {"type": "call", "agent_name": "User", "description": "Lost them",
         "disposition": "dead", "contact_id": str(uuid.uuid4())},
    )

    assert resp.status_code == 201
    assert contact.status == "churned"
    assert recent_lead.stage == "lost"
    mock_db.commit.assert_awaited_once()  # single atomic commit


@pytest.mark.asyncio
async def test_dead_leaves_older_lead_unchanged(app_client):
    """Only the most-recent lead is lost; an older lead is never touched because the
    query is ORDER BY created_at DESC LIMIT 1 — the DB returns only the recent one."""
    app, mock_db, workspace_id = app_client
    contact = MagicMock(); contact.status = "active"
    recent_lead = MagicMock(); recent_lead.stage = "qualified"
    older_lead = MagicMock(); older_lead.stage = "engaged"
    mock_db.execute = AsyncMock(side_effect=[
        _make_scalar_result(contact),
        _make_scalar_result(recent_lead),  # LIMIT 1 -> only the most-recent
    ])
    mock_db.refresh.side_effect = fake_refresh

    resp = await _post(
        app, workspace_id,
        {"type": "call", "agent_name": "User", "description": "Lost them",
         "disposition": "dead", "contact_id": str(uuid.uuid4())},
    )

    assert resp.status_code == 201
    assert recent_lead.stage == "lost"
    assert older_lead.stage == "engaged"  # untouched


@pytest.mark.asyncio
async def test_dead_with_no_lead_churns_contact_only(app_client):
    """A 'dead' contact with zero matching leads: churn the contact, no error."""
    app, mock_db, workspace_id = app_client
    contact = MagicMock(); contact.status = "active"
    mock_db.execute = AsyncMock(side_effect=[
        _make_scalar_result(contact),
        _make_scalar_result(None),  # no lead
    ])
    mock_db.refresh.side_effect = fake_refresh

    resp = await _post(
        app, workspace_id,
        {"type": "call", "agent_name": "User", "description": "Gone cold",
         "disposition": "dead", "contact_id": str(uuid.uuid4())},
    )

    assert resp.status_code == 201
    assert contact.status == "churned"
    mock_db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_dead_without_contact_id_skips_side_effects(app_client):
    """'dead' with no contact_id has nothing to churn — 201, no contact/lead lookups."""
    app, mock_db, workspace_id = app_client
    mock_db.refresh.side_effect = fake_refresh
    resp = await _post(
        app, workspace_id,
        {"type": "call", "agent_name": "User", "description": "No contact attached", "disposition": "dead"},
    )
    assert resp.status_code == 201
    mock_db.execute.assert_not_awaited()
