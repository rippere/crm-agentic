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
# GET /workspaces/{wid}/ai/pipeline-pulse
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pipeline_pulse_returns_structured_data(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    def _make_scalars_all(rows):
        result = MagicMock()
        result.scalars.return_value.all.return_value = rows
        return result

    deal1 = _fake_deal(workspace_id, title="Big Win", stage="proposal", value=120000.0, health_score=75, ml_win_probability=70)
    deal2 = _fake_deal(workspace_id, title="At Risk Deal", stage="discovery", value=30000.0, health_score=35, ml_win_probability=25)

    mock_db.execute = AsyncMock(return_value=_make_scalars_all([deal1, deal2]))

    import json as _json
    pulse_json = _json.dumps({
        "insight": "$150K open pipeline with 1 at-risk deal in discovery. Run Deal Health check on the at-risk deal to generate a targeted re-engagement plan.",
    })
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=pulse_json)]

    with patch("app.routers.ai._anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = mock_response

        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.get(f"/workspaces/{workspace_id}/ai/pipeline-pulse")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total_value"] == pytest.approx(150000.0)
    assert body["at_risk_count"] == 1
    assert body["health_avg"] == 55
    assert isinstance(body["stage_breakdown"], list)
    assert len(body["stage_breakdown"]) == 2
    assert body["top_deal"]["title"] == "Big Win"
    assert body["top_deal"]["value"] == pytest.approx(120000.0)
    assert "insight" in body
    assert "generated_at" in body


@pytest.mark.asyncio
async def test_pipeline_pulse_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("22222222-2222-2222-2222-222222222222")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong_id}/ai/pipeline-pulse")

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


# ---------------------------------------------------------------------------
# POST /workspaces/{wid}/deals/{did}/ai/close-plan
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deal_close_plan_returns_structured_response(app_client):
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
        stage="negotiation",
        health_score=75,
        ml_win_probability=68,
        next_action_date=_dt.date.today(),
    )
    deal.expected_close = "2026-09-15"

    mock_db.execute = AsyncMock(side_effect=[
        _make_scalar_result_local(deal),  # deal lookup
        _make_all_result([]),              # deal notes (empty)
    ])

    import json as _json
    plan_json = _json.dumps({
        "phases": [
            {
                "label": "Next 30 days",
                "actions": [
                    "Schedule a QBR call to confirm close timeline and address remaining concerns.",
                    "Add a Deal Note capturing the latest negotiation status.",
                ],
            },
            {
                "label": "30–60 days",
                "actions": [
                    "Send the final contract draft to procurement.",
                    "Request exec sponsor approval.",
                ],
            },
            {
                "label": "60–90 days",
                "actions": [
                    "Close the deal and log the win in Win/Loss Analysis.",
                    "Schedule onboarding kickoff within 7 days of signature.",
                ],
            },
        ],
        "recommended_close_date": "2026-09-15",
    })
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=plan_json)]

    with patch("app.routers.ai._anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = mock_response

        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(
                f"/workspaces/{workspace_id}/deals/{deal.id}/ai/close-plan"
            )

    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["phases"], list)
    assert len(body["phases"]) == 3
    assert body["phases"][0]["label"] == "Next 30 days"
    assert isinstance(body["phases"][0]["actions"], list)
    assert len(body["phases"][0]["actions"]) == 2
    assert body["recommended_close_date"] == "2026-09-15"
    assert body["deal_id"] == str(deal.id)
    assert "generated_at" in body


@pytest.mark.asyncio
async def test_deal_close_plan_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("99999999-9999-9999-9999-999999999999")
    deal_id = uuid.uuid4()

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(f"/workspaces/{wrong_id}/deals/{deal_id}/ai/close-plan")

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/ai/contacts/{cid}/summary
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_contact_summary_returns_structured_response(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    def _make_scalar_result_local(obj):
        result = MagicMock()
        result.scalar_one_or_none.return_value = obj
        return result

    def _make_all_result(rows):
        result = MagicMock()
        result.all.return_value = rows
        return result

    contact = _fake_contact(workspace_id, name="Sarah Chen", company="TechCorp")

    deal = MagicMock()
    deal.title = "Enterprise Deal"
    deal.value = 95000.0
    deal.stage = "proposal"
    deal.health_score = 82

    mock_db.scalar = AsyncMock(return_value=2)  # open task count
    mock_db.execute = AsyncMock(side_effect=[
        _make_scalar_result_local(contact),  # contact lookup
        _make_all_result([]),                 # messages with clarity scores
        _make_all_result([deal]),             # open deals
        _make_scalar_result_local(None),      # last contact note
    ])

    import json as _json
    summary_json = _json.dumps({
        "relationship_status": "strong",
        "summary": "Sarah Chen has been actively engaged this month with 3 messages exchanged. Her Enterprise Deal is at proposal stage with a health score of 82, suggesting strong momentum.",
        "next_best_action": "Schedule a QBR call to confirm the legal review timeline and lock in the signature date.",
    })
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=summary_json)]

    with patch("app.routers.ai._anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = mock_response

        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.get(f"/workspaces/{workspace_id}/ai/contacts/{contact.id}/summary")

    assert resp.status_code == 200
    body = resp.json()
    assert body["relationship_status"] == "strong"
    assert isinstance(body["summary"], str)
    assert len(body["summary"]) > 0
    assert isinstance(body["next_best_action"], str)
    assert body["deal_value"] == pytest.approx(95000.0)
    assert body["contact_id"] == str(contact.id)
    assert "generated_at" in body


@pytest.mark.asyncio
async def test_contact_summary_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("88888888-8888-8888-8888-888888888888")
    contact_id = uuid.uuid4()

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong_id}/ai/contacts/{contact_id}/summary")

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /workspaces/{wid}/ai/deals/compare
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compare_deals_returns_winner_and_comparison_points(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    def _make_scalars_all(rows):
        result = MagicMock()
        result.scalars.return_value.all.return_value = rows
        return result

    deal1 = _fake_deal(workspace_id, title="Big Win", value=95000.0, health_score=78, ml_win_probability=65)
    deal2 = _fake_deal(workspace_id, title="Small Deal", value=42000.0, health_score=52, ml_win_probability=38)

    mock_db.execute = AsyncMock(return_value=_make_scalars_all([deal1, deal2]))

    compare_json = (
        '{"winner_id": "' + str(deal1.id) + '", '
        '"rationale": "Big Win leads on all fronts.", '
        '"comparison_points": ['
        '{"dimension": "Deal Value", "verdict": "Big Win is 2.3x larger"}, '
        '{"dimension": "Health Score", "verdict": "Big Win scores 78 vs 52"}]}'
    )
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=compare_json)]

    with patch("app.routers.ai._anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = mock_response

        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(
                f"/workspaces/{workspace_id}/ai/deals/compare",
                json={"deal_ids": [str(deal1.id), str(deal2.id)]},
            )

    assert resp.status_code == 200
    body = resp.json()
    assert body["winner_id"] == str(deal1.id)
    assert isinstance(body["rationale"], str)
    assert len(body["rationale"]) > 0
    assert isinstance(body["comparison_points"], list)
    assert len(body["comparison_points"]) >= 2
    assert body["comparison_points"][0]["dimension"] == "Deal Value"
    assert isinstance(body["deal_ids"], list)
    assert "generated_at" in body


@pytest.mark.asyncio
async def test_compare_deals_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("99999999-9999-9999-9999-999999999999")
    deal_id1 = uuid.uuid4()
    deal_id2 = uuid.uuid4()

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{wrong_id}/ai/deals/compare",
            json={"deal_ids": [str(deal_id1), str(deal_id2)]},
        )

    assert resp.status_code == 403



# ---------------------------------------------------------------------------
# POST /workspaces/{wid}/ai/messages/triage
# ---------------------------------------------------------------------------


def _fake_message(**kwargs) -> MagicMock:
    m = MagicMock()
    m.id = kwargs.get("id", uuid.uuid4())
    m.subject = kwargs.get("subject", "Test Subject")
    m.sender_email = kwargs.get("sender_email", "sender@example.com")
    m.body_plain = kwargs.get("body_plain", "Hello, please respond urgently.")
    m.received_at = None
    return m


