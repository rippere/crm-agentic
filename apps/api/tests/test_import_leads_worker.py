"""Tests for workers.import_leads — bulk lead import. Zero DB, zero Celery, zero creds.

Mocking style mirrors tests/test_workers.py: an AsyncMock db behind a MagicMock
async-context-manager session factory, patched over `_get_async_session`.
"""

from __future__ import annotations

import json
import uuid as uuid_mod
from unittest.mock import AsyncMock, MagicMock, patch

import app.workers.import_leads as il

_WS = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


# ---------------------------------------------------------------------------
# _map_row — source columns -> Lead kwargs, passthrough -> custom_fields
# ---------------------------------------------------------------------------


def test_map_row_maps_standard_columns():
    raw = {"Full Name": "Jane Doe", "Email": "JANE@Acme.com", "Company": "Acme"}
    mapping = {"Full Name": "name", "Email": "email", "Company": "company"}
    out = il._map_row(raw, mapping)
    assert out["name"] == "Jane Doe"
    assert out["email"] == "jane@acme.com"   # lowercased
    assert out["company"] == "Acme"
    assert out["source"] == "import"          # defaulted


def test_map_row_unmapped_columns_go_to_custom_fields():
    raw = {"email": "a@b.com", "Region": "West", "Tier": "Gold"}
    out = il._map_row(raw, {})
    assert out["email"] == "a@b.com"
    assert out["custom_fields"] == {"Region": "West", "Tier": "Gold"}


def test_map_row_blank_strings_become_none_and_are_dropped():
    raw = {"email": "  ", "name": "  Bob  ", "phone": ""}
    out = il._map_row(raw, {})
    assert "email" not in out          # blank -> None -> not set
    assert out["name"] == "Bob"        # trimmed
    assert "phone" not in out


def test_map_row_respects_explicit_source_and_external_id():
    raw = {"email": "x@y.com", "src": "web", "ext": "crm-99"}
    out = il._map_row(raw, {"src": "source", "ext": "external_id"})
    assert out["source"] == "web"
    assert out["external_id"] == "crm-99"


# ---------------------------------------------------------------------------
# _load_rows — mock-friendly staged-payload boundary
# ---------------------------------------------------------------------------


def test_load_rows_inline_list():
    rows = [{"email": "a@b.com"}]
    assert il._load_rows(rows) is rows


def test_load_rows_json_string():
    assert il._load_rows('[{"email": "a@b.com"}]') == [{"email": "a@b.com"}]


def test_load_rows_from_file(tmp_path):
    p = tmp_path / "staged.json"
    p.write_text(json.dumps([{"email": "f@b.com"}]), encoding="utf-8")
    assert il._load_rows(str(p)) == [{"email": "f@b.com"}]


def test_load_rows_unknown_type_returns_empty():
    assert il._load_rows(None) == []


# ---------------------------------------------------------------------------
# _chunks — batch sizing
# ---------------------------------------------------------------------------


def test_chunks_splits_by_size():
    out = list(il._chunks(list(range(1250)), il.BATCH_SIZE))
    assert [len(c) for c in out] == [500, 500, 250]


# ---------------------------------------------------------------------------
# _run_import — the async worker body (mocked session)
# ---------------------------------------------------------------------------


def _session(rowcounts):
    """Build (session_factory, mock_db). db.execute returns a result whose
    .rowcount is drawn in order from `rowcounts` (one per insert chunk)."""
    results = [MagicMock(rowcount=rc) for rc in rowcounts]
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=results)

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=mock_db)
    cm.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=cm), mock_db


def _run(rows, mapping=None, dedupe_on="email", rowcounts=None):
    import asyncio

    factory, mock_db = _session(rowcounts or [len(rows)])
    with patch.object(il, "_get_async_session", return_value=factory):
        result = asyncio.run(il._run_import(_WS, rows, mapping or {}, dedupe_on))
    return result, mock_db


def test_run_import_inserts_all_rows():
    rows = [{"email": f"u{i}@x.com"} for i in range(3)]
    result, mock_db = _run(rows, rowcounts=[3])
    assert result["inserted"] == 3
    assert result["skipped"] == 0
    assert result["errors"] == 0
    assert result["workspace_id"] == _WS
    mock_db.execute.assert_awaited_once()
    mock_db.commit.assert_awaited_once()


def test_run_import_dedupes_on_conflict():
    """rowcount < chunk size => the difference counts as skipped duplicates."""
    rows = [{"email": f"u{i}@x.com"} for i in range(5)]
    result, _ = _run(rows, rowcounts=[3])   # 2 hit the unique index -> skipped
    assert result["inserted"] == 3
    assert result["skipped"] == 2
    assert result["dedupe_on"] == "email"


def test_run_import_writes_summary_activity_event():
    from app.models.activity_event import ActivityEvent

    rows = [{"email": "a@b.com"}]
    _, mock_db = _run(rows, rowcounts=[1])
    mock_db.add.assert_called_once()
    event = mock_db.add.call_args.args[0]
    assert isinstance(event, ActivityEvent)
    assert event.type == "leads_imported"
    assert event.workspace_id == uuid_mod.UUID(_WS)
    meta = json.loads(event.meta)
    assert meta["inserted"] == 1


def test_run_import_multiple_chunks_accumulate():
    rows = [{"email": f"u{i}@x.com"} for i in range(1100)]  # 500 + 500 + 100
    result, mock_db = _run(rows, rowcounts=[500, 490, 100])
    assert mock_db.execute.await_count == 3
    assert result["inserted"] == 1090
    assert result["skipped"] == 10


def test_run_import_caps_at_10k_and_flags_truncated():
    rows = [{"email": f"u{i}@x.com"} for i in range(10_050)]
    # 10k rows -> 20 chunks of 500; each fully inserts
    result, _ = _run(rows, rowcounts=[500] * 20)
    assert result["inserted"] == 10_000
    assert result["truncated"] is True


def test_run_import_bad_row_counts_as_error_not_crash():
    rows = [{"email": "ok@x.com"}, "not-a-dict", {"email": "ok2@x.com"}]
    result, _ = _run(rows, rowcounts=[2])
    assert result["errors"] == 1
    assert result["inserted"] == 2


def test_run_import_empty_rows_still_commits_zeros():
    result, mock_db = _run([], rowcounts=[])
    assert result["inserted"] == 0
    assert result["skipped"] == 0
    assert result["errors"] == 0
    mock_db.execute.assert_not_awaited()   # no chunks
    mock_db.commit.assert_awaited_once()   # summary event still written


def test_run_import_insert_failure_counts_chunk_as_errors():
    rows = [{"email": f"u{i}@x.com"} for i in range(4)]
    factory, mock_db = _session([])
    mock_db.execute = AsyncMock(side_effect=RuntimeError("db down"))
    import asyncio

    with patch.object(il, "_get_async_session", return_value=factory):
        result = asyncio.run(il._run_import(_WS, rows, {}, "email"))
    assert result["errors"] == 4
    assert result["inserted"] == 0


# ---------------------------------------------------------------------------
# Celery task wrapper — delegates to asyncio.run(_run_import(...))
# ---------------------------------------------------------------------------


def test_task_wrapper_delegates_to_run_import():
    with patch.object(il, "_run_import", new=AsyncMock(return_value={"inserted": 7})) as m:
        out = il.process_lead_import.run(_WS, [{"email": "a@b.com"}], {"e": "email"}, "email")
    assert out == {"inserted": 7}
    m.assert_awaited_once()


def test_task_registered_under_conventional_name():
    assert "app.workers.import_leads.process_lead_import" in il.celery_app.tasks
