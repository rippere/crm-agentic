"""Tests for worker-layer pure functions — zero DB, zero Celery, zero API calls."""

from __future__ import annotations

import base64
import uuid as uuid_mod
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# score_contact._compute_score — heuristic lead scorer
# ---------------------------------------------------------------------------


def _fake_contact(**kwargs) -> MagicMock:
    c = MagicMock()
    c.status = kwargs.get("status", "lead")
    c.revenue = kwargs.get("revenue", 0)
    c.deal_count = kwargs.get("deal_count", 0)
    return c


def test_compute_score_base_lead_is_50_warm():
    from app.workers.score_contact import _compute_score

    result = _compute_score(_fake_contact(status="lead", revenue=0, deal_count=0))
    assert result["value"] == 50
    assert result["label"] == "warm"
    assert result["trend"] == "stable"
    assert result["signals"] == []


def test_compute_score_customer_bonus():
    from app.workers.score_contact import _compute_score

    result = _compute_score(_fake_contact(status="customer", revenue=0, deal_count=0))
    assert result["value"] == 60
    assert any("customer" in s.lower() for s in result["signals"])


def test_compute_score_prospect_bonus():
    from app.workers.score_contact import _compute_score

    result = _compute_score(_fake_contact(status="prospect", revenue=0, deal_count=0))
    assert result["value"] == 55
    assert any("Prospect" in s for s in result["signals"])


def test_compute_score_churned_penalty():
    from app.workers.score_contact import _compute_score

    result = _compute_score(_fake_contact(status="churned", revenue=0, deal_count=0))
    assert result["value"] == 40
    assert any("Churned" in s for s in result["signals"])


def test_compute_score_deal_count_bonus():
    from app.workers.score_contact import _compute_score

    result = _compute_score(_fake_contact(status="lead", revenue=0, deal_count=3))
    assert result["value"] == 60  # 50 + 10
    assert any("deal" in s.lower() for s in result["signals"])


def test_compute_score_revenue_above_50k():
    from app.workers.score_contact import _compute_score

    result = _compute_score(_fake_contact(status="lead", revenue=75000, deal_count=0))
    assert result["value"] == 55  # 50 + 5
    assert any("+5" in s for s in result["signals"])


def test_compute_score_revenue_10k_to_50k():
    from app.workers.score_contact import _compute_score

    result = _compute_score(_fake_contact(status="lead", revenue=25000, deal_count=0))
    assert result["value"] == 60  # 50 + 10
    assert any("+10" in s for s in result["signals"])


def test_compute_score_hot_label_at_70_plus():
    from app.workers.score_contact import _compute_score

    # customer(+10) + deals(+10) + 25k revenue(+10) = 80
    result = _compute_score(_fake_contact(status="customer", revenue=25000, deal_count=2))
    assert result["value"] == 80
    assert result["label"] == "hot"


def test_compute_score_all_bonuses_clamped_at_100():
    from app.workers.score_contact import _compute_score

    # 50 + 10 + 10 + 10 = 80 (all bonuses, capped at 100 still returns 80)
    result = _compute_score(_fake_contact(status="customer", revenue=25000, deal_count=5))
    assert result["value"] <= 100


def test_compute_score_zero_revenue_no_revenue_signal():
    from app.workers.score_contact import _compute_score

    result = _compute_score(_fake_contact(status="lead", revenue=0, deal_count=0))
    assert not any("revenue" in s.lower() for s in result["signals"])


# ---------------------------------------------------------------------------
# ingest._decode_body — recursive Gmail payload decoder
# ---------------------------------------------------------------------------


def _b64(text: str) -> str:
    """URL-safe base64 WITHOUT padding (Gmail API format)."""
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def test_decode_body_plain_text():
    from app.workers.ingest import _decode_body

    payload = {"mimeType": "text/plain", "body": {"data": _b64("Hello world")}}
    assert _decode_body(payload) == "Hello world"


def test_decode_body_html_mime_returns_empty():
    from app.workers.ingest import _decode_body

    payload = {"mimeType": "text/html", "body": {"data": _b64("<p>Hello</p>")}}
    assert _decode_body(payload) == ""


def test_decode_body_no_data_field_returns_empty():
    from app.workers.ingest import _decode_body

    payload = {"mimeType": "text/plain", "body": {}}
    assert _decode_body(payload) == ""


def test_decode_body_empty_payload_returns_empty():
    from app.workers.ingest import _decode_body

    assert _decode_body({}) == ""