@pytest.mark.asyncio
async def test_triage_messages_returns_structured_response(app_client):
    import json as _json

    fastapi_app, mock_db, workspace_id = app_client

    msg = _fake_message(subject="Urgent: SLA deadline", sender_email="client@corp.com")

    result = MagicMock()
    result.scalars.return_value.all.return_value = [msg]
    mock_db.execute = AsyncMock(return_value=result)

    triage_json = _json.dumps([
        {
            "message_id": str(msg.id),
            "priority": "urgent",
            "action": "Reply immediately to avoid deal loss.",
            "rationale": "Hard deadline mentioned in subject.",
        }
    ])
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=triage_json)]

    with patch("app.routers.ai._anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = mock_response

        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(f"/workspaces/{workspace_id}/ai/messages/triage")

    assert resp.status_code == 200
    body = resp.json()
    assert body["message_count"] == 1
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["priority"] == "urgent"
    assert item["message_id"] == str(msg.id)
    assert isinstance(item["action"], str) and len(item["action"]) > 0
    assert "generated_at" in body


@pytest.mark.asyncio
async def test_triage_messages_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("99999999-9999-9999-9999-999999999999")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(f"/workspaces/{wrong_id}/ai/messages/triage")

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /workspaces/{wid}/ai/contacts/reengagement-plan
# ---------------------------------------------------------------------------


def _fake_contact_row(workspace_id, **kwargs) -> MagicMock:
    row = MagicMock()
    row.id = kwargs.get("id", uuid.uuid4())
    row.workspace_id = workspace_id
    row.name = kwargs.get("name", "Test Contact")
    row.email = kwargs.get("email", "test@example.com")
    row.company = kwargs.get("company", "Acme Corp")
    row.role = kwargs.get("role", "Head of Sales")
    row.status = kwargs.get("status", "prospect")
    return row


@pytest.mark.asyncio
async def test_reengagement_plan_returns_prioritised_plan(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    c1_id = uuid.uuid4()
    c2_id = uuid.uuid4()

    c1 = _fake_contact_row(workspace_id, id=c1_id, name="Alice Smith", status="customer")
    c2 = _fake_contact_row(workspace_id, id=c2_id, name="Bob Jones", status="prospect")

    def _make_scalars_result(rows):
        result = MagicMock()
        result.scalars.return_value.all.return_value = rows
        return result

    def _make_all_result(rows):
        result = MagicMock()
        result.all.return_value = rows
        return result

    mock_db.execute = AsyncMock(side_effect=[
        _make_scalars_result([c1, c2]),  # contacts query
        _make_all_result([]),            # messages query (none recent)
        _make_all_result([]),            # notes query (none recent)
    ])

    plan_json = (
        '[{"contact_id": "' + str(c1_id) + '", "contact_name": "Alice Smith", "days_silent": 65, '
        '"channel": "email", "message_template": "Hi Alice, checking in!", "urgency": "high"}, '
        '{"contact_id": "' + str(c2_id) + '", "contact_name": "Bob Jones", "days_silent": 42, '
        '"channel": "call", "message_template": "Hey Bob, let\'s reconnect soon.", "urgency": "medium"}]'
    )
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=plan_json)]

    with patch("app.routers.ai._anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = mock_response

        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(f"/workspaces/{workspace_id}/ai/contacts/reengagement-plan")

    assert resp.status_code == 200
    body = resp.json()
    assert "plan" in body
    assert "generated_at" in body
    plan = body["plan"]
    assert len(plan) == 2
    high = next(p for p in plan if p["urgency"] == "high")
    assert high["contact_id"] == str(c1_id)
    assert high["channel"] == "email"
    assert isinstance(high["message_template"], str) and len(high["message_template"]) > 0
    medium = next(p for p in plan if p["urgency"] == "medium")
    assert medium["channel"] == "call"


@pytest.mark.asyncio
async def test_reengagement_plan_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(f"/workspaces/{wrong_id}/ai/contacts/reengagement-plan")

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /workspaces/{wid}/deals/{did}/ai/objection-handler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deal_objection_handler_returns_four_objections(app_client):
    """objection-handler returns exactly 4 objections covering all strategies."""
    import json as _json

    fastapi_app, mock_db, workspace_id = app_client

    def _make_scalar_result_local(obj):
        result = MagicMock()
        result.scalar_one_or_none.return_value = obj
        return result

    def _make_fetchall_result(rows):
        result = MagicMock()
        result.fetchall.return_value = rows
        return result

    deal = _fake_deal(workspace_id, stage="proposal", health_score=65, ml_win_probability=45)

    mock_db.execute = AsyncMock(side_effect=[
        _make_scalar_result_local(deal),   # deal lookup
        _make_fetchall_result([]),          # deal notes (none)
    ])

    objections_json = _json.dumps([
        {"objection": "Your price is too high.", "response": "We offer great long-term value.", "strategy": "prove"},
        {"objection": "The timing isn't right for us.", "response": "Let me show you the ROI curve.", "strategy": "redirect"},
        {"objection": "We trust our current vendor deeply.", "response": "That loyalty is admirable; let me offer data.", "strategy": "empathize"},
        {"objection": "We don't think you can scale with us.", "response": "Let me challenge that assumption directly.", "strategy": "challenge"},
    ])
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=objections_json)]

    with patch("app.routers.ai._anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = mock_response

        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(
                f"/workspaces/{workspace_id}/deals/{deal.id}/ai/objection-handler"
            )

    assert resp.status_code == 200
    body = resp.json()
    assert "objections" in body
    assert "deal_id" in body
    assert "generated_at" in body
    assert len(body["objections"]) == 4
    strategies = {o["strategy"] for o in body["objections"]}
    assert strategies == {"prove", "redirect", "empathize", "challenge"}
    for obj in body["objections"]:
        assert isinstance(obj["objection"], str) and len(obj["objection"]) > 0
        assert isinstance(obj["response"], str) and len(obj["response"]) > 0


@pytest.mark.asyncio
async def test_deal_objection_handler_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
    deal_id = uuid.uuid4()

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{wrong_id}/deals/{deal_id}/ai/objection-handler"
        )

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /workspaces/{wid}/deals/{did}/ai/stakeholder-map
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deal_stakeholder_map_returns_four_stakeholders(app_client):
    """stakeholder-map returns exactly 4 stakeholders with valid roles and engagements."""
    import json as _json

    fastapi_app, mock_db, workspace_id = app_client

    def _make_scalar_result_local(obj):
        result = MagicMock()
        result.scalar_one_or_none.return_value = obj
        return result

    def _make_fetchall_result(rows):
        result = MagicMock()
        result.fetchall.return_value = rows
        return result

    deal = _fake_deal(workspace_id, stage="negotiation", health_score=72, ml_win_probability=60)

    mock_db.execute = AsyncMock(side_effect=[
        _make_scalar_result_local(deal),   # deal lookup
        _make_fetchall_result([]),          # deal notes (none)
    ])

    stakeholders_json = _json.dumps([
        {"name": "Sarah Chen", "role": "champion", "engagement": "high", "recommended_action": "Schedule weekly syncs"},
        {"name": "David Park", "role": "decision_maker", "engagement": "medium", "recommended_action": "Prepare exec summary"},
        {"name": "IT Security", "role": "blocker", "engagement": "low", "recommended_action": "Send SOC 2 report"},
        {"name": "Ops Team", "role": "influencer", "engagement": "medium", "recommended_action": "Offer technical deep-dive"},
    ])
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=stakeholders_json)]

    with patch("app.routers.ai._anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = mock_response

        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(
                f"/workspaces/{workspace_id}/deals/{deal.id}/ai/stakeholder-map"
            )

    assert resp.status_code == 200
    body = resp.json()
    assert "stakeholders" in body
    assert "deal_id" in body
    assert "generated_at" in body
    assert len(body["stakeholders"]) == 4
    roles = {s["role"] for s in body["stakeholders"]}
    assert roles == {"champion", "decision_maker", "blocker", "influencer"}
    engagements = {s["engagement"] for s in body["stakeholders"]}
    assert engagements <= {"high", "medium", "low"}
    for s in body["stakeholders"]:
        assert isinstance(s["name"], str) and len(s["name"]) > 0
        assert isinstance(s["recommended_action"], str)


@pytest.mark.asyncio
async def test_deal_stakeholder_map_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
    deal_id = uuid.uuid4()

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{wrong_id}/deals/{deal_id}/ai/stakeholder-map"
        )

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /workspaces/{wid}/deals/{did}/ai/negotiation-script
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deal_negotiation_script_returns_structure(app_client):
    """negotiation-script returns opening_move, 3 concessions, walk_away_signal, closing_line."""
    import json as _json

    fastapi_app, mock_db, workspace_id = app_client

    def _make_scalar_result_local(obj):
        result = MagicMock()
        result.scalar_one_or_none.return_value = obj
        return result

    def _make_fetchall_result(rows):
        result = MagicMock()
        result.fetchall.return_value = rows
        return result

    deal = _fake_deal(workspace_id, stage="negotiation", health_score=72, ml_win_probability=60)

    mock_db.execute = AsyncMock(side_effect=[
        _make_scalar_result_local(deal),
        _make_fetchall_result([]),
    ])

    script_json = _json.dumps({
        "opening_move": "We're ready to move quickly — let's finalise the terms.",
        "concessions": [
            {"offer": "10% first-year discount", "condition": "Sign by end of quarter", "limit": "Maximum 10%"},
            {"offer": "Free premium onboarding", "condition": "3-year commitment", "limit": "Year-one only"},
            {"offer": "Dedicated CSM year one", "condition": "Full-suite subscription", "limit": "Year-one only"},
        ],
        "walk_away_signal": "Buyer demands >15% discount and refuses multi-year commitment",
        "closing_line": "Let's lock this in — I'll send the paperwork in 30 minutes.",
    })
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=script_json)]

    with patch("app.routers.ai._anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = mock_response

        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(
                f"/workspaces/{workspace_id}/deals/{deal.id}/ai/negotiation-script"
            )

    assert resp.status_code == 200
    body = resp.json()
    assert "opening_move" in body
    assert "concessions" in body
    assert "walk_away_signal" in body
    assert "closing_line" in body
    assert "deal_id" in body
    assert "generated_at" in body
    assert len(body["concessions"]) == 3
    for c in body["concessions"]:
        assert "offer" in c and "condition" in c and "limit" in c


@pytest.mark.asyncio
async def test_deal_negotiation_script_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
    deal_id = uuid.uuid4()

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{wrong_id}/deals/{deal_id}/ai/negotiation-script"
        )

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /workspaces/{wid}/messages/{mid}/ai/reply
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_draft_message_reply_returns_structured_response(app_client):
    """draft_message_reply returns subject, body, tone, message_id, generated_at."""
    import json as _json

    fastapi_app, mock_db, workspace_id = app_client

    msg = _fake_message(
        subject="Partnership opportunity",
        sender_email="partner@acme.com",
        body_plain="Hi, we would love to explore a partnership with your team.",
    )
    msg.contact_id = None  # no linked contact — single DB query

    def _make_scalar_result_local(obj):
        result = MagicMock()
        result.scalar_one_or_none.return_value = obj
        return result

    mock_db.execute = AsyncMock(return_value=_make_scalar_result_local(msg))

    reply_json = _json.dumps({
        "subject": "Re: Partnership opportunity",
        "body": "Thank you for reaching out. We would be delighted to explore this further.",
        "tone": "professional",
    })
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=reply_json)]

    with patch("app.routers.ai._anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = mock_response

        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(
                f"/workspaces/{workspace_id}/messages/{msg.id}/ai/reply"
            )

    assert resp.status_code == 200
    body = resp.json()
    assert "subject" in body
    assert "body" in body
    assert "tone" in body
    assert "message_id" in body
    assert "generated_at" in body
    assert body["tone"] == "professional"
    assert body["message_id"] == str(msg.id)
    assert body["subject"].startswith("Re:")


@pytest.mark.asyncio
async def test_draft_message_reply_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
    message_id = uuid.uuid4()

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{wrong_id}/messages/{message_id}/ai/reply"
        )

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /workspaces/{wid}/deals/{did}/ai/sentiment-digest
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deal_sentiment_digest_returns_structured_response(app_client):
    """deal_sentiment_digest returns overall_sentiment, key_signals, sentiment_trend, deal_id, generated_at."""
    import json as _json

    fastapi_app, mock_db, workspace_id = app_client

    def _make_scalar_result_local(obj):
        result = MagicMock()
        result.scalar_one_or_none.return_value = obj
        return result

    def _make_all_result(rows):
        result = MagicMock()
        result.all.return_value = rows
        return result

    deal = _fake_deal(workspace_id, stage="proposal", health_score=62, ml_win_probability=48)
    deal.contact_id = None  # no linked contact — simplifies mock setup

    note_row1 = MagicMock()
    note_row1.body = "Customer expressed excitement about the timeline and confirmed budget availability."
    note_row1.created_at = None

    note_row2 = MagicMock()
    note_row2.body = "Follow-up call went well; champion reiterated strong internal support."
    note_row2.created_at = None

    mock_db.execute = AsyncMock(side_effect=[
        _make_scalar_result_local(deal),            # deal lookup
        _make_all_result([note_row2, note_row1]),   # deal notes (desc → reversed in handler)
    ])

    digest_json = _json.dumps({
        "overall_sentiment": "positive",
        "key_signals": [
            "Customer explicitly confirmed budget availability in the latest note.",
            "Champion reiterated strong internal support — no objections raised.",
            "Excitement expressed about the proposed timeline.",
        ],
        "sentiment_trend": "improving",
    })
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=digest_json)]

    with patch("app.routers.ai._anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = mock_response

        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(
                f"/workspaces/{workspace_id}/deals/{deal.id}/ai/sentiment-digest"
            )

    assert resp.status_code == 200
    body = resp.json()
    assert body["overall_sentiment"] == "positive"
    assert isinstance(body["key_signals"], list)
    assert len(body["key_signals"]) == 3
    assert body["sentiment_trend"] == "improving"
    assert body["deal_id"] == str(deal.id)
    assert "generated_at" in body


@pytest.mark.asyncio
async def test_deal_sentiment_digest_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
    deal_id = uuid.uuid4()

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{wrong_id}/deals/{deal_id}/ai/sentiment-digest"
        )

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_contact_communication_style_returns_structured_response(app_client):
    """communication-style returns style, preferred_channel, best_time, tone_tips, contact_id, generated_at."""
    import json as _json

    fastapi_app, mock_db, workspace_id = app_client

    def _make_scalar_result_local(obj):
        result = MagicMock()
        result.scalar_one_or_none.return_value = obj
        return result

    def _make_scalars_result(rows):
        result = MagicMock()
        result.scalars.return_value.all.return_value = rows
        return result

    contact = _fake_contact(workspace_id, name="Sarah Chen", company="TechCorp")

    msg1 = MagicMock()
    msg1.subject = "Q3 Review"
    msg1.sender_email = "sarah@techcorp.com"
    msg1.body_plain = "Hi, please send over the detailed metrics and ROI breakdown before our call. I need the numbers."
    msg1.received_at = None

    mock_db.execute = AsyncMock(side_effect=[
        _make_scalar_result_local(contact),   # contact lookup
        _make_scalars_result([msg1]),          # last 5 messages
    ])

    style_json = _json.dumps({
        "style": "analytical",
        "preferred_channel": "email",
        "best_time": "morning",
        "tone_tips": [
            "Lead with data and ROI figures before any narrative.",
            "Use structured bullet points — avoid rambling paragraphs.",
            "Always confirm next steps in writing after each call.",
        ],
    })
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=style_json)]

    with patch("app.routers.ai._anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = mock_response

        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(
                f"/workspaces/{workspace_id}/ai/contacts/{contact.id}/communication-style"
            )

    assert resp.status_code == 200
    body = resp.json()
    assert body["style"] == "analytical"
    assert body["preferred_channel"] == "email"
    assert body["best_time"] == "morning"
    assert isinstance(body["tone_tips"], list)
    assert len(body["tone_tips"]) == 3
    assert body["contact_id"] == str(contact.id)
    assert "generated_at" in body


@pytest.mark.asyncio
async def test_contact_communication_style_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")
    contact_id = uuid.uuid4()

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{wrong_id}/ai/contacts/{contact_id}/communication-style"
        )

    assert resp.status_code == 403


