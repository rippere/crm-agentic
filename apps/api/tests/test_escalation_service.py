"""Tests for the pure escalation decision service (app/services/escalation.py).

No DB, no LLM, no network — an exhaustive decision truth table over the
PROPOSE × CLAMP matrix, plus the fail-closed defaults (R12) and the R8 vocab.
"""
from __future__ import annotations

import itertools

import pytest

from app.services import escalation as esc


# ── Vocabularies + fail-closed defaults (R12) ──────────────────────────────────
def test_default_stage_mode_is_ask_for_every_stage():
    """R12: every one of the six stages fail-closes to 'ask' (no day-zero auto)."""
    stages = ("new", "contacted", "engaged", "qualified", "converted", "lost")
    assert set(esc.DEFAULT_STAGE_MODE.keys()) == set(stages)
    assert all(mode == "ask" for mode in esc.DEFAULT_STAGE_MODE.values())


def test_sentiment_vocab_is_the_r8_set():
    assert esc.SENTIMENTS == (
        "positive", "neutral", "negative", "objection", "booking", "unsubscribe",
    )


def test_action_vocabs():
    assert esc.PROPOSED_ACTIONS == ("send", "escalate", "stop", "hold")
    assert esc.FINAL_ACTIONS == ("send", "park", "escalate", "stop", "hold")
    assert esc.DECIDERS == ("threshold", "model", "human")


# ── propose_action — signal-driven ─────────────────────────────────────────────
def test_propose_cold_lead_sends():
    """No reply, zero score, default floor -> ordinary drip send."""
    assert esc.propose_action(sentiment=None, score=0) == "send"


def test_propose_positive_and_neutral_send():
    assert esc.propose_action(sentiment="positive", score=10) == "send"
    assert esc.propose_action(sentiment="neutral", score=10) == "send"


def test_propose_unsubscribe_stops():
    assert esc.propose_action(sentiment="unsubscribe", score=99) == "stop"


def test_propose_negative_and_objection_escalate():
    assert esc.propose_action(sentiment="negative", score=10) == "escalate"
    assert esc.propose_action(sentiment="objection", score=80) == "escalate"


def test_propose_booking_escalates():
    assert esc.propose_action(sentiment="booking", score=80) == "escalate"


def test_propose_below_send_floor_holds():
    assert esc.propose_action(sentiment=None, score=-5, thresholds={"send_floor": 0}) == "hold"
    # A positive send_floor holds a low-but-nonnegative score.
    assert esc.propose_action(sentiment=None, score=10, thresholds={"send_floor": 20}) == "hold"


# ── clamp_action — the _CLAMP table ─────────────────────────────────────────────
@pytest.mark.parametrize(
    "proposed,mode,expected",
    [
        ("send", "auto", "send"), ("send", "ask", "park"), ("send", "off", "hold"),
        ("escalate", "auto", "escalate"), ("escalate", "ask", "escalate"), ("escalate", "off", "hold"),
        ("stop", "auto", "stop"), ("stop", "ask", "stop"), ("stop", "off", "stop"),
        ("hold", "auto", "hold"), ("hold", "ask", "hold"), ("hold", "off", "hold"),
    ],
)
def test_clamp_matrix(proposed, mode, expected):
    assert esc.clamp_action(proposed, mode) == expected


def test_clamp_fails_closed_on_unknown():
    assert esc.clamp_action("bogus", "auto") == "hold"       # unknown proposed -> hold
    assert esc.clamp_action("send", "bogus") == "park"        # unknown mode -> treated as ask


def test_clamp_never_widens():
    """Every clamp output is 'weaker or equal' — 'send' only survives under 'auto'."""
    for proposed, mode in itertools.product(esc.PROPOSED_ACTIONS, esc.STAGE_MODES):
        final = esc.clamp_action(proposed, mode)
        if final == "send":
            assert mode == "auto" and proposed == "send"


# ── decide_action — composition + audit shape ──────────────────────────────────
def test_decide_action_composes_and_records_reason():
    d = esc.decide_action(stage="contacted", mode="ask", sentiment="positive", score=30)
    assert d.stage == "contacted"
    assert d.proposed_action == "send"
    assert d.final_action == "park"
    assert d.mode == "ask"
    assert d.sentiment == "positive"
    assert d.score == 30
    assert d.decided_by == "threshold"
    assert "propose=send" in d.reason and "clamp(ask)=park" in d.reason


def test_decide_action_off_holds_even_a_booking():
    d = esc.decide_action(stage="engaged", mode="off", sentiment="booking", score=90)
    assert d.proposed_action == "escalate"
    assert d.final_action == "hold"   # off kill switch collapses escalate -> hold


def test_decide_action_model_is_unbuilt_placeholder():
    import asyncio

    with pytest.raises(NotImplementedError):
        asyncio.run(esc.decide_action_model())