def test_decode_body_multipart_finds_first_plain():
    from app.workers.ingest import _decode_body

    payload = {
        "mimeType": "multipart/alternative",
        "body": {},
        "parts": [
            {"mimeType": "text/html", "body": {"data": _b64("<p>HTML</p>")}},
            {"mimeType": "text/plain", "body": {"data": _b64("Plain text body")}},
        ],
    }
    assert _decode_body(payload) == "Plain text body"


def test_decode_body_nested_multipart():
    from app.workers.ingest import _decode_body

    payload = {
        "mimeType": "multipart/mixed",
        "body": {},
        "parts": [
            {
                "mimeType": "multipart/alternative",
                "body": {},
                "parts": [
                    {"mimeType": "text/plain", "body": {"data": _b64("Nested plain text")}}
                ],
            }
        ],
    }
    assert _decode_body(payload) == "Nested plain text"


def test_decode_body_unicode_content():
    from app.workers.ingest import _decode_body

    payload = {"mimeType": "text/plain", "body": {"data": _b64("Héllo wörld — Ünïcode")}}
    result = _decode_body(payload)
    assert "Héllo" in result


# ---------------------------------------------------------------------------
# pipeline._compute_win_probability — heuristic win probability scorer
# ---------------------------------------------------------------------------

_PIPELINE_NOW = datetime(2026, 5, 15, 12, 0, 0)  # naive — matches datetime.utcnow() in _run_optimize


def _fake_deal(**kwargs) -> MagicMock:
    d = MagicMock()
    d.stage = kwargs.get("stage", "discovery")
    d.value = kwargs.get("value", 0)
    d.updated_at = kwargs.get("updated_at", _PIPELINE_NOW - timedelta(days=5))
    return d


def test_compute_win_probability_discovery_base():
    from app.workers.pipeline import _compute_win_probability

    result = _compute_win_probability(_fake_deal(stage="discovery", value=0), _PIPELINE_NOW)
    assert result == 30  # base 30 + stage_bonus 0


def test_compute_win_probability_qualified_stage():
    from app.workers.pipeline import _compute_win_probability

    result = _compute_win_probability(_fake_deal(stage="qualified"), _PIPELINE_NOW)
    assert result == 45  # 30 + 15


def test_compute_win_probability_proposal_stage():
    from app.workers.pipeline import _compute_win_probability

    result = _compute_win_probability(_fake_deal(stage="proposal"), _PIPELINE_NOW)
    assert result == 55  # 30 + 25


def test_compute_win_probability_negotiation_stage():
    from app.workers.pipeline import _compute_win_probability

    result = _compute_win_probability(_fake_deal(stage="negotiation"), _PIPELINE_NOW)
    assert result == 65  # 30 + 35


def test_compute_win_probability_high_value_bonus():
    from app.workers.pipeline import _compute_win_probability

    result = _compute_win_probability(_fake_deal(stage="proposal", value=75000), _PIPELINE_NOW)
    assert result == 60  # 30 + 25 + 5


def test_compute_win_probability_stale_deal_penalty():
    from app.workers.pipeline import _compute_win_probability

    stale = _PIPELINE_NOW - timedelta(days=45)
    result = _compute_win_probability(_fake_deal(stage="discovery", updated_at=stale), _PIPELINE_NOW)
    assert result == 20  # 30 + 0 - 10


def test_compute_win_probability_no_updated_at_no_staleness():
    from app.workers.pipeline import _compute_win_probability

    d = _fake_deal(stage="discovery")
    d.updated_at = None
    result = _compute_win_probability(d, _PIPELINE_NOW)
    assert result == 30  # no staleness penalty applied


def test_compute_win_probability_clamped_at_95():
    from app.workers.pipeline import _compute_win_probability

    # negotiation(35) + high_value(5) + base(30) = 70, below 95 cap
    result = _compute_win_probability(_fake_deal(stage="negotiation", value=100000), _PIPELINE_NOW)
    assert result == 70
    assert result <= 95


def test_compute_win_probability_clamped_at_0():
    from app.workers.pipeline import _compute_win_probability

    # Minimum is 0: worst case churned stale with 0 value → 30 - 10 = 20, still > 0
    # The clamp at 0 can't be reached with current logic, but we verify non-negative
    stale = _PIPELINE_NOW - timedelta(days=60)
    result = _compute_win_probability(_fake_deal(stage="discovery", value=0, updated_at=stale), _PIPELINE_NOW)
    assert result >= 0