# ── Win Probability Explainer ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_deal_win_probability_explainer_returns_structured_response(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    deal = _fake_deal(workspace_id, stage="proposal", ml_win_probability=65, health_score=72)

    def _make_scalar_result(obj):
        r = MagicMock()
        r.scalar_one_or_none.return_value = obj
        return r

    def _make_scalars_all(rows):
        r = MagicMock()
        r.scalars.return_value.all.return_value = rows
        return r

    mock_db.execute = AsyncMock(side_effect=[
        _make_scalar_result(deal),   # deal lookup
        _make_scalars_all([]),       # deal notes (none)
    ])

    import json as _json
    explainer_json = _json.dumps({
        "probability_assessment": "overestimated",
        "key_drivers": ["Strong champion engagement", "Clear budget confirmed"],
        "risk_factors": ["Competitor pricing pressure", "Decision delayed twice"],
        "recommended_adjustment": -10,
    })
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=explainer_json)]

    with patch("app.routers.ai._anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = mock_response

        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(
                f"/workspaces/{workspace_id}/deals/{deal.id}/ai/win-probability-explainer"
            )

    assert resp.status_code == 200
    body = resp.json()
    assert body["probability_assessment"] == "overestimated"
    assert isinstance(body["key_drivers"], list)
    assert len(body["key_drivers"]) == 2
    assert isinstance(body["risk_factors"], list)
    assert body["recommended_adjustment"] == -10
    assert body["deal_id"] == str(deal.id)
    assert "generated_at" in body


@pytest.mark.asyncio
async def test_deal_win_probability_explainer_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
    deal_id = uuid.uuid4()

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{wrong_id}/deals/{deal_id}/ai/win-probability-explainer"
        )

    assert resp.status_code == 403


# ── Task Prioritization ────────────────────────────────────────────────────────

def _fake_task(workspace_id: uuid.UUID, **kwargs) -> MagicMock:
    t = MagicMock()
    t.id = kwargs.get("id", uuid.uuid4())
    t.workspace_id = workspace_id
    t.title = kwargs.get("title", "Test Task")
    t.description = kwargs.get("description", "")
    t.status = kwargs.get("status", "open")
    t.due_date = kwargs.get("due_date", None)
    return t


@pytest.mark.asyncio
async def test_prioritize_tasks_returns_structured_response(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    task1 = _fake_task(workspace_id, title="Send proposal to Acme")
    task2 = _fake_task(workspace_id, title="Follow up with prospect")

    def _make_scalars_all(rows):
        r = MagicMock()
        r.scalars.return_value.all.return_value = rows
        return r

    mock_db.execute = AsyncMock(return_value=_make_scalars_all([task1, task2]))

    import json as _json
    priority_json = _json.dumps({
        "items": [
            {"task_id": str(task1.id), "priority_rank": 1, "urgency": "high", "reason": "Unblocks deal closure."},
            {"task_id": str(task2.id), "priority_rank": 2, "urgency": "medium", "reason": "Keeps pipeline warm."},
        ],
        "summary_note": "Focus on the proposal first to unblock revenue.",
    })
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=priority_json)]

    with patch("app.routers.ai._anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = mock_response

        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(f"/workspaces/{workspace_id}/ai/tasks/prioritize")

    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["items"], list)
    assert len(body["items"]) == 2
    assert body["items"][0]["priority_rank"] == 1
    assert body["items"][0]["urgency"] == "high"
    assert body["items"][0]["task_id"] == str(task1.id)
    assert "summary_note" in body
    assert "generated_at" in body


@pytest.mark.asyncio
async def test_prioritize_tasks_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(f"/workspaces/{wrong_id}/ai/tasks/prioritize")

    assert resp.status_code == 403


# ── Lead Score Explanation ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_lead_score_explanation_returns_structured_response(app_client):
    """lead-score-explanation returns assessment, summary, key_signals, improvement_tips."""
    import json as _json

    fastapi_app, mock_db, workspace_id = app_client

    def _scalar_result(obj):
        r = MagicMock()
        r.scalar_one_or_none.return_value = obj
        return r

    def _scalars_all(rows):
        r = MagicMock()
        r.scalars.return_value.all.return_value = rows
        return r

    contact = _fake_contact(workspace_id, name="Alice Wu", company="TechCorp", status="prospect")
    contact.ml_score = {"value": 72, "label": "hot", "trend": "up", "signals": ["multiple meetings booked"]}

    msg = _fake_message(subject="Pricing inquiry", body_plain="Can you send me detailed pricing and ROI data?")
    deal = _fake_deal(workspace_id, stage="proposal", value=45000.0)
    deal.contact_id = contact.id

    mock_db.execute = AsyncMock(side_effect=[
        _scalar_result(contact),   # contact lookup
        _scalars_all([msg]),        # recent messages
        _scalars_all([deal]),       # deals
        _scalars_all([]),           # tasks
    ])

    response_json = _json.dumps({
        "score_assessment": "accurate",
        "score_summary": "Alice shows strong buying intent with a $45K proposal in flight and detailed pricing inquiries.",
        "key_signals": [
            "Active $45K deal in proposal stage.",
            "Requested detailed pricing and ROI data — high purchase intent.",
            "Multiple meetings already booked (from signals).",
        ],
        "improvement_tips": [
            "Log the outcome of each meeting to reinforce positive scoring signals.",
            "Send an ROI summary to keep engagement high.",
            "Set a next-action date within 7 days to prevent deal cooling.",
        ],
    })
    mock_resp = MagicMock()
    mock_resp.content = [MagicMock(text=response_json)]

    with patch("app.routers.ai._anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = mock_resp

        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(
                f"/workspaces/{workspace_id}/ai/contacts/{contact.id}/lead-score-explanation"
            )

    assert resp.status_code == 200
    body = resp.json()
    assert body["score_assessment"] == "accurate"
    assert "Alice" in body["score_summary"]
    assert isinstance(body["key_signals"], list)
    assert len(body["key_signals"]) >= 1
    assert isinstance(body["improvement_tips"], list)
    assert len(body["improvement_tips"]) >= 1
    assert body["contact_id"] == str(contact.id)
    assert "generated_at" in body


@pytest.mark.asyncio
async def test_lead_score_explanation_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
    contact_id = uuid.uuid4()

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{wrong_id}/ai/contacts/{contact_id}/lead-score-explanation"
        )

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/ai/pipeline-health-briefing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pipeline_health_briefing_returns_structured_response(app_client):
    import json as _json

    fastapi_app, mock_db, workspace_id = app_client

    def _make_one_result(**attrs):
        row = MagicMock()
        for k, v in attrs.items():
            setattr(row, k, v)
        result = MagicMock()
        result.one.return_value = row
        return result

    def _make_scalar_res(value):
        result = MagicMock()
        result.scalar.return_value = value
        return result

    stage_row = MagicMock()
    stage_row.stage = "proposal"
    stage_row.count = 3
    stage_row.value = 90000.0
    stage_result = MagicMock()
    stage_result.all.return_value = [stage_row]

    mock_db.execute = AsyncMock(side_effect=[
        _make_one_result(total=8, pipeline_value=285000.0, avg_win_prob=62.5),  # open agg
        _make_scalar_res(2),   # at-risk count
        _make_scalar_res(1),   # overdue count
        stage_result,          # stage breakdown
        _make_one_result(count=5, value=210000.0),  # won agg
    ])

    briefing_json = _json.dumps({
        "health_score": 68,
        "rating": "healthy",
        "briefing": "Your pipeline shows solid momentum with $285K in open deals. Two at-risk deals need immediate attention to prevent value erosion.",
        "priorities": [
            "Engage the 2 at-risk deals with updated health plans this week.",
            "Push the 1 overdue-close deal to a firm commitment or re-date the close.",
            "Add 3 new qualified opportunities to proposal stage to maintain pipeline coverage.",
        ],
    })
    mock_resp = MagicMock()
    mock_resp.content = [MagicMock(text=briefing_json)]

    with patch("app.routers.ai._anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = mock_resp

        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.get(f"/workspaces/{workspace_id}/ai/pipeline-health-briefing")

    assert resp.status_code == 200
    body = resp.json()
    assert body["health_score"] == 68
    assert body["rating"] == "healthy"
    assert isinstance(body["briefing"], str)
    assert len(body["briefing"]) > 10
    assert isinstance(body["priorities"], list)
    assert len(body["priorities"]) == 3
    assert "generated_at" in body


@pytest.mark.asyncio
async def test_pipeline_health_briefing_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong_id}/ai/pipeline-health-briefing")

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Phase 15c: AI team performance summary tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_team_performance_returns_structured_response(app_client):
    import json as _json
    fastapi_app, mock_db, workspace_id = app_client

    # 5 scalar() calls: agent_runs, task_total, task_done, messages_processed,
    # deals_moved, active_contacts
    mock_db.scalar = AsyncMock(side_effect=[12, 30, 21, 45, 7, 14])

    perf_json = _json.dumps({
        "performance_rating": "good",
        "highlights": [
            "21 tasks completed this month represents a 70% completion rate.",
            "12 AI agent runs surfaced key insights across the pipeline.",
            "14 contacts actively engaged with 45 messages processed.",
        ],
        "areas_for_improvement": [
            "Increase deal stage velocity — only 7 moves in 30 days.",
            "Schedule weekly pipeline review to catch stalled deals earlier.",
        ],
        "summary_sentence": (
            "The team shows solid engagement with a 70% task completion rate and strong "
            "contact outreach. Focusing on deal progression will convert pipeline momentum "
            "into closed revenue."
        ),
    })
    mock_resp = MagicMock()
    mock_resp.content = [MagicMock(text=perf_json)]

    with patch("app.routers.ai._anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = mock_resp

        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.get(f"/workspaces/{workspace_id}/ai/team-performance")

    assert resp.status_code == 200
    body = resp.json()
    assert body["performance_rating"] == "good"
    assert isinstance(body["highlights"], list)
    assert len(body["highlights"]) == 3
    assert isinstance(body["areas_for_improvement"], list)
    assert len(body["areas_for_improvement"]) == 2
    assert isinstance(body["summary_sentence"], str)
    assert len(body["summary_sentence"]) > 10
    metrics = body["metrics"]
    assert metrics["agent_runs"] == 12
    assert metrics["task_completion_rate"] == 70
    assert metrics["messages_processed"] == 45
    assert metrics["deals_moved"] == 7
    assert metrics["active_contacts"] == 14
    assert "generated_at" in body


@pytest.mark.asyncio
async def test_team_performance_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong_id}/ai/team-performance")

    assert resp.status_code == 403


