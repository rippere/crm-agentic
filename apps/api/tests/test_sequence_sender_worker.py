"""Tests for the sequence_sender worker — pure helpers + tick orchestration.

Zero DB, zero Celery broker, zero external sends. Mirrors the mocking idiom in
tests/test_campaign_enroll_worker.py and tests/test_engagement_score_worker.py:
the DB-touching loaders (_due_enrollments / _load_sequence / _load_step /
_load_lead / _has_event_after_last_send) and the external-send boundary
(_deliver) are patched, so _run_tick's state machine is exercised with no
credentials and no network.
"""

from __future__ import annotations

import asyncio
import uuid as uuid_mod
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_WS_ID = uuid_mod.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_NOW = datetime(2026, 8, 13, 15, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# fixtures / builders
# ---------------------------------------------------------------------------


def _enrollment(*, current_step=0, status="active", last_sent_at=None):
    e = MagicMock()
    e.id = uuid_mod.uuid4()
    e.workspace_id = _WS_ID
    e.campaign_id = uuid_mod.uuid4()
    e.sequence_id = uuid_mod.uuid4()
    e.lead_id = uuid_mod.uuid4()
    e.current_step = current_step
    e.status = status
    e.next_run_at = _NOW - timedelta(hours=1)
    e.last_sent_at = last_sent_at
    return e


def _step(*, step_order=0, channel="email", delay_hours=0, requires_approval=False,
          ai_generate=False, subject="Hi {{name}}", body="Hello {{name}} at {{company}}"):
    s = MagicMock()
    s.id = uuid_mod.uuid4()
    s.step_order = step_order
    s.channel = channel
    s.delay_hours = delay_hours
    s.requires_approval = requires_approval
    s.ai_generate = ai_generate
    s.subject = subject
    s.body_template = body
    return s


def _sequence(settings=None):
    s = MagicMock()
    s.settings = settings if settings is not None else {}
    return s


def _lead(name="Zach", company="Photo Booth Co", email="zach@example.com", phone="+15550001111"):
    l = MagicMock()
    l.name = name
    l.company = company
    l.email = email
    l.phone = phone
    l.title = "Owner"
    return l


def _patched_session(db):
    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=db)
    session_cm.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=session_cm)


def _run_tick(*, enrollments, sequence, steps, lead, replied=False, approved=False,
              deliver_result=None, db=None):
    """Drive _run_tick with all DB loaders + the send boundary patched.

    `steps` is a dict {step_order: step_or_None} consulted by the patched
    _load_step (current + next lookups). `replied`/`approved` drive the
    _has_event_after_last_send gate. Returns (result, db, deliver_mock).
    """
    import app.workers.sequence_sender as mod

    if db is None:
        db = AsyncMock()
        db.add = MagicMock()
        db.commit = AsyncMock()

    async def _fake_load_step(_db, _ws, _seq, order):
        return steps.get(order)

    async def _fake_has_event(_db, _ws, _enr, event_type):
        if event_type == "replied":
            return replied
        if event_type == "approved":
            return approved
        return False

    deliver_mock = AsyncMock(return_value=deliver_result or {"delivered": True, "channel": "email"})

    with patch.object(mod, "_get_async_session", return_value=_patched_session(db)), \
         patch.object(mod, "_due_enrollments", new=AsyncMock(return_value=enrollments)), \
         patch.object(mod, "_load_sequence", new=AsyncMock(return_value=sequence)), \
         patch.object(mod, "_load_step", new=_fake_load_step), \
         patch.object(mod, "_load_lead", new=AsyncMock(return_value=lead)), \
         patch.object(mod, "_has_event_after_last_send", new=_fake_has_event), \
         patch.object(mod, "_deliver", new=deliver_mock):
        result = asyncio.run(mod._run_tick(str(_WS_ID)))
    return result, db, deliver_mock


# ---------------------------------------------------------------------------
# _render_template — token substitution
# ---------------------------------------------------------------------------


def test_render_template_substitutes_tokens():
    from app.workers.sequence_sender import _render_template

    out = _render_template("Hi {{name}} at {{company}}", _lead(name="Zach", company="PB Co"))
    assert out == "Hi Zach at PB Co"


