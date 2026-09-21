"""_run_sync header capture + the metadata-only lane.

The behavior under test is the one that used to lose data silently: an email the
relevance judge rejects must still be STORED (headers only), because those weak
ties are what a warm-intro graph is made of. Everything is mocked — no DB, no
Gmail, no Anthropic.
"""

from __future__ import annotations

import base64
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_BODY = base64.urlsafe_b64encode(b"Hello - following up on our chat.").decode()

WS = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
CONNECTOR_ID = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")


def _gmail_message(
    gmail_id: str,
    *,
    sender: str,
    to: str,
    cc: str | None = None,
    thread_id: str = "thread-1",
    sent: bool = False,
) -> dict:
    headers = [
        {"name": "From", "value": sender},
        {"name": "To", "value": to},
        {"name": "Subject", "value": "Quick question"},
        {"name": "Date", "value": "Tue, 14 Jul 2026 09:00:00 +0000"},
        {"name": "Message-ID", "value": f"<{gmail_id}@mail.example.com>"},
        {"name": "In-Reply-To", "value": "<parent@mail.example.com>"},
    ]
    if cc:
        headers.append({"name": "Cc", "value": cc})
    return {
        "id": gmail_id,
        "threadId": thread_id,
        "labelIds": ["SENT"] if sent else ["INBOX"],
        "snippet": "hello there",
        "payload": {
            "headers": headers,
            "mimeType": "text/plain",
            "body": {"data": _BODY},
        },
    }


def _mock_db() -> AsyncMock:
    """Session where the connector resolves and every other lookup misses."""
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
        # Connector lookup resolves; dedupe + contact lookups miss.
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


async def _run(messages: list[dict], relevance: list[bool], db: AsyncMock):
    gmail = MagicMock()
    gmail.list_messages = AsyncMock(
        return_value={"messages": [{"id": m["id"]} for m in messages]}
    )
    gmail.get_message = AsyncMock(side_effect=lambda mid: next(
        m for m in messages if m["id"] == mid
    ))

    with patch("app.workers.ingest._get_async_session", return_value=_session_factory(db)), \
         patch("app.services.gmail_client.GmailClient", return_value=gmail), \
         patch("app.workers.ingest._is_deal_relevant_async", AsyncMock(side_effect=relevance)), \
         patch("app.workers.ingest.enrich_message") as enrich:
        enrich.delay = MagicMock()
        from app.workers.ingest import _run_sync

        return await _run_sync(str(CONNECTOR_ID))


def _added_messages(db: AsyncMock) -> list:
    from app.models.message import Message

    return [c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], Message)]


@pytest.mark.asyncio
async def test_irrelevant_mail_is_stored_metadata_only_not_dropped():
    """The regression that matters: rejected mail used to vanish entirely."""
    db = _mock_db()
    msg = _gmail_message("m1", sender="jane@example.com", to="ben@novacrm.io")

    result = await _run([msg], [False], db)

    stored = _added_messages(db)
    assert len(stored) == 1, "irrelevant mail must still be persisted"
    row = stored[0]
    assert row.graph_only is True
    assert row.relevant is False
    assert row.body_plain == "", "metadata-only rows must not store the body"
    assert row.to_emails == ["ben@novacrm.io"]
    assert result["graph_only_rows"] == 1
    assert result["new_messages"] == 0


@pytest.mark.asyncio
async def test_relevant_mail_captures_headers_and_keeps_body():
    db = _mock_db()
    msg = _gmail_message(
        "m2",
        sender="Jane <jane@example.com>",
        to="ben@novacrm.io",
        cc="sam@example.com, bob@example.com",
        thread_id="thread-42",
    )

    result = await _run([msg], [True], db)

    row = _added_messages(db)[0]
    assert row.graph_only is False
    assert row.relevant is True
    assert row.to_emails == ["ben@novacrm.io"]
    assert row.cc_emails == ["sam@example.com", "bob@example.com"]
    assert row.thread_id == "thread-42"
    assert row.rfc_message_id == "<m2@mail.example.com>"
    assert row.in_reply_to == "<parent@mail.example.com>"
    assert row.direction == "inbound"
    assert result["new_messages"] == 1


@pytest.mark.asyncio
async def test_sent_mail_is_marked_outbound():
    """Direction comes from Gmail's SENT label — reciprocity depends on it."""
    db = _mock_db()
    msg = _gmail_message(
        "m3", sender="ben@novacrm.io", to="jane@example.com", sent=True
    )

    await _run([msg], [True], db)

    assert _added_messages(db)[0].direction == "outbound"


@pytest.mark.asyncio
async def test_sent_mail_does_not_auto_create_contacts():
    """Syncing years of sent mail must not mint a lead per address ever emailed."""
    from app.models.contact import Contact

    db = _mock_db()
    msg = _gmail_message(
        "m5", sender="ben@novacrm.io", to="stranger@example.com", sent=True
    )

    await _run([msg], [True], db)

    created = [c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], Contact)]
    assert created == [], "outbound sync must link only, never auto-create"


