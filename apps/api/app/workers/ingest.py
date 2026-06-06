"""
Celery ingest worker.

Task: process_gmail_sync(connector_id: str)
  1. Load connector from DB
  2. Fetch Primary-inbox messages via GmailClient (category:primary + no-reply filter)
  3. Deduplicate against messages table (UNIQUE workspace_id + external_id)
  4. Pre-filter each message with Claude Haiku (deal relevance check)
  5. Insert new relevant messages
  6. Call Claude extraction on each new message body
  7. Insert extracted tasks
  8. Update connector.last_sync and message_count
"""
from __future__ import annotations

import asyncio
import base64
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.database import PGBOUNCER_CONNECT_ARGS

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

# Automated sender patterns — skip without even pre-filtering
_SKIP_SENDER_PATTERNS = [
    "noreply", "no-reply", "no_reply", "donotreply", "do-not-reply",
    "notifications@", "newsletter", "mailer-daemon", "bounce@",
    "automated@", "unsubscribe",
]


def _get_async_session() -> async_sessionmaker[AsyncSession]:
    url = os.getenv("DATABASE_URL", "")
    engine = create_async_engine(url, echo=False, connect_args=PGBOUNCER_CONNECT_ARGS)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def _decode_body(payload: dict[str, Any]) -> str:
    """Recursively extract plain text from a Gmail message payload."""
    mime_type: str = payload.get("mimeType", "")
    body: dict = payload.get("body", {})
    data: str = body.get("data", "")

    if mime_type == "text/plain" and data:
        return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")

    parts: list[dict] = payload.get("parts", [])
    for part in parts:
        text = _decode_body(part)
        if text:
            return text

    return ""


def _is_automated_sender(sender: str) -> bool:
    lower = sender.lower()
    return any(pattern in lower for pattern in _SKIP_SENDER_PATTERNS)


async def _link_contact(db: AsyncSession, workspace_id: uuid.UUID, sender_email: str | None) -> uuid.UUID | None:
    """Parse the bare address out of a (possibly RFC2822) sender header, then
    SELECT a workspace-scoped Contact by case-insensitive email. Link-only — never
    auto-creates a Contact. Returns the contact id, or None if no match.
    """
    from email.utils import parseaddr
    from sqlalchemy import func as sa_func

    from app.models.contact import Contact

    if not sender_email:
        return None
    _, addr = parseaddr(sender_email)
    addr = addr.strip().lower()
    if not addr:
        return None

    result = await db.execute(
        select(Contact).where(
            Contact.workspace_id == workspace_id,
            sa_func.lower(Contact.email) == addr,
        )
    )
    contact = result.scalar_one_or_none()
    return contact.id if contact is not None else None


def _build_relevance_prompt(subject: str, sender: str, snippet: str) -> str:
    return (
        f"Subject: {subject}\nFrom: {sender}\nPreview: {snippet[:300]}\n\n"
        "Is this a business or deal-relevant email a sales professional should track "
        "(e.g. client communication, proposal, follow-up, meeting, contract, introduction)? "
        "Answer only 'yes' or 'no'."
    )


async def _is_deal_relevant_async(subject: str, sender: str, snippet: str) -> bool:
    """Claude Haiku pre-filter (async): is this email deal/business relevant?

    Uses AsyncAnthropic so a batch of relevance checks can be fanned out
    concurrently via asyncio.gather instead of blocking the worker on N
    sequential round-trips.
    """
    import anthropic
    client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
    try:
        message = await client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=5,
            messages=[{"role": "user", "content": _build_relevance_prompt(subject, sender, snippet)}],
        )
        return message.content[0].text.strip().lower().startswith("y")
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "ingest relevance_check_failed sender=%s subject=%s exc=%s — including by default",
            sender, subject[:60], exc,
        )
        return True  # on error, include the email rather than silently drop it