def test_render_template_none_lead_returns_raw():
    from app.workers.sequence_sender import _render_template

    assert _render_template("Hi {{name}}", None) == "Hi {{name}}"


def test_render_template_missing_name_defaults_there():
    from app.workers.sequence_sender import _render_template

    out = _render_template("Hi {{name}}", _lead(name=None))
    assert out == "Hi there"


# ---------------------------------------------------------------------------
# _in_quiet_hours — pure window check
# ---------------------------------------------------------------------------


def test_quiet_hours_absent_is_never_quiet():
    from app.workers.sequence_sender import _in_quiet_hours

    assert _in_quiet_hours(_NOW, {}) is False
    assert _in_quiet_hours(_NOW, None) is False


def test_quiet_hours_same_day_window():
    from app.workers.sequence_sender import _in_quiet_hours

    # quiet 09:00-17:00; _NOW is 15:00 -> quiet
    assert _in_quiet_hours(_NOW, {"quiet_hours": [9, 17]}) is True
    # 15:00 not inside 18:00-20:00
    assert _in_quiet_hours(_NOW, {"quiet_hours": [18, 20]}) is False


def test_quiet_hours_wraps_midnight():
    from app.workers.sequence_sender import _in_quiet_hours

    night = datetime(2026, 8, 13, 23, 0, 0, tzinfo=timezone.utc)
    morning = datetime(2026, 8, 13, 3, 0, 0, tzinfo=timezone.utc)
    day = datetime(2026, 8, 13, 12, 0, 0, tzinfo=timezone.utc)
    # quiet 22:00-07:00
    assert _in_quiet_hours(night, {"quiet_hours": [22, 7]}) is True
    assert _in_quiet_hours(morning, {"quiet_hours": [22, 7]}) is True
    assert _in_quiet_hours(day, {"quiet_hours": [22, 7]}) is False


def test_quiet_hours_dict_form_and_malformed():
    from app.workers.sequence_sender import _in_quiet_hours

    assert _in_quiet_hours(_NOW, {"quiet_hours": {"start": 9, "end": 17}}) is True
    assert _in_quiet_hours(_NOW, {"quiet_hours": "bad"}) is False
    assert _in_quiet_hours(_NOW, {"quiet_hours": [5]}) is False
    assert _in_quiet_hours(_NOW, {"quiet_hours": [9, 9]}) is False


# ---------------------------------------------------------------------------
# _draft_body — Claude guarded, template fallback (no creds)
# ---------------------------------------------------------------------------


def test_draft_body_template_when_not_ai():
    from app.workers.sequence_sender import _draft_body

    step = _step(ai_generate=False, body="Hello {{name}}")
    body, ai = asyncio.run(_draft_body(step, _lead(name="Zach")))
    assert body == "Hello Zach"
    assert ai is False


def test_draft_body_ai_without_key_falls_back_to_template():
    import app.workers.sequence_sender as mod

    step = _step(ai_generate=True, body="Hello {{name}}")
    fake_settings = MagicMock()
    fake_settings.ANTHROPIC_API_KEY = ""
    with patch.dict("sys.modules", {"app.config": MagicMock(settings=fake_settings)}):
        body, ai = asyncio.run(mod._draft_body(step, _lead(name="Zach")))
    assert body == "Hello Zach"
    assert ai is False


# ---------------------------------------------------------------------------
# _run_tick — the state machine
# ---------------------------------------------------------------------------


def test_requires_approval_parks_pending_no_send():
    """A due, approval-gated step on a fresh enrollment -> queued draft, waiting, NO send."""
    enr = _enrollment(current_step=0, status="active")
    step0 = _step(step_order=0, requires_approval=True)
    result, db, deliver = _run_tick(
        enrollments=[enr],
        sequence=_sequence(),
        steps={0: step0},
        lead=_lead(),
        approved=False,
    )
    assert result["queued"] == 1
    assert result["sent"] == 0
    assert enr.status == "waiting"
    deliver.assert_not_awaited()
    db.commit.assert_awaited_once()


