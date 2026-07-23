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


# ---------------------------------------------------------------------------
# POST /workspaces/{wid}/ai/pipeline-summary
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pipeline_summary_returns_headline_and_bullets(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    def _make_scalars_all(rows):
        result = MagicMock()
        result.scalars.return_value.all.return_value = rows
        return result

    deal = _fake_deal(workspace_id, title="Big Win", stage="proposal", health_score=45, ml_win_probability=60)

    mock_db.execute = AsyncMock(return_value=_make_scalars_all([deal]))

    summary_json = (
        '{"headline": "Pipeline is trending up with 1 active deal.",'
        ' "opportunities": ["Follow up on Big Win proposal.", "Run Pipeline Optimizer.", "Score the lead."],'
        ' "risks": ["Health below 70 on Big Win.", "No competitors tracked.", "Next action unset."]}'
    )
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=summary_json)]

    with patch("app.routers.ai._anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = mock_response

        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(f"/workspaces/{workspace_id}/ai/pipeline-summary")

    assert resp.status_code == 200
    body = resp.json()
    assert "headline" in body
    assert isinstance(body["opportunities"], list)
    assert isinstance(body["risks"], list)
    assert "generated_at" in body


@pytest.mark.asyncio
async def test_pipeline_summary_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("11111111-1111-1111-1111-111111111111")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(f"/workspaces/{wrong_id}/ai/pipeline-summary")

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /workspaces/{wid}/ai/contacts/{cid}/suggest-tasks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_suggest_tasks_returns_suggestions(app_client):
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
        _make_all_result([]),                 # messages
        _make_all_result([]),                 # open deals
    ])

    suggestions_json = (
        '{"suggestions": ['
        '{"title": "Send intro email to Jane", "due_days": 2, "priority": "high"},'
        '{"title": "Schedule discovery call with Jane", "due_days": 5, "priority": "medium"},'
        '{"title": "Enrich Jane\'s contact record", "due_days": 10, "priority": "low"}'
        ']}'
    )
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=suggestions_json)]

    with patch("app.routers.ai._anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = mock_response

        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(
                f"/workspaces/{workspace_id}/ai/contacts/{contact.id}/suggest-tasks"
            )

    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["suggestions"], list)
    assert len(body["suggestions"]) == 3
    assert body["suggestions"][0]["priority"] == "high"
    assert body["suggestions"][0]["due_days"] == 2
    assert body["contact_id"] == str(contact.id)
    assert "generated_at" in body


