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


# ---------------------------------------------------------------------------
# Redis-staged payloads — the api and worker are separate containers, so the
# router stages rows in Redis (shared) rather than on the api's local disk.
# ---------------------------------------------------------------------------


def test_load_rows_resolves_redis_ref():
    with patch.object(il, "_read_staged_payload", return_value='[{"email": "r@b.com"}]') as rd:
        assert il._load_rows("redis:lead-import:staged:ws:1") == [{"email": "r@b.com"}]
    rd.assert_called_once_with("lead-import:staged:ws:1")


def test_read_staged_payload_missing_key_raises():
    fake = MagicMock()
    fake.get.return_value = None
    with patch("redis.Redis.from_url", return_value=fake):
        try:
            il._read_staged_payload("lead-import:staged:gone")
        except ValueError as exc:
            assert "missing or expired" in str(exc)
        else:
            raise AssertionError("expected ValueError for a missing staged payload")


def test_read_staged_payload_does_not_delete():
    """A failed import must be retryable — the payload survives the read."""
    fake = MagicMock()
    fake.get.return_value = b'[{"email": "x@y.com"}]'
    with patch("redis.Redis.from_url", return_value=fake):
        assert il._read_staged_payload("k") == '[{"email": "x@y.com"}]'
    fake.delete.assert_not_called()


def test_run_import_deletes_staged_payload_only_after_success():
    ref = f"redis:lead-import:staged:{_WS}:abc"
    with patch.object(il, "_read_staged_payload", return_value='[{"email": "a@b.com"}]'), \
         patch.object(il, "_delete_staged_payload") as dele, \
         patch.object(il, "_get_async_session", return_value=_session([1])[0]):
        import asyncio
        asyncio.run(il._run_import(_WS, ref, {}, "email"))
    dele.assert_called_once_with(ref)


def test_run_import_rejects_staged_key_from_other_workspace():
    ref = "redis:lead-import:staged:bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb:abc"
    import asyncio
    try:
        asyncio.run(il._run_import(_WS, ref, {}, "email"))
    except ValueError as exc:
        assert "does not belong" in str(exc)
    else:
        raise AssertionError("expected cross-workspace staged key to be rejected")


# ---------------------------------------------------------------------------
# score + email-route mapping (ABC-tool prospect dossiers)
# ---------------------------------------------------------------------------


def test_map_row_score_is_coerced_and_clamped():
    assert il._map_row({"Working Score": "97"}, {"Working Score": "score"})["score"] == 97
    assert il._map_row({"s": "88.6"}, {"s": "score"})["score"] == 89
    assert il._map_row({"s": "140"}, {"s": "score"})["score"] == 100
    assert il._map_row({"s": "85%"}, {"s": "score"})["score"] == 85


def test_map_row_unparseable_score_is_kept_as_custom_field():
    out = il._map_row({"Working Score": "TBD"}, {"Working Score": "score"})
    assert "score" not in out
    assert out["custom_fields"]["Working Score"] == "TBD"
    # a column literally named "score" is namespaced so it can't shadow the real field
    assert il._map_row({"score": "n/a"}, {})["custom_fields"]["score_raw"] == "n/a"


def test_map_row_email_like_non_addresses_are_not_emails():
    for bogus in ("@VenueHandle", "REF@2024", "a@b"):
        out = il._map_row({"e": bogus}, {"e": "email"})
        assert "email" not in out, bogus
        assert out["custom_fields"]["contact_route"] == bogus


def test_map_row_non_email_contact_route_goes_to_custom_fields():
    out = il._map_row({"Route": "Online contact form"}, {"Route": "email"})
    assert "email" not in out
    assert out["custom_fields"]["contact_route"] == "Online contact form"


def test_map_row_real_email_still_maps():
    out = il._map_row({"Route": "NAngus@MononaTerrace.com"}, {"Route": "email"})
    assert out["email"] == "nangus@mononaterrace.com"


def test_uniform_keys_pads_sparse_rows_so_one_insert_renders():
    chunk = [
        {"workspace_id": "w", "email": "a@b.com", "source": "import"},
        {"workspace_id": "w", "company": "No Email Co", "source": "import", "custom_fields": {"x": 1}},
        {"workspace_id": "w", "score": 90, "source": "import"},
    ]
    out = il._uniform_keys(chunk)
    assert all(set(r) == set(out[0]) for r in out)
    assert out[0]["custom_fields"] == {}      # NOT NULL jsonb gets {}
    assert out[1]["email"] is None             # nullable pads None
    assert out[0]["score"] == 0 and out[2]["score"] == 90


def test_map_row_derives_stable_external_id_when_no_email():
    raw = {"Venue": "Olbrich Gardens", "Contact": "Tanya Z", "Phone": "608-246-4550"}
    mapping = {"Venue": "company", "Contact": "name", "Phone": "phone"}
    a = il._map_row(raw, mapping)
    b = il._map_row(dict(raw), mapping)
    assert a["external_id"].startswith("import:")
    assert a["external_id"] == b["external_id"]   # re-upload dedupes


def test_map_row_keeps_email_rows_without_derived_id():
    out = il._map_row({"email": "a@b.com", "company": "X"}, {})
    assert "external_id" not in out