def _is_deal_relevant(subject: str, sender: str, snippet: str) -> bool:
    """Synchronous relevance pre-filter (used by the reprocess path)."""
    import anthropic
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
    try:
        message = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=5,
            messages=[{"role": "user", "content": _build_relevance_prompt(subject, sender, snippet)}],
        )
        return message.content[0].text.strip().lower().startswith("y")
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "reprocess relevance_check_failed sender=%s subject=%s exc=%s — including by default",
            sender, subject[:60], exc,
        )
        return True  # on error, include the email rather than silently drop it


# Bound the number of pages a single sync will walk so an enormous mailbox can't
# pin the worker forever. When the cap is hit before nextPageToken is exhausted we
# return truncated=True instead of silently dropping the remainder (the next sync
# resumes via dedupe). Tune via INGEST_MAX_PAGES (default 10 pages × 100 = 1000).
_MAX_INGEST_PAGES = int(os.getenv("INGEST_MAX_PAGES", "10"))


async def _run_sync(connector_id: str) -> dict[str, Any]:
    from app.models.connector import Connector
    from app.models.message import Message
    from app.services.gmail_client import GmailClient

    google_client_id = os.getenv("GOOGLE_CLIENT_ID", "")
    google_client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "")

    SessionFactory = _get_async_session()
    new_count = 0
    skipped_automated = 0
    skipped_irrelevant = 0
    truncated = False
    enrich_ids: list[str] = []

    async with SessionFactory() as db:
        result = await db.execute(select(Connector).where(Connector.id == uuid.UUID(connector_id)))
        connector = result.scalar_one_or_none()
        if connector is None:
            logger.warning("ingest connector_not_found connector_id=%s", connector_id)
            return {"error": "Connector not found", "connector_id": connector_id}

        workspace_id = connector.workspace_id
        gmail = GmailClient(connector, db, google_client_id, google_client_secret)

        # Bounded pagination: walk pages until nextPageToken is exhausted OR the
        # page cap is reached (then flag truncated). category:primary filter is
        # applied inside GmailClient.
        page_token: str | None = None
        messages_to_process: list[str] = []
        pages_walked = 0

        while True:
            try:
                listing = await gmail.list_messages(max_results=100, page_token=page_token)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "ingest list_messages_failed connector=%s page=%d exc=%s",
                    connector_id, pages_walked, exc,
                )
                break
            for stub in listing.get("messages", []):
                messages_to_process.append(stub["id"])
            pages_walked += 1
            page_token = listing.get("nextPageToken")
            if not page_token:
                break
            if pages_walked >= _MAX_INGEST_PAGES:
                truncated = True
                logger.info(
                    "ingest truncated connector=%s pages=%d collected=%d — more remain",
                    connector_id, pages_walked, len(messages_to_process),
                )
                break

        # Stage 1: fetch + dedupe + parse headers (no Claude). Collect candidates
        # that survive the automated-sender gate so relevance checks can be fanned
        # out concurrently rather than blocking on N sequential round-trips.
        candidates: list[dict[str, Any]] = []
        for gmail_id in messages_to_process:
            dup = await db.execute(
                select(Message).where(
                    Message.workspace_id == workspace_id,
                    Message.external_id == gmail_id,
                )
            )
            if dup.scalar_one_or_none() is not None:
                continue

            try:
                msg_data = await gmail.get_message(gmail_id)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "ingest get_message_failed connector=%s gmail_id=%s exc=%s",
                    connector_id, gmail_id, exc,
                )
                continue

            headers: dict[str, str] = {
                h["name"].lower(): h["value"]
                for h in msg_data.get("payload", {}).get("headers", [])
            }
            subject = headers.get("subject", "")
            sender_email = headers.get("from", "")
            date_str = headers.get("date")
            received_at: datetime | None = None
            if date_str:
                try:
                    from email.utils import parsedate_to_datetime
                    received_at = parsedate_to_datetime(date_str)
                except Exception as exc:  # noqa: BLE001
                    logger.debug(
                        "ingest date_parse_failed gmail_id=%s date=%s exc=%s",
                        gmail_id, date_str, exc,
                    )

            if _is_automated_sender(sender_email):
                skipped_automated += 1
                continue

            body_plain = _decode_body(msg_data.get("payload", {}))
            snippet = msg_data.get("snippet", "")
            candidates.append({
                "gmail_id": gmail_id,
                "subject": subject,
                "sender_email": sender_email,
                "received_at": received_at,
                "body_plain": body_plain,
                "snippet": snippet,
            })

        # Stage 2: concurrent Claude Haiku relevance pre-filter (fanned out).
        relevance_flags: list[bool] = []
        if candidates:
            relevance_flags = await asyncio.gather(*[
                _is_deal_relevant_async(
                    c["subject"], c["sender_email"], c["snippet"] or c["body_plain"][:300]
                )
                for c in candidates
            ])

        # Stage 3: insert relevant messages only. Enrichment (tasks/clarity/
        # sentiment) is decoupled — enqueued as a separate task per message so the
        # ingest critical path is fetch/dedupe/insert only.
        for cand, is_relevant in zip(candidates, relevance_flags):
            if not is_relevant:
                skipped_irrelevant += 1
                logger.debug(
                    "ingest skipped_irrelevant gmail_id=%s subject=%s",
                    cand["gmail_id"], cand["subject"][:60],
                )
                continue

            contact_id = await _link_contact(db, workspace_id, cand["sender_email"])

            message = Message(
                workspace_id=workspace_id,
                connector_id=connector.id,
                external_id=cand["gmail_id"],
                subject=cand["subject"],
                body_plain=cand["body_plain"],
                sender_email=cand["sender_email"],
                received_at=cand["received_at"],
                contact_id=contact_id,
                processed=False,  # enrichment task flips this once complete
                relevant=True,  # passed _is_automated_sender + relevance gates
            )
            db.add(message)
            await db.flush()

            new_count += 1
            if cand["body_plain"].strip():
                enrich_ids.append(str(message.id))

        connector.last_sync = datetime.now(tz=timezone.utc)  # type: ignore[assignment]
        connector.message_count = (connector.message_count or 0) + new_count  # type: ignore[assignment]
        db.add(connector)
        await db.commit()

    # Off the critical path: enqueue per-message enrichment (tasks/clarity/
    # sentiment). Failures here must not fail the ingest itself.
    enqueued = 0
    for mid in enrich_ids:
        try:
            enrich_message.delay(mid)
            enqueued += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("ingest enrich_enqueue_failed message_id=%s exc=%s", mid, exc)

    logger.info(
        "ingest complete connector=%s new=%d enqueued_enrich=%d skipped_automated=%d "
        "skipped_irrelevant=%d truncated=%s",
        connector_id, new_count, enqueued, skipped_automated, skipped_irrelevant, truncated,
    )
    return {
        "new_messages": new_count,
        "enqueued_enrich": enqueued,
        "skipped_automated": skipped_automated,
        "skipped_irrelevant": skipped_irrelevant,
        "truncated": truncated,
        "connector_id": connector_id,
    }


