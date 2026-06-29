"""Tests for the events router — activity list and create."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

from tests.conftest import _make_scalar_result, _make_scalars_result


def _fake_event(workspace_id: uuid.UUID, **kwargs) -> MagicMock:
    ev = MagicMock()
    ev.id = uuid.uuid4()
    ev.workspace_id = workspace_id
    ev.type = kwargs.get("type", "email_sent")
    ev.agent_name = kwargs.get("agent_name", "Gmail")
    ev.description = kwargs.get("description", "Email sent to contact")
    ev.meta = kwargs.get("meta", "")
    ev.severity = kwargs.get("severity", "info")
    ev.created_at = kwargs.get("created_at", datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc))
    return ev


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/activity — list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_activity_empty(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/activity")

    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_activity_returns_events(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    ev = _fake_event(workspace_id, description="Deal moved to proposal")
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([ev]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/activity")

    assert resp.status_code == 200
    assert resp.json()[0]["description"] == "Deal moved to proposal"


@pytest.mark.asyncio
async def test_list_activity_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong_id}/activity")

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /workspaces/{wid}/activity — create
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_activity_returns_201(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    ev = _fake_event(workspace_id, type="note", agent_name="User", description="Logged a call")

    def fake_refresh(obj):
        for attr in ("id", "workspace_id", "type", "agent_name", "description", "meta", "severity", "created_at"):
            setattr(obj, attr, getattr(ev, attr))

    mock_db.refresh.side_effect = fake_refresh

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{workspace_id}/activity",
            json={"type": "note", "agent_name": "User", "description": "Logged a call"},
        )

    assert resp.status_code == 201
    assert resp.json()["description"] == "Logged a call"
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_create_activity_missing_fields_returns_422(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(f"/workspaces/{workspace_id}/activity", json={"type": "note"})

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_activity_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{wrong_id}/activity",
            json={"type": "note", "agent_name": "User", "description": "test"},
        )

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/events — SSE stream (auth guard only; generator at ceiling)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stream_events_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong_id}/events")

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/activity with type filter + offset
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_activity_type_filter_passes_query_param(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    from app.models.activity_event import ActivityEvent
    import uuid as _uuid
    from datetime import datetime, timezone
    ev = MagicMock(spec=ActivityEvent)
    ev.id = _uuid.uuid4()
    ev.workspace_id = workspace_id
    ev.type = "contact_created"
    ev.agent_name = "System"
    ev.description = "New contact"
    ev.meta = ""
    ev.severity = "info"
    ev.created_at = datetime.now(timezone.utc)
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([ev]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(
            f"/workspaces/{workspace_id}/activity?event_type=contact_created&limit=10"
        )

    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["type"] == "contact_created"


# ---------------------------------------------------------------------------
# SSE generator (stream_events) — error handling: rollback + log + bounded break
# ---------------------------------------------------------------------------
#
# These drive the closure generator directly (not via AsyncClient) because the
# real handler sleeps 3s/poll and loops until disconnect; we patch the module's
# asyncio.sleep to a no-op and script request.is_disconnected() to bound the loop.


def _disconnect_after(n_polls: int):
    """is_disconnected() returns False for n_polls connection checks, then True.

    The generator yields ': connected' then checks is_disconnected() at the top of
    every loop iteration, so n_polls=2 allows two poll attempts before teardown.
    """
    calls = {"i": 0}

    async def _is_disconnected() -> bool:
        calls["i"] += 1
        return calls["i"] > n_polls

    return _is_disconnected


async def _drain(streaming_response) -> list[str]:
    return [
        chunk.decode() if isinstance(chunk, (bytes, bytearray)) else chunk
        async for chunk in streaming_response.body_iterator
    ]


@pytest.mark.asyncio
async def test_stream_events_poll_failure_rolls_back_and_heartbeats(workspace_id):
    """A failing poll rolls the session back (so a poisoned txn can't wedge every
    subsequent poll) and emits a heartbeat instead of silently swallowing."""
    from app.routers import events as events_mod

    user = MagicMock()
    user.workspace_id = workspace_id

    request = MagicMock()
    request.is_disconnected = _disconnect_after(1)  # one poll, then disconnect

    mock_db = AsyncMock()
    # Seed cursor query (scalar_one_or_none) returns None; first poll raises.
    mock_db.execute = AsyncMock(side_effect=[_make_scalar_result(None), RuntimeError("conn reset")])
    mock_db.rollback = AsyncMock()

    with patch.object(events_mod.asyncio, "sleep", new=AsyncMock(return_value=None)):
        resp = await events_mod.stream_events(workspace_id, request, db=mock_db, current_user=user)
        chunks = await _drain(resp)

    mock_db.rollback.assert_awaited_once()
    assert ": connected\n\n" in chunks
    assert ": heartbeat\n\n" in chunks
    # Did NOT abort — only one failure, below the ceiling.
    assert not any("stream-error" in c for c in chunks)


@pytest.mark.asyncio
async def test_stream_events_aborts_after_max_consecutive_errors(workspace_id):
    """After _MAX_CONSECUTIVE_ERRORS consecutive poll failures the generator breaks
    out instead of looping forever heartbeating on a wedged session."""
    from app.routers import events as events_mod

    user = MagicMock()
    user.workspace_id = workspace_id

    # Never disconnect on our own — the break MUST come from the error ceiling.
    request = MagicMock()
    request.is_disconnected = AsyncMock(return_value=False)

    n = events_mod._MAX_CONSECUTIVE_ERRORS
    side_effects = [_make_scalar_result(None)] + [RuntimeError("boom")] * (n + 3)
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=side_effects)
    mock_db.rollback = AsyncMock()

    with patch.object(events_mod.asyncio, "sleep", new=AsyncMock(return_value=None)):
        resp = await events_mod.stream_events(workspace_id, request, db=mock_db, current_user=user)
        chunks = await _drain(resp)

    # Aborted exactly at the ceiling: one rollback per failed poll, no infinite loop.
    assert any("stream-error" in c for c in chunks)
    assert mock_db.rollback.await_count == n
    # n-1 heartbeats before the final abort chunk.
    assert chunks.count(": heartbeat\n\n") == n - 1


@pytest.mark.asyncio
async def test_stream_events_success_resets_error_counter(workspace_id):
    """A successful poll after failures resets the consecutive-error counter, so the
    stream is not torn down by intermittent (non-consecutive) blips."""
    from app.routers import events as events_mod

    user = MagicMock()
    user.workspace_id = workspace_id

    request = MagicMock()
    request.is_disconnected = _disconnect_after(2)  # two polls, then disconnect

    ev = _fake_event(workspace_id, description="recovered")
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=[
        _make_scalar_result(None),          # seed cursor
        RuntimeError("transient"),          # poll 1 fails
        _make_scalars_result([ev]),         # poll 2 succeeds
    ])
    mock_db.rollback = AsyncMock()

    with patch.object(events_mod.asyncio, "sleep", new=AsyncMock(return_value=None)):
        resp = await events_mod.stream_events(workspace_id, request, db=mock_db, current_user=user)
        chunks = await _drain(resp)

    mock_db.rollback.assert_awaited_once()  # only the one failed poll rolled back
    assert ": heartbeat\n\n" in chunks
    assert any("recovered" in c for c in chunks)  # the successful poll's event streamed
    assert not any("stream-error" in c for c in chunks)


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/activity/trends — Phase 13a
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_activity_trends_returns_weekly_buckets(app_client):
    """Returns 12 weekly buckets with category counts."""
    fastapi_app, mock_db, workspace_id = app_client
    from datetime import date as date_cls, timedelta

    # Place events explicitly inside the current Mon–Sun calendar week so the
    # test is robust regardless of which day of the week it runs on.
    today = datetime.now(timezone.utc).date()
    this_monday = today - timedelta(days=today.weekday())
    week_open = datetime(this_monday.year, this_monday.month, this_monday.day, 0, 0, tzinfo=timezone.utc)
    ev1 = _fake_event(workspace_id, type="deal_moved", created_at=week_open + timedelta(hours=1))
    ev2 = _fake_event(workspace_id, type="contact_created", created_at=week_open + timedelta(hours=2))

    mock_db.execute = AsyncMock(return_value=_make_scalars_result([ev1, ev2]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/activity/trends?weeks=12")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 12
    # Most-recent bucket (last entry) should have both events
    last = data[-1]
    assert last["deals"] == 1
    assert last["contacts"] == 1
    assert last["total"] == 2
    assert "week_start" in last


@pytest.mark.asyncio
async def test_activity_trends_wrong_workspace_returns_403(app_client):
    """Returns 403 when requesting another workspace's activity trends."""
    fastapi_app, mock_db, workspace_id = app_client
    wrong_id = uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong_id}/activity/trends")
    assert resp.status_code == 403
