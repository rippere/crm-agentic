"""
Celery task: embed_workspace_contacts(workspace_id: str)

Iterates over every contact in a workspace and updates the embedding column.
Safe to run multiple times — existing embeddings are overwritten.
"""
from __future__ import annotations

import asyncio
import os
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.workers.celery_app import celery_app


def _make_session() -> async_sessionmaker[AsyncSession]:
    url = os.getenv("DATABASE_URL", "")
    if not url:
        url = os.getenv("SUPABASE_URL", "").replace("postgres://", "postgresql+asyncpg://", 1)
    return async_sessionmaker(
        create_async_engine(url, echo=False),
        class_=AsyncSession,
        expire_on_commit=False,
    )


async def _run(workspace_id: str) -> dict[str, Any]:
    from app.models.contact import Contact
    from app.services.embedding import embed_text, contact_text

    factory = _make_session()
    updated = 0

    async with factory() as db:
        result = await db.execute(
            select(Contact).where(Contact.workspace_id == uuid.UUID(workspace_id))
        )
        contacts = result.scalars().all()

        for c in contacts:
            text = contact_text(c.name, c.company, c.role, c.email)
            c.embedding = embed_text(text)
            db.add(c)
            updated += 1

        await db.commit()

    return {"workspace_id": workspace_id, "contacts_embedded": updated}


@celery_app.task(name="app.workers.embed_contacts.embed_workspace_contacts", bind=True)
def embed_workspace_contacts(self: Any, workspace_id: str) -> dict[str, Any]:
    """Batch-embed all contacts in a workspace and store vectors in Postgres."""
    return asyncio.get_event_loop().run_until_complete(_run(workspace_id))