# ── Meeting Prep ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_deal_meeting_prep_returns_structured_response(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    deal = _fake_deal(workspace_id, stage="proposal", ml_win_probability=72, health_score=80)
    deal.contact_id = None  # no contact to simplify mock

    def _make_scalar_result(obj):
        r = MagicMock()
        r.scalar_one_or_none.return_value = obj
        return r

    def _make_scalars_all(rows):
        r = MagicMock()
        r.scalars.return_value.all.return_value = rows
        return r

    mock_db.execute = AsyncMock(side_effect=[
        _make_scalar_result(deal),   # deal lookup
        _make_scalars_all([]),       # deal notes (none)
    ])

    import json as _json
    prep_json = _json.dumps({
        "agenda_items": [
            {"topic": "Deal Status Review", "goal": "Align on current state and blockers.", "talking_points": ["Recap Q2 progress", "Discuss open issues"]},
            {"topic": "Competitive Landscape", "goal": "Address competitor concerns proactively.", "talking_points": ["Highlight differentiators"]},
            {"topic": "Next Steps", "goal": "Agree on clear action items before close.", "talking_points": ["Set final timeline", "Confirm decision makers"]},
        ],
        "questions_to_ask": [
            "What is your timeline for final sign-off?",
            "Are there any unresolved concerns with legal?",
            "Who else needs to be involved in the decision?",
        ],
        "things_to_avoid": [
            "Discounting without approval",
            "Pressuring for immediate commitment",
        ],
    })
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=prep_json)]

    with patch("app.routers.ai._anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = mock_response

        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(
                f"/workspaces/{workspace_id}/deals/{deal.id}/ai/meeting-prep"
            )

    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["agenda_items"], list)
    assert len(body["agenda_items"]) == 3
    assert "topic" in body["agenda_items"][0]
    assert "goal" in body["agenda_items"][0]
    assert isinstance(body["agenda_items"][0]["talking_points"], list)
    assert isinstance(body["questions_to_ask"], list)
    assert len(body["questions_to_ask"]) == 3
    assert isinstance(body["things_to_avoid"], list)
    assert len(body["things_to_avoid"]) == 2
    assert body["deal_id"] == str(deal.id)
    assert "generated_at" in body


@pytest.mark.asyncio
async def test_deal_meeting_prep_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
    deal_id = uuid.uuid4()

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{wrong_id}/deals/{deal_id}/ai/meeting-prep"
        )

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_workspace_digest_returns_structured_response(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    import json as _json

    def _scalar(v):
        r = MagicMock()
        r.scalar.return_value = v
        return r

    def _scalar_one(row):
        r = MagicMock()
        r.one.return_value = row
        return r

    def _all(rows):
        r = MagicMock()
        r.all.return_value = rows
        return r

    mock_db.execute = AsyncMock(side_effect=[
        _scalar(25),                         # total_contacts
        _scalar(3),                          # going_dark_count
        _all([]),                            # open_deals_rows
        _scalar(2),                          # overdue_close_count
        _scalar(10),                         # open_task_count
        _scalar(4),                          # overdue_task_count
        _scalar(18),                         # agent_run_count
        _scalar_one((1, 45000)),             # closed_won count + value
    ])

    digest_json = _json.dumps({
        "health_rating": "good",
        "summary": "The workspace has 25 contacts with 3 going dark. Pipeline is light with no open deals.",
        "highlights": ["18 agent runs in the last 30 days", "1 deal closed won worth $45K"],
        "warnings": ["3 contacts have had no touch in 30 days", "4 tasks are overdue"],
        "recommended_actions": [
            "Re-engage the 3 dark contacts this week",
            "Close out the 4 overdue tasks",
            "Open new deals to build pipeline",
        ],
    })
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=digest_json)]

    with patch("app.routers.ai._anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = mock_response

        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.get(f"/workspaces/{workspace_id}/ai/workspace-digest")

    assert resp.status_code == 200
    body = resp.json()
    assert body["health_rating"] in {"excellent", "good", "needs_attention", "critical"}
    assert isinstance(body["summary"], str) and len(body["summary"]) > 0
    assert isinstance(body["highlights"], list)
    assert isinstance(body["warnings"], list)
    assert isinstance(body["recommended_actions"], list)
    assert "metrics" in body
    assert body["metrics"]["total_contacts"] == 25
    assert "generated_at" in body


@pytest.mark.asyncio
async def test_workspace_digest_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong_id}/ai/workspace-digest")

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_contact_onboarding_checklist_returns_structured_response(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    contact = _fake_contact(workspace_id)
    contact.status = "prospect"
    contact.ml_score = {"value": 55, "label": "warm"}
    contact.company = "Acme Corp"
    contact.role = "VP Engineering"
    contact.email = "alex@acme.com"
    contact.phone = None

    def _scalar(v):
        r = MagicMock()
        r.scalar.return_value = v
        return r

    def _all(rows):
        r = MagicMock()
        r.all.return_value = rows
        return r

    def _scalar_one_or_none(v):
        r = MagicMock()
        r.scalar_one_or_none.return_value = v
        return r

    mock_db.execute = AsyncMock(side_effect=[
        _scalar_one_or_none(contact),   # contact lookup
        _scalar(3),                      # msg_count
        _scalar(1),                      # note_count
        _all([]),                        # open_deals
    ])

    import json as _json
    checklist_json = _json.dumps({
        "checklist": [
            {"step": "Send intro email today", "detail": "Personalised opener referencing their eng role.", "category": "outreach", "priority": "high"},
            {"step": "Add phone number to profile", "detail": "Required for call-based follow-up.", "category": "data", "priority": "high"},
            {"step": "Research company tech stack", "detail": "Understand fit with your product before next touch.", "category": "research", "priority": "medium"},
            {"step": "Link to an open deal", "detail": "Convert prospect engagement into pipeline.", "category": "relationship", "priority": "medium"},
            {"step": "Schedule a 30-min discovery call", "detail": "Move relationship from email to live conversation.", "category": "outreach", "priority": "low"},
        ],
        "readiness": "in_progress",
        "readiness_reason": "3 messages exchanged but no open deal yet — nearly ready to qualify.",
    })
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=checklist_json)]

    with patch("app.routers.ai._anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = mock_response

        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(
                f"/workspaces/{workspace_id}/ai/contacts/{contact.id}/onboarding-checklist"
            )

    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["checklist"], list)
    assert len(body["checklist"]) == 5
    item = body["checklist"][0]
    assert "step" in item and "detail" in item and "category" in item and "priority" in item
    assert item["category"] in {"data", "outreach", "research", "relationship"}
    assert item["priority"] in {"high", "medium", "low"}
    assert body["readiness"] in {"new", "in_progress", "ready"}
    assert isinstance(body["readiness_reason"], str)
    assert body["contact_id"] == str(contact.id)
    assert "generated_at" in body