def test_already_waiting_does_not_requeue():
    """An enrollment already parked ('waiting') with no approval yet is left alone."""
    enr = _enrollment(current_step=0, status="waiting")
    step0 = _step(step_order=0, requires_approval=True)
    result, db, deliver = _run_tick(
        enrollments=[enr],
        sequence=_sequence(),
        steps={0: step0},
        lead=_lead(),
        approved=False,
    )
    assert result["queued"] == 0
    assert result["sent"] == 0
    assert enr.status == "waiting"
    deliver.assert_not_awaited()


def test_approved_sends_and_advances():
    """Approval present -> send, advance current_step, set next_run_at from next.delay_hours."""
    enr = _enrollment(current_step=0, status="active")
    step0 = _step(step_order=0, requires_approval=True)
    step1 = _step(step_order=1, requires_approval=False, delay_hours=48)
    result, db, deliver = _run_tick(
        enrollments=[enr],
        sequence=_sequence(),
        steps={0: step0, 1: step1},
        lead=_lead(),
        approved=True,
    )
    assert result["sent"] == 1
    assert result["queued"] == 0
    deliver.assert_awaited_once()
    assert enr.current_step == 1
    assert enr.status == "active"
    assert enr.last_sent_at is not None
    # next_run_at pushed out by the *next* step's delay (48h)
    assert enr.next_run_at is not None
    assert enr.next_run_at > enr.last_sent_at


def test_no_approval_step_sends_immediately():
    """A step that needs no approval sends on the tick with no gating."""
    enr = _enrollment(current_step=0, status="active")
    step0 = _step(step_order=0, requires_approval=False, delay_hours=0)
    step1 = _step(step_order=1, requires_approval=False, delay_hours=24)
    result, db, deliver = _run_tick(
        enrollments=[enr],
        sequence=_sequence(),
        steps={0: step0, 1: step1},
        lead=_lead(),
        approved=False,  # irrelevant: step needs no approval
    )
    assert result["sent"] == 1
    deliver.assert_awaited_once()
    assert enr.current_step == 1


def test_last_step_completes():
    """Sending the final step (no next step) marks the enrollment completed."""
    enr = _enrollment(current_step=2, status="active")
    last = _step(step_order=2, requires_approval=False)
    result, db, deliver = _run_tick(
        enrollments=[enr],
        sequence=_sequence(),
        steps={2: last, 3: None},  # no step 3
        lead=_lead(),
    )
    assert result["sent"] == 1
    assert result["completed"] == 1
    assert enr.status == "completed"
    assert enr.current_step == 3


def test_step_missing_completes_without_send():
    """current_step points past the end -> completed, no send."""
    enr = _enrollment(current_step=5, status="active")
    result, db, deliver = _run_tick(
        enrollments=[enr],
        sequence=_sequence(),
        steps={5: None},
        lead=_lead(),
    )
    assert result["completed"] == 1
    assert result["sent"] == 0
    assert enr.status == "completed"
    deliver.assert_not_awaited()


def test_stop_on_reply_halts_before_send():
    """stop_on_reply (default on) + a reply -> enrollment stopped, no send."""
    enr = _enrollment(current_step=0, status="active")
    step0 = _step(step_order=0, requires_approval=False)
    result, db, deliver = _run_tick(
        enrollments=[enr],
        sequence=_sequence({"stop_on_reply": True}),
        steps={0: step0},
        lead=_lead(),
        replied=True,
    )
    assert result["stopped"] == 1
    assert result["sent"] == 0
    assert enr.status == "stopped"
    deliver.assert_not_awaited()


def test_stop_on_reply_disabled_still_sends_after_reply():
    """With stop_on_reply=False a reply does not halt the drip."""
    enr = _enrollment(current_step=0, status="active")
    step0 = _step(step_order=0, requires_approval=False)
    result, db, deliver = _run_tick(
        enrollments=[enr],
        sequence=_sequence({"stop_on_reply": False}),
        steps={0: step0, 1: None},
        lead=_lead(),
        replied=True,
    )
    assert result["sent"] == 1
    deliver.assert_awaited_once()