async def _run_enrich_message(message_id: str) -> dict[str, Any]:
    """Off-critical-path enrichment for a single ingested message.

    Runs task extraction, clarity scoring and sentiment analysis, then marks the
    message processed. Each step is independently logged so one failure doesn't
    silently lose the others.
    """
    from app.models.clarity_score import ClarityScore
    from app.models.contact import Contact
    from app.models.message import Message
    from app.models.task import Task
    from app.services.clarity import score_clarity
    from app.services.extraction import extract_tasks
    from app.services.sentiment import analyze_sentiment

    SessionFactory = _get_async_session()
    task_count = 0

    async with SessionFactory() as db:
        result = await db.execute(select(Message).where(Message.id == uuid.UUID(message_id)))
        message = result.scalar_one_or_none()
        if message is None:
            logger.warning("enrich message_not_found message_id=%s", message_id)
            return {"error": "Message not found", "message_id": message_id}

        workspace_id = message.workspace_id
        body_plain = message.body_plain or ""

        if body_plain.strip():
            try:
                extracted = await extract_tasks(body_plain, str(workspace_id))
                for t in extracted:
                    db.add(Task(
                        workspace_id=workspace_id,
                        message_id=message.id,
                        title=t.get("title", "Untitled task"),
                        description=t.get("description", ""),
                        status="open",
                        due_date=t.get("due_date"),
                    ))
                    task_count += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "enrich extract_tasks_failed message_id=%s workspace=%s exc=%s",
                    message_id, workspace_id, exc,
                )

            try:
                sentiment_result = analyze_sentiment(body_plain)
                if message.contact_id and sentiment_result.get("signals"):
                    contact_result = await db.execute(
                        select(Contact).where(Contact.id == message.contact_id)
                    )
                    contact = contact_result.scalar_one_or_none()
                    if contact is not None:
                        existing_score: dict = dict(contact.ml_score or {})
                        existing_signals: list = list(existing_score.get("signals", []))
                        for sig in sentiment_result["signals"]:
                            sentiment_signal = f"[{sentiment_result['sentiment']}] {sig}"
                            if sentiment_signal not in existing_signals:
                                existing_signals.insert(0, sentiment_signal)
                        existing_score["signals"] = existing_signals[:10]
                        contact.ml_score = existing_score  # type: ignore[assignment]
                        db.add(contact)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "enrich analyze_sentiment_failed message_id=%s workspace=%s exc=%s",
                    message_id, workspace_id, exc,
                )

            try:
                clarity = await score_clarity(body_plain)
                db.add(ClarityScore(
                    workspace_id=workspace_id,
                    message_id=message.id,
                    score=clarity["score"],
                    rationale=clarity["rationale"],
                    model_used="claude-sonnet-4-6",
                ))
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "enrich score_clarity_failed message_id=%s workspace=%s exc=%s",
                    message_id, workspace_id, exc,
                )

        message.processed = True  # type: ignore[assignment]
        db.add(message)
        await db.commit()

    logger.info("enrich complete message_id=%s tasks=%d", message_id, task_count)
    return {"message_id": message_id, "new_tasks": task_count}


