"""
Celery Slack ingest worker.

Task: process_slack_sync(connector_id: str)
  1. Load connector from DB
  2. List conversations (DMs + public/private channels)
  3. Fetch message history per conversation
  4. Deduplicate against messages table (workspace_id + external_id)
  5. Insert new messages + run Claude extraction
  6. Update connector.last_sync and message_count
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

_SKIP_SUBTYPES = {"channel_join", "channel_leave", "channel_archive", "bot_message", "channel_purpose", "channel_name"}


def _get_async_session() -> async_sessionmaker[AsyncSession]:
    url = os.getenv("DATABASE_URL", "")
    if not url:
        url = os.getenv("SUPABASE_URL", "")
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    engine = create_async_engine(url, echo=False)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _record_auth_failure(db: AsyncSession, workspace_id: uuid.UUID, connector_id: str, exc: Any) -> None:
    """Persist a Slack auth failure so monitoring can see it.

    The Connector model has no last_error column, so we record an ActivityEvent
    (the spec-sanctioned alternative). Best-effort — never raises.
    """
    from app.models.activity_event import ActivityEvent

    try:
        db.add(ActivityEvent(
            workspace_id=workspace_id,
            type="connector_auth_error",
            agent_name="slack_ingest",
            description=f"Slack connector authorization failed: {exc}. Reconnect required.",
            meta=f"connector_id={connector_id} code={getattr(exc, 'code', 'unknown')}",
            severity="error",
        ))
        await db.commit()
    except Exception as log_exc:  # noqa: BLE001
        logger.warning(
            "slack_ingest auth_failure_persist_failed connector=%s exc=%s",
            connector_id, log_exc,
        )


async def _run_sync(connector_id: str) -> dict[str, Any]:
    from app.models.connector import Connector
    from app.models.message import Message
    from app.services.slack_client import SlackClient, SlackAuthError
    from app.workers.ingest import _link_contact, enrich_message

    SessionFactory = _get_async_session()
    new_count = 0
    enrich_ids: list[str] = []

    async with SessionFactory() as db:
        result = await db.execute(select(Connector).where(Connector.id == uuid.UUID(connector_id)))
        connector = result.scalar_one_or_none()
        if connector is None:
            logger.warning("slack_ingest connector_not_found connector_id=%s", connector_id)
            return {"error": "Connector not found", "connector_id": connector_id}

        workspace_id = connector.workspace_id
        slack = SlackClient(connector)

        # Collect conversations — DMs + channels (up to 3 pages × 100). An auth
        # failure here is terminal: surface it, do NOT bump last_sync, persist it.
        conversations: list[dict] = []
        cursor: str | None = None
        for _ in range(3):
            try:
                page = await slack.list_conversations(
                    types="im,mpim,public_channel", limit=100, cursor=cursor
                )
            except SlackAuthError as exc:
                logger.error(
                    "slack_ingest auth_error connector=%s workspace=%s code=%s",
                    connector_id, workspace_id, exc.code,
                )
                await _record_auth_failure(db, workspace_id, connector_id, exc)
                # Do NOT bump connector.last_sync — leaving it stale keeps the
                # failure visible to monitoring instead of masking it.
                return {
                    "error": "slack_auth_error",
                    "code": exc.code,
                    "connector_id": connector_id,
                }
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "slack_ingest list_conversations_failed connector=%s exc=%s",
                    connector_id, exc,
                )
                break
            conversations.extend(page.get("channels", []))
            cursor = page.get("response_metadata", {}).get("next_cursor") or None
            if not cursor:
                break

        # Process each conversation
        for conv in conversations:
            channel_id: str = conv.get("id", "")
            is_dm: bool = conv.get("is_im", False) or conv.get("is_mpim", False)
            channel_name: str = conv.get("name", "") or channel_id

            try:
                history = await slack.get_history(channel=channel_id, limit=200)
            except SlackAuthError as exc:
                logger.error(
                    "slack_ingest auth_error connector=%s workspace=%s channel=%s code=%s",
                    connector_id, workspace_id, channel_id, exc.code,
                )
                await _record_auth_failure(db, workspace_id, connector_id, exc)
                return {
                    "error": "slack_auth_error",
                    "code": exc.code,
                    "connector_id": connector_id,
                }
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "slack_ingest get_history_failed connector=%s channel=%s exc=%s",
                    connector_id, channel_id, exc,
                )
                continue

            for msg in history.get("messages", []):
                if msg.get("type") != "message":
                    continue
                if msg.get("subtype", "") in _SKIP_SUBTYPES:
                    continue

                ts: str = msg.get("ts", "")
                text: str = msg.get("text", "").strip()
                slack_user_id: str = msg.get("user", "")

                if not text or not ts:
                    continue

                external_id = f"{channel_id}:{ts}"

                # Dedup
                dup = await db.execute(
                    select(Message).where(
                        Message.workspace_id == workspace_id,
                        Message.external_id == external_id,
                    )
                )
                if dup.scalar_one_or_none() is not None:
                    continue

                # Resolve sender email
                sender_email: str | None = None
                if slack_user_id:
                    try:
                        user_info = await slack.get_user_info(slack_user_id)
                        sender_email = user_info.get("user", {}).get("profile", {}).get("email")
                    except SlackAuthError as exc:
                        logger.error(
                            "slack_ingest auth_error connector=%s workspace=%s code=%s",
                            connector_id, workspace_id, exc.code,
                        )
                        await _record_auth_failure(db, workspace_id, connector_id, exc)
                        return {
                            "error": "slack_auth_error",
                            "code": exc.code,
                            "connector_id": connector_id,
                        }
                    except Exception as exc:  # noqa: BLE001
                        logger.debug(
                            "slack_ingest user_info_failed connector=%s user=%s exc=%s",
                            connector_id, slack_user_id, exc,
                        )

                received_at = datetime.fromtimestamp(float(ts), tz=timezone.utc)
                subject = f"Slack {'DM' if is_dm else f'#{channel_name}'}"

                contact_id = await _link_contact(db, workspace_id, sender_email)

                message = Message(
                    workspace_id=workspace_id,
                    connector_id=connector.id,
                    external_id=external_id,
                    subject=subject,
                    body_plain=text,
                    sender_email=sender_email,
                    received_at=received_at,
                    contact_id=contact_id,
                    processed=False,  # enrichment task flips this once complete
                )
                db.add(message)
                await db.flush()

                new_count += 1
                if text.strip():
                    enrich_ids.append(str(message.id))

        connector.last_sync = datetime.now(tz=timezone.utc)
        connector.message_count = (connector.message_count or 0) + new_count
        db.add(connector)
        await db.commit()

    # Off the critical path: enqueue per-message enrichment.
    enqueued = 0
    for mid in enrich_ids:
        try:
            enrich_message.delay(mid)
            enqueued += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("slack_ingest enrich_enqueue_failed message_id=%s exc=%s", mid, exc)

    logger.info(
        "slack_ingest complete connector=%s new=%d enqueued_enrich=%d",
        connector_id, new_count, enqueued,
    )
    return {"new_messages": new_count, "enqueued_enrich": enqueued, "connector_id": connector_id}


@celery_app.task(name="app.workers.slack_ingest.process_slack_sync", bind=True)
def process_slack_sync(self: Any, connector_id: str) -> dict[str, Any]:
    """Celery task: fetch and store new Slack messages, extract tasks via Claude."""
    return asyncio.get_event_loop().run_until_complete(_run_sync(connector_id))