@pytest.mark.asyncio
async def test_suggest_tasks_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("22222222-2222-2222-2222-222222222222")
    contact_id = uuid.uuid4()

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(f"/workspaces/{wrong_id}/ai/contacts/{contact_id}/suggest-tasks")

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /workspaces/{wid}/deals/{did}/ai/win-loss-analysis
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deal_win_loss_analysis_returns_verdict_and_factors(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    def _make_scalar_result_local(obj):
        result = MagicMock()
        result.scalar_one_or_none.return_value = obj
        return result

    def _make_all_result(rows):
        result = MagicMock()
        result.all.return_value = rows
        return result

    deal_id = uuid.uuid4()
    deal = MagicMock()
    deal.id = deal_id
    deal.workspace_id = workspace_id
    deal.stage = "closed_won"
    deal.title = "Enterprise Expansion"
    deal.company = "Acme Corp"
    deal.value = 95000.0
    deal.win_loss_reason = "Best pricing and champion support"
    deal.health_score = 88
    deal.ml_win_probability = 82
    deal.stage_changed_at = None
    deal.created_at = None
    deal.competitors = ["Competitor X"]

    mock_db.execute = AsyncMock(side_effect=[
        _make_scalar_result_local(deal),  # deal lookup
        _make_all_result([]),              # notes
    ])

    import json as _json
    analysis_json = _json.dumps({
        "narrative": "Strong champion and competitive pricing drove the win.",
        "key_factors": ["Champion support", "Competitive price", "Fast response"],
        "lessons": ["Engage champion early", "Match competitor pricing", "Fast follow-up"],
    })
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=analysis_json)]

    with patch("app.routers.ai._anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = mock_response

        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(
                f"/workspaces/{workspace_id}/deals/{deal_id}/ai/win-loss-analysis"
            )

    assert resp.status_code == 200
    body = resp.json()
    assert body["verdict"] == "won"
    assert "narrative" in body
    assert isinstance(body["key_factors"], list)
    assert len(body["key_factors"]) == 3
    assert isinstance(body["lessons"], list)
    assert body["deal_id"] == str(deal_id)
    assert "generated_at" in body


@pytest.mark.asyncio
async def test_deal_win_loss_analysis_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("33333333-3333-3333-3333-333333333333")
    deal_id = uuid.uuid4()

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(f"/workspaces/{wrong_id}/deals/{deal_id}/ai/win-loss-analysis")

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /workspaces/{wid}/ai/contacts/{cid}/outreach-sequence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_outreach_sequence_returns_three_steps(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    def _make_scalar_result_local(obj):
        result = MagicMock()
        result.scalar_one_or_none.return_value = obj
        return result

    def _make_all_result(rows):
        result = MagicMock()
        result.all.return_value = rows
        return result

    contact = MagicMock()
    contact.id = uuid.uuid4()
    contact.workspace_id = workspace_id
    contact.name = "Jane Smith"
    contact.role = "VP Sales"
    contact.company = "Acme Corp"
    contact.email = "jane@acme.com"
    contact.status = "prospect"
    contact.last_activity = "2026-07-01"

    mock_db.execute = AsyncMock(side_effect=[
        _make_scalar_result_local(contact),  # contact lookup
        _make_all_result([]),                 # recent messages with clarity
        _make_all_result([]),                 # open tasks
    ])

    import json as _json
    seq_json = _json.dumps({
        "steps": [
            {
                "step": 1,
                "channel": "email",
                "timing": "now",
                "subject": "Quick check-in — Jane at Acme",
                "body_preview": "Hi Jane, I wanted to reconnect and see if the platform upgrade is still on your radar.",
                "goal": "Re-open the conversation and gauge current interest",
            },
            {
                "step": 2,
                "channel": "call",
                "timing": "3d",
                "subject": None,
                "body_preview": "Call script: confirm receipt of email, ask about timeline and blockers.",
                "goal": "Qualify urgency and identify decision-maker",
            },
            {
                "step": 3,
                "channel": "slack",
                "timing": "7d",
                "subject": "Resources for Acme team",
                "body_preview": "Hey Jane — sharing our ROI playbook and a proposed next step.",
                "goal": "Deliver value and propose a follow-up meeting",
            },
        ]
    })
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=seq_json)]

    with patch("app.routers.ai._anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = mock_response

        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(
                f"/workspaces/{workspace_id}/ai/contacts/{contact.id}/outreach-sequence"
            )

    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["steps"], list)
    assert len(body["steps"]) == 3
    assert body["steps"][0]["channel"] == "email"
    assert body["steps"][0]["timing"] == "now"
    assert body["steps"][0]["subject"] == "Quick check-in — Jane at Acme"
    assert body["steps"][1]["channel"] == "call"
    assert body["steps"][1]["subject"] is None
    assert body["steps"][2]["channel"] == "slack"
    assert body["contact_id"] == str(contact.id)
    assert "generated_at" in body


