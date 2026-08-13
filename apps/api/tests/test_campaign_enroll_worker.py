"""Tests for the campaign_enroll worker — mocked async session, zero DB / Celery / creds.

Mirrors the mocking idiom in tests/test_workers.py: patch the module's
`_get_async_session` with a factory that yields an AsyncMock db whose
`execute` is driven by a side_effect list of fake result objects.
"""

from __future__ import annotations

import asyncio
import uuid as uuid_mod
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_WS_ID = uuid_mod.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_CAMP_ID = uuid_mod.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
_SEG_ID = uuid_mod.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
_SEQ_ID = uuid_mod.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _scalar_result(obj):
    r = MagicMock()
    r.scalar_one_or_none.return_value = obj
    return r


def _rows_result(rows):
    """Result whose .all() returns row tuples (the resolve query shape)."""
    r = MagicMock()
    r.all.return_value = rows
    return r


def _returning_result(ids):
    """Result whose .scalars().all() returns inserted ids (the ON CONFLICT insert)."""
    r = MagicMock()
    r.scalars.return_value.all.return_value = ids
    return r


def _fake_campaign(segment_id=_SEG_ID, sequence_id=_SEQ_ID, scheduled_at=None, stats=None):
    c = MagicMock()
    c.id = _CAMP_ID
    c.workspace_id = _WS_ID
    c.segment_id = segment_id
    c.sequence_id = sequence_id
    c.scheduled_at = scheduled_at
    c.stats = stats if stats is not None else {}
    c.name = "Spring Blast"
    return c


def _fake_segment(kind="static", seg_filter=None):
    s = MagicMock()
    s.id = _SEG_ID
    s.workspace_id = _WS_ID
    s.kind = kind
    s.filter = seg_filter or {}
    s.name = "Warm Leads"
    return s


def _patched_session(db):
    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=db)
    session_cm.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=session_cm)


def _run(workspace_id=str(_WS_ID), campaign_id=str(_CAMP_ID), *, execute_results, db=None):
    import app.workers.campaign_enroll as mod

    if db is None:
        db = AsyncMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
    db.execute = AsyncMock(side_effect=execute_results)

    with patch.object(mod, "_get_async_session", return_value=_patched_session(db)):
        result = asyncio.run(mod._run_enroll(workspace_id, campaign_id))
    return result, db


# ---------------------------------------------------------------------------
# _dynamic_filter_conditions — pure filter -> SQL condition translation
# ---------------------------------------------------------------------------


def _compile(cond):
    from sqlalchemy.dialects import postgresql

    return str(cond.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


def test_dynamic_filter_always_scopes_workspace():
    from app.workers.campaign_enroll import _dynamic_filter_conditions

    conds = _dynamic_filter_conditions(_WS_ID, {})
    assert len(conds) == 1
    assert "workspace_id" in _compile(conds[0])


def test_dynamic_filter_scalar_stage_and_min_score():
    from app.workers.campaign_enroll import _dynamic_filter_conditions

    conds = _dynamic_filter_conditions(_WS_ID, {"stage": "engaged", "min_score": 40})
    sql = " ".join(_compile(c) for c in conds)
    assert "stage" in sql and "engaged" in sql
    assert "score >= 40" in sql


def test_dynamic_filter_list_source_uses_in():
    from app.workers.campaign_enroll import _dynamic_filter_conditions

    conds = _dynamic_filter_conditions(_WS_ID, {"source": ["web", "referral"]})
    sql = " ".join(_compile(c) for c in conds)
    assert "IN" in sql.upper()
    assert "web" in sql and "referral" in sql


def test_dynamic_filter_ignores_unknown_keys():
    from app.workers.campaign_enroll import _dynamic_filter_conditions

    # only workspace scope, unknown key produces no extra condition
    conds = _dynamic_filter_conditions(_WS_ID, {"totally_unknown": "x"})
    assert len(conds) == 1


def test_dynamic_filter_non_dict_is_safe():
    from app.workers.campaign_enroll import _dynamic_filter_conditions

    conds = _dynamic_filter_conditions(_WS_ID, None)  # type: ignore[arg-type]
    assert len(conds) == 1


# ---------------------------------------------------------------------------
# _resolve_segment_lead_ids — static join vs dynamic eval
# ---------------------------------------------------------------------------


def test_resolve_static_reads_member_join():
    from app.workers.campaign_enroll import _resolve_segment_lead_ids

    lead_a = uuid_mod.uuid4()
    lead_b = uuid_mod.uuid4()
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_rows_result([(lead_a,), (lead_b,)]))

    out = asyncio.run(_resolve_segment_lead_ids(db, _WS_ID, _fake_segment(kind="static")))
    assert out == [lead_a, lead_b]


def test_resolve_dynamic_evaluates_filter():
    from app.workers.campaign_enroll import _resolve_segment_lead_ids

    lead_a = uuid_mod.uuid4()
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_rows_result([(lead_a,)]))

    seg = _fake_segment(kind="dynamic", seg_filter={"stage": "engaged"})
    out = asyncio.run(_resolve_segment_lead_ids(db, _WS_ID, seg))
    assert out == [lead_a]
    db.execute.assert_awaited_once()


