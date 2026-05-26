"""Tests for service-layer modules — all mocked, zero network calls."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# events._serialize — pure SSE formatter
# ---------------------------------------------------------------------------


def _fake_activity_event(**kwargs) -> MagicMock:
    ev = MagicMock()
    ev.id = kwargs.get("id", uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))
    ev.type = kwargs.get("type", "email_sent")
    ev.agent_name = kwargs.get("agent_name", "Gmail")
    ev.description = kwargs.get("description", "Email sent to contact")
    ev.meta = kwargs.get("meta", "")
    ev.severity = kwargs.get("severity", "info")
    ev.created_at = kwargs.get("created_at", datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc))
    return ev


def test_serialize_builds_sse_data_line():
    from app.routers.events import _serialize

    ev = _fake_activity_event(description="Deal moved to proposal", severity="warning")
    result = _serialize(ev)

    assert result.startswith("data: ")
    assert result.endswith("\n\n")
    payload = json.loads(result[6:])
    assert payload["description"] == "Deal moved to proposal"
    assert payload["severity"] == "warning"
    assert payload["id"] == str(ev.id)


def test_serialize_none_created_at_produces_null():
    from app.routers.events import _serialize

    ev = _fake_activity_event()
    ev.created_at = None
    payload = json.loads(_serialize(ev)[6:])
    assert payload["created_at"] is None


def test_serialize_created_at_is_isoformat():
    from app.routers.events import _serialize

    ts = datetime(2026, 5, 15, 9, 30, 0, tzinfo=timezone.utc)
    ev = _fake_activity_event(created_at=ts)
    payload = json.loads(_serialize(ev)[6:])
    assert "2026-05-15" in payload["created_at"]


# ---------------------------------------------------------------------------
# services/embedding.py — contact_text (pure) + embed_text (model-mocked)
# ---------------------------------------------------------------------------


def test_contact_text_all_fields():
    from app.services.embedding import contact_text

    result = contact_text("Alice", "Acme", "CEO", "a@ex.com")
    assert "Alice" in result
    assert "CEO" in result
    assert "Acme" in result
    assert "a@ex.com" in result


def test_contact_text_all_none_returns_unknown():
    from app.services.embedding import contact_text

    assert contact_text(None, None, None, None) == "unknown contact"


def test_contact_text_some_none_omits_missing():
    from app.services.embedding import contact_text

    result = contact_text("Bob", None, "Engineer", None)
    assert "Bob" in result
    assert "Engineer" in result
    assert "None" not in result


def test_embed_text_returns_float_list():
    import app.services.embedding as emb_mod

    mock_vec = MagicMock()
    mock_vec.tolist.return_value = [0.1] * 384

    mock_model = MagicMock()
    mock_model.encode.return_value = mock_vec

    with patch.object(emb_mod, "_model", return_value=mock_model):
        result = emb_mod.embed_text("hello world")

    assert isinstance(result, list)
    assert len(result) == 384


# ---------------------------------------------------------------------------
# services/sentiment.py
# ---------------------------------------------------------------------------


def test_analyze_sentiment_no_api_key_returns_neutral_default():
    import app.services.sentiment as sent_mod

    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}):
        result = sent_mod.analyze_sentiment("Great work!")

    assert result["sentiment"] == "neutral"
    assert result["confidence"] == 0.0
    assert result["signals"] == []


def _mock_sentiment_client(text: str) -> MagicMock:
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=text)]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_msg
    return mock_client


def test_analyze_sentiment_happy_path():
    import app.services.sentiment as sent_mod

    mock_client = _mock_sentiment_client(
        '{"sentiment": "positive", "confidence": 0.92, "signals": ["great news"]}'
    )

    with (
        patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}),
        patch.object(sent_mod, "_get_client", return_value=mock_client),
    ):
        result = sent_mod.analyze_sentiment("Great news!")

    assert result["sentiment"] == "positive"
    assert result["confidence"] == 0.92
    assert "great news" in result["signals"]


def test_analyze_sentiment_strips_markdown_fence():
    import app.services.sentiment as sent_mod

    raw = '```json\n{"sentiment": "negative", "confidence": 0.8, "signals": ["missed deadline"]}\n```'
    mock_client = _mock_sentiment_client(raw)

    with (
        patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}),
        patch.object(sent_mod, "_get_client", return_value=mock_client),
    ):
        result = sent_mod.analyze_sentiment("We missed the deadline again.")

    assert result["sentiment"] == "negative"
    assert result["confidence"] == 0.8


def test_analyze_sentiment_exception_returns_default():
    import app.services.sentiment as sent_mod

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = Exception("API unreachable")

    with (
        patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}),
        patch.object(sent_mod, "_get_client", return_value=mock_client),
    ):
        result = sent_mod.analyze_sentiment("Whatever")

    assert result["sentiment"] == "neutral"
    assert result["signals"] == []


def test_analyze_sentiment_missing_fields_use_defaults():
    import app.services.sentiment as sent_mod

    mock_client = _mock_sentiment_client('{"sentiment": "urgent"}')

    with (
        patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}),
        patch.object(sent_mod, "_get_client", return_value=mock_client),
    ):
        result = sent_mod.analyze_sentiment("URGENT reply needed")

    assert result["sentiment"] == "urgent"
    assert result["confidence"] == 0.0
    assert result["signals"] == []


# ---------------------------------------------------------------------------
# services/extraction.py
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_tasks_happy_path():
    import app.services.extraction as ext_mod

    tasks_json = '[{"title": "Follow up", "description": "Call back ASAP", "due_date": "2026-06-01"}]'
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=tasks_json)]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_msg

    with patch.object(ext_mod, "_get_client", return_value=mock_client):
        result = await ext_mod.extract_tasks("Please follow up by June 1", "ws-abc")

    assert len(result) == 1
    assert result[0]["title"] == "Follow up"
    assert result[0]["due_date"] == "2026-06-01"


@pytest.mark.asyncio
async def test_extract_tasks_invalid_json_returns_empty():
    import app.services.extraction as ext_mod

    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text="not json at all")]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_msg

    with patch.object(ext_mod, "_get_client", return_value=mock_client):
        result = await ext_mod.extract_tasks("some email body", "ws-abc")

    assert result == []


@pytest.mark.asyncio
async def test_extract_tasks_non_list_response_returns_empty():
    import app.services.extraction as ext_mod

    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text='{"title": "single not a list"}')]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_msg

    with patch.object(ext_mod, "_get_client", return_value=mock_client):
        result = await ext_mod.extract_tasks("some email body", "ws-abc")

    assert result == []


@pytest.mark.asyncio
async def test_extract_tasks_empty_content_blocks_returns_empty():
    import app.services.extraction as ext_mod

    mock_msg = MagicMock()
    mock_msg.content = []
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_msg

    with patch.object(ext_mod, "_get_client", return_value=mock_client):
        result = await ext_mod.extract_tasks("some email body", "ws-abc")

    assert result == []


@pytest.mark.asyncio
async def test_extract_tasks_multiple_items():
    import app.services.extraction as ext_mod

    tasks_json = json.dumps([
        {"title": "Send proposal", "description": "", "due_date": None},
        {"title": "Schedule call", "description": "With Alice", "due_date": "2026-06-15"},
    ])
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=tasks_json)]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_msg

    with patch.object(ext_mod, "_get_client", return_value=mock_client):
        result = await ext_mod.extract_tasks("Two action items here", "ws-abc")

    assert len(result) == 2
    assert result[1]["title"] == "Schedule call"


# ---------------------------------------------------------------------------
# services/clarity.py — score_clarity (Claude Sonnet, mocked)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_score_clarity_happy_path():
    import app.services.clarity as clarity_mod

    response_json = json.dumps({"score": 88, "rationale": "Clear and well structured"})
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=response_json)]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_msg

    with patch.object(clarity_mod, "_get_client", return_value=mock_client):
        result = await clarity_mod.score_clarity("Please review the attached proposal by Friday.")

    assert result["score"] == 88
    assert result["rationale"] == "Clear and well structured"


@pytest.mark.asyncio
async def test_score_clarity_clamps_score_to_0_100():
    import app.services.clarity as clarity_mod

    response_json = json.dumps({"score": 150, "rationale": "Over the top"})
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=response_json)]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_msg

    with patch.object(clarity_mod, "_get_client", return_value=mock_client):
        result = await clarity_mod.score_clarity("Some message")

    assert result["score"] == 100


@pytest.mark.asyncio
async def test_score_clarity_invalid_json_returns_default():
    import app.services.clarity as clarity_mod

    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text="not valid json {{")]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_msg

    with patch.object(clarity_mod, "_get_client", return_value=mock_client):
        result = await clarity_mod.score_clarity("Vague message")

    assert result["score"] == 50
    assert result["rationale"] == "Scoring failed"


@pytest.mark.asyncio
async def test_score_clarity_empty_content_returns_default():
    import app.services.clarity as clarity_mod

    mock_msg = MagicMock()
    mock_msg.content = []
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_msg

    with patch.object(clarity_mod, "_get_client", return_value=mock_client):
        result = await clarity_mod.score_clarity("Some message body")

    assert result["score"] == 50


@pytest.mark.asyncio
async def test_score_clarity_truncates_long_rationale():
    import app.services.clarity as clarity_mod

    long_rationale = "x" * 300
    response_json = json.dumps({"score": 60, "rationale": long_rationale})
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=response_json)]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_msg

    with patch.object(clarity_mod, "_get_client", return_value=mock_client):
        result = await clarity_mod.score_clarity("Some message")

    assert len(result["rationale"]) == 200