@pytest.mark.asyncio
async def test_outreach_sequence_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("66666666-6666-6666-6666-666666666666")
    contact_id = uuid.uuid4()

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{wrong_id}/ai/contacts/{contact_id}/outreach-sequence"
        )

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /workspaces/{wid}/ai/contacts/{cid}/relationship-health
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_relationship_health_returns_rating_and_actions(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    def _make_scalar_result_local(obj):
        result = MagicMock()
        result.scalar_one_or_none.return_value = obj
        return result

    def _make_all_result(rows):
        result = MagicMock()
        result.all.return_value = rows
        return result

    contact = _fake_contact(workspace_id, name="Carol Smith", status="customer")

    # execute: contact lookup; messages with clarity
    mock_db.execute = AsyncMock(side_effect=[
        _make_scalar_result_local(contact),
        _make_all_result([]),  # recent messages + clarity
    ])
    # scalar: msg_count, note_count, tasks_total, tasks_done
    mock_db.scalar = AsyncMock(side_effect=[7, 3, 5, 3])

    health_json = (
        '{"health_rating": "strong",'
        ' "summary": "Carol has been highly engaged with 7 messages and 3 notes in 90 days. '
        'Sentiment is positive and task completion rate is at 60%.",'
        ' "action_items": ['
        '{"priority": "medium", "action": "Schedule a QBR to review progress and expand the account"},'
        '{"priority": "low", "action": "Run Lead Scorer to refresh ML probability score"}'
        ']}'
    )
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=health_json)]

    with patch("app.routers.ai._anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = mock_response

        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(
                f"/workspaces/{workspace_id}/ai/contacts/{contact.id}/relationship-health"
            )

    assert resp.status_code == 200
    body = resp.json()
    assert body["health_rating"] == "strong"
    assert "summary" in body
    assert isinstance(body["action_items"], list)
    assert len(body["action_items"]) == 2
    assert body["action_items"][0]["priority"] == "medium"
    assert body["contact_id"] == str(contact.id)
    assert "generated_at" in body


@pytest.mark.asyncio
async def test_relationship_health_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("44444444-4444-4444-4444-444444444444")
    contact_id = uuid.uuid4()

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{wrong_id}/ai/contacts/{contact_id}/relationship-health"
        )

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /workspaces/{wid}/deals/{did}/ai/risk-narrative
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_risk_narrative_returns_structured_response(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    def _make_scalar_result_local(obj):
        result = MagicMock()
        result.scalar_one_or_none.return_value = obj
        return result

    def _make_all_result(rows):
        result = MagicMock()
        result.all.return_value = rows
        return result

    deal = _fake_deal(workspace_id, stage="negotiation", health_score=28, ml_win_probability=18)
    deal.expected_close = None
    deal.created_at = None

    mock_db.execute = AsyncMock(side_effect=[
        _make_scalar_result_local(deal),  # deal lookup
        _make_all_result([]),              # deal notes
    ])

    import json as _json
    risk_json = _json.dumps({
        "risk_level": "high",
        "narrative": "This deal is critically at risk with a health score of 28 and win probability of 18%.",
        "top_risks": [
            "Win probability at 18% is critically low — escalate to executive sponsor.",
            "Deal stalled in Negotiation for 38 days past stage average.",
            "Two competitors actively engaged with no recent counter-strategy.",
        ],
    })
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=risk_json)]

    with patch("app.routers.ai._anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = mock_response

        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(
                f"/workspaces/{workspace_id}/deals/{deal.id}/ai/risk-narrative"
            )

    assert resp.status_code == 200
    body = resp.json()
    assert body["risk_level"] == "high"
    assert "narrative" in body
    assert isinstance(body["top_risks"], list)
    assert len(body["top_risks"]) == 3
    assert body["deal_id"] == str(deal.id)
    assert "generated_at" in body


@pytest.mark.asyncio
async def test_risk_narrative_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("55555555-5555-5555-5555-555555555555")
    deal_id = uuid.uuid4()

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(f"/workspaces/{wrong_id}/deals/{deal_id}/ai/risk-narrative")

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/ai/contacts/health-overview
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_contact_health_overview_returns_structured_response(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    def _make_scalar_result_local(obj):
        result = MagicMock()
        result.scalar_one_or_none.return_value = obj
        return result

    def _make_all_result(rows):
        result = MagicMock()
        result.all.return_value = rows
        return result

    contact = MagicMock()
    contact.id = uuid.uuid4()
    contact.workspace_id = workspace_id
    contact.name = "Alice Johnson"

    import datetime as _dt
    last_msg_dt = _dt.datetime(2026, 7, 10, 12, 0, tzinfo=_dt.timezone.utc)

    # execute calls in order:
    # 1) join subquery → contact_rows.all() → [(contact, pipeline_value)]
    # 2) last_msg_date query → scalar_one_or_none → datetime
    # 3) last_note_date query → scalar_one_or_none → None
    mock_db.execute = AsyncMock(side_effect=[
        _make_all_result([(contact, 50000)]),
        _make_scalar_result_local(last_msg_dt),
        _make_scalar_result_local(None),
    ])
    # scalar calls in order: msg_count, note_count, tasks_total, tasks_done
    mock_db.scalar = AsyncMock(side_effect=[5, 2, 4, 2])

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="0 contacts at risk, 1 in strong health — Alice is well engaged.")]

    with patch("app.routers.ai._anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = mock_response

        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.get(f"/workspaces/{workspace_id}/ai/contacts/health-overview")

    assert resp.status_code == 200
    body = resp.json()
    assert "at_risk_count" in body
    assert "strong_count" in body
    assert "summary_sentence" in body
    assert isinstance(body["contacts"], list)
    assert len(body["contacts"]) == 1
    c = body["contacts"][0]
    assert c["name"] == "Alice Johnson"
    assert c["health"] in ("strong", "neutral", "at_risk")
    assert "days_since_touch" in c
    assert "top_action" in c
    assert "engagement_score" in c
    assert "generated_at" in body


@pytest.mark.asyncio
async def test_contact_health_overview_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("55555555-5555-5555-5555-555555555555")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong_id}/ai/contacts/health-overview")

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /workspaces/{wid}/deals/{did}/ai/momentum-check
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deal_momentum_check_returns_structured_response(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    def _make_scalar_result_local(obj):
        result = MagicMock()
        result.scalar_one_or_none.return_value = obj
        return result

    def _make_all_result(rows):
        result = MagicMock()
        result.all.return_value = rows
        return result

    import datetime as _dt

    deal = _fake_deal(
        workspace_id,
        stage="proposal",
        health_score=78,
        ml_win_probability=62,
        next_action_date=_dt.date.today(),
    )

    history_row1 = MagicMock()
    history_row1.score = 65
    history_row1.recorded_at = _dt.datetime(2026, 7, 1, tzinfo=_dt.timezone.utc)

    history_row2 = MagicMock()
    history_row2.score = 78
    history_row2.recorded_at = _dt.datetime(2026, 7, 15, tzinfo=_dt.timezone.utc)

    mock_db.execute = AsyncMock(side_effect=[
        _make_scalar_result_local(deal),      # deal lookup
        _make_all_result([history_row2, history_row1]),  # health history (desc → reversed to oldest first)
    ])
    mock_db.scalar = AsyncMock(return_value=12)  # recent activity count

    import json as _json
    momentum_json = _json.dumps({
        "momentum": "gaining",
        "drivers": [
            "Health score rose from 65 to 78 across the last two readings.",
            "12 activity events in the last 30 days with recent engagement.",
        ],
        "recommendation": "Schedule a QBR call to confirm close timeline before month-end.",
    })
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=momentum_json)]

    with patch("app.routers.ai._anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = mock_response

        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(
                f"/workspaces/{workspace_id}/deals/{deal.id}/ai/momentum-check"
            )

    assert resp.status_code == 200
    body = resp.json()
    assert body["momentum"] == "gaining"
    assert isinstance(body["drivers"], list)
    assert len(body["drivers"]) == 2
    assert "recommendation" in body
    assert body["deal_id"] == str(deal.id)
    assert "generated_at" in body


@pytest.mark.asyncio
async def test_deal_momentum_check_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("88888888-8888-8888-8888-888888888888")
    deal_id = uuid.uuid4()

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(f"/workspaces/{wrong_id}/deals/{deal_id}/ai/momentum-check")

    assert resp.status_code == 403