@pytest.mark.asyncio
async def test_contact_onboarding_checklist_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
    contact_id = uuid.uuid4()

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{wrong_id}/ai/contacts/{contact_id}/onboarding-checklist"
        )

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /workspaces/{wid}/deals/{did}/ai/roi-projection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deal_roi_projection_returns_structured_response(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    deal = _fake_deal_row(stage="proposal", value=20000.0, health_score=78)
    deal.stage_changed_at = None
    deal.ml_win_probability = 65
    deal.competitors = []
    deal.next_action_date = None

    def _scalar_one_or_none(v):
        r = MagicMock()
        r.scalar_one_or_none.return_value = v
        return r

    def _all(rows):
        r = MagicMock()
        r.all.return_value = rows
        return r

    mock_db.execute = AsyncMock(side_effect=[
        _scalar_one_or_none(deal),   # deal lookup
        _all([]),                     # deal notes
    ])

    import json as _json
    roi_json = _json.dumps({
        "roi_multiplier": 3.8,
        "payback_months": 8,
        "year1_value": 56000,
        "year3_value": 228000,
        "assumptions": [
            "Team of 8 saves 12 hours/week on manual CRM tasks",
            "Current tooling costs estimated at $15K/year",
            "Full adoption reached by month 4",
        ],
    })
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=roi_json)]

    with patch("app.routers.ai._anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = mock_response

        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(
                f"/workspaces/{workspace_id}/deals/{uuid.uuid4()}/ai/roi-projection"
            )

    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["roi_multiplier"], float)
    assert isinstance(body["payback_months"], int)
    assert isinstance(body["year1_value"], int)
    assert isinstance(body["year3_value"], int)
    assert isinstance(body["assumptions"], list)
    assert len(body["assumptions"]) == 3
    assert "deal_id" in body
    assert "generated_at" in body


@pytest.mark.asyncio
async def test_deal_roi_projection_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
    deal_id = uuid.uuid4()

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{wrong_id}/deals/{deal_id}/ai/roi-projection"
        )

    assert resp.status_code == 403

# ---------------------------------------------------------------------------
# POST /workspaces/{wid}/ai/contacts/{cid}/growth-forecast
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_contact_growth_forecast_returns_structured_response(app_client):
    """growth-forecast returns forecast_revenue_3m/12m, growth_trajectory, key_drivers."""
    import json as _json

    fastapi_app, mock_db, workspace_id = app_client

    def _scalar_one_or_none(v):
        r = MagicMock()
        r.scalar_one_or_none.return_value = v
        return r

    def _scalars_all(rows):
        r = MagicMock()
        r.scalars.return_value.all.return_value = rows
        return r

    def _scalar(v):
        r = MagicMock()
        r.scalar.return_value = v
        return r

    contact = _fake_contact(workspace_id, name="Priya Nair", company="StartupBase", status="customer")
    contact.ml_score = {"value": 80, "label": "hot"}

    deal = _fake_deal(workspace_id, stage="closed_won", value=30000.0)
    deal.contact_id = contact.id

    mock_db.execute = AsyncMock(side_effect=[
        _scalar_one_or_none(contact),  # contact lookup
        _scalars_all([deal]),           # all deals for contact
        _scalar(7),                     # message count last 90d
        _scalar(3),                     # note count last 90d
    ])

    forecast_json = _json.dumps({
        "forecast_revenue_3m": 18000,
        "forecast_revenue_12m": 75000,
        "growth_trajectory": "growing",
        "key_drivers": [
            "Existing closed-won deal signals high-intent re-purchase potential",
            "Strong recent message cadence (7 in 90 days) shows active engagement",
            "Customer status with healthy ML score supports upsell forecasting",
        ],
    })
    mock_resp = MagicMock()
    mock_resp.content = [MagicMock(text=forecast_json)]

    with patch("app.routers.ai._anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = mock_resp

        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(
                f"/workspaces/{workspace_id}/ai/contacts/{contact.id}/growth-forecast"
            )

    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["forecast_revenue_3m"], int)
    assert body["forecast_revenue_3m"] == 18000
    assert isinstance(body["forecast_revenue_12m"], int)
    assert body["growth_trajectory"] in {"declining", "flat", "growing", "accelerating"}
    assert body["growth_trajectory"] == "growing"
    assert isinstance(body["key_drivers"], list)
    assert len(body["key_drivers"]) == 3
    assert body["contact_id"] == str(contact.id)
    assert "generated_at" in body


@pytest.mark.asyncio
async def test_contact_growth_forecast_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
    contact_id = uuid.uuid4()

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{wrong_id}/ai/contacts/{contact_id}/growth-forecast"
        )

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /workspaces/{wid}/ai/goal-tracker
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_goal_tracker_returns_structured_response(app_client):
    """goal-tracker returns goals list with status, progress_pct, and overall_health."""
    import json as _json

    fastapi_app, mock_db, workspace_id = app_client

    def _open_deals_result():
        row1 = MagicMock()
        row1.value = 85000.0
        row1.health_score = 72
        row1.ml_win_probability = 65
        row2 = MagicMock()
        row2.value = 45000.0
        row2.health_score = 38
        row2.ml_win_probability = 22
        r = MagicMock()
        r.all.return_value = [row1, row2]
        return r

    def _cw_result():
        row = MagicMock()
        row.__getitem__ = lambda self, i: [3, 210000.0][i]
        r = MagicMock()
        r.first.return_value = row
        return r

    mock_db.scalar = AsyncMock(side_effect=[
        12,  # total_contacts
        18,  # total_tasks
        13,  # done_tasks
        7,   # contacts_with_recent_msg
    ])
    mock_db.execute = AsyncMock(side_effect=[
        _open_deals_result(),
        _cw_result(),
    ])

    goal_json = _json.dumps({
        "goals": [
            {
                "name": "Close $130K pipeline",
                "target_description": "Convert all open deals to closed-won this quarter",
                "progress_pct": 62,
                "status": "at_risk",
                "insight": "One deal at health 38 is dragging the pipeline. Immediate outreach needed.",
            },
            {
                "name": "Improve task completion",
                "target_description": "Maintain task completion rate above 80%",
                "progress_pct": 72,
                "status": "on_track",
                "insight": "Task completion at 72% is close to target. Three overdue tasks remain.",
            },
        ],
        "overall_health": "at_risk",
    })
    mock_resp = MagicMock()
    mock_resp.content = [MagicMock(text=goal_json)]

    with patch("app.routers.ai._anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = mock_resp

        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.get(f"/workspaces/{workspace_id}/ai/goal-tracker")

    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["goals"], list)
    assert len(body["goals"]) == 2
    goal = body["goals"][0]
    assert goal["name"] == "Close $130K pipeline"
    assert goal["progress_pct"] == 62
    assert goal["status"] == "at_risk"
    assert isinstance(goal["insight"], str)
    assert body["overall_health"] == "at_risk"
    assert "generated_at" in body


@pytest.mark.asyncio
async def test_goal_tracker_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong_id}/ai/goal-tracker")

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Phase 15m — AI competitive landscape
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_competitive_landscape_returns_structured_response(app_client):
    import json as _json

    fastapi_app, mock_db, workspace_id = app_client

    def _open_deals_result():
        row1 = MagicMock()
        row1.title = "Deal A"
        row1.stage = "proposal"
        row1.competitors = ["Salesforce", "HubSpot"]
        row1.value = 50000.0
        row2 = MagicMock()
        row2.title = "Deal B"
        row2.stage = "negotiation"
        row2.competitors = ["Salesforce", "Pipedrive"]
        row2.value = 80000.0
        row3 = MagicMock()
        row3.title = "Deal C"
        row3.stage = "qualified"
        row3.competitors = ["HubSpot"]
        row3.value = 30000.0
        r = MagicMock()
        r.all.return_value = [row1, row2, row3]
        return r

    mock_db.execute = AsyncMock(return_value=_open_deals_result())

    landscape_json = _json.dumps({
        "top_competitors": [
            {
                "name": "Salesforce",
                "deal_count": 2,
                "stages_present": ["proposal", "negotiation"],
                "threat_level": "high",
                "positioning_note": "Emphasize ease-of-use and lower TCO vs Salesforce.",
            },
            {
                "name": "HubSpot",
                "deal_count": 2,
                "stages_present": ["proposal", "qualified"],
                "threat_level": "medium",
                "positioning_note": "Lead with AI-native features that HubSpot lacks.",
            },
        ],
        "competitive_summary": "Salesforce and HubSpot dominate. Focus on differentiated AI capabilities.",
        "win_strategies": [
            "Lead with AI automation demos in discovery calls.",
            "Offer a competitive migration package for Salesforce customers.",
            "Reference case studies that highlight ROI over HubSpot deployments.",
        ],
    })

    mock_resp = MagicMock()
    mock_resp.content = [MagicMock(text=landscape_json)]

    with patch("app.routers.ai._anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = mock_resp

        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.get(f"/workspaces/{workspace_id}/ai/competitive-landscape")

    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["top_competitors"], list)
    assert len(body["top_competitors"]) == 2
    comp = body["top_competitors"][0]
    assert comp["name"] == "Salesforce"
    assert comp["threat_level"] == "high"
    assert isinstance(comp["positioning_note"], str)
    assert isinstance(body["competitive_summary"], str)
    assert len(body["win_strategies"]) == 3
    assert "generated_at" in body


@pytest.mark.asyncio
async def test_competitive_landscape_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get(f"/workspaces/{wrong_id}/ai/competitive-landscape")

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /workspaces/{wid}/deals/{did}/ai/followup-sequence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deal_followup_sequence_returns_structured_response(app_client):
    """followup-sequence returns 3 steps with timing/channel/action/goal + rationale."""
    import json as _json

    fastapi_app, mock_db, workspace_id = app_client

    def _make_scalar_result_local(obj):
        result = MagicMock()
        result.scalar_one_or_none.return_value = obj
        return result

    def _make_fetchall_result(rows):
        result = MagicMock()
        result.fetchall.return_value = rows
        return result

    deal = _fake_deal(workspace_id, stage="proposal", health_score=72, ml_win_probability=60)

    mock_db.execute = AsyncMock(side_effect=[
        _make_scalar_result_local(deal),
        _make_fetchall_result([]),
    ])

    seq_json = _json.dumps({
        "steps": [
            {
                "step": 1,
                "timing": "now",
                "channel": "email",
                "action": "Send a personalized proposal recap highlighting ROI.",
                "goal": "Confirm receipt and surface any questions.",
            },
            {
                "step": 2,
                "timing": "3d",
                "channel": "call",
                "action": "Schedule a 30-minute call to address legal questions.",
                "goal": "Remove blockers and align on contract structure.",
            },
            {
                "step": 3,
                "timing": "7d",
                "channel": "slack",
                "action": "Share a relevant customer success story.",
                "goal": "Build confidence before final sign-off.",
            },
        ],
        "rationale": "Multi-channel approach balances urgency with relationship-building.",
    })

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=seq_json)]

    with patch("app.routers.ai._anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = mock_response

        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(
                f"/workspaces/{workspace_id}/deals/{deal.id}/ai/followup-sequence"
            )

    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["steps"], list)
    assert len(body["steps"]) == 3
    step = body["steps"][0]
    assert step["timing"] in ("now", "3d", "7d", "14d")
    assert step["channel"] in ("email", "call", "slack")
    assert isinstance(step["action"], str)
    assert isinstance(step["goal"], str)
    assert isinstance(body["rationale"], str)
    assert "deal_id" in body
    assert "generated_at" in body


