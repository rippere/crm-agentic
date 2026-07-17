"""Tests for ai.py — Nova AI assistant endpoint."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient, ASGITransport


def _fake_deal_row(**kwargs) -> MagicMock:
    row = MagicMock()
    row.stage = kwargs.get("stage", "proposal")
    row.title = kwargs.get("title", "Test Deal")
    row.company = kwargs.get("company", "Acme")
    row.value = kwargs.get("value", 15000.0)
    row.health_score = kwargs.get("health_score", 85)
    return row


def _fake_event_row(**kwargs) -> MagicMock:
    row = MagicMock()
    row.type = kwargs.get("type", "contact_created")
    row.description = kwargs.get("description", "New contact added")
    row.agent_name = kwargs.get("agent_name", "System")
    row.severity = kwargs.get("severity", "info")
    return row


def _make_execute_result(rows: list) -> MagicMock:
    result = MagicMock()
    result.all.return_value = rows
    return result


# ---------------------------------------------------------------------------
# POST /workspaces/{wid}/ai/query
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ai_query_empty_body_returns_400(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{workspace_id}/ai/query",
            json={"query": "   "},
        )

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_ai_query_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{wrong_id}/ai/query",
            json={"query": "How is my pipeline?"},
        )

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_ai_query_returns_claude_answer(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    deal = _fake_deal_row(stage="proposal", value=25000.0, health_score=90)
    event = _fake_event_row(description="Deal moved to proposal")

    # scalar() calls: contact_count=5, open_tasks=3
    mock_db.scalar = AsyncMock(side_effect=[5, 3])
    # execute() calls: deals, events
    mock_db.execute = AsyncMock(side_effect=[
        _make_execute_result([deal]),
        _make_execute_result([event]),
    ])

    mock_claude_response = MagicMock()
    mock_claude_response.content = [MagicMock(text="Your pipeline looks strong.")]

    with patch("app.routers.ai._anthropic.Anthropic") as mock_anthropic_cls:
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.return_value = mock_claude_response

        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(
                f"/workspaces/{workspace_id}/ai/query",
                json={"query": "How is my pipeline doing?"},
            )

    assert resp.status_code == 200
    assert resp.json()["answer"] == "Your pipeline looks strong."


@pytest.mark.asyncio
async def test_ai_query_claude_unavailable_returns_503(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    mock_db.scalar = AsyncMock(side_effect=[0, 0])
    mock_db.execute = AsyncMock(side_effect=[
        _make_execute_result([]),
        _make_execute_result([]),
    ])

    with patch("app.routers.ai._anthropic.Anthropic") as mock_anthropic_cls:
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.side_effect = Exception("Connection timeout")

        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(
                f"/workspaces/{workspace_id}/ai/query",
                json={"query": "What should I focus on today?"},
            )

    assert resp.status_code == 503
    assert "AI unavailable" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# POST /workspaces/{wid}/ai/digest
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ai_digest_returns_structured_response(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    deal = _fake_deal_row(stage="closed_won", value=50000.0, health_score=95)
    event = _fake_event_row(description="Deal closed won", severity="success")

    # scalar() calls: contact_count, open_task_count, overdue_task_count, message_count
    mock_db.scalar = AsyncMock(side_effect=[12, 5, 2, 88])
    mock_db.execute = AsyncMock(side_effect=[
        _make_execute_result([deal]),
        _make_execute_result([event]),
    ])

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="**Top Wins**\n- Closed a big deal.\n\n**Watch Out**\n- 2 overdue tasks.\n\n**Recommended Actions**\n- Check /pipeline.")]

    with patch("app.routers.ai._anthropic.Anthropic") as mock_anthropic_cls:
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.return_value = mock_response

        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(f"/workspaces/{workspace_id}/ai/digest")

    assert resp.status_code == 200
    body = resp.json()
    assert "digest" in body
    assert "Top Wins" in body["digest"]
    assert body["contact_count"] == 12
    assert body["open_task_count"] == 5
    assert body["message_count"] == 88
    assert "generated_at" in body


@pytest.mark.asyncio
async def test_ai_digest_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(f"/workspaces/{wrong_id}/ai/digest")

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /workspaces/{wid}/deals/{did}/ai/coach
# ---------------------------------------------------------------------------


def _fake_deal(workspace_id: uuid.UUID, **kwargs) -> MagicMock:
    import datetime
    from datetime import timezone

    deal = MagicMock()
    deal.id = uuid.uuid4()
    deal.workspace_id = workspace_id
    deal.title = kwargs.get("title", "Enterprise Expansion")
    deal.company = kwargs.get("company", "Acme Corp")
    deal.value = kwargs.get("value", 50000.0)
    deal.stage = kwargs.get("stage", "proposal")
    deal.health_score = kwargs.get("health_score", 35)
    deal.ml_win_probability = kwargs.get("ml_win_probability", 25)
    deal.stage_changed_at = kwargs.get(
        "stage_changed_at",
        datetime.datetime(2026, 6, 1, tzinfo=timezone.utc),
    )
    deal.next_action = kwargs.get("next_action", "Send pricing sheet")
    deal.next_action_date = kwargs.get("next_action_date", datetime.date(2026, 6, 1))
    deal.competitors = kwargs.get("competitors", ["CompetitorX", "CompetitorY"])
    return deal


@pytest.mark.asyncio
async def test_deal_coaching_returns_structured_response(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    def _make_scalar_result_local(obj):
        result = MagicMock()
        result.scalar_one_or_none.return_value = obj
        return result

    deal = _fake_deal(workspace_id)
    mock_db.execute = AsyncMock(return_value=_make_scalar_result_local(deal))

    coach_json = '{"urgency": "high", "bullets": ["Schedule a demo.", "Send pricing.", "Involve legal."]}'
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=coach_json)]

    with patch("app.routers.ai._anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = mock_response

        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(
                f"/workspaces/{workspace_id}/deals/{deal.id}/ai/coach"
            )

    assert resp.status_code == 200
    body = resp.json()
    assert body["urgency"] == "high"
    assert len(body["bullets"]) == 3
    assert "deal_id" in body
    assert "generated_at" in body


@pytest.mark.asyncio
async def test_deal_coaching_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")
    deal_id = uuid.uuid4()

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(f"/workspaces/{wrong_id}/deals/{deal_id}/ai/coach")

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /workspaces/{wid}/ai/contacts/{cid}/outreach
# ---------------------------------------------------------------------------


def _fake_contact(workspace_id: uuid.UUID, **kwargs) -> MagicMock:
    contact = MagicMock()
    contact.id = uuid.uuid4()
    contact.workspace_id = workspace_id
    contact.name = kwargs.get("name", "Jane Doe")
    contact.email = kwargs.get("email", "jane@example.com")
    contact.company = kwargs.get("company", "Acme Corp")
    contact.role = kwargs.get("role", "VP of Engineering")
    contact.status = kwargs.get("status", "prospect")
    return contact


@pytest.mark.asyncio
async def test_contact_outreach_returns_subject_and_body(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    def _make_scalar_result_local(obj):
        result = MagicMock()
        result.scalar_one_or_none.return_value = obj
        return result

    def _make_all_result(rows):
        result = MagicMock()
        result.all.return_value = rows
        return result

    contact = _fake_contact(workspace_id)

    mock_db.execute = AsyncMock(side_effect=[
        _make_scalar_result_local(contact),  # contact lookup
        _make_all_result([]),                 # recent messages
        _make_all_result([]),                 # open tasks
    ])

    outreach_json = '{"subject": "Quick chat about Acme Corp?", "body": "Hi Jane,\\n\\nLooking forward to connecting."}'
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=outreach_json)]

    with patch("app.routers.ai._anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = mock_response

        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(
                f"/workspaces/{workspace_id}/ai/contacts/{contact.id}/outreach"
            )

    assert resp.status_code == 200
    body = resp.json()
    assert "subject" in body
    assert "body" in body
    assert body["contact_id"] == str(contact.id)
    assert "generated_at" in body


@pytest.mark.asyncio
async def test_contact_outreach_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
    contact_id = uuid.uuid4()

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(f"/workspaces/{wrong_id}/ai/contacts/{contact_id}/outreach")

    assert resp.status_code == 403
