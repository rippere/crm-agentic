"""Tests for the engagement_score worker — pure functions + beat dispatcher.

Zero DB, zero Celery broker, zero external sends. Mirrors the mocking style in
tests/test_workers.py (MagicMock events, AsyncMock sessions, patched
_get_async_session / _enumerate_workspace_ids).
"""

from __future__ import annotations

import uuid as uuid_mod
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


_NOW = datetime(2026, 8, 13, 12, 0, 0, tzinfo=timezone.utc)


def _ev(type_: str, occurred_at: datetime | None = _NOW) -> MagicMock:
    e = MagicMock()
    e.type = type_
    e.occurred_at = occurred_at
    return e


# ---------------------------------------------------------------------------
# _compute_score — weighted sum, window, clamp, label
# ---------------------------------------------------------------------------


def test_compute_score_empty_is_zero_cold():
    from app.workers.engagement_score import _compute_score

    result = _compute_score([], now=_NOW)
    assert result["value"] == 0
    assert result["label"] == "cold"
    assert result["trend"] == "stable"
    assert result["signals"] == []
    assert result["replied"] is False
    assert result["converted"] is False


def test_compute_score_single_open_is_5():
    from app.workers.engagement_score import _compute_score

    assert _compute_score([_ev("opened")], now=_NOW)["value"] == 5


def test_compute_score_weighting_sum():
    from app.workers.engagement_score import _compute_score

    # open+5 + click+15 + reply+30 = 50
    events = [_ev("opened"), _ev("clicked"), _ev("replied")]
    result = _compute_score(events, now=_NOW)
    assert result["value"] == 50
    assert result["label"] == "warm"
    assert result["replied"] is True


def test_compute_score_negative_signals_clamp_at_zero():
    from app.workers.engagement_score import _compute_score

    # open+5 then bounce-20 then unsub-30 = -45 -> clamped to 0
    events = [_ev("opened"), _ev("bounced"), _ev("unsubscribed")]
    assert _compute_score(events, now=_NOW)["value"] == 0


def test_compute_score_clamps_at_100():
    from app.workers.engagement_score import _compute_score

    # 4 conversions = 160 -> clamped to 100
    events = [_ev("converted") for _ in range(4)]
    result = _compute_score(events, now=_NOW)
    assert result["value"] == 100
    assert result["label"] == "hot"
    assert result["converted"] is True


def test_compute_score_hot_label_at_70():
    from app.workers.engagement_score import _compute_score

    # reply+30 + click+15 + converted... use reply+30 + converted+40 = 70
    events = [_ev("replied"), _ev("converted")]
    result = _compute_score(events, now=_NOW)
    assert result["value"] == 70
    assert result["label"] == "hot"


def test_compute_score_ignores_non_engagement_types():
    from app.workers.engagement_score import _compute_score

    # queued/sent/delivered/approved/rejected carry no weight
    events = [_ev("queued"), _ev("sent"), _ev("delivered"), _ev("approved")]
    result = _compute_score(events, now=_NOW)
    assert result["value"] == 0
    assert result["signals"] == []


def test_compute_score_excludes_events_outside_window():
    from app.workers.engagement_score import _compute_score

    old = _NOW - timedelta(days=200)
    events = [_ev("replied", occurred_at=old), _ev("opened", occurred_at=_NOW)]
    # old reply excluded, only the recent open counts
    assert _compute_score(events, now=_NOW, window_days=90)["value"] == 5


def test_compute_score_none_occurred_at_always_counted():
    from app.workers.engagement_score import _compute_score

    assert _compute_score([_ev("clicked", occurred_at=None)], now=_NOW)["value"] == 15


def test_compute_score_signals_describe_counts():
    from app.workers.engagement_score import _compute_score

    events = [_ev("opened"), _ev("opened"), _ev("clicked")]
    result = _compute_score(events, now=_NOW)
    # 2 opens (+10), 1 click (+15) = 25
    assert result["value"] == 25
    joined = " ".join(result["signals"])
    assert "open" in joined
    assert "click" in joined


# ---------------------------------------------------------------------------
# _next_stage — auto-advance thresholds (forward-only)
# ---------------------------------------------------------------------------


def test_next_stage_reply_advances_new_to_engaged():
    from app.workers.engagement_score import _next_stage

    detail = {"value": 30, "replied": True, "converted": False}
    assert _next_stage("new", detail) == "engaged"


def test_next_stage_high_score_and_reply_advances_to_qualified():
    from app.workers.engagement_score import _next_stage

    detail = {"value": 75, "replied": True, "converted": False}
    assert _next_stage("contacted", detail) == "qualified"


def test_next_stage_converted_signal_advances_to_converted():
    from app.workers.engagement_score import _next_stage

    detail = {"value": 40, "replied": False, "converted": True}
    assert _next_stage("engaged", detail) == "converted"


def test_next_stage_no_reply_no_advance():
    from app.workers.engagement_score import _next_stage

    detail = {"value": 20, "replied": False, "converted": False}
    assert _next_stage("new", detail) is None


def test_next_stage_never_regresses():
    from app.workers.engagement_score import _next_stage

    # already qualified; a bare reply (would target engaged) must not pull it back
    detail = {"value": 35, "replied": True, "converted": False}
    assert _next_stage("qualified", detail) is None