@pytest.mark.asyncio
async def test_deal_followup_sequence_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
    deal_id = uuid.uuid4()

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{wrong_id}/deals/{deal_id}/ai/followup-sequence"
        )

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /workspaces/{wid}/deals/{did}/ai/champion-risk
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deal_champion_risk_returns_structured_response(app_client):
    import json as _json

    fastapi_app, mock_db, workspace_id = app_client

    deal = _fake_deal_row(stage="proposal", value=30000.0, health_score=45)
    deal.stage_changed_at = None
    deal.ml_win_probability = 40
    deal.mentions = [
        {"name": "Alice Johnson", "type": "champion"},
        {"name": "Bob Smith", "type": "decision_maker"},
    ]

    def _scalar_one_or_none(v):
        r = MagicMock()
        r.scalar_one_or_none.return_value = v
        return r

    def _all(rows):
        r = MagicMock()
        r.all.return_value = rows
        return r

    mock_db.execute = AsyncMock(side_effect=[
        _scalar_one_or_none(deal),  # deal lookup
        _all([]),                    # deal notes
    ])

    risk_json = _json.dumps({
        "risk_level": "high",
        "champion_status": "uncertain",
        "risk_signals": [
            "No response from Alice Johnson in 3 weeks despite 2 follow-up emails.",
            "Deal stalled in Proposal stage for 21 days with no meeting scheduled.",
            "Bob Smith (decision-maker) has not been directly engaged in 30 days.",
        ],
        "mitigation_steps": [
            "Schedule a direct call with Alice Johnson to confirm her internal support status.",
            "Request an introduction to Bob Smith to gauge executive-level commitment.",
            "Send an executive summary to help Alice champion the deal at the board level.",
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
                f"/workspaces/{workspace_id}/deals/{uuid.uuid4()}/ai/champion-risk"
            )

    assert resp.status_code == 200
    body = resp.json()
    assert body["risk_level"] in {"low", "medium", "high", "critical"}
    assert body["champion_status"] in {"active", "uncertain", "at_risk", "unknown"}
    assert isinstance(body["risk_signals"], list)
    assert len(body["risk_signals"]) == 3
    assert isinstance(body["mitigation_steps"], list)
    assert len(body["mitigation_steps"]) == 3
    assert "deal_id" in body
    assert "generated_at" in body


@pytest.mark.asyncio
async def test_deal_champion_risk_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")
    deal_id = uuid.uuid4()

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{wrong_id}/deals/{deal_id}/ai/champion-risk"
        )

    assert resp.status_code == 403


# POST /workspaces/{wid}/deals/{did}/ai/competitive-response
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deal_competitive_response_returns_structured_response(app_client):
    import json as _json

    fastapi_app, mock_db, workspace_id = app_client

    deal = _fake_deal_row(stage="negotiation", value=50000.0, health_score=60)
    deal.stage_changed_at = None
    deal.ml_win_probability = 55
    deal.competitors = ["Salesforce", "HubSpot"]

    def _scalar_one_or_none(v):
        r = MagicMock()
        r.scalar_one_or_none.return_value = v
        return r

    def _all(rows):
        r = MagicMock()
        r.all.return_value = rows
        return r

    mock_db.execute = AsyncMock(side_effect=[
        _scalar_one_or_none(deal),  # deal lookup
        _all([]),                    # deal notes
    ])

    response_json = _json.dumps({
        "primary_competitor": "Salesforce",
        "battle_card": {
            "strengths": [
                "Massive ecosystem with AppExchange marketplace.",
                "Strong enterprise brand recognition.",
                "Extensive third-party integrations.",
            ],
            "weaknesses": [
                "High TCO and complex per-feature licensing.",
                "Steep learning curve requiring dedicated admins.",
                "Slow implementation — typically 6–18 months.",
            ],
            "key_differentiators": [
                "NovaCRM deploys in days, not months, with no implementation fees.",
                "AI-native pipeline intelligence built in — no plugins required.",
                "Predictable flat pricing that scales with headcount.",
            ],
            "suggested_talk_track": (
                "When Salesforce comes up, acknowledge their breadth but pivot to speed. "
                "Ask how long their last CRM implementation took and what percentage of features they actually used."
            ),
        },
    })

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=response_json)]

    with patch("app.routers.ai._anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = mock_response

        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(
                f"/workspaces/{workspace_id}/deals/{uuid.uuid4()}/ai/competitive-response"
            )

    assert resp.status_code == 200
    body = resp.json()
    assert "primary_competitor" in body
    assert isinstance(body["primary_competitor"], str)
    bc = body["battle_card"]
    assert isinstance(bc["strengths"], list) and len(bc["strengths"]) == 3
    assert isinstance(bc["weaknesses"], list) and len(bc["weaknesses"]) == 3
    assert isinstance(bc["key_differentiators"], list) and len(bc["key_differentiators"]) == 3
    assert isinstance(bc["suggested_talk_track"], str)
    assert "deal_id" in body
    assert "generated_at" in body


@pytest.mark.asyncio
async def test_deal_competitive_response_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
    deal_id = uuid.uuid4()

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{wrong_id}/deals/{deal_id}/ai/competitive-response"
        )

    assert resp.status_code == 403

