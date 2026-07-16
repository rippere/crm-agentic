"""
Celery task: enrich_contact(contact_id: str)

Two-pass enrichment:
  1. Hunter.io email finder (if HUNTER_API_KEY is set and contact has no email)
  2. Claude Sonnet — reads last 10 messages from linked contact, infers
     missing fields (company, role, semantic_tags, notes snippet).

Only non-null fields are updated — existing data is never overwritten.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.database import PGBOUNCER_CONNECT_ARGS

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

_ENRICH_PROMPT = """\
You are a CRM data enrichment assistant. Given a contact's name, email, and their recent messages, \
infer as much as possible about them.

Contact:
  Name: {name}
  Email: {email}
  Company (known): {company}
  Role (known): {role}

Recent messages (newest first):
{messages}

Respond ONLY in this JSON format (null for unknown fields):
{{
  "company": "...",
  "role": "...",
  "notes": "1-2 sentence insight about this contact",
  "tags": ["tag1", "tag2"]
}}
"""


def _make_session() -> async_sessionmaker[AsyncSession]:
    url = os.getenv("DATABASE_URL", "")
    if not url:
        url = os.getenv("SUPABASE_URL", "").replace("postgres://", "postgresql+asyncpg://", 1)
    return async_sessionmaker(
        create_async_engine(url, echo=False, connect_args=PGBOUNCER_CONNECT_ARGS),
        class_=AsyncSession,
        expire_on_commit=False,
    )


async def _provider_lookup(email: str | None, name: str | None, company: str | None) -> dict[str, str | None]:
    """Resolve 'email'/'role' via the enrichment provider waterfall.

    Delegates to app.services.enrichment (Hunter.io today; future sources plug in
    behind the same interface). Returns an empty dict if nothing is configured.
    """
    from app.services.enrichment import enrich_contact_fields

    return await enrich_contact_fields(email=email, name=name, company=company)


async def _claude_enrich(
    name: str | None,
    email: str | None,
    company: str | None,
    role: str | None,
    messages: list[str],
) -> dict[str, Any]:
    if not messages:
        return {}

    import anthropic as _anthropic
    client = _anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
    msgs_text = "\n".join(f"- {m[:200]}" for m in messages[:10])
    prompt = _ENRICH_PROMPT.format(
        name=name or "Unknown",
        email=email or "Unknown",
        company=company or "Unknown",
        role=role or "Unknown",
        messages=msgs_text,
    )
    try:
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text.strip()
        import re
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            return json.loads(m.group(0))
    except Exception as exc:  # noqa: BLE001
        logger.warning("enrich_contact claude_enrich_failed email=%s exc=%s", email, exc)
    return {}


async def _run(contact_id: str) -> dict[str, Any]:
    from app.models.contact import Contact
    from app.models.message import Message

    factory = _make_session()
    async with factory() as db:
        result = await db.execute(select(Contact).where(Contact.id == uuid.UUID(contact_id)))
        contact = result.scalar_one_or_none()
        if contact is None:
            return {"error": "Contact not found"}

        # Fetch last 10 message bodies. graph_only rows are excluded in SQL rather
        # than dropped afterwards: they store an empty body, and since the LIMIT
        # applies before that filtering, ten recent metadata rows would otherwise
        # starve enrichment of every real body this contact has.
        msg_result = await db.execute(
            select(Message.body_plain)
            .where(
                Message.contact_id == contact.id,
                Message.graph_only.is_(False),
            )
            .order_by(Message.received_at.desc())
            .limit(10)
        )
        message_texts: list[str] = [r[0] for r in msg_result.all() if r[0]]

        updates: dict[str, Any] = {}

        # Pass 1: enrichment provider waterfall (Hunter.io today)
        provider = await _provider_lookup(contact.email, contact.name, contact.company)
        if provider.get("email") and not contact.email:
            updates["email"] = provider["email"]
        if provider.get("role") and not contact.role:
            updates["role"] = provider["role"]

        # Pass 2: Claude Haiku (cheap, fast)
        claude = await _claude_enrich(
            contact.name,
            updates.get("email") or contact.email,
            contact.company,
            updates.get("role") or contact.role,
            message_texts,
        )
        if claude.get("company") and not contact.company:
            updates["company"] = claude["company"]
        if claude.get("role") and not (updates.get("role") or contact.role):
            updates["role"] = claude["role"]
        if claude.get("tags"):
            existing = list(contact.semantic_tags or [])
            new_tags = [{"label": t, "color": "indigo"} for t in claude["tags"] if t not in [e.get("label") for e in existing]]
            if new_tags:
                updates["semantic_tags"] = existing + new_tags

        if updates:
            for k, v in updates.items():
                setattr(contact, k, v)
            db.add(contact)
            await db.commit()

        return {"contact_id": contact_id, "fields_updated": list(updates.keys())}


@celery_app.task(name="app.workers.enrich_contact.enrich_contact", bind=True)
def enrich_contact(self: Any, contact_id: str) -> dict[str, Any]:
    """Enrich a contact via Hunter.io (if key set) + Claude Haiku inference from messages."""
    return asyncio.run(_run(contact_id))
