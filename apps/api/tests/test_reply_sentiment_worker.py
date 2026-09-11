"""Tests for the reply-sentiment classifier worker (app/workers/reply_sentiment.py, R9).

Offline: the LLM boundary (_classify_text) is monkeypatched or short-circuits on
an empty API key, so the worker runs with no credentials and no network. Verifies
the R8 vocab is written to engagement_event.metadata.sentiment, and that any
failure leaves sentiment unset.
"""
from __future__ import annotations

import asyncio
import uuid as uuid_mod
from unittest.mock import AsyncMock, MagicMock, patch

import app.workers.reply_sentiment as mod

_WS = uuid_mod.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_EVENT_ID = uuid_mod.uuid4()


def _event(type_="replied", metadata=None):
    e = MagicMock()
    e.id = _EVENT_ID
    e.type = type_
    e.metadata_ = metadata if metadata is not None else {"body": "Sounds great, can we book a call?"}
    return e


def _patched_session(db):
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=db)
    cm.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=cm)


def _run(event, classify_return="booking"):
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    res = MagicMock()
    res.scalar_one_or_none.return_value = event
    db.execute = AsyncMock(return_value=res)

    with patch.object(mod, "_get_async_session", return_value=_patched_session(db)), \
         patch.object(mod, "_classify_text", new=AsyncMock(return_value=classify_return)), \
         patch.object(mod, "_reader_rubric", new=AsyncMock(return_value="rubric")):
        out = asyncio.run(mod._classify(str(_WS), str(_EVENT_ID)))
    return out, event, db


# ── _parse_sentiment — vocab mapping ────────────────────────────────────────────
def test_parse_exact_and_embedded():
    assert mod._parse_sentiment("booking") == "booking"
    assert mod._parse_sentiment("  Positive ") == "positive"
    assert mod._parse_sentiment("I think this is an objection about price") == "objection"


def test_parse_unknown_returns_none():
    assert mod._parse_sentiment("maybe") is None
    assert mod._parse_sentiment("") is None
    assert mod._parse_sentiment(None) is None


# ── _classify_text — guarded, key-gated ─────────────────────────────────────────
def test_classify_text_no_key_short_circuits():
    """No ANTHROPIC_API_KEY -> None, never touches the network."""
    fake_settings = MagicMock()
    fake_settings.ANTHROPIC_API_KEY = ""
    with patch.object(mod, "settings", fake_settings):
        out = asyncio.run(mod._classify_text("hello", "rubric"))
    assert out is None


def test_classify_text_empty_reply_is_none():
    out = asyncio.run(mod._classify_text("", "rubric"))
    assert out is None


# ── _classify — writes metadata.sentiment ───────────────────────────────────────
def test_classify_writes_sentiment_into_metadata():
    out, event, db = _run(_event(), classify_return="booking")
    assert out["status"] == "classified"
    assert out["sentiment"] == "booking"
    assert event.metadata_["sentiment"] == "booking"
    # original body preserved (metadata reassigned, not clobbered)
    assert "body" in event.metadata_
    db.commit.assert_awaited_once()


def test_classify_unclassified_leaves_sentiment_unset():
    out, event, db = _run(_event(), classify_return=None)
    assert out["status"] == "unclassified"
    assert out["sentiment"] is None
    assert "sentiment" not in (event.metadata_ or {})


def test_classify_non_reply_is_skipped():
    out, event, db = _run(_event(type_="opened"))
    assert out["status"] == "not_a_reply"
    assert out["sentiment"] is None


def test_classify_missing_event_is_not_found():
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    res = MagicMock()
    res.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=res)
    with patch.object(mod, "_get_async_session", return_value=_patched_session(db)):
        out = asyncio.run(mod._classify(str(_WS), str(_EVENT_ID)))
    assert out["status"] == "not_found"


# ── task registration ───────────────────────────────────────────────────────────
def test_classify_reply_task_registered():
    from app.workers.celery_app import celery_app

    assert "app.workers.reply_sentiment.classify_reply" in celery_app.tasks