# POST /workspaces/{wid}/deals/{did}/ai/expansion-opportunity
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deal_expansion_opportunity_returns_structured_response(app_client):
    import json as _json

    fastapi_app, mock_db, workspace_id = app_client

    deal = _fake_deal_row(stage="closed_won", value=95000.0, health_score=88)
    deal.contact_id = None

    def _scalar_one_or_none(v):
        r = MagicMock()
        r.scalar_one_or_none.return_value = v
        return r

    def _all(rows):
        r = MagicMock()
        r.all.return_value = rows
        return r

    mock_db.execute = AsyncMock(side_effect=[
        _scalar_one_or_none(deal),  # deal lookup
        _all([]),                    # deal notes
    ])

    response_json = _json.dumps({
        "opportunity_score": 82,
        "upsell_products": [
            "Enterprise Analytics Suite add-on",
            "Dedicated Customer Success Manager package",
            "Advanced API access tier",
        ],
        "cross_sell_signals": [
            "Mentioned interest in reporting dashboards during onboarding",
            "Team size suggests need for multi-seat license expansion",
            "High engagement score signals strong platform adoption",
        ],
        "recommended_timing": "3_months",
        "next_step": "Schedule a 90-day business review to surface new use cases and expansion budget",
    })

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=response_json)]

    with patch("app.routers.ai._anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = mock_response

        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(
                f"/workspaces/{workspace_id}/deals/{uuid.uuid4()}/ai/expansion-opportunity"
            )

    assert resp.status_code == 200
    body = resp.json()
    assert "opportunity_score" in body
    assert isinstance(body["opportunity_score"], int)
    assert 0 <= body["opportunity_score"] <= 100
    assert "upsell_products" in body
    assert isinstance(body["upsell_products"], list) and len(body["upsell_products"]) == 3
    assert "cross_sell_signals" in body
    assert isinstance(body["cross_sell_signals"], list) and len(body["cross_sell_signals"]) == 3
    assert body["recommended_timing"] in ("immediate", "3_months", "6_months")
    assert "next_step" in body and isinstance(body["next_step"], str)
    assert "deal_id" in body
    assert "generated_at" in body


@pytest.mark.asyncio
async def test_deal_expansion_opportunity_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
    deal_id = uuid.uuid4()

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{wrong_id}/deals/{deal_id}/ai/expansion-opportunity"
        )

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Phase 15r — AI contact churn risk assessment
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_contact_churn_risk_returns_structured_response(app_client):
    """churn-risk returns risk_level, churn_signals x3, retention_actions x3."""
    import json as _json

    fastapi_app, mock_db, workspace_id = app_client

    def _sone(v):
        r = MagicMock()
        r.scalar_one_or_none.return_value = v
        return r

    def _scalar(v):
        r = MagicMock()
        r.scalar.return_value = v
        return r

    contact = _fake_contact(workspace_id, name="Dana Nguyen", company="FinCorp", status="customer")
    contact.ml_score = 55
    contact.ml_score_label = "warm"

    import datetime as _dt
    last_touch_ts = _dt.datetime.utcnow() - _dt.timedelta(days=45)

    mock_db.execute = AsyncMock(side_effect=[
        _sone(contact),          # contact lookup
        _scalar(2),              # message count last 90d
        _scalar(1),              # note count last 90d
        _scalar(12000.0),        # open pipeline value
        _scalar(3),              # open task count
        _scalar(last_touch_ts),  # last message received_at
        _scalar(None),           # last note created_at
    ])

    response_json = _json.dumps({
        "risk_level": "high",
        "churn_signals": [
            "Only 2 messages in the last 90 days — engagement frequency is declining",
            "45 days since last touch — contact has gone silent past the 30-day threshold",
            "Warm ML score with low recent activity suggests pipeline stall risk",
        ],
        "retention_actions": [
            "Send a personalised re-engagement email referencing their open deal",
            "Schedule a discovery call to understand any blockers or competitor conversations",
            "Share a relevant industry insight to provide value before the next ask",
        ],
    })
    mock_resp = MagicMock()
    mock_resp.content = [MagicMock(text=response_json)]

    with patch("app.routers.ai._anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = mock_resp

        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(
                f"/workspaces/{workspace_id}/ai/contacts/{contact.id}/churn-risk"
            )

    assert resp.status_code == 200
    body = resp.json()
    assert body["risk_level"] in {"low", "medium", "high", "critical"}
    assert body["risk_level"] == "high"
    assert isinstance(body["churn_signals"], list)
    assert len(body["churn_signals"]) == 3
    assert isinstance(body["retention_actions"], list)
    assert len(body["retention_actions"]) == 3
    assert body["contact_id"] == str(contact.id)
    assert "generated_at" in body


@pytest.mark.asyncio
async def test_contact_churn_risk_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")
    contact_id = uuid.uuid4()

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{wrong_id}/ai/contacts/{contact_id}/churn-risk"
        )

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Phase 15s — AI contact deal velocity benchmark
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_contact_deal_velocity_benchmark_returns_structured_response(app_client):
    """deal-velocity-benchmark returns contact/workspace avg days, velocity_rating, insight."""
    import json as _json
    import datetime as _dt

    fastapi_app, mock_db, workspace_id = app_client

    def _sone(v):
        r = MagicMock()
        r.scalar_one_or_none.return_value = v
        return r

    def _scalars(lst):
        r = MagicMock()
        r.scalars.return_value.all.return_value = lst
        return r

    contact = _fake_contact(workspace_id, name="Quinn Rivera", company="RivTech", status="customer")

    now = _dt.datetime.utcnow()
    # Two closed deals for contact — each ~30 days to close
    contact_deal_a = MagicMock()
    contact_deal_a.stage = "closed_won"
    contact_deal_a.created_at = now - _dt.timedelta(days=30)
    contact_deal_a.stage_changed_at = now
    contact_deal_b = MagicMock()
    contact_deal_b.stage = "closed_won"
    contact_deal_b.created_at = now - _dt.timedelta(days=26)
    contact_deal_b.stage_changed_at = now

    # Workspace deals — contact deals plus a slower one averaging 42 days
    ws_deal_extra = MagicMock()
    ws_deal_extra.stage = "closed_lost"
    ws_deal_extra.created_at = now - _dt.timedelta(days=70)
    ws_deal_extra.stage_changed_at = now

    mock_db.execute = AsyncMock(side_effect=[
        _sone(contact),                                        # contact lookup
        _scalars([contact_deal_a, contact_deal_b]),            # contact closed deals
        _scalars([contact_deal_a, contact_deal_b, ws_deal_extra]),  # workspace closed deals
    ])

    response_json = _json.dumps({
        "velocity_rating": "fast",
        "insight": "Deals with this contact close 33% faster than the workspace average.",
    })
    mock_resp = MagicMock()
    mock_resp.content = [MagicMock(text=response_json)]

    with patch("app.routers.ai._anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = mock_resp

        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(
                f"/workspaces/{workspace_id}/ai/contacts/{contact.id}/deal-velocity-benchmark"
            )

    assert resp.status_code == 200
    body = resp.json()
    assert body["velocity_rating"] in {"fast", "on_par", "slow"}
    assert body["velocity_rating"] == "fast"
    assert body["contact_avg_days"] is not None
    assert body["workspace_avg_days"] is not None
    assert isinstance(body["stage_breakdown"], list)
    assert isinstance(body["insight"], str)
    assert len(body["insight"]) > 0
    assert body["contact_id"] == str(contact.id)
    assert "generated_at" in body


@pytest.mark.asyncio
async def test_contact_deal_velocity_benchmark_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")
    contact_id = uuid.uuid4()

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{wrong_id}/ai/contacts/{contact_id}/deal-velocity-benchmark"
        )

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_contact_deal_outcome_predictor_returns_structured_response(app_client):
    """deal-outcome-predictor returns predicted_outcome, confidence, key_risks, recommended_actions."""
    import json as _json

    fastapi_app, mock_db, workspace_id = app_client

    def _sone(v):
        r = MagicMock()
        r.scalar_one_or_none.return_value = v
        return r

    def _scalars(lst):
        r = MagicMock()
        r.scalars.return_value.all.return_value = lst
        return r

    contact = _fake_contact(workspace_id, name="Petra Lang", company="LangCo", status="customer")

    deal_a = MagicMock()
    deal_a.title = "LangCo Enterprise"
    deal_a.stage = "proposal"
    deal_a.value = 45000.0
    deal_a.health_score = 78
    deal_a.ml_win_probability = 65

    deal_b = MagicMock()
    deal_b.title = "LangCo Upsell"
    deal_b.stage = "negotiation"
    deal_b.value = 12000.0
    deal_b.health_score = 82
    deal_b.ml_win_probability = 70

    mock_db.execute = AsyncMock(side_effect=[
        _sone(contact),
        _scalars([deal_a, deal_b]),
    ])

    response_json = _json.dumps({
        "predicted_outcome": "win",
        "confidence": "high",
        "key_risks": [
            "Competitor pricing pressure in negotiation stage.",
            "Champion may not have full budget authority.",
            "Deal may slip if decision delayed past quarter end.",
        ],
        "recommended_actions": [
            "Schedule executive alignment call this week.",
            "Send ROI case study tailored to LangCo vertical.",
            "Offer a limited-time incentive to accelerate signing.",
        ],
    })
    mock_resp = MagicMock()
    mock_resp.content = [MagicMock(text=response_json)]

    with patch("app.routers.ai._anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = mock_resp

        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(
                f"/workspaces/{workspace_id}/ai/contacts/{contact.id}/deal-outcome-predictor"
            )

    assert resp.status_code == 200
    body = resp.json()
    assert body["predicted_outcome"] in {"win", "loss", "stalled"}
    assert body["predicted_outcome"] == "win"
    assert body["confidence"] in {"high", "medium", "low"}
    assert isinstance(body["key_risks"], list)
    assert len(body["key_risks"]) == 3
    assert isinstance(body["recommended_actions"], list)
    assert len(body["recommended_actions"]) == 3
    assert body["contact_id"] == str(contact.id)
    assert "generated_at" in body


@pytest.mark.asyncio
async def test_contact_deal_outcome_predictor_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
    contact_id = uuid.uuid4()

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{wrong_id}/ai/contacts/{contact_id}/deal-outcome-predictor"
        )

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_contact_deal_portfolio_overview_returns_structured_response(app_client):
    """deal-portfolio-overview returns pipeline_health, totals, highlights x3, risks x3."""
    import json as _json

    fastapi_app, mock_db, workspace_id = app_client

    def _sone(v):
        r = MagicMock()
        r.scalar_one_or_none.return_value = v
        return r

    def _scalars(lst):
        r = MagicMock()
        r.scalars.return_value.all.return_value = lst
        return r

    contact = _fake_contact(workspace_id, name="Priya Shah", company="ShahCo", status="customer")

    deal_a = MagicMock()
    deal_a.title = "ShahCo Platform"
    deal_a.stage = "proposal"
    deal_a.value = 55000.0
    deal_a.health_score = 80
    deal_a.ml_win_probability = 68

    deal_b = MagicMock()
    deal_b.title = "ShahCo Expansion"
    deal_b.stage = "closed_won"
    deal_b.value = 30000.0
    deal_b.health_score = None
    deal_b.ml_win_probability = None

    mock_db.execute = AsyncMock(side_effect=[
        _sone(contact),
        _scalars([deal_a, deal_b]),
    ])

    response_json = _json.dumps({
        "pipeline_health": "strong",
        "highlights": [
            "One deal in proposal stage worth $55K shows active pipeline.",
            "Previously closed $30K deal demonstrates proven buying relationship.",
            "Average health score of 80 indicates strong deal momentum.",
        ],
        "risks": [
            "Single open deal creates pipeline concentration risk.",
            "No early-stage deals to replenish pipeline post-close.",
            "Proposal stage can stall without executive alignment.",
        ],
    })
    mock_resp = MagicMock()
    mock_resp.content = [MagicMock(text=response_json)]

    with patch("app.routers.ai._anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = mock_resp

        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(
                f"/workspaces/{workspace_id}/ai/contacts/{contact.id}/deal-portfolio-overview"
            )

    assert resp.status_code == 200
    body = resp.json()
    assert body["pipeline_health"] in {"strong", "at_risk", "mixed"}
    assert body["pipeline_health"] == "strong"
    assert isinstance(body["total_pipeline_value"], (int, float))
    assert body["open_deal_count"] == 1
    assert isinstance(body["highlights"], list) and len(body["highlights"]) == 3
    assert isinstance(body["risks"], list) and len(body["risks"]) == 3
    assert body["contact_id"] == str(contact.id)
    assert "generated_at" in body


@pytest.mark.asyncio
async def test_contact_deal_portfolio_overview_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
    contact_id = uuid.uuid4()

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{wrong_id}/ai/contacts/{contact_id}/deal-portfolio-overview"
        )

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_contact_competitive_positioning_returns_structured_response(app_client):
    """competitive-positioning returns positioning_strength, top_competitor, win_rate, tips x3, diffs x3."""
    import json as _json

    fastapi_app, mock_db, workspace_id = app_client

    def _sone(v):
        r = MagicMock()
        r.scalar_one_or_none.return_value = v
        return r

    def _scalars(lst):
        r = MagicMock()
        r.scalars.return_value.all.return_value = lst
        return r

    contact = _fake_contact(workspace_id, name="Jordan Lee", company="LeeCo", status="prospect")

    deal_a = MagicMock()
    deal_a.title = "LeeCo Platform"
    deal_a.stage = "proposal"
    deal_a.value = 40000.0
    deal_a.health_score = 72
    deal_a.ml_win_probability = 60
    deal_a.competitors = ["Salesforce", "HubSpot"]

    deal_b = MagicMock()
    deal_b.title = "LeeCo Expansion"
    deal_b.stage = "closed_won"
    deal_b.value = 25000.0
    deal_b.health_score = None
    deal_b.ml_win_probability = None
    deal_b.competitors = ["Salesforce"]

    mock_db.execute = AsyncMock(side_effect=[
        _sone(contact),
        _scalars([deal_a, deal_b]),
    ])

    response_json = _json.dumps({
        "positioning_strength": "strong",
        "top_competitor": "Salesforce",
        "win_rate_vs_competitor": 100,
        "positioning_tips": [
            "Lead with agentic AI differentiators to outmanoeuvre Salesforce on intelligence features.",
            "Reference the closed-won deal history to anchor the conversation in proven delivery.",
            "Use the competitive-response analysis to build a tailored battle card for this account.",
        ],
        "differentiators": [
            "NovaCRM's real-time health scoring updates without manual entry — Salesforce requires custom reports.",
            "Unified sales + PM workspace eliminates the tool-switching overhead Salesforce imposes.",
            "Claude-powered semantic search surfaces relevant notes far faster than Salesforce SOQL queries.",
        ],
    })
    mock_resp = MagicMock()
    mock_resp.content = [MagicMock(text=response_json)]

    with patch("app.routers.ai._anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = mock_resp

        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(
                f"/workspaces/{workspace_id}/ai/contacts/{contact.id}/competitive-positioning"
            )

    assert resp.status_code == 200
    body = resp.json()
    assert body["positioning_strength"] in {"strong", "moderate", "weak"}
    assert body["positioning_strength"] == "strong"
    assert body["top_competitor"] == "Salesforce"
    assert isinstance(body["win_rate_vs_competitor"], int)
    assert isinstance(body["positioning_tips"], list) and len(body["positioning_tips"]) == 3
    assert isinstance(body["differentiators"], list) and len(body["differentiators"]) == 3
    assert body["contact_id"] == str(contact.id)
    assert "generated_at" in body


@pytest.mark.asyncio
async def test_contact_competitive_positioning_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
    contact_id = uuid.uuid4()

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{wrong_id}/ai/contacts/{contact_id}/competitive-positioning"
        )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /workspaces/{wid}/ai/contacts/{cid}/meeting-agenda
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_contact_meeting_agenda_returns_structured_response(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    def _sone(obj):
        r = MagicMock()
        r.scalar_one_or_none.return_value = obj
        return r

    def _all(rows):
        r = MagicMock()
        r.all.return_value = rows
        return r

    def _scalars(lst):
        r = MagicMock()
        r.scalars.return_value.all.return_value = lst
        return r

    import json as _json

    contact = _fake_contact(workspace_id)

    mock_db.execute = AsyncMock(side_effect=[
        _sone(contact),   # contact lookup
        _all([]),          # messages + clarity join
        _scalars([]),      # open tasks
        _scalars([]),      # open deals
    ])

    response_json = _json.dumps({
        "opening_hook": "Great to connect — let's align on the deal and open tasks.",
        "agenda_items": [
            {
                "topic": "Deal status check",
                "goal": "Confirm progress and remove blockers.",
                "talking_points": ["Review deal health score.", "Confirm timeline expectations."],
                "time_estimate_mins": 15,
            },
            {
                "topic": "Open task review",
                "goal": "Clear outstanding action items.",
                "talking_points": ["Review open tasks.", "Set due dates."],
                "time_estimate_mins": 10,
            },
            {
                "topic": "Competitive landscape",
                "goal": "Understand competitive dynamics.",
                "talking_points": ["Ask about competitors.", "Reinforce differentiators."],
                "time_estimate_mins": 10,
            },
            {
                "topic": "Next steps",
                "goal": "Agree on next actions.",
                "talking_points": ["Summarise actions.", "Schedule next call."],
                "time_estimate_mins": 5,
            },
        ],
    })
    mock_resp = MagicMock()
    mock_resp.content = [MagicMock(text=response_json)]

    with patch("app.routers.ai._anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = mock_resp

        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(
                f"/workspaces/{workspace_id}/ai/contacts/{contact.id}/meeting-agenda"
            )

    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["opening_hook"], str) and len(body["opening_hook"]) > 0
    assert isinstance(body["agenda_items"], list) and len(body["agenda_items"]) == 4
    for item in body["agenda_items"]:
        assert "topic" in item and isinstance(item["topic"], str)
        assert "goal" in item and isinstance(item["goal"], str)
        assert isinstance(item["talking_points"], list) and len(item["talking_points"]) == 2
        assert item["time_estimate_mins"] in (5, 10, 15)
    assert body["contact_id"] == str(contact.id)
    assert "generated_at" in body


@pytest.mark.asyncio
async def test_contact_meeting_agenda_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
    contact_id = uuid.uuid4()

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{wrong_id}/ai/contacts/{contact_id}/meeting-agenda"
        )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /workspaces/{wid}/ai/contacts/{cid}/communication-gap-analysis
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_contact_communication_gap_analysis_returns_structured_response(app_client):
    import json as _json
    import datetime as _datetime

    fastapi_app, mock_db, workspace_id = app_client

    def _sone(obj):
        r = MagicMock()
        r.scalar_one_or_none.return_value = obj
        return r

    def _scalars(lst):
        r = MagicMock()
        r.scalars.return_value.all.return_value = lst
        return r

    contact = _fake_contact(workspace_id)

    dt1 = _datetime.datetime(2026, 8, 1, tzinfo=_datetime.timezone.utc)
    dt2 = _datetime.datetime(2026, 8, 8, tzinfo=_datetime.timezone.utc)
    dt3 = _datetime.datetime(2026, 8, 20, tzinfo=_datetime.timezone.utc)
    ws_dts = [
        _datetime.datetime(2026, 8, 1, tzinfo=_datetime.timezone.utc),
        _datetime.datetime(2026, 8, 6, tzinfo=_datetime.timezone.utc),
        _datetime.datetime(2026, 8, 11, tzinfo=_datetime.timezone.utc),
        _datetime.datetime(2026, 8, 16, tzinfo=_datetime.timezone.utc),
        _datetime.datetime(2026, 8, 21, tzinfo=_datetime.timezone.utc),
    ]

    mock_db.execute = AsyncMock(side_effect=[
        _sone(contact),
        _scalars([dt1, dt2, dt3]),
        _scalars(ws_dts),
    ])

    response_json = _json.dumps({
        "recommendations": [
            "Send a personalised check-in email referencing a recent industry event.",
            "Schedule a 15-minute reconnect call to surface any unaddressed concerns.",
            "Share a relevant case study to provide value and re-open the conversation.",
        ]
    })
    mock_resp = MagicMock()
    mock_resp.content = [MagicMock(text=response_json)]

    with patch("app.routers.ai._anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = mock_resp

        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(
                f"/workspaces/{workspace_id}/ai/contacts/{contact.id}/communication-gap-analysis"
            )

    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["avg_gap_days"], (int, float))
    assert isinstance(body["longest_silence_days"], (int, float))
    assert isinstance(body["workspace_avg_gap_days"], (int, float))
    assert body["gap_assessment"] in ("frequent", "normal", "sparse", "dark")
    assert body["risk_level"] in ("low", "medium", "high", "critical")
    assert isinstance(body["recommendations"], list) and len(body["recommendations"]) == 3
    assert all(isinstance(r, str) for r in body["recommendations"])
    assert body["contact_id"] == str(contact.id)
    assert "generated_at" in body


