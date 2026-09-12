"""
Celery task: market-discovery worker for the Autonomous Lead Engine (Inc 1).

run_market_discovery(workspace_id, run_id)  (resolution R2)
  Drives the hybrid discovery spine for one ``discovery_runs`` row:
    1. Load the run (workspace-scoped); mark status='running', started_at=now;
       commit.
    2. Build the deduped venue universe via ``discover_venue_universe`` (§2.1.4).
    3. Score every venue concurrently (bounded by DISCOVERY_LLM_CONCURRENCY) via
       ``score_venue`` (§2.1.5) — each guarded; one failure counts an error and
       never aborts the run.
    4. Upsert each scored venue into the EXISTING ``leads`` table as
       ``source='discovery'`` via the import_leads pg_insert ON CONFLICT idiom,
       writing the durable fit record into ``custom_fields.discovery.fit_score``
       (NOT ``lead.score`` — R5/R6). Cross-run dedup rides the existing
       ``idx_leads_ws_extid`` partial unique index; an existing discovered lead is
       refreshed (UPDATE), never duplicated.
    5. Log one ``market_discovered`` ActivityEvent (``meta=json.dumps(summary)``).
    6. status='succeeded' (0 errors) else 'partial'; a fatal error -> 'failed' +
       error; completed_at=now; write stats; commit. Return the shared summary.

House shape copied from ``engagement_score.py``: sync ``@celery_app.task`` wrapper
delegating to ``asyncio.run(_run_discovery(...))``; own ``_get_async_session()``
reusing PGBOUNCER_CONNECT_ARGS; primitive ``str`` args cast to UUID inside.
On-demand only — NO ``*_all`` dispatcher and NO ``beat_schedule`` entry.

The returned summary uses EXACTLY the R2/C4 shared key set — the same schema the
web poller renders (*"Found {found} venues, {inserted} loaded to Leads"*):
    {run_id, workspace_id, locality, found, scored, inserted, skipped, status}
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.config import settings
from app.database import PGBOUNCER_CONNECT_ARGS
from app.services.discovery_research import score_venue
from app.services.discovery_rubric import DEFAULT_RUBRIC
from app.services.places import discover_venue_universe
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def _get_async_session() -> async_sessionmaker[AsyncSession]:
    # Prefer DATABASE_URL (already asyncpg-formatted) over SUPABASE_URL.
    url = os.getenv("DATABASE_URL", "") or os.getenv("SUPABASE_URL", "")
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://") and "+asyncpg" not in url:
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    engine = create_async_engine(url, echo=False, connect_args=PGBOUNCER_CONNECT_ARGS)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def _summary(
    *,
    run_id: str,
    workspace_id: str,
    locality: str,
    found: int,
    scored: int,
    inserted: int,
    skipped: int,
    status: str,
) -> dict[str, Any]:
    """The ONE worker/poller summary schema (R2/C4). Keys are load-bearing."""
    return {
        "run_id": run_id,
        "workspace_id": workspace_id,
        "locality": locality,
        "found": found,
        "scored": scored,
        "inserted": inserted,
        "skipped": skipped,
        "status": status,
    }


def _build_lead_values(
    *,
    workspace_id: uuid.UUID,
    run_id: str,
    place: Any,
    score: Any,
    rubric: dict,
) -> dict[str, Any]:
    """Map one scored venue to ``leads`` upsert kwargs (the §2.1.1 mapping table).

    The fit record lands in ``custom_fields.discovery`` and the fit score in
    ``custom_fields.discovery.fit_score`` — NEVER ``lead.score`` (R5): score /
    score_detail stay owned by the hourly ``engagement_score`` worker. The four
    qualitative fields (``fit_summary``/``why_it_works``/``best_outreach_angle``/
    ``key_risks``) are the R6 shared contract read by the psychology spine.
    """
    external_id = f"{place.provider}:{place.place_id}"
    weights = {c.get("key"): c.get("weight") for c in rubric.get("criteria", []) if c.get("key")}
    discovery_blob = {
        "run_id": run_id,
        "provider": place.provider,
        "place_id": place.place_id,
        "category": place.category,
        "area": place.locality,
        "address": place.address,
        "lat": place.lat,
        "lng": place.lng,
        "website": place.website,
        "fit_score": score.overall,          # fit (0..100) — NOT lead.score (R5)
        "tier": score.tier,
        "rubric_scores": score.subscores,    # criterion.key -> 1..scale_max
        "weights": weights,
        "fit_summary": score.fit_summary,
        "why_it_works": score.why_it_works,
        "best_outreach_angle": score.best_outreach_angle,
        "key_risks": score.key_risks,
        "best_contact": score.best_contact,
        "contact_role": score.contact_role,
        "contact_email": score.contact_email,
        "contact_phone": score.contact_phone,
        "research_confidence": score.research_confidence,
        "best_scouting_window": score.best_scouting_window,
        "primary_source_url": place.source_url,
        "contact_source_url": None,
    }
    return {
        "workspace_id": workspace_id,
        "source": "discovery",
        "external_id": external_id,
        "company": place.name,
        "name": score.best_contact,
        "email": score.contact_email,
        "phone": score.contact_phone or place.phone,
        "title": score.contact_role,
        "stage": "new",
        # score / score_detail intentionally left at their column defaults (R5).
        "custom_fields": {"discovery": discovery_blob},
    }


async def _score_all(universe: list[Any], rubric: dict, market_context: str) -> list[tuple[Any, Any]]:
    """Score every venue concurrently, bounded by ``DISCOVERY_LLM_CONCURRENCY``.

    Returns a list of ``(place, VenueScore)`` for venues that scored. ``score_venue``
    is itself never-raising, but the per-venue guard here is defensive: a venue
    that somehow raises is dropped (and counted as an error by the caller via the
    universe/scored length delta), never aborting the run.
    """
    sem = asyncio.Semaphore(max(1, settings.DISCOVERY_LLM_CONCURRENCY))

    async def _one(place: Any) -> tuple[Any, Any] | None:
        async with sem:
            try:
                score = await score_venue(place, rubric=rubric, market_context=market_context)
                return place, score
            except Exception as exc:  # noqa: BLE001 — one bad venue never aborts the run
                logger.warning(
                    "discovery score_failed venue=%s exc=%s", getattr(place, "name", None), exc
                )
                return None

    results = await asyncio.gather(*[_one(p) for p in universe])
    return [r for r in results if r is not None]


async def _run_discovery(workspace_id: str, run_id: str) -> dict[str, Any]:
    from app.models.lead import Lead
    from app.models.discovery_run import DiscoveryRun
    from app.models.activity_event import ActivityEvent

    ws_uuid = uuid.UUID(str(workspace_id))
    run_uuid = uuid.UUID(str(run_id))

    found = scored = inserted = skipped = errors = 0
    locality = ""

    SessionFactory = _get_async_session()

    async with SessionFactory() as db:
        # ── 1. load run, mark running ──────────────────────────────────────────
        result = await db.execute(
            select(DiscoveryRun).where(
                DiscoveryRun.id == run_uuid,
                DiscoveryRun.workspace_id == ws_uuid,
            )
        )
        run = result.scalar_one_or_none()
        if run is None:
            logger.warning("discovery run_not_found run_id=%s ws=%s", run_id, workspace_id)
            return _summary(
                run_id=run_id, workspace_id=str(ws_uuid), locality="",
                found=0, scored=0, inserted=0, skipped=0, status="failed",
            )

        locality = run.locality
        rubric = run.rubric or DEFAULT_RUBRIC
        params = run.params or {}
        run.status = "running"
        run.started_at = datetime.now(timezone.utc)
        db.add(run)
        await db.commit()

        try:
            # ── 2. build the deduped venue universe ────────────────────────────
            universe = await discover_venue_universe(
                market=locality,
                categories=params.get("categories"),
                radius_m=params.get("radius_m"),
                max_venues=params.get("max_venues") or settings.DISCOVERY_MAX_VENUES,
            )
            found = len(universe)

            # ── 3. score concurrently (bounded) ────────────────────────────────
            pairs = await _score_all(universe, rubric, market_context="")
            scored = len(pairs)
            errors = found - scored

            # ── 4. upsert each scored venue into leads (import_leads idiom) ─────
            now = datetime.now(timezone.utc)
            for place, score in pairs:
                values = _build_lead_values(
                    workspace_id=ws_uuid, run_id=run_id, place=place, score=score, rubric=rubric,
                )
                try:
                    # SAVEPOINT per row so a single bad upsert cannot poison the
                    # whole batch's transaction. RETURNING (xmax = 0) tells an
                    # INSERT (fresh tuple, xmax 0) from an ON CONFLICT UPDATE
                    # (existing tuple, xmax != 0) — needed for V8 idempotency
                    # (2nd pass => all UPDATEs => inserted == 0).
                    async with db.begin_nested():
                        stmt = (
                            pg_insert(Lead)
                            .values(**values)
                            .on_conflict_do_update(
                                index_elements=[Lead.workspace_id, Lead.external_id],
                                set_={
                                    "custom_fields": values["custom_fields"],
                                    "name": values["name"],
                                    "email": values["email"],
                                    "phone": values["phone"],
                                    "title": values["title"],
                                    "company": values["company"],
                                    "updated_at": now,
                                },
                            )
                            .returning(text("(xmax = 0) AS was_insert"))
                        )
                        res = await db.execute(stmt)
                        row = res.first()
                    if row is not None and bool(row[0]):
                        inserted += 1
                    else:
                        skipped += 1
                except Exception as exc:  # noqa: BLE001 — one bad upsert never aborts the run
                    errors += 1
                    logger.warning(
                        "discovery upsert_failed venue=%s exc=%s", getattr(place, "name", None), exc
                    )
            await db.commit()

            # ── 5/6. finalize + audit ──────────────────────────────────────────
            status_out = "succeeded" if errors == 0 else "partial"
            run.status = status_out
            run.stats = {
                "found": found, "scored": scored, "inserted": inserted,
                "skipped": skipped, "errors": errors,
            }
            run.completed_at = datetime.now(timezone.utc)
            db.add(run)

            summary = _summary(
                run_id=run_id, workspace_id=str(ws_uuid), locality=locality,
                found=found, scored=scored, inserted=inserted, skipped=skipped,
                status=status_out,
            )
            event = ActivityEvent(
                workspace_id=ws_uuid,
                type="market_discovered",
                agent_name="Discovery Engine",
                description=f"Discovered {found} venues in {locality}: {inserted} new",
                severity="info",
                meta=json.dumps(summary),
            )
            db.add(event)
            await db.commit()
            return summary

        except Exception as exc:  # noqa: BLE001 — fatal: mark failed, never crash the task
            logger.exception("discovery run_failed run_id=%s exc=%s", run_id, exc)
            # The transaction may be aborted; roll back before persisting failure.
            try:
                await db.rollback()
            except Exception:  # noqa: BLE001
                pass
            try:
                r2 = await db.execute(
                    select(DiscoveryRun).where(
                        DiscoveryRun.id == run_uuid,
                        DiscoveryRun.workspace_id == ws_uuid,
                    )
                )
                run_row = r2.scalar_one_or_none()
                if run_row is not None:
                    run_row.status = "failed"
                    run_row.error = str(exc)[:2000]
                    run_row.stats = {
                        "found": found, "scored": scored, "inserted": inserted,
                        "skipped": skipped, "errors": errors,
                    }
                    run_row.completed_at = datetime.now(timezone.utc)
                    db.add(run_row)
                    await db.commit()
            except Exception as inner:  # noqa: BLE001
                logger.warning("discovery run_fail_persist_failed run_id=%s exc=%s", run_id, inner)

            return _summary(
                run_id=run_id, workspace_id=str(ws_uuid), locality=locality,
                found=found, scored=scored, inserted=inserted, skipped=skipped,
                status="failed",
            )


@celery_app.task(name="app.workers.discovery.run_market_discovery", bind=True)
def run_market_discovery(self: Any, workspace_id: str, run_id: str) -> dict[str, Any]:
    """Celery task: run one market-discovery job end-to-end. On-demand (no beat)."""
    return asyncio.run(_run_discovery(workspace_id, run_id))
