"""Tests for the segments router — CRUD + static/dynamic members + auth checks."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

from tests.conftest import _make_scalar_result, _make_scalars_result

_NOW = datetime(2026, 5, 15, 12, 0, 0, tzinfo=timezone.utc)


def _fake_segment(workspace_id: uuid.UUID, **kwargs) -> MagicMock:
    seg = MagicMock()
    seg.id = kwargs.get("id", uuid.uuid4())
    seg.workspace_id = workspace_id
    seg.name = kwargs.get("name", "Hot Leads")
    seg.description = kwargs.get("description", None)
    seg.kind = kwargs.get("kind", "static")
    seg.filter = kwargs.get("filter", {})
    seg.member_count = kwargs.get("member_count", 0)
    seg.created_at = kwargs.get("created_at", _NOW - timedelta(days=1))
    seg.updated_at = kwargs.get("updated_at", _NOW - timedelta(days=1))
    return seg


def _fake_lead(workspace_id: uuid.UUID, **kwargs) -> MagicMock:
    lead = MagicMock()
    lead.id = kwargs.get("id", uuid.uuid4())
    lead.workspace_id = workspace_id
    lead.contact_id = kwargs.get("contact_id", None)
    lead.name = kwargs.get("name", "Jane Prospect")
    lead.email = kwargs.get("email", "jane@example.com")
    lead.phone = kwargs.get("phone", None)
    lead.company = kwargs.get("company", "Acme")
    lead.title = kwargs.get("title", None)
    lead.source = kwargs.get("source", "import")
    lead.stage = kwargs.get("stage", "new")
    lead.score = kwargs.get("score", 0)
    lead.owner_id = kwargs.get("owner_id", None)
    lead.created_at = kwargs.get("created_at", _NOW - timedelta(days=2))
    return lead


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/segments — list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_segments_returns_empty(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/segments")

    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_segments_returns_segments(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    seg = _fake_segment(workspace_id, name="Warm Buyers", member_count=7)
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([seg]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/segments")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "Warm Buyers"
    assert data[0]["member_count"] == 7


@pytest.mark.asyncio
async def test_list_segments_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong_id}/segments")

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_segments_bad_kind_returns_422(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/segments?kind=bogus")

    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /workspaces/{wid}/segments — create
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_segment_returns_201(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    seg = _fake_segment(workspace_id, name="New Segment", kind="dynamic", filter={"stage": "engaged"})

    def fake_refresh(obj):
        for attr in ("id", "workspace_id", "name", "description", "kind", "filter",
                     "member_count", "created_at", "updated_at"):
            setattr(obj, attr, getattr(seg, attr))

    mock_db.refresh.side_effect = fake_refresh

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{workspace_id}/segments",
            json={"name": "New Segment", "kind": "dynamic", "filter": {"stage": "engaged"}},
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["kind"] == "dynamic"
    assert data["filter"] == {"stage": "engaged"}
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_create_segment_bad_kind_returns_422(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{workspace_id}/segments",
            json={"name": "X", "kind": "not_a_kind"},
        )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_segment_empty_name_returns_422(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{workspace_id}/segments",
            json={"name": "   ", "kind": "static"},
        )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_segment_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(f"/workspaces/{wrong_id}/segments", json={"name": "X"})

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/segments/{id} — detail
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_segment_returns_segment(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    seg = _fake_segment(workspace_id, name="Detail Segment")
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(seg))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/segments/{seg.id}")

    assert resp.status_code == 200
    assert resp.json()["name"] == "Detail Segment"


@pytest.mark.asyncio
async def test_get_segment_not_found_returns_404(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    # ORM miss falls through to the Supabase REST fallback before 404; stub it out.
    with patch("app.routers.segments.get_row", new=AsyncMock(return_value=None)):
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.get(f"/workspaces/{workspace_id}/segments/{uuid.uuid4()}")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_segment_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong_id}/segments/{uuid.uuid4()}")

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# PATCH /workspaces/{wid}/segments/{id} — update
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patch_segment_updates_fields(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    seg = _fake_segment(workspace_id, name="Old Name")
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(seg))
    mock_db.refresh.side_effect = lambda obj: None

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.patch(
            f"/workspaces/{workspace_id}/segments/{seg.id}",
            json={"name": "New Name", "filter": {"min_score": 50}},
        )

    assert resp.status_code == 200
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_patch_segment_bad_kind_returns_422(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.patch(
            f"/workspaces/{workspace_id}/segments/{uuid.uuid4()}",
            json={"kind": "invalid"},
        )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_patch_segment_not_found_returns_404(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.patch(
            f"/workspaces/{workspace_id}/segments/{uuid.uuid4()}",
            json={"name": "x"},
        )

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /workspaces/{wid}/segments/{id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_segment_returns_204(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    seg = _fake_segment(workspace_id)
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(seg))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.delete(f"/workspaces/{workspace_id}/segments/{seg.id}")

    assert resp.status_code == 204
    mock_db.delete.assert_awaited_with(seg)
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_delete_segment_not_found_returns_404(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.delete(f"/workspaces/{workspace_id}/segments/{uuid.uuid4()}")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_segment_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.delete(f"/workspaces/{wrong_id}/segments/{uuid.uuid4()}")

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/segments/{id}/members — resolved leads
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_members_static_join(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    seg = _fake_segment(workspace_id, kind="static")
    lead = _fake_lead(workspace_id, name="Static Member")

    call_count = 0

    async def _execute_side_effect(q):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _make_scalar_result(seg)          # segment lookup
        return _make_scalars_result([lead])          # join → leads

    mock_db.execute = AsyncMock(side_effect=_execute_side_effect)

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/segments/{seg.id}/members")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "Static Member"


@pytest.mark.asyncio
async def test_list_members_dynamic_filter_eval(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    seg = _fake_segment(workspace_id, kind="dynamic", filter={"stage": "engaged", "min_score": 40})
    lead = _fake_lead(workspace_id, name="Dynamic Member", stage="engaged", score=55)

    call_count = 0

    async def _execute_side_effect(q):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _make_scalar_result(seg)
        return _make_scalars_result([lead])

    mock_db.execute = AsyncMock(side_effect=_execute_side_effect)

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/segments/{seg.id}/members")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["stage"] == "engaged"


@pytest.mark.asyncio
async def test_list_members_segment_not_found_returns_404(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/segments/{uuid.uuid4()}/members")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_members_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong_id}/segments/{uuid.uuid4()}/members")

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /workspaces/{wid}/segments/{id}/members — add + recompute
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_members_recomputes_count(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    seg = _fake_segment(workspace_id, kind="static", member_count=0)
    lead_a = uuid.uuid4()
    lead_b = uuid.uuid4()

    call_count = 0

    async def _execute_side_effect(q):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _make_scalar_result(seg)               # segment lookup
        if call_count == 2:
            return _make_scalars_result([lead_a, lead_b])  # valid lead ids
        return _make_scalars_result([])                    # existing members

    mock_db.execute = AsyncMock(side_effect=_execute_side_effect)

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{workspace_id}/segments/{seg.id}/members",
            json={"lead_ids": [str(lead_a), str(lead_b)]},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["added"] == 2
    assert data["member_count"] == 2
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_add_members_empty_returns_422(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{workspace_id}/segments/{uuid.uuid4()}/members",
            json={"lead_ids": []},
        )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_add_members_dynamic_segment_returns_422(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    seg = _fake_segment(workspace_id, kind="dynamic")
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(seg))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{workspace_id}/segments/{seg.id}/members",
            json={"lead_ids": [str(uuid.uuid4())]},
        )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_add_members_segment_not_found_returns_404(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{workspace_id}/segments/{uuid.uuid4()}/members",
            json={"lead_ids": [str(uuid.uuid4())]},
        )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_add_members_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{wrong_id}/segments/{uuid.uuid4()}/members",
            json={"lead_ids": [str(uuid.uuid4())]},
        )

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# DELETE /workspaces/{wid}/segments/{id}/members/{lead_id} — remove
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_remove_member_returns_204(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    seg = _fake_segment(workspace_id, kind="static", member_count=3)
    member = MagicMock()
    lead_id = uuid.uuid4()

    call_count = 0

    async def _execute_side_effect(q):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _make_scalar_result(seg)      # segment lookup
        if call_count == 2:
            return _make_scalar_result(member)   # member lookup
        result = MagicMock()
        result.scalar.return_value = 3           # pre-delete count
        return result

    mock_db.execute = AsyncMock(side_effect=_execute_side_effect)

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.delete(f"/workspaces/{workspace_id}/segments/{seg.id}/members/{lead_id}")

    assert resp.status_code == 204
    mock_db.delete.assert_awaited_with(member)
    mock_db.commit.assert_awaited()
    assert seg.member_count == 2


@pytest.mark.asyncio
async def test_remove_member_not_found_returns_404(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    seg = _fake_segment(workspace_id, kind="static")

    call_count = 0

    async def _execute_side_effect(q):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _make_scalar_result(seg)
        return _make_scalar_result(None)         # no such member

    mock_db.execute = AsyncMock(side_effect=_execute_side_effect)

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.delete(
            f"/workspaces/{workspace_id}/segments/{seg.id}/members/{uuid.uuid4()}"
        )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_remove_member_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.delete(
            f"/workspaces/{wrong_id}/segments/{uuid.uuid4()}/members/{uuid.uuid4()}"
        )

    assert resp.status_code == 403
