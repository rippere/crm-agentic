"""
Celery ingest worker.

Task: process_gmail_sync(connector_id: str)
  1. Load connector from DB
  2. Fetch messages from Gmail API via GmailClient
  3. Deduplicate against messages table (UNIQUE workspace_id + external_id)
  4. Insert new messages
  5. Call Claude extraction on each new message body
  6. Insert extracted tasks
  7. Update connector.last_sync and message_count
"""
from __future__ import annotations

import asyncio
import base64
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.workers.celery_app import celery_app


def _get_async_session() -> async_sessionmaker[AsyncSession]:
    url = os.getenv("SUPABASE_URL", "")
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    engine = create_async_engine(url, echo=False)
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


async def _run_sync(connector_id: str) -> dict[str, Any]:
    from app.models.connector import Connector
    from app.models.message import Message
    from app.models.task import Task
    from app.services.gmail_client import GmailClient
    from app.services.extraction import extract_tasks

    google_client_id = os.getenv("GOOGLE_CLIENT_ID", "")
    google_client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "")

    SessionFactory = _get_async_session()
    new_count = 0
    task_count = 0

    async with SessionFactory() as db:
        result = await db.execute(select(Connector).where(Connector.id == uuid.UUID(connector_id)))
        connector = result.scalar_one_or_none()
        if connector is None:
            return {"error": "Connector not found", "connector_id": connector_id}

        workspace_id = connector.workspace_id
        gmail = GmailClient(connector, db, google_client_id, google_client_secret)

        # Fetch up to 200 messages
        page_token: str | None = None
        messages_to_process: list[str] = []

        for _ in range(2):  # max 2 pages × 100
            listing = await gmail.list_messages(max_results=100, page_token=page_token)
            for stub in listing.get("messages", []):
                messages_to_process.append(stub["id"])
            page_token = listing.get("nextPageToken")
            if not page_token:
                break

        for gmail_id in messages_to_process:
            # Check for duplicate
            dup = await db.execute(
                select(Message).where(
                    Message.workspace_id == workspace_id,
                    Message.external_id == gmail_id,
                )
            )
            if dup.scalar_one_or_none() is not None:
                continue  # already stored

            # Fetch full message
            try:
                msg_data = await gmail.get_message(gmail_id)
            except Exception:
                continue

            headers: dict[str, str] = {
                h["name"].lower(): h["value"]
                for h in msg_data.get("payload", {}).get("headers", [])
            }
            subject = headers.get("subject")
            sender_email = headers.get("from")
            date_str = headers.get("date")
            received_at: datetime | None = None
            if date_str:
                try:
                    from email.utils import parsedate_to_datetime
                    received_at = parsedate_to_datetime(date_str)
                except Exception:
                    pass

            body_plain = _decode_body(msg_data.get("payload", {}))

            message = Message(
                workspace_id=workspace_id,
                connector_id=connector.id,
                external_id=gmail_id,
                subject=subject,
                body_plain=body_plain,
                sender_email=sender_email,
                received_at=received_at,
                processed=False,
            )
            db.add(message)
            await db.flush()  # get message.id

            new_count += 1

            # Claude extraction
            if body_plain.strip():
                try:
                    extracted = await extract_tasks(body_plain, str(workspace_id))
                    for t in extracted:
                        task = Task(
                            workspace_id=workspace_id,
                            message_id=message.id,
                            title=t.get("title", "Untitled task"),
                            description=t.get("description", ""),
                            status="open",
                            due_date=t.get("due_date"),  # may be None or ISO string
                        )
                        db.add(task)
                        task_count += 1
                except Exception:
                    pass  # extraction failure must not block ingestion

            message.processed = True  # type: ignore[assignment]
            db.add(message)

        # Update connector stats
        connector.last_sync = datetime.now(tz=timezone.utc)  # type: ignore[assignment]
        connector.message_count = (connector.message_count or 0) + new_count  # type: ignore[assignment]
        db.add(connector)
        await db.commit()

    return {"new_messages": new_count, "new_tasks": task_count, "connector_id": connector_id}


@celery_app.task(name="app.workers.ingest.process_gmail_sync", bind=True)
def process_gmail_sync(self: Any, connector_id: str) -> dict[str, Any]:
    """Celery task: fetch and store new Gmail messages, extract tasks via Claude."""
    return asyncio.get_event_loop().run_until_complete(_run_sync(connector_id))
