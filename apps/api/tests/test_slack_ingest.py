"""process_slack_sync fan-out cap — SLACK_MAX_MESSAGES.

The behavior under test is the twin of the Gmail-ingest burn: the first sync of a
busy Slack workspace must not enqueue an enrich_message (≈3 Claude calls each) for
every message in history. One sync inserts + enqueues at most SLACK_MAX_MESSAGES
new messages; the remainder is left unstored so the next sync re-fetches it via
dedupe-miss (never dropped). Everything is mocked — no DB, no Slack, no Anthropic.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

WS = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
CONNECTOR_ID = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")


def _slack_message(idx: int) -> dict:
    """A plain, enrichable text message from a Slack conversation history."""
    return {
        "type": "message",
        "ts": f"1700000000.{idx:06d}",
        "text": f"Hey, following up on item {idx}",
        # No "user" → sender resolution is skipped (get_user_info never called).
    }


def _mock_db() -> AsyncMock:
    """Session where the connector resolves and every dedupe lookup misses."""
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()

    connector = MagicMock()
    connector.id = CONNECTOR_ID
    connector.workspace_id = WS
    connector.message_count = 0

    def _execute(stmt, *a, **kw):
        result = MagicMock()
        text = str(stmt)
        result.scalar_one_or_none.return_value = (
            connector if "FROM connectors" in text else None
        )
        result.scalars.return_value.all.return_value = []
        return result

    db.execute = AsyncMock(side_effect=_execute)
    return db


def _session_factory(db: AsyncMock):
    factory = MagicMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=db)
    ctx.__aexit__ = AsyncMock(return_value=False)
    factory.return_value = ctx
    return factory


async def _run(messages: list[dict], db: AsyncMock):
    slack = MagicMock()
    # One conversation, one page, no next cursor.
    slack.list_conversations = AsyncMock(
        return_value={"channels": [{"id": "C1", "name": "general"}]}
    )
    slack.get_history = AsyncMock(return_value={"messages": messages})
    slack.get_user_info = AsyncMock(return_value={"user": {}})

    with patch("app.workers.slack_ingest._get_async_session", return_value=_session_factory(db)), \
         patch("app.services.slack_client.SlackClient", return_value=slack), \
         patch("app.workers.ingest._link_contact", AsyncMock(return_value=None)), \
         patch("app.workers.ingest.enrich_message") as enrich:
        enrich.delay = MagicMock()
        from app.workers.slack_ingest import _run_sync

        result = await _run_sync(str(CONNECTOR_ID))
        return result, enrich.delay


@pytest.mark.asyncio
async def test_slack_sync_respects_hard_message_cap(monkeypatch):
    """One sync must insert + enqueue at most SLACK_MAX_MESSAGES, no matter how
    many messages Slack history returns — the guard that stops a busy first sync
    from fanning ~3 Claude calls per message across an entire workspace. With the
    cap set to 3 and ten messages available, exactly three are enqueued for
    enrichment and the run reports truncated so the remainder is re-fetched next
    sync (never dropped)."""
    monkeypatch.setattr("app.config.settings.SLACK_MAX_MESSAGES", 3)

    db = _mock_db()
    messages = [_slack_message(i) for i in range(10)]

    result, enrich_delay = await _run(messages, db)

    assert result["new_messages"] == 3, "must insert no more than the hard message cap"
    assert result["enqueued_enrich"] == 3, "enrich dispatch is bounded to cap-many"
    assert enrich_delay.call_count == 3, "≈3 Claude calls fire only for cap-many messages"
    assert result["truncated"] is True, "hitting the cap must flag truncation, not drop silently"
