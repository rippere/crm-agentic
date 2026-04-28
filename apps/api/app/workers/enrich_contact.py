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
import os
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.workers.celery_app import celery_app

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
        create_async_engine(url, echo=False),
        class_=AsyncSession,
        expire_on_commit=False,
    )


async def _hunter_lookup(email: str | None, name: str | None, company: str | None) -> dict[str, str | None]:
    """Return dict with 'email', 'role' from Hunter.io — or empty dict if not configured / no result."""
    from app.config import settings
    if not settings.HUNTER_API_KEY:
        return {}

    import httpx
    result: dict[str, str | None] = {}

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            if not email and name and company:
                # Email finder
                parts = (name or "").split()
                first, last = parts[0] if parts else "", parts[-1] if len(parts) > 1 else ""
                resp = await client.get(
                    "https://api.hunter.io/v2/email-finder",
                    params={"domain": company, "first_name": first, "last_name": last, "api_key": settings.HUNTER_API_KEY},
                )
                data = resp.json()
                found = data.get("data", {})
                if found.get("email"):
                    result["email"] = found["email"]
                    result["role"] = found.get("position")
            elif email:
                # Email verifier + enrichment
                resp = await client.get(
                    "https://api.hunter.io/v2/email-verifier",
                    params={"email": email, "api_key": settings.HUNTER_API_KEY},
                )
                data = resp.json()
                found = data.get("data", {})
                result["role"] = found.get("position") or None
    except Exception:
        pass

    return result


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
    except Exception:
        pass
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

        # Fetch last 10 message bodies
        msg_result = await db.execute(
            select(Message.body_plain)
            .where(Message.contact_id == contact.id)
            .order_by(Message.received_at.desc())
            .limit(10)
        )
        message_texts: list[str] = [r[0] for r in msg_result.all() if r[0]]

        updates: dict[str, Any] = {}

        # Pass 1: Hunter.io
        hunter = await _hunter_lookup(contact.email, contact.name, contact.company)
        if hunter.get("email") and not contact.email:
            updates["email"] = hunter["email"]
        if hunter.get("role") and not contact.role:
            updates["role"] = hunter["role"]

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
    return asyncio.get_event_loop().run_until_complete(_run(contact_id))
