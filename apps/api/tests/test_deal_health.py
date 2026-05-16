"""Tests for deal_health.py — pure datetime calculation, no DB or API calls."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.services.deal_health import compute_health

_NOW = datetime(2026, 5, 15, 12, 0, 0, tzinfo=timezone.utc)


def _days_ago(n: int) -> datetime:
    return _NOW - timedelta(days=n)


# ---------------------------------------------------------------------------
# Healthy deal
# ---------------------------------------------------------------------------


def test_healthy_deal_returns_100():
    score, signals = compute_health(
        stage="discovery",
        stage_changed_at=_days_ago(3),
        last_message_at=_days_ago(2),
        now=_NOW,
    )
    assert score == 100
    assert "Healthy" in signals[0]


# ---------------------------------------------------------------------------
# Stage staleness
# ---------------------------------------------------------------------------


def test_stale_deal_past_threshold_reduces_score():
    # discovery threshold = 7 days; 10 days in stage → 3 overdue × 3 pts = 9 pts off
    score, signals = compute_health(
        stage="discovery",
        stage_changed_at=_days_ago(10),
        last_message_at=_days_ago(1),
        now=_NOW,
    )
    assert score == 91
    assert any("Stale" in s for s in signals)


def test_qualified_has_longer_threshold():
    # qualified threshold = 14 days; 13 days → still healthy
    score, signals = compute_health(
        stage="qualified",
        stage_changed_at=_days_ago(13),
        last_message_at=_days_ago(1),
        now=_NOW,
    )
    assert score == 100


def test_closed_won_never_decays():
    score, signals = compute_health(
        stage="closed_won",
        stage_changed_at=_days_ago(200),
        last_message_at=_days_ago(100),
        now=_NOW,
    )
    assert score == 100
    assert "Healthy" in signals[0]


def test_closed_lost_never_decays():
    score, signals = compute_health(
        stage="closed_lost",
        stage_changed_at=_days_ago(200),
        last_message_at=None,
        now=_NOW,
    )
    assert score == 100


# ---------------------------------------------------------------------------
# Engagement gap
# ---------------------------------------------------------------------------


def test_no_messages_penalizes_20():
    score, signals = compute_health(
        stage="discovery",
        stage_changed_at=_days_ago(1),
        last_message_at=None,
        now=_NOW,
    )
    assert score == 80
    assert any("No messages" in s for s in signals)


def test_engagement_floor_penalizes_20():
    # > 14 days but ≤ 30 days → 20pt penalty
    score, signals = compute_health(
        stage="proposal",
        stage_changed_at=_days_ago(1),
        last_message_at=_days_ago(20),
        now=_NOW,
    )
    assert score == 80
    assert any("Low engagement" in s for s in signals)


def test_engagement_cut_penalizes_30():
    # > 30 days since last message → 30pt penalty
    score, signals = compute_health(
        stage="proposal",
        stage_changed_at=_days_ago(1),
        last_message_at=_days_ago(35),
        now=_NOW,
    )
    assert score == 70
    assert any("No contact" in s for s in signals)


# ---------------------------------------------------------------------------
# Score clamping and timezone handling
# ---------------------------------------------------------------------------


def test_score_clamped_to_zero():
    # Very stale + no messages → score would be negative, clamped to 0
    score, signals = compute_health(
        stage="discovery",
        stage_changed_at=_days_ago(100),
        last_message_at=None,
        now=_NOW,
    )
    assert score == 0


def test_score_cannot_exceed_100():
    score, _ = compute_health(
        stage="discovery",
        stage_changed_at=_days_ago(0),
        last_message_at=_days_ago(0),
        now=_NOW,
    )
    assert score <= 100


def test_naive_datetimes_handled():
    naive_stage = datetime(2026, 5, 14, 12, 0, 0)  # no tzinfo
    naive_msg = datetime(2026, 5, 13, 12, 0, 0)
    score, _ = compute_health(
        stage="discovery",
        stage_changed_at=naive_stage,
        last_message_at=naive_msg,
        now=_NOW,
    )
    assert 0 <= score <= 100


def test_now_defaults_to_current_time():
    score, signals = compute_health(
        stage="closed_won",
        stage_changed_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
        last_message_at=None,
    )
    assert score == 100
