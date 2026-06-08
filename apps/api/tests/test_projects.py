"""Tests for the projects router — list, create, get."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient, ASGITransport

from tests.conftest import _make_scalar_result, _make_scalars_result


def _fake_project(workspace_id: uuid.UUID, **kwargs) -> MagicMock:
    project = MagicMock()
    project.id = uuid.uuid4()
    project.workspace_id = workspace_id
    project.external_id = kwargs.get("external_id", None)
    project.name = kwargs.get("name", "Website Redesign")
    project.description = kwargs.get("description", "Q3 marketing site")
    project.status = kwargs.get("status", "active")
    project.contact_id = kwargs.get("contact_id", None)
    # _to_response calls .isoformat() on these, so they must be real datetimes.
    project.created_at = kwargs.get("created_at", datetime(2026, 1, 1, tzinfo=timezone.utc))
    project.updated_at = kwargs.get("updated_at", datetime(2026, 1, 2, tzinfo=timezone.utc))
    return project


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/projects — list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_projects_empty(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/projects")

    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_projects_returns_projects(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    project = _fake_project(workspace_id, name="Mobile App")
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([project]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/projects")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "Mobile App"


@pytest.mark.asyncio
async def test_list_projects_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong_id}/projects")

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_projects_pagination_applies_limit_offset(app_client):
    """limit/offset query params are forwarded into the SQL while the response
    shape stays a bare list."""
    fastapi_app, mock_db, workspace_id = app_client
    project = _fake_project(workspace_id, name="Paged Project")
    mock_db.execute = AsyncMock(return_value=_make_scalars_result([project]))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/projects?limit=7&offset=3")

    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert body[0]["name"] == "Paged Project"

    stmt = mock_db.execute.call_args.args[0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "LIMIT 7" in compiled
    assert "OFFSET 3" in compiled


# ---------------------------------------------------------------------------
# POST /workspaces/{wid}/projects — create
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_project_returns_201(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    seeded = _fake_project(workspace_id, name="New Project")

    def fake_refresh(obj):
        for attr in ("id", "workspace_id", "external_id", "name", "description",
                     "status", "contact_id", "created_at", "updated_at"):
            setattr(obj, attr, getattr(seeded, attr))

    mock_db.refresh.side_effect = fake_refresh

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{workspace_id}/projects",
            json={"name": "New Project", "description": "desc", "status": "active"},
        )

    assert resp.status_code == 201
    assert resp.json()["name"] == "New Project"
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_create_project_missing_name_returns_422(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(f"/workspaces/{workspace_id}/projects", json={})

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_project_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(f"/workspaces/{wrong_id}/projects", json={"name": "x"})

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/projects/{pid}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_project_returns_project(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    project = _fake_project(workspace_id, name="Fetched Project")
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(project))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/projects/{project.id}")

    assert resp.status_code == 200
    assert resp.json()["name"] == "Fetched Project"


@pytest.mark.asyncio
async def test_get_project_not_found_returns_404(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/projects/{uuid.uuid4()}")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_project_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong_id}/projects/{uuid.uuid4()}")

    assert resp.status_code == 403
