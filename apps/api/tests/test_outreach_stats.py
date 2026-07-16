"""Reply derivation — the question the CRM could not answer before migration 022."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.outreach_stats import compute_outreach_stats

WS = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
NOW = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)


def _msg(direction: str, thread_id: str, at: datetime) -> SimpleNamespace:
    return SimpleNamespace(direction=direction, thread_id=thread_id, received_at=at)


def _db(messages: list) -> AsyncMock:
    db = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = messages
    db.execute = AsyncMock(return_value=result)
    return db


@pytest.mark.asyncio
async def test_reply_detected_in_same_thread():
    db = _db([
        _msg("outbound", "t1", NOW - timedelta(days=2)),
        _msg("inbound", "t1", NOW - timedelta(days=1)),
    ])
    stats = await compute_outreach_stats(db, WS, since=NOW - timedelta(days=30))

    assert stats.sent == 1
    assert stats.replied == 1
    assert stats.reply_rate == 1.0
    assert stats.median_reply_hours == pytest.approx(24.0)


@pytest.mark.asyncio
async def test_send_with_no_reply_counts_as_sent_not_replied():
    db = _db([_msg("outbound", "t1", NOW - timedelta(days=2))])
    stats = await compute_outreach_stats(db, WS, since=NOW - timedelta(days=30))

    assert (stats.sent, stats.replied) == (1, 0)
    assert stats.reply_rate == 0.0
    assert stats.median_reply_hours is None


@pytest.mark.asyncio
async def test_inbound_before_the_send_is_not_a_reply():
    """A pre-existing thread we replied INTO must not score as them replying."""
    db = _db([
        _msg("inbound", "t1", NOW - timedelta(days=5)),
        _msg("outbound", "t1", NOW - timedelta(days=2)),
    ])
    stats = await compute_outreach_stats(db, WS, since=NOW - timedelta(days=30))

    assert (stats.sent, stats.replied) == (1, 0)


@pytest.mark.asyncio
async def test_followups_on_one_thread_are_one_outreach():
    """Chasing hard must not dilute the reply rate."""
    db = _db([
        _msg("outbound", "t1", NOW - timedelta(days=9)),
        _msg("outbound", "t1", NOW - timedelta(days=6)),
        _msg("outbound", "t1", NOW - timedelta(days=3)),
    ])
    stats = await compute_outreach_stats(db, WS, since=NOW - timedelta(days=30))

    assert stats.sent == 1


@pytest.mark.asyncio
async def test_reply_latency_measured_from_first_send_in_thread():
    db = _db([
        _msg("outbound", "t1", NOW - timedelta(days=4)),
        _msg("outbound", "t1", NOW - timedelta(days=3)),  # follow-up
        _msg("inbound", "t1", NOW - timedelta(days=2)),
    ])
    stats = await compute_outreach_stats(db, WS, since=NOW - timedelta(days=30))

    assert stats.median_reply_hours == pytest.approx(48.0)


@pytest.mark.asyncio
async def test_sends_before_the_window_are_excluded():
    db = _db([
        _msg("outbound", "old", NOW - timedelta(days=200)),
        _msg("inbound", "old", NOW - timedelta(days=199)),
        _msg("outbound", "new", NOW - timedelta(days=2)),
    ])
    stats = await compute_outreach_stats(db, WS, since=NOW - timedelta(days=30))

    assert (stats.sent, stats.replied) == (1, 0)


@pytest.mark.asyncio
async def test_reply_rate_across_threads():
    db = _db([
        _msg("outbound", "t1", NOW - timedelta(days=5)),
        _msg("inbound", "t1", NOW - timedelta(days=4)),
        _msg("outbound", "t2", NOW - timedelta(days=5)),
        _msg("outbound", "t3", NOW - timedelta(days=5)),
        _msg("outbound", "t4", NOW - timedelta(days=5)),
    ])
    stats = await compute_outreach_stats(db, WS, since=NOW - timedelta(days=30))

    assert (stats.sent, stats.replied) == (4, 1)
    assert stats.reply_rate == pytest.approx(0.25)


@pytest.mark.asyncio
async def test_empty_workspace_does_not_divide_by_zero():
    stats = await compute_outreach_stats(_db([]), WS, since=NOW - timedelta(days=30))

    assert (stats.sent, stats.replied, stats.reply_rate) == (0, 0, 0.0)
    assert stats.median_reply_hours is None