def test_quiet_hours_skips_without_touching_row():
    """Inside quiet hours the enrollment is skipped and left unchanged for a later tick."""
    enr = _enrollment(current_step=0, status="active")
    step0 = _step(step_order=0, requires_approval=False)
    result, db, deliver = _run_tick(
        enrollments=[enr],
        sequence=_sequence({"quiet_hours": [0, 23]}),  # _NOW (15:00) is inside
        steps={0: step0},
        lead=_lead(),
    )
    assert result["skipped"] == 1
    assert result["sent"] == 0
    assert enr.status == "active"  # untouched
    deliver.assert_not_awaited()


def test_sms_channel_uses_stub_delivery():
    """An SMS step still sends (via the stub boundary) and advances."""
    enr = _enrollment(current_step=0, status="active")
    step0 = _step(step_order=0, channel="sms", requires_approval=False)
    result, db, deliver = _run_tick(
        enrollments=[enr],
        sequence=_sequence(),
        steps={0: step0, 1: None},
        lead=_lead(),
        deliver_result={"delivered": True, "channel": "sms", "stub": True},
    )
    assert result["sent"] == 1
    deliver.assert_awaited_once()
    assert enr.status == "completed"


# ---------------------------------------------------------------------------
# _deliver — guarded external boundary (no creds / no network)
# ---------------------------------------------------------------------------


def test_deliver_email_no_recipient_is_guarded():
    import app.workers.sequence_sender as mod

    db = AsyncMock()
    step = _step(channel="email")
    lead = _lead(email=None)
    out = asyncio.run(mod._deliver(db, _WS_ID, step, lead, "Subj", "Body"))
    assert out["delivered"] is False
    assert out["channel"] == "email"


def test_deliver_email_no_connector_is_guarded():
    import app.workers.sequence_sender as mod

    db = AsyncMock()
    # connector lookup returns None
    res = MagicMock()
    res.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=res)
    step = _step(channel="email")
    out = asyncio.run(mod._deliver(db, _WS_ID, step, _lead(), "Subj", "Body"))
    assert out["delivered"] is False
    assert "connector" in out["reason"]


def test_deliver_sms_is_stub():
    import app.workers.sequence_sender as mod

    db = AsyncMock()
    step = _step(channel="sms")
    out = asyncio.run(mod._deliver(db, _WS_ID, step, _lead(phone="+15551234567"), None, "hi"))
    assert out["channel"] == "sms"
    assert out["stub"] is True
    assert out["delivered"] is True


# ---------------------------------------------------------------------------
# beat dispatcher + task registration
# ---------------------------------------------------------------------------


def test_tick_sequences_all_dispatches_per_workspace():
    import app.workers.sequence_sender as mod

    ws_ids = [
        "11111111-1111-1111-1111-111111111111",
        "22222222-2222-2222-2222-222222222222",
    ]
    with patch.object(mod, "_enumerate_workspace_ids", new=AsyncMock(return_value=ws_ids)), \
         patch.object(mod.tick_sequences, "delay") as mock_delay:
        result = mod.tick_sequences_all.run()

    assert result["dispatched"] == 2
    assert result["workspace_ids"] == ws_ids
    assert mock_delay.call_count == 2
    mock_delay.assert_any_call(ws_ids[0])
    mock_delay.assert_any_call(ws_ids[1])


def test_tick_sequences_all_no_workspaces_dispatches_nothing():
    import app.workers.sequence_sender as mod

    with patch.object(mod, "_enumerate_workspace_ids", new=AsyncMock(return_value=[])), \
         patch.object(mod.tick_sequences, "delay") as mock_delay:
        result = mod.tick_sequences_all.run()

    assert result["dispatched"] == 0
    mock_delay.assert_not_called()


def test_tick_task_wrapper_delegates_to_async_run():
    import app.workers.sequence_sender as mod

    with patch.object(mod, "_run_tick", new=AsyncMock(return_value={"sent": 2})):
        out = mod.tick_sequences.run(str(_WS_ID))
    assert out == {"sent": 2}


def test_tasks_registered_under_expected_names():
    import app.workers.sequence_sender  # noqa: F401  (ensures decorators ran)
    from app.workers.celery_app import celery_app

    assert "app.workers.sequence_sender.tick_sequences" in celery_app.tasks
    assert "app.workers.sequence_sender.tick_sequences_all" in celery_app.tasks