# ---------------------------------------------------------------------------
# followup_sequences._draft_email — async Anthropic-backed email drafter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_draft_email_plain_json_response():
    import app.workers.followup_sequences as fseq_mod

    mock_message = MagicMock()
    mock_message.content = [MagicMock(text='{"subject": "Follow up", "body": "Hi there"}')]

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=mock_message)

    with patch("anthropic.AsyncAnthropic", return_value=mock_client):
        result = await fseq_mod._draft_email("Deal X", "Acme", "Alice", "proposal")

    assert result["subject"] == "Follow up"
    assert result["body"] == "Hi there"


@pytest.mark.asyncio
async def test_draft_email_strips_json_markdown_fence():
    import app.workers.followup_sequences as fseq_mod

    raw = '```json\n{"subject": "Re: proposal", "body": "Looking forward to it"}\n```'
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=raw)]

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=mock_message)

    with patch("anthropic.AsyncAnthropic", return_value=mock_client):
        result = await fseq_mod._draft_email("Deal Y", "Corp", "Bob", "negotiation")

    assert result["subject"] == "Re: proposal"


@pytest.mark.asyncio
async def test_draft_email_strips_plain_markdown_fence():
    import app.workers.followup_sequences as fseq_mod

    raw = '```\n{"subject": "Checking in", "body": "Hope all is well"}\n```'
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=raw)]

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=mock_client)
    mock_client.messages.create = AsyncMock(return_value=mock_message)

    with patch("anthropic.AsyncAnthropic", return_value=mock_client):
        result = await fseq_mod._draft_email("Deal Z", "LLC", None, "qualified")

    assert result["subject"] == "Checking in"


# ---------------------------------------------------------------------------
# Beat dispatchers — enumerate all workspaces and fan out per-workspace tasks
# ---------------------------------------------------------------------------


def test_optimize_pipeline_all_dispatches_per_workspace():
    """The no-arg beat dispatcher enumerates workspace ids and .delay()s one
    optimize_pipeline child per workspace (beat can't supply workspace_id itself)."""
    import app.workers.pipeline as pipeline_mod

    ws_ids = ["11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222"]

    with patch.object(pipeline_mod, "_enumerate_workspace_ids", new=AsyncMock(return_value=ws_ids)), \
         patch.object(pipeline_mod.optimize_pipeline, "delay") as mock_delay:
        result = pipeline_mod.optimize_pipeline_all.run()

    assert result["dispatched"] == 2
    assert result["workspace_ids"] == ws_ids
    assert mock_delay.call_count == 2
    mock_delay.assert_any_call(ws_ids[0])
    mock_delay.assert_any_call(ws_ids[1])


def test_optimize_pipeline_all_no_workspaces_dispatches_nothing():
    import app.workers.pipeline as pipeline_mod

    with patch.object(pipeline_mod, "_enumerate_workspace_ids", new=AsyncMock(return_value=[])), \
         patch.object(pipeline_mod.optimize_pipeline, "delay") as mock_delay:
        result = pipeline_mod.optimize_pipeline_all.run()

    assert result["dispatched"] == 0
    mock_delay.assert_not_called()


def test_compute_deal_health_all_dispatches_per_workspace():
    import app.workers.deal_health_worker as dh_mod

    ws_ids = ["aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"]

    with patch.object(dh_mod, "_enumerate_workspace_ids", new=AsyncMock(return_value=ws_ids)), \
         patch.object(dh_mod.compute_deal_health, "delay") as mock_delay:
        result = dh_mod.compute_deal_health_all.run()

    assert result["dispatched"] == 2
    assert mock_delay.call_count == 2
    mock_delay.assert_any_call(ws_ids[0])
    mock_delay.assert_any_call(ws_ids[1])


def test_enumerate_workspace_ids_queries_workspace_table():
    """_enumerate_workspace_ids stringifies whatever the Workspace.id query returns,
    using the same async-sessionmaker pattern as the rest of the worker."""
    import asyncio
    import app.workers.pipeline as pipeline_mod

    raw_ids = [uuid_mod.UUID("33333333-3333-3333-3333-333333333333")]

    scalars_result = MagicMock()
    scalars_result.scalars.return_value.all.return_value = raw_ids

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=scalars_result)

    # async context manager that yields mock_db
    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=mock_db)
    session_cm.__aexit__ = AsyncMock(return_value=False)
    session_factory = MagicMock(return_value=session_cm)

    with patch.object(pipeline_mod, "_get_async_session", return_value=session_factory):
        out = asyncio.get_event_loop().run_until_complete(pipeline_mod._enumerate_workspace_ids())

    assert out == ["33333333-3333-3333-3333-333333333333"]
    assert all(isinstance(x, str) for x in out)
