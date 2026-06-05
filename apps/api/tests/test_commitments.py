"""Tests for the commitments router — by-external upsert (incl. the never-reopen
rule), list, patch, and the stats kept_rate aggregation math."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient, ASGITransport

from tests.conftest import _make_scalar_result, _make_scalars_result


def _fake_commitment(workspace_id: uuid.UUID, **kwargs) -> MagicMock:
    c = MagicMock()
    c.id = kwargs.get("id", uuid.uuid4())
    c.workspace_id = workspace_id
    c.external_id = kwargs.get("external_id", "session-2026-06-05#L12")
    c.title = kwargs.get("title", "Ship the ledger API")
    c.kind = kwargs.get("kind", "auto")
    c.source = kwargs.get("source", "sessions/2026-06-05.md")
    c.declared_at = kwargs.get("declared_at", datetime(2026, 6, 5, 9, 0, tzinfo=timezone.utc))
    c.due_date = kwargs.get("due_date", None)
    c.status = kwargs.get("status", "open")
    c.evidence = kwargs.get("evidence", None)
    c.scored_at = kwargs.get("scored_at", None)
    c.created_at = kwargs.get("created_at", None)
    c.updated_at = kwargs.get("updated_at", None)
    return c


def _make_agg_result(rows):
    """Mock execute() result whose .all() yields aggregation rows (.week/.declared/...)."""
    result = MagicMock()
    result.all.return_value = rows
    return result


def _week_row(week_dt: datetime, *, declared, kept, broken, dropped, open_):
    row = MagicMock()
    row.week = week_dt
    row.declared = declared
    row.kept = kept
    row.broken = broken
    row.dropped = dropped
    row.open = open_
    return row


# ---------------------------------------------------------------------------
# PUT /workspaces/{wid}/commitments/by-external/{external_id} — upsert
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upsert_commitment_creates(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))
    created = _fake_commitment(workspace_id, external_id="ext-1", title="Do the thing")

    def fake_refresh(obj):
        for attr in ("id", "workspace_id", "external_id", "title", "kind", "source",
                     "declared_at", "due_date", "status", "evidence", "scored_at"):
            if getattr(obj, attr, None) is None and hasattr(created, attr):
                setattr(obj, attr, getattr(created, attr))

    mock_db.refresh.side_effect = fake_refresh

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.put(
            f"/workspaces/{workspace_id}/commitments/by-external/ext-1",
            json={"title": "Do the thing", "declared_at": "2026-06-05T09:00:00+00:00"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] is True
    assert body["commitment"]["title"] == "Do the thing"
    mock_db.add.assert_called_once()
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_upsert_commitment_updates_existing(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    existing = _fake_commitment(workspace_id, external_id="ext-2", title="Old title", status="open")
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(existing))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.put(
            f"/workspaces/{workspace_id}/commitments/by-external/ext-2",
            json={"title": "New title", "declared_at": "2026-06-05T09:00:00+00:00"},
        )

    assert resp.status_code == 200
    assert resp.json()["created"] is False
    assert existing.title == "New title"
    mock_db.add.assert_not_called()


@pytest.mark.asyncio
async def test_upsert_commitment_never_reopens_scored(app_client):
    """CRITICAL: a re-harvest re-declares status='open', but an already-scored
    commitment (kept/broken/dropped) must keep its status/evidence/scored_at."""
    fastapi_app, mock_db, workspace_id = app_client
    scored_ts = datetime(2026, 6, 6, 12, 0, tzinfo=timezone.utc)
    existing = _fake_commitment(
        workspace_id,
        external_id="ext-3",
        status="kept",
        evidence="git:abc123",
        scored_at=scored_ts,
    )
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(existing))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        # Re-harvest: no status field (omitted) — historically would default to open.
        resp = await ac.put(
            f"/workspaces/{workspace_id}/commitments/by-external/ext-3",
            json={"title": "Ship the ledger API", "declared_at": "2026-06-05T09:00:00+00:00"},
        )

    assert resp.status_code == 200
    # Status/evidence/scored_at preserved — NOT reset to open.
    assert existing.status == "kept"
    assert existing.evidence == "git:abc123"
    assert existing.scored_at == scored_ts
    assert resp.json()["commitment"]["status"] == "kept"


@pytest.mark.asyncio
async def test_upsert_commitment_explicit_status_reopen_overrides(app_client):
    """An EXPLICIT non-open status on an open row still applies (scorer marking kept)."""
    fastapi_app, mock_db, workspace_id = app_client
    existing = _fake_commitment(workspace_id, external_id="ext-4", status="open")
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(existing))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.put(
            f"/workspaces/{workspace_id}/commitments/by-external/ext-4",
            json={
                "title": "Ship the ledger API",
                "declared_at": "2026-06-05T09:00:00+00:00",
                "status": "kept",
                "evidence": "git:def456",
            },
        )

    assert resp.status_code == 200
    assert existing.status == "kept"
    assert existing.evidence == "git:def456"


@pytest.mark.asyncio
async def test_upsert_commitment_wrong_workspace_returns_403(app_client):
    fastapi_app, _, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.put(
            f"/workspaces/{wrong_id}/commitments/by-external/ext-x",
            json={"title": "x", "declared_at": "2026-06-05T09:00:00+00:00"},
        )

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_upsert_commitment_missing_declared_at_returns_422(app_client):
    fastapi_app, _, workspace_id = app_client

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.put(
            f"/workspaces/{workspace_id}/commitments/by-external/ext-y",
            json={"title": "no declared_at"},
        )

    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/commitments — list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_commitments_returns_rows(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    c = _fake_commitment(workspace_id, title="Call Bob back")
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([c]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/commitments?status=open&kind=auto")

    assert resp.status_code == 200
    assert resp.json()[0]["title"] == "Call Bob back"


# ---------------------------------------------------------------------------
# PATCH /workspaces/{wid}/commitments/{cid}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patch_commitment_updates_fields(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    c = _fake_commitment(workspace_id, status="open")
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(c))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.patch(
            f"/workspaces/{workspace_id}/commitments/{c.id}",
            json={"status": "broken", "evidence": "no commit found", "due_date": "2026-06-10"},
        )

    assert resp.status_code == 200
    assert c.status == "broken"
    assert c.evidence == "no commit found"
    assert c.due_date == date(2026, 6, 10)
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_patch_commitment_not_found_returns_404(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.patch(
            f"/workspaces/{workspace_id}/commitments/{uuid.uuid4()}",
            json={"status": "kept"},
        )

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/commitments/stats — kept_rate math
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stats_kept_rate_math(app_client):
    """kept_rate = kept/(kept+broken); null when denominator is 0."""
    fastapi_app, mock_db, workspace_id = app_client

    # Two populated weeks: one with kept+broken outcomes, one all-open (denom 0).
    from datetime import timedelta
    today = datetime.now(timezone.utc).date()
    this_monday = today - timedelta(days=today.weekday())
    monday_dt = datetime(this_monday.year, this_monday.month, this_monday.day, tzinfo=timezone.utc)
    prev_monday_dt = monday_dt - timedelta(weeks=1)

    rows = [
        _week_row(monday_dt, declared=5, kept=3, broken=1, dropped=0, open_=1),      # 3/(3+1)=0.75
        _week_row(prev_monday_dt, declared=2, kept=0, broken=0, dropped=0, open_=2),  # denom 0 -> null
    ]
    mock_db.execute = AsyncMock(return_value=_make_agg_result(rows))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/commitments/stats?weeks=12")

    assert resp.status_code == 200
    body = resp.json()
    # Zero-filled contiguous run of 12 weeks.
    assert len(body) == 12
    by_week = {row["week_start"]: row for row in body}

    cur = by_week[this_monday.isoformat()]
    assert cur["kept"] == 3 and cur["broken"] == 1
    assert cur["kept_rate"] == 0.75

    prev = by_week[(this_monday - timedelta(weeks=1)).isoformat()]
    assert prev["open"] == 2
    assert prev["kept_rate"] is None

    # An untouched (zero-filled) earlier week.
    empty = by_week[(this_monday - timedelta(weeks=5)).isoformat()]
    assert empty["declared"] == 0
    assert empty["kept_rate"] is None


@pytest.mark.asyncio
async def test_stats_wrong_workspace_returns_403(app_client):
    fastapi_app, _, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong_id}/commitments/stats")

    assert resp.status_code == 403
