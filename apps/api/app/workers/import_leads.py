"""
Celery task: bulk lead import processor.

process_lead_import(workspace_id, rows_ref, mapping, dedupe_on)
  1. Load the staged rows (inline list, JSON string, or path to a staged JSON file)
  2. Map source columns -> Lead fields via `mapping`; unmapped columns -> custom_fields
  3. Chunked insert (batch 500) up to 10k rows using
     INSERT ... ON CONFLICT DO NOTHING (dedupe on (workspace_id, email/external_id))
  4. Accumulate {inserted, skipped, errors}
  5. Write a summary ActivityEvent

Triggered from POST /leads/import. Poll via the shared GET /jobs/{job_id}.
For a 10k CSV the router persists the payload to a staging area and passes a
reference (path), NOT 10k rows through the JSON serializer.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from typing import Any, Iterable, Iterator

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.database import PGBOUNCER_CONNECT_ARGS

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

BATCH_SIZE = 500
MAX_ROWS = 10_000

# Lead columns the import path is allowed to populate directly; everything else
# in a source row falls through to custom_fields (import passthrough).
_MAPPABLE_FIELDS = frozenset(
    {"name", "email", "phone", "company", "title", "source", "external_id"}
)


def _get_async_session() -> async_sessionmaker[AsyncSession]:
    # Prefer DATABASE_URL (already asyncpg-formatted) over SUPABASE_URL
    url = os.getenv("DATABASE_URL", "") or os.getenv("SUPABASE_URL", "")
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://") and "+asyncpg" not in url:
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    engine = create_async_engine(url, echo=False, connect_args=PGBOUNCER_CONNECT_ARGS)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def _load_rows(rows_ref: Any) -> list[dict[str, Any]]:
    """Resolve the worker's `rows_ref` argument into a list of raw dict rows.

    Mock-friendly boundary for the staged payload — accepts an inline list, a
    JSON string, or a filesystem path to a staged JSON file (what the router
    writes for a 10k import). Anything else yields an empty list.
    """
    if isinstance(rows_ref, list):
        return rows_ref
    if isinstance(rows_ref, str):
        if os.path.exists(rows_ref):
            with open(rows_ref, encoding="utf-8") as fh:
                data = json.load(fh)
        else:
            data = json.loads(rows_ref)
        return data if isinstance(data, list) else []
    return []


def _map_row(raw: dict[str, Any], mapping: dict[str, str]) -> dict[str, Any]:
    """Map one source row into Lead insert kwargs.

    `mapping` is {source_column -> lead_field}. Mapped fields in _MAPPABLE_FIELDS
    populate the column directly; any other mapped/unmapped source column is
    carried through in custom_fields. Blank strings become None.
    """
    fields: dict[str, Any] = {}
    custom: dict[str, Any] = {}

    for src_col, value in raw.items():
        target = mapping.get(src_col, src_col)
        if isinstance(value, str):
            value = value.strip()
            if value == "":
                value = None
        if target in _MAPPABLE_FIELDS:
            if value is not None:
                fields[target] = value
        else:
            if value is not None:
                custom[target] = value

    if "email" in fields and isinstance(fields["email"], str):
        fields["email"] = fields["email"].lower()

    fields.setdefault("source", "import")
    if custom:
        fields["custom_fields"] = custom
    return fields


def _chunks(seq: list[Any], size: int) -> Iterator[list[Any]]:
    """Yield successive `size`-length chunks of `seq`."""
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


async def _run_import(
    workspace_id: str,
    rows_ref: Any,
    mapping: dict[str, str] | None,
    dedupe_on: str,
) -> dict[str, Any]:
    from app.models.lead import Lead
    from app.models.activity_event import ActivityEvent

    ws_uuid = uuid.UUID(str(workspace_id))
    mapping = mapping or {}

    raw_rows = _load_rows(rows_ref)
    # Best-effort cleanup: the router stages up to 10k rows of lead PII (name/
    # email/phone/company) to a temp JSON file; delete it now that it's loaded
    # so PII doesn't accumulate on local disk across imports.
    if isinstance(rows_ref, str) and "lead-import" in rows_ref and os.path.isfile(rows_ref):
        try:
            os.remove(rows_ref)
        except OSError as exc:  # noqa: BLE001
            logger.warning("import_leads staging_cleanup_failed path=%s exc=%s", rows_ref, exc)
    truncated = len(raw_rows) > MAX_ROWS
    raw_rows = raw_rows[:MAX_ROWS]

    inserted = 0
    skipped = 0
    errors = 0

    # Map first so a single malformed row is counted as an error, not a crash.
    mapped: list[dict[str, Any]] = []
    for raw in raw_rows:
        try:
            if not isinstance(raw, dict):
                raise TypeError("row is not an object")
            record = _map_row(raw, mapping)
            record["workspace_id"] = ws_uuid
            mapped.append(record)
        except Exception as exc:  # noqa: BLE001
            errors += 1
            logger.warning("import_leads map_failed workspace=%s exc=%s", ws_uuid, exc)

    SessionFactory = _get_async_session()
    async with SessionFactory() as db:
        for chunk in _chunks(mapped, BATCH_SIZE):
            if not chunk:
                continue
            try:
                # ON CONFLICT DO NOTHING against the partial unique indexes on
                # (workspace_id, email) and (workspace_id, external_id). No index
                # target => any unique violation is silently skipped, which covers
                # both dedupe keys regardless of `dedupe_on`.
                stmt = pg_insert(Lead).values(chunk).on_conflict_do_nothing()
                result = await db.execute(stmt)
                rc = getattr(result, "rowcount", None)
                inserted_chunk = rc if isinstance(rc, int) and rc >= 0 else len(chunk)
                inserted += inserted_chunk
                skipped += len(chunk) - inserted_chunk
            except Exception as exc:  # noqa: BLE001
                errors += len(chunk)
                logger.warning(
                    "import_leads insert_failed workspace=%s size=%s exc=%s",
                    ws_uuid, len(chunk), exc,
                )

        summary = {
            "inserted": inserted,
            "skipped": skipped,
            "errors": errors,
            "dedupe_on": dedupe_on,
            "truncated": truncated,
        }

        event = ActivityEvent(
            workspace_id=ws_uuid,
            type="leads_imported",
            agent_name="Lead Importer",
            description=(
                f"Imported {inserted} lead(s): {skipped} skipped (dup), "
                f"{errors} error(s) on {dedupe_on}"
            ),
            meta=json.dumps(summary),
            severity="info",
        )
        db.add(event)
        await db.commit()

    return {"workspace_id": str(ws_uuid), **summary}


@celery_app.task(name="app.workers.import_leads.process_lead_import", bind=True)
def process_lead_import(
    self: Any,
    workspace_id: str,
    rows_ref: Any,
    mapping: dict[str, str] | None = None,
    dedupe_on: str = "email",
) -> dict[str, Any]:
    """Celery task: bulk-import leads (chunked, deduped) and log a summary event."""
    return asyncio.run(_run_import(workspace_id, rows_ref, mapping, dedupe_on))
