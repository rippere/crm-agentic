"""
Resolve a workspace's connected mailbox — Gmail or Outlook / Microsoft 365 — for
the outbound send paths (contact send-email, sequence sender, Slack HITL approve).

Callers keep constructing GmailClient themselves (their tests patch it where it
is imported); for an Outlook connector they use build_outlook_client instead.
Both clients expose the same ``send_message(to, subject, body)`` coroutine.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.connector import Connector

MAILBOX_SERVICES = ("gmail", "outlook")


async def get_mailbox_connector(db: AsyncSession, workspace_id: uuid.UUID) -> Connector | None:
    """The workspace's send-capable mailbox connector, or None.

    If a workspace has connected both providers, the most recently connected one
    wins — connecting a second mailbox is taken as the intent to send from it.
    """
    result = await db.execute(
        select(Connector)
        .where(
            Connector.workspace_id == workspace_id,
            Connector.service.in_(MAILBOX_SERVICES),
        )
        .order_by(Connector.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def is_outlook(connector: Connector) -> bool:
    return connector.service == "outlook"


def mailbox_label(connector: Connector) -> str:
    """Human-facing provider name for logs, activity events and error details."""
    return "Outlook" if is_outlook(connector) else "Gmail"


def build_outlook_client(connector: Connector, db: AsyncSession):
    from app.config import settings
    from app.services.outlook_client import OutlookClient

    return OutlookClient(
        connector,
        db,
        microsoft_client_id=settings.MICROSOFT_CLIENT_ID,
        microsoft_client_secret=settings.MICROSOFT_CLIENT_SECRET,
    )
