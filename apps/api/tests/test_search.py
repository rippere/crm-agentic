"""Tests for search.py — semantic search endpoints."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

from tests.conftest import _make_scalars_result


def _fake_contact(workspace_id: uuid.UUID, **kwargs) -> MagicMock:
    c = MagicMock()
    c.id = uuid.uuid4()
    c.workspace_id = workspace_id
    c.name = kwargs.get("name", "Alice Smith")
    c.email = kwargs.get("email", "alice@example.com")
    c.company = kwargs.get("company", "Acme")
    c.role = kwargs.get("role", "CEO")
    c.status = kwargs.get("status", "active")
    c.ml_score = kwargs.get("ml_score", 75)
    c.revenue = kwargs.get("revenue", 10000.0)
    c.deal_count = kwargs.get("deal_count", 2)
    return c


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/contacts/search
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_semantic_search_fallback_ilike_returns_contacts(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    contact = _fake_contact(workspace_id, name="Alice Smith")

    # First execute: COUNT of embedded contacts → 0 (no pgvector)
    count_result = MagicMock()
    count_result.scalar.return_value = 0

    # Second execute: ILIKE fallback
    ilike_result = _make_scalars_result([contact])

    mock_db.execute = AsyncMock(side_effect=[count_result, ilike_result])

    with patch("app.services.embedding.embed_text", return_value=[0.1] * 384):
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.get(f"/workspaces/{workspace_id}/contacts/search?q=Alice")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "Alice Smith"
    assert data[0]["similarity"] is None  # fallback path has no similarity score


@pytest.mark.asyncio
async def test_semantic_search_empty_results(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    count_result = MagicMock()
    count_result.scalar.return_value = 0
    ilike_result = _make_scalars_result([])
    mock_db.execute = AsyncMock(side_effect=[count_result, ilike_result])

    with patch("app.services.embedding.embed_text", return_value=[0.0] * 384):
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.get(f"/workspaces/{workspace_id}/contacts/search?q=nobody")

    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_semantic_search_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong_id}/contacts/search?q=test")

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /workspaces/{wid}/contacts/embed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trigger_embed_enqueues_job(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    mock_task = MagicMock()
    mock_task.id = "embed-job-789"

    with patch("app.workers.embed_contacts.embed_workspace_contacts") as mock_celery:
        mock_celery.delay.return_value = mock_task
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(f"/workspaces/{workspace_id}/contacts/embed")

    assert resp.status_code == 202
    assert resp.json()["job_id"] == "embed-job-789"
    assert resp.json()["status"] == "queued"


@pytest.mark.asyncio
async def test_trigger_embed_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(f"/workspaces/{wrong_id}/contacts/embed")

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_semantic_search_pgvector_path(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    # First execute: COUNT → 3 (pgvector embeddings exist)
    count_result = MagicMock()
    count_result.scalar.return_value = 3

    # Second execute: pgvector query result rows
    row = MagicMock()
    row.__getitem__ = lambda self, key: {
        "id": uuid.uuid4(),
        "name": "Alice Smith",
        "email": "alice@example.com",
        "company": "Acme",
        "role": "CEO",
        "status": "active",
        "ml_score": 80,
        "revenue": 50000.0,
        "deal_count": 3,
        "score": 0.92,
    }[key]

    pgvector_result = MagicMock()
    pgvector_result.mappings.return_value.all.return_value = [row]
    mock_db.execute = AsyncMock(side_effect=[count_result, pgvector_result])

    with patch("app.services.embedding.embed_text", return_value=[0.1] * 384):
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.get(f"/workspaces/{workspace_id}/contacts/search?q=alice")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "Alice Smith"
    assert data[0]["similarity"] == 0.92


# ---------------------------------------------------------------------------
# POST /workspaces/{wid}/contacts/embed-all
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trigger_embed_all_enqueues_job_with_count(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    count_result = MagicMock()
    count_result.scalar.return_value = 12

    mock_db.execute = AsyncMock(return_value=count_result)

    mock_task = MagicMock()
    mock_task.id = "embed-all-job-42"

    with patch("app.workers.embed_contacts.embed_workspace_contacts") as mock_celery:
        mock_celery.delay.return_value = mock_task
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(f"/workspaces/{workspace_id}/contacts/embed-all")

    assert resp.status_code == 202
    body = resp.json()
    assert body["job_id"] == "embed-all-job-42"
    assert body["status"] == "queued"
    assert body["contacts_total"] == 12


@pytest.mark.asyncio
async def test_trigger_embed_all_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(f"/workspaces/{wrong_id}/contacts/embed-all")

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/search  (global search)
# ---------------------------------------------------------------------------


def _fake_deal(workspace_id: uuid.UUID, **kwargs) -> MagicMock:
    d = MagicMock()
    d.id = uuid.uuid4()
    d.workspace_id = workspace_id
    d.title = kwargs.get("title", "Acme Deal")
    d.company = kwargs.get("company", "Acme")
    d.value = kwargs.get("value", 50000.0)
    d.stage = kwargs.get("stage", "proposal")
    return d


def _fake_task(workspace_id: uuid.UUID, **kwargs) -> MagicMock:
    t = MagicMock()
    t.id = uuid.uuid4()
    t.workspace_id = workspace_id
    t.title = kwargs.get("title", "Follow up")
    t.status = kwargs.get("status", "open")
    t.due_date = None
    t.contact_id = None
    return t


@pytest.mark.asyncio
async def test_global_search_returns_grouped_results(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    contact = _fake_contact(workspace_id, name="Alice Smith")
    deal = _fake_deal(workspace_id, title="Alice Corp Deal")
    task = _fake_task(workspace_id, title="Follow up with Alice")

    mock_db.execute = AsyncMock(side_effect=[
        _make_scalars_result([contact]),
        _make_scalars_result([deal]),
        _make_scalars_result([task]),
    ])

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/search?q=alice")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["contacts"]) == 1
    assert body["contacts"][0]["name"] == "Alice Smith"
    assert len(body["deals"]) == 1
    assert body["deals"][0]["title"] == "Alice Corp Deal"
    assert len(body["tasks"]) == 1
    assert body["tasks"][0]["title"] == "Follow up with Alice"


@pytest.mark.asyncio
async def test_global_search_empty_results(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    mock_db.execute = AsyncMock(side_effect=[
        _make_scalars_result([]),
        _make_scalars_result([]),
        _make_scalars_result([]),
    ])

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{workspace_id}/search?q=zzznomatch")

    assert resp.status_code == 200
    body = resp.json()
    assert body == {"contacts": [], "deals": [], "tasks": []}


@pytest.mark.asyncio
async def test_global_search_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong_id}/search?q=test")

    assert resp.status_code == 403