@pytest.mark.asyncio
async def test_contact_communication_gap_analysis_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
    contact_id = uuid.uuid4()

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{wrong_id}/ai/contacts/{contact_id}/communication-gap-analysis"
        )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /workspaces/{wid}/ai/contacts/{cid}/sentiment-trend
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_contact_sentiment_trend_returns_structured_response(app_client):
    import json as _json
    import datetime as _datetime

    fastapi_app, mock_db, workspace_id = app_client

    def _sone(obj):
        r = MagicMock()
        r.scalar_one_or_none.return_value = obj
        return r

    def _all_rows(rows):
        r = MagicMock()
        r.all.return_value = rows
        return r

    contact = _fake_contact(workspace_id)

    dt1 = _datetime.datetime(2026, 8, 1, tzinfo=_datetime.timezone.utc)
    dt2 = _datetime.datetime(2026, 8, 15, tzinfo=_datetime.timezone.utc)

    mock_db.execute = AsyncMock(side_effect=[
        _sone(contact),
        _all_rows([(dt2, "Some issues lately."), (dt1, "Great product, very happy!")]),
    ])

    response_json = _json.dumps({
        "sentiment_points": [
            {"received_at": dt1.isoformat(), "score": 0.8},
            {"received_at": dt2.isoformat(), "score": -0.3},
        ],
        "recommendations": [
            "Address the recent concerns promptly with a personalised follow-up.",
            "Schedule a review call to rebuild trust and surface blockers.",
            "Share a success story relevant to their use case to re-engage.",
        ],
    })
    mock_resp = MagicMock()
    mock_resp.content = [MagicMock(text=response_json)]

    with patch("app.routers.ai._anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = mock_resp

        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(
                f"/workspaces/{workspace_id}/ai/contacts/{contact.id}/sentiment-trend"
            )

    assert resp.status_code == 200
    body = resp.json()
    assert body["messages_analyzed"] == 2
    assert isinstance(body["avg_sentiment"], (int, float))
    assert body["trend_direction"] in ("improving", "stable", "declining")
    assert isinstance(body["recent_sentiment"], (int, float))
    assert isinstance(body["oldest_sentiment"], (int, float))
    assert isinstance(body["sentiment_points"], list)
    assert isinstance(body["recommendations"], list) and len(body["recommendations"]) == 3
    assert all(isinstance(r, str) for r in body["recommendations"])
    assert body["contact_id"] == str(contact.id)
    assert "generated_at" in body


@pytest.mark.asyncio
async def test_contact_sentiment_trend_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
    contact_id = uuid.uuid4()

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{wrong_id}/ai/contacts/{contact_id}/sentiment-trend"
        )
    assert resp.status_code == 403


# POST /workspaces/{wid}/ai/contacts/{cid}/account-plan
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_contact_account_plan_returns_structured_response(app_client):
    import json as _json

    fastapi_app, mock_db, workspace_id = app_client

    def _sone(obj):
        r = MagicMock()
        r.scalar_one_or_none.return_value = obj
        return r

    def _all_rows(rows):
        r = MagicMock()
        r.all.return_value = rows
        return r

    def _scalar(val):
        r = MagicMock()
        r.scalar.return_value = val
        return r

    contact = _fake_contact(workspace_id, name="Acme Corp", status="customer")

    response_json = _json.dumps({
        "account_status": "strategic",
        "plan_horizon": 180,
        "objectives": [
            {"objective": "Close expansion deal", "metric": "$120K ARR", "timeline": "60 days"},
            {"objective": "Onboard exec sponsor", "metric": "Monthly EBR", "timeline": "30 days"},
            {"objective": "Drive adoption to 80%", "metric": "8/10 modules active", "timeline": "90 days"},
        ],
        "key_risks": [
            "Competitor pitching renewal alternative",
            "Budget freeze risk",
            "Single point of contact",
        ],
        "recommended_actions": [
            "Present ROI case study to CFO",
            "Schedule exec alignment call",
            "Provide dedicated CSM support",
        ],
    })
    mock_resp = MagicMock()
    mock_resp.content = [MagicMock(text=response_json)]

    mock_db.execute = AsyncMock(side_effect=[
        _sone(contact),
        _all_rows([]),
        _scalar(2),
        _all_rows([]),
    ])

    with patch("app.routers.ai._anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = mock_resp

        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(
                f"/workspaces/{workspace_id}/ai/contacts/{contact.id}/account-plan"
            )

    assert resp.status_code == 200
    body = resp.json()
    assert body["account_status"] in ("strategic", "growth", "maintain", "at_risk")
    assert body["plan_horizon"] in (30, 90, 180)
    assert isinstance(body["objectives"], list) and len(body["objectives"]) == 3
    for obj in body["objectives"]:
        assert "objective" in obj and "metric" in obj and "timeline" in obj
    assert isinstance(body["key_risks"], list) and len(body["key_risks"]) == 3
    assert isinstance(body["recommended_actions"], list) and len(body["recommended_actions"]) == 3
    assert body["contact_id"] == str(contact.id)
    assert "generated_at" in body


@pytest.mark.asyncio
async def test_contact_account_plan_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
    contact_id = uuid.uuid4()

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{wrong_id}/ai/contacts/{contact_id}/account-plan"
        )
    assert resp.status_code == 403