@pytest.mark.asyncio
async def test_inbound_mail_still_auto_creates_a_lead():
    """The existing 'inbound becomes pipeline' behavior must survive."""
    from app.models.contact import Contact

    db = _mock_db()
    msg = _gmail_message("m6", sender="newlead@example.com", to="ben@novacrm.io")

    await _run([msg], [True], db)

    created = [c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], Contact)]
    assert len(created) == 1
    assert created[0].email == "newlead@example.com"


@pytest.mark.asyncio
async def test_automated_senders_never_become_rows():
    """noreply@ must not be stored at all — not even as a graph node."""
    db = _mock_db()
    msg = _gmail_message("m4", sender="noreply@stripe.com", to="ben@novacrm.io")

    result = await _run([msg], [True], db)

    assert _added_messages(db) == []
    assert result["skipped_automated"] == 1


@pytest.mark.asyncio
async def test_ingest_respects_hard_message_cap(monkeypatch):
    """One sync must process at most INGEST_MAX_MESSAGES, no matter how many the
    mailbox returns — the guard that stops a connect from fanning LLM calls over
    an entire multi-year mailbox. With the cap set to 3 and ten candidates
    available, exactly three are fetched, stored and relevance-checked; the run
    reports truncated so the remainder is picked up next sync (never dropped)."""
    monkeypatch.setattr("app.config.settings.INGEST_MAX_MESSAGES", 3)

    db = _mock_db()
    msgs = [
        _gmail_message(f"m{i}", sender=f"lead{i}@example.com", to="ben@novacrm.io")
        for i in range(10)
    ]
    # Ten relevance verdicts offered; only cap-many may be consumed.
    result = await _run(msgs, [True] * 10, db)

    stored = _added_messages(db)
    assert len(stored) == 3, "must persist no more than the hard message cap"
    assert result["new_messages"] == 3, "at most cap-many messages enter the pipeline"
    assert result["truncated"] is True, "hitting the cap must flag truncation, not drop silently"


@pytest.mark.asyncio
async def test_metadata_only_rows_are_not_enqueued_for_enrichment():
    """Relevance still gates Claude spend; only the drop was removed."""
    db = _mock_db()
    msgs = [
        _gmail_message("keep", sender="jane@example.com", to="ben@novacrm.io"),
        _gmail_message("meta", sender="mum@example.com", to="ben@novacrm.io"),
    ]

    result = await _run(msgs, [True, False], db)

    assert result["new_messages"] == 1
    assert result["graph_only_rows"] == 1
    assert result["enqueued_enrich"] == 1, "only the relevant message costs a Claude call"


# ---------------------------------------------------------------------------
# reprocess ("Re-run enrichment") fan-out cap — REPROCESS_MAX_MESSAGES
# ---------------------------------------------------------------------------


def _reprocess_message(idx: int):
    """A stored, enrichable (has-body) message row for the reprocess path."""
    m = MagicMock()
    m.id = uuid.uuid4()
    m.sender_email = f"lead{idx}@example.com"
    m.subject = "Following up"
    m.body_plain = "Hi - checking in on the proposal."
    m.contact_id = None
    return m


def _reprocess_db(messages: list) -> AsyncMock:
    """Session whose Message scan returns `messages` and every scalar lookup misses."""
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()

    def _execute(stmt, *a, **kw):
        result = MagicMock()
        result.scalars.return_value.all.return_value = messages
        result.scalar_one_or_none.return_value = None  # no existing ClarityScore
        return result

    db.execute = AsyncMock(side_effect=_execute)
    return db


@pytest.mark.asyncio
async def test_reprocess_respects_message_cap(monkeypatch):
    """One 'Re-run enrichment' run enriches at most REPROCESS_MAX_MESSAGES, no
    matter how many messages the workspace holds — the guard that stops one click
    from fanning ~4 Claude calls per message across an entire mailbox. With the
    cap set to 3 and ten messages available, exactly three are processed and each
    fires its relevance + enrichment calls only for those three; the run reports
    truncated so the remainder is deferred to the next run (never dropped)."""
    monkeypatch.setattr("app.config.settings.REPROCESS_MAX_MESSAGES", 3)

    messages = [_reprocess_message(i) for i in range(10)]
    db = _reprocess_db(messages)

    relevance = MagicMock(return_value=True)
    extract = AsyncMock(return_value=[])
    clarity = AsyncMock(return_value={"score": 0.5, "rationale": "ok"})
    sentiment = MagicMock(return_value={"sentiment": "neutral", "signals": []})

    with patch("app.workers.ingest._get_async_session", return_value=_session_factory(db)), \
         patch("app.workers.ingest._link_contact", AsyncMock(return_value=None)), \
         patch("app.workers.ingest._is_deal_relevant", relevance), \
         patch("app.services.extraction.extract_tasks", extract), \
         patch("app.services.clarity.score_clarity", clarity), \
         patch("app.services.sentiment.analyze_sentiment", sentiment):
        from app.workers.ingest import _run_reprocess

        result = await _run_reprocess(str(WS))

    assert result["processed"] == 3, "must enrich no more than the message cap"
    assert result["truncated"] is True, "hitting the cap must flag truncation, not drop silently"
    # LLM fan-out is bounded to cap-many messages, not the full workspace.
    assert relevance.call_count == 3, "relevance LLM fires only for cap-many messages"
    assert extract.await_count == 3, "task extraction fires only for cap-many messages"
