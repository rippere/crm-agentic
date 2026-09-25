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
import hashlib
import json
import logging
import os
import re
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
    {"name", "email", "phone", "company", "title", "source", "external_id", "score"}
)

_REDIS_REF_PREFIX = "redis:"
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


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
    ``redis:<key>`` reference (what the router stages; Redis is shared by the api
    and worker services), a JSON string, or a filesystem path to a staged JSON
    file. Anything else yields an empty list. A redis ref whose key is gone
    (expired / never written) raises, so the job reports failure instead of
    silently importing zero rows. The key is NOT deleted here — only after a
    successful import (see _delete_staged_payload) so a failed run can retry.
    """
    if isinstance(rows_ref, list):
        return rows_ref
    if isinstance(rows_ref, str):
        if rows_ref.startswith(_REDIS_REF_PREFIX):
            data = json.loads(_read_staged_payload(rows_ref[len(_REDIS_REF_PREFIX):]))
        elif os.path.exists(rows_ref):
            with open(rows_ref, encoding="utf-8") as fh:
                data = json.load(fh)
        else:
            data = json.loads(rows_ref)
        return data if isinstance(data, list) else []
    return []


def _redis_client():
    import redis as _redis

    from app.config import settings

    return _redis.Redis.from_url(settings.REDIS_URL, socket_connect_timeout=2, socket_timeout=5)


def _read_staged_payload(key: str) -> str:
    """GET a staged import payload from Redis; raise if it's gone."""
    client = _redis_client()
    try:
        payload = client.get(key)
    finally:
        client.close()
    if payload is None:
        raise ValueError(f"staged lead-import payload missing or expired: {key}")
    return payload.decode("utf-8") if isinstance(payload, bytes) else payload


def _delete_staged_payload(rows_ref: Any) -> None:
    """Best-effort DELETE of a staged payload once imported (PII doesn't linger; TTL backstops)."""
    if not (isinstance(rows_ref, str) and rows_ref.startswith(_REDIS_REF_PREFIX)):
        return
    try:
        client = _redis_client()
        try:
            client.delete(rows_ref[len(_REDIS_REF_PREFIX):])
        finally:
            client.close()
    except Exception as exc:  # noqa: BLE001
        logger.warning("import_leads staging_delete_failed exc=%s", exc)


def _coerce_score(value: Any) -> int | None:
    """Parse an imported score into the 0-100 int the column holds; None if unusable."""
    try:
        score = int(round(float(str(value).strip().rstrip("%"))))
    except (TypeError, ValueError):
        return None
    return max(0, min(100, score))


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
        if target == "score":
            if value is not None:
                score = _coerce_score(value)
                if score is not None:
                    fields["score"] = score
                else:
                    custom[f"{src_col}_raw" if src_col == "score" else src_col] = value
        elif target == "email":
            # Prospect sheets often put a contact ROUTE ("Online form", a phone
            # number) in the email column. Only a real address is an email — it
            # is also a dedupe key, so garbage there would collide rows.
            if isinstance(value, str) and _EMAIL_RE.match(value):
                fields["email"] = value
            elif value is not None:
                custom["contact_route"] = value
        elif target in _MAPPABLE_FIELDS:
            if value is not None:
                fields[target] = value
        else:
            if value is not None:
                custom[target] = value

    if "email" in fields and isinstance(fields["email"], str):
        fields["email"] = fields["email"].lower()

    fields.setdefault("source", "import")
    # Without an email or external_id a row has no dedupe key, so re-uploading
    # an updated sheet would duplicate it. Derive a stable key from identity.
    if not fields.get("email") and not fields.get("external_id"):
        ident = "|".join(
            str(fields.get(k, "")).strip().lower() for k in ("company", "name", "phone")
        )
        if ident.strip("|"):
            fields["external_id"] = "import:" + hashlib.sha1(ident.encode("utf-8")).hexdigest()[:20]
    if custom:
        fields["custom_fields"] = custom
    return fields


# Defaults for NOT NULL columns when a sparse row omits them; every other
# column pads with None.
_PAD_DEFAULTS: dict[str, Any] = {"score": 0, "source": "import"}


def _uniform_keys(chunk: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pad every record in a chunk to the same key set.

    A multi-row INSERT ... VALUES renders one column list for the whole chunk,
    so a row missing a key another row has (a lead with no email) fails the
    ENTIRE chunk. Sparse CSVs are the norm, so normalise before inserting.
    """
    keys = set().union(*(r.keys() for r in chunk)) if chunk else set()
    return [
        {
            k: r[k] if k in r else (dict() if k == "custom_fields" else _PAD_DEFAULTS.get(k))
            for k in keys
        }
        for r in chunk
    ]


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

    if isinstance(rows_ref, str) and rows_ref.startswith(_REDIS_REF_PREFIX):
        # Keys are lead-import:staged:<workspace_id>:<uuid>; refuse a mismatched tenant.
        parts = rows_ref[len(_REDIS_REF_PREFIX):].split(":")
        if len(parts) < 4 or parts[2] != str(ws_uuid):
            raise ValueError("staged lead-import payload does not belong to this workspace")

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
                stmt = pg_insert(Lead).values(_uniform_keys(chunk)).on_conflict_do_nothing()
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

    _delete_staged_payload(rows_ref)
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