def test_next_stage_high_score_reply_does_not_regress_converted():
    from app.workers.engagement_score import _next_stage

    detail = {"value": 90, "replied": True, "converted": False}
    assert _next_stage("converted", detail) is None


def test_next_stage_lost_is_terminal():
    from app.workers.engagement_score import _next_stage

    detail = {"value": 90, "replied": True, "converted": True}
    assert _next_stage("lost", detail) is None


# ---------------------------------------------------------------------------
# _run_score — end-to-end over a mocked async session
# ---------------------------------------------------------------------------


def _scalar_result(obj):
    result = MagicMock()
    result.scalar_one_or_none.return_value = obj
    return result


def _scalars_result(rows):
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows
    return result


def _session_patch(mock_db):
    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=mock_db)
    session_cm.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=session_cm)


def test_run_score_lead_not_found_returns_error():
    import asyncio
    import app.workers.engagement_score as mod

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=_scalar_result(None))

    with patch.object(mod, "_get_async_session", return_value=_session_patch(mock_db)):
        result = asyncio.run(
            mod._run_score(str(uuid_mod.uuid4()), str(uuid_mod.uuid4()))
        )

    assert result["error"] == "Lead not found"


def test_run_score_writes_score_detail_and_advances_stage():
    import asyncio
    import app.workers.engagement_score as mod

    ws_id = uuid_mod.uuid4()
    lead_id = uuid_mod.uuid4()

    lead = MagicMock()
    lead.id = lead_id
    lead.workspace_id = ws_id
    lead.name = "Zach Lead"
    lead.stage = "new"

    events = [_ev("replied"), _ev("opened")]  # 30 + 5 = 35, replied -> engaged

    mock_db = AsyncMock()
    # 1st execute -> lead lookup; 2nd -> engagement events
    mock_db.execute = AsyncMock(side_effect=[
        _scalar_result(lead),
        _scalars_result(events),
    ])
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()

    with patch.object(mod, "_get_async_session", return_value=_session_patch(mock_db)):
        result = asyncio.run(mod._run_score(str(ws_id), str(lead_id)))

    assert result["score"] == 35
    assert result["label"] == "cold"  # 35 < 40
    assert result["stage"] == "engaged"
    assert result["stage_changed"] is True
    assert lead.score == 35
    assert lead.score_detail["value"] == 35
    assert lead.stage == "engaged"
    assert lead.last_engaged_at == _NOW
    mock_db.commit.assert_awaited_once()


def test_run_score_no_events_keeps_stage_and_zero_score():
    import asyncio
    import app.workers.engagement_score as mod

    ws_id = uuid_mod.uuid4()
    lead_id = uuid_mod.uuid4()

    lead = MagicMock()
    lead.name = "Quiet Lead"
    lead.stage = "contacted"

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=[
        _scalar_result(lead),
        _scalars_result([]),
    ])
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()

    with patch.object(mod, "_get_async_session", return_value=_session_patch(mock_db)):
        result = asyncio.run(mod._run_score(str(ws_id), str(lead_id)))

    assert result["score"] == 0
    assert result["stage"] == "contacted"
    assert result["stage_changed"] is False
    assert lead.score == 0


# ---------------------------------------------------------------------------
# Beat dispatcher — score_leads_all fans out per workspace
# ---------------------------------------------------------------------------


def test_score_leads_all_dispatches_per_workspace():
    import app.workers.engagement_score as mod

    ws_ids = [
        "11111111-1111-1111-1111-111111111111",
        "22222222-2222-2222-2222-222222222222",
    ]

    with patch.object(mod, "_enumerate_workspace_ids", new=AsyncMock(return_value=ws_ids)), \
         patch.object(mod.rescore_workspace_leads, "delay") as mock_delay:
        result = mod.score_leads_all.run()

    assert result["dispatched"] == 2
    assert result["workspace_ids"] == ws_ids
    assert mock_delay.call_count == 2
    mock_delay.assert_any_call(ws_ids[0])
    mock_delay.assert_any_call(ws_ids[1])


def test_score_leads_all_no_workspaces_dispatches_nothing():
    import app.workers.engagement_score as mod

    with patch.object(mod, "_enumerate_workspace_ids", new=AsyncMock(return_value=[])), \
         patch.object(mod.rescore_workspace_leads, "delay") as mock_delay:
        result = mod.score_leads_all.run()

    assert result["dispatched"] == 0
    mock_delay.assert_not_called()


def test_rescore_workspace_enqueues_recent_leads():
    import asyncio
    import app.workers.engagement_score as mod

    ws_id = uuid_mod.uuid4()
    lead_ids = [uuid_mod.uuid4(), uuid_mod.uuid4()]

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=_scalars_result(lead_ids))

    with patch.object(mod, "_get_async_session", return_value=_session_patch(mock_db)), \
         patch.object(mod.score_lead_engagement, "delay") as mock_delay:
        result = asyncio.run(mod._run_rescore_workspace(str(ws_id)))

    assert result["enqueued"] == 2
    assert mock_delay.call_count == 2
    for lid in lead_ids:
        mock_delay.assert_any_call(str(ws_id), str(lid))
