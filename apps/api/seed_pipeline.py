"""
One-shot, idempotent pipeline seed — lights up the dashboard with real deals.

ZERO Anthropic tokens: pure DB writes. Run once; safe to re-run (skips rows
that already exist).

Run (credential stays in Railway's injected env, never printed):
    cd apps/api && railway run -s api -- .venv/bin/python seed_pipeline.py

Values/stages are DRAFTS — edit them in the UI afterward.
"""
from __future__ import annotations

import asyncio
import os
import uuid

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.database import PGBOUNCER_CONNECT_ARGS
from app.models.contact import Contact
from app.models.deal import Deal

WORKSPACE_ID = uuid.UUID("9dbfbe4d-2e0d-4fca-944c-6960bf6b586d")  # Ben's workspace

DRAFT = "DRAFT (seeded 2026-09-21) — edit value/stage in the UI."

# Contacts to ensure exist (matched by name when no email; created if absent).
CONTACTS = [
    # name, email, company, role
    ("Mike Betti", None, "Betson", "Buyer / stakeholder"),
]

# Deals to seed (matched by title within the workspace; skipped if present).
DEALS = [
    dict(
        title="Staff training + telehealth ops",
        company="Priv pediatrician practice",
        contact_email="jmperkek@yahoo.com",
        contact_name="Jason Mark Perkel",
        value=6000, stage="qualified", ml_win_probability=40,
        expected_close="2026-11-20", notes=DRAFT,
    ),
    dict(
        title="Betson engagement — fleet & floorplan",
        company="Betson",
        contact_email=None,
        contact_name="Mike Betti",
        value=15000, stage="negotiation", ml_win_probability=65,
        expected_close="2026-10-31", notes=DRAFT,
    ),
    dict(
        title="Legal ops scoping",
        company="BPGCOMP",
        contact_email="john@bpgcomp.com",
        contact_name="John Wolfert",
        value=5000, stage="discovery", ml_win_probability=20,
        expected_close="2026-12-15", notes=DRAFT,
    ),
]


def _session_factory() -> async_sessionmaker[AsyncSession]:
    url = os.environ["DATABASE_URL"]
    return async_sessionmaker(
        create_async_engine(url, echo=False, connect_args=PGBOUNCER_CONNECT_ARGS),
        class_=AsyncSession, expire_on_commit=False,
    )


async def _contact_by_email(db: AsyncSession, email: str) -> Contact | None:
    r = await db.execute(
        select(Contact).where(Contact.workspace_id == WORKSPACE_ID, Contact.email == email)
    )
    return r.scalar_one_or_none()


async def _contact_by_name(db: AsyncSession, name: str) -> Contact | None:
    r = await db.execute(
        select(Contact).where(Contact.workspace_id == WORKSPACE_ID, Contact.name == name)
    )
    return r.scalars().first()


async def main() -> None:
    factory = _session_factory()
    created_contacts, created_deals, skipped = [], [], []

    async with factory() as db:
        # 1. Ensure named contacts exist (Mike Betti).
        for name, email, company, role in CONTACTS:
            existing = (await _contact_by_email(db, email)) if email else await _contact_by_name(db, name)
            if existing is None:
                db.add(Contact(
                    workspace_id=WORKSPACE_ID, name=name, email=email,
                    company=company, role=role, status="lead",
                ))
                created_contacts.append(name)
        await db.commit()

        # 2. Seed deals (idempotent by title).
        for d in DEALS:
            r = await db.execute(
                select(Deal).where(Deal.workspace_id == WORKSPACE_ID, Deal.title == d["title"])
            )
            if r.scalar_one_or_none() is not None:
                skipped.append(d["title"])
                continue

            contact = None
            if d["contact_email"]:
                contact = await _contact_by_email(db, d["contact_email"])
            if contact is None and d["contact_name"]:
                contact = await _contact_by_name(db, d["contact_name"])

            db.add(Deal(
                workspace_id=WORKSPACE_ID,
                title=d["title"], company=d["company"],
                contact_id=contact.id if contact else None,
                contact_name=d["contact_name"],
                value=d["value"], stage=d["stage"],
                ml_win_probability=d["ml_win_probability"],
                expected_close=d["expected_close"], notes=d["notes"],
            ))
            created_deals.append(f'{d["title"]} (${d["value"]:,}, {d["stage"]})')
        await db.commit()

        # 3. Retire the Test User / Acme Corp stub (only if it has no deals).
        stub = await _contact_by_email(db, "test@example.com")
        retired = None
        if stub is not None:
            dr = await db.execute(select(Deal).where(Deal.contact_id == stub.id))
            if dr.first() is None:
                await db.execute(delete(Contact).where(Contact.id == stub.id))
                await db.commit()
                retired = stub.name

    print("── Seed complete ─────────────────────────────")
    print(f"  contacts created : {created_contacts or 'none'}")
    print(f"  deals created    : {created_deals or 'none'}")
    print(f"  deals skipped    : {skipped or 'none'} (already existed)")
    print(f"  stub retired     : {retired or 'none'}")


if __name__ == "__main__":
    asyncio.run(main())