# ---------------------------------------------------------------------------
# _run_enroll — full enrollment flow
# ---------------------------------------------------------------------------


def test_enroll_one_row_per_lead_bumps_stats_and_commits():
    """Two segment leads -> two enrollment rows inserted, stats.enrolled bumped by 2."""
    lead_a, lead_b = uuid_mod.uuid4(), uuid_mod.uuid4()
    campaign = _fake_campaign(stats={})
    result, db = _run(
        execute_results=[
            _scalar_result(campaign),                    # load campaign
            _scalar_result(_fake_segment()),             # load segment
            _rows_result([(lead_a,), (lead_b,)]),        # resolve leads
            _returning_result([uuid_mod.uuid4(), uuid_mod.uuid4()]),  # insert returns 2 ids
        ],
    )

    assert result["resolved"] == 2
    assert result["enrolled"] == 2
    assert campaign.stats["enrolled"] == 2
    db.commit.assert_awaited_once()
    # ActivityEvent + campaign both added
    assert db.add.call_count >= 2


def test_enroll_on_conflict_does_not_double_count():
    """3 leads resolved but only 1 newly inserted (2 already enrolled) -> enrolled=1."""
    leads = [(uuid_mod.uuid4(),) for _ in range(3)]
    campaign = _fake_campaign(stats={"enrolled": 5})
    result, db = _run(
        execute_results=[
            _scalar_result(campaign),
            _scalar_result(_fake_segment()),
            _rows_result(leads),
            _returning_result([uuid_mod.uuid4()]),  # ON CONFLICT dropped 2, only 1 returned
        ],
    )

    assert result["resolved"] == 3
    assert result["enrolled"] == 1
    assert campaign.stats["enrolled"] == 6  # 5 + 1, not 5 + 3


def test_enroll_scheduled_at_used_as_next_run_at():
    """When the campaign has scheduled_at, it flows into the inserted row values."""
    import app.workers.campaign_enroll as mod

    sched = datetime(2026, 9, 1, 14, 0, tzinfo=timezone.utc)
    lead_a = uuid_mod.uuid4()
    campaign = _fake_campaign(scheduled_at=sched, stats={})

    captured = {}

    async def _capture_execute(stmt):
        # Fourth call is the insert; capture its compiled values-bearing SQL.
        if "INSERT" in str(stmt).upper():
            from sqlalchemy.dialects import postgresql

            captured["sql"] = str(
                stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
            )
            return _returning_result([uuid_mod.uuid4()])
        _capture_execute.calls.append(stmt)
        return _capture_execute.results.pop(0)

    _capture_execute.calls = []
    _capture_execute.results = [
        _scalar_result(campaign),
        _scalar_result(_fake_segment()),
        _rows_result([(lead_a,)]),
    ]

    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.execute = _capture_execute

    with patch.object(mod, "_get_async_session", return_value=_patched_session(db)):
        result = asyncio.run(mod._run_enroll(str(_WS_ID), str(_CAMP_ID)))

    assert result["enrolled"] == 1
    assert "2026-09-01" in captured["sql"]


def test_enroll_campaign_not_found_returns_error():
    result, db = _run(execute_results=[_scalar_result(None)])
    assert result["error"] == "Campaign not found"
    db.commit.assert_not_called()


def test_enroll_missing_segment_id_short_circuits():
    campaign = _fake_campaign(segment_id=None)
    result, db = _run(execute_results=[_scalar_result(campaign)])
    assert result["enrolled"] == 0
    assert "missing segment_id" in result["reason"]
    db.commit.assert_not_called()


def test_enroll_segment_not_found_returns_error():
    campaign = _fake_campaign()
    result, db = _run(
        execute_results=[
            _scalar_result(campaign),
            _scalar_result(None),  # segment missing
        ],
    )
    assert result["error"] == "Segment not found"
    db.commit.assert_not_called()


def test_enroll_no_resolved_leads_enrolls_zero_but_still_commits():
    """Empty segment: no insert issued, enrolled=0, but an audit event + commit still land."""
    campaign = _fake_campaign(stats={"enrolled": 0})
    result, db = _run(
        execute_results=[
            _scalar_result(campaign),
            _scalar_result(_fake_segment()),
            _rows_result([]),  # zero leads
        ],
    )
    assert result["resolved"] == 0
    assert result["enrolled"] == 0
    assert campaign.stats["enrolled"] == 0
    db.commit.assert_awaited_once()


# ---------------------------------------------------------------------------
# celery task wrapper
# ---------------------------------------------------------------------------


def test_task_wrapper_delegates_to_async_run():
    import app.workers.campaign_enroll as mod

    with patch.object(mod, "_run_enroll", new=AsyncMock(return_value={"enrolled": 3})):
        out = mod.enroll_campaign.run(str(_WS_ID), str(_CAMP_ID))
    assert out == {"enrolled": 3}


def test_task_registered_under_expected_name():
    import app.workers.campaign_enroll  # noqa: F401  (ensures decorator ran)
    from app.workers.celery_app import celery_app

    assert "app.workers.campaign_enroll.enroll_campaign" in celery_app.tasks