@celery_app.task(name="app.workers.ingest.enrich_message", bind=True)
def enrich_message(self: Any, message_id: str) -> dict[str, Any]:
    """Celery task: enrich a single ingested message off the ingest critical path."""
    return asyncio.get_event_loop().run_until_complete(_run_enrich_message(message_id))


@celery_app.task(name="app.workers.ingest.process_gmail_sync", bind=True)
def process_gmail_sync(self: Any, connector_id: str) -> dict[str, Any]:
    """Celery task: fetch and store new Gmail messages, extract tasks via Claude."""
    return asyncio.get_event_loop().run_until_complete(_run_sync(connector_id))


async def _run_reprocess(workspace_id: str) -> dict[str, Any]:
    """Non-destructive re-enrichment of existing messages for a workspace.

    For every message already stored in the workspace this re-runs contact
    linking, task extraction, clarity scoring and sentiment analysis, and flags
    messages.relevant using the same _is_automated_sender + _is_deal_relevant
    heuristics the live ingest path uses. Nothing is ever deleted.
    """
    from app.models.clarity_score import ClarityScore
    from app.models.contact import Contact
    from app.models.message import Message
    from app.models.task import Task
    from app.services.clarity import score_clarity
    from app.services.extraction import extract_tasks
    from app.services.sentiment import analyze_sentiment

    ws_uuid = uuid.UUID(workspace_id)
    SessionFactory = _get_async_session()
    processed = 0
    relevant_count = 0
    linked = 0

    async with SessionFactory() as db:
        result = await db.execute(
            select(Message).where(Message.workspace_id == ws_uuid)
        )
        messages = list(result.scalars().all())

        for message in messages:
            sender_email = message.sender_email or ""
            body_plain = message.body_plain or ""
            subject = message.subject or ""

            # Contact linking (link-only, never auto-create)
            if message.contact_id is None:
                contact_id = await _link_contact(db, ws_uuid, sender_email)
                if contact_id is not None:
                    message.contact_id = contact_id  # type: ignore[assignment]
                    linked += 1

            # Relevance flag — same heuristics as the live ingest path
            if _is_automated_sender(sender_email):
                is_relevant = False
            else:
                is_relevant = _is_deal_relevant(subject, sender_email, body_plain[:300])
            message.relevant = is_relevant  # type: ignore[assignment]
            if is_relevant:
                relevant_count += 1

            if body_plain.strip():
                try:
                    # Idempotent re-run: clear tasks from a prior reprocess of this message
                    # before re-extracting, so the user-facing "Re-run enrichment" button
                    # cannot duplicate tasks on repeated runs (mirrors the clarity upsert).
                    from sqlalchemy import delete as _sa_delete
                    await db.execute(_sa_delete(Task).where(Task.message_id == message.id))
                    extracted = await extract_tasks(body_plain, workspace_id)
                    for t in extracted:
                        task = Task(
                            workspace_id=ws_uuid,
                            message_id=message.id,
                            title=t.get("title", "Untitled task"),
                            description=t.get("description", ""),
                            status="open",
                            due_date=t.get("due_date"),
                        )
                        db.add(task)
                except Exception:
                    logger.exception("reprocess extract_tasks failed message_id=%s", message.id)

                try:
                    sentiment_result = analyze_sentiment(body_plain)
                    if message.contact_id and sentiment_result.get("signals"):
                        contact_result = await db.execute(
                            select(Contact).where(Contact.id == message.contact_id)
                        )
                        contact = contact_result.scalar_one_or_none()
                        if contact is not None:
                            existing_score: dict = dict(contact.ml_score or {})
                            existing_signals: list = list(existing_score.get("signals", []))
                            for sig in sentiment_result["signals"]:
                                sentiment_signal = f"[{sentiment_result['sentiment']}] {sig}"
                                if sentiment_signal not in existing_signals:
                                    existing_signals.insert(0, sentiment_signal)
                            existing_score["signals"] = existing_signals[:10]
                            contact.ml_score = existing_score  # type: ignore[assignment]
                            db.add(contact)
                except Exception:
                    logger.exception("reprocess analyze_sentiment failed message_id=%s", message.id)

                try:
                    clarity = await score_clarity(body_plain)
                    existing_cs = await db.execute(
                        select(ClarityScore).where(ClarityScore.message_id == message.id)
                    )
                    cs = existing_cs.scalar_one_or_none()
                    if cs is not None:
                        cs.score = clarity["score"]
                        cs.rationale = clarity["rationale"]
                    else:
                        db.add(ClarityScore(
                            workspace_id=ws_uuid,
                            message_id=message.id,
                            score=clarity["score"],
                            rationale=clarity["rationale"],
                            model_used="claude-sonnet-4-6",
                        ))
                except Exception:
                    logger.exception("reprocess score_clarity failed message_id=%s", message.id)

            message.processed = True  # type: ignore[assignment]
            db.add(message)
            processed += 1

        await db.commit()

    logger.info(
        "reprocess complete workspace=%s processed=%d relevant=%d linked=%d",
        workspace_id, processed, relevant_count, linked,
    )
    return {
        "workspace_id": workspace_id,
        "processed": processed,
        "relevant": relevant_count,
        "linked": linked,
    }


@celery_app.task(name="app.workers.ingest.reprocess_workspace_messages", bind=True)
def reprocess_workspace_messages(self: Any, workspace_id: str) -> dict[str, Any]:
    """Celery task: non-destructively re-enrich + relevance-flag existing messages."""
    return asyncio.get_event_loop().run_until_complete(_run_reprocess(workspace_id))
