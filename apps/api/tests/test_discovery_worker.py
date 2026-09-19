"""Tests for the discovery worker (app.workers.discovery).

Zero DB, zero Celery broker, zero network, zero LLM. Mirrors the
engagement_score / import_leads worker test style: an AsyncMock db behind a
MagicMock async-context-manager session factory patched over
``_get_async_session``; the provider waterfall and the LLM scorer are patched at
their seams.

Keystone assertions (BUILD-SPEC V7/V11):
  * the returned summary dict has EXACTLY the shared key set
    ``{run_id, workspace_id, locality, found, scored, inserted, skipped, status}``
    (R2/C4 — the ONE schema shared with the web poller);
  * discovery writes fit into ``custom_fields.discovery.fit_score`` and leaves
    ``lead.score`` at 0 (R5 — fit score != engagement score).
"""

from __future__ import annotations

import asyncio
import uuid as uuid_mod
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_WS = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"

_EXPECTED_SUMMARY_KEYS = {
    "run_id", "workspace_id", "locality", "found", "scored", "inserted", "skipped", "status",
}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _place(name, provider="google_places", place_id=None):
    from app.services.places import PlaceResult

    return PlaceResult(
        provider=provider,
        place_id=place_id or f"{provider}:{name}",
        name=name,
        category="Bar",
        address="1 Main St",
        locality="Burlington, VT",
        lat=44.47,
        lng=-73.21,
        phone="802-000-0000",
        website="https://x.test",
        source_url="https://x.test/about",
    )


def _make_run(run_id, ws_id, locality="Burlington, VT", params=None):
    run = MagicMock()
    run.id = run_id
    run.workspace_id = ws_id
    run.locality = locality
    run.params = params or {}
    run.rubric = {}
    run.status = "queued"
    run.stats = {}
    run.started_at = None
    run.completed_at = None
    run.job_id = None
    run.error = None
    return run


def _scalar_result(obj):
    result = MagicMock()
    result.scalar_one_or_none.return_value = obj
    return result


def _session_patch(mock_db):
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=mock_db)
    cm.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=cm)


def _nested_cm() -> MagicMock:
    """A SAVEPOINT (``db.begin_nested()``) async-context-manager stand-in.

    The worker upserts each row inside ``async with db.begin_nested():``. On a
    bare ``AsyncMock`` session, ``db.begin_nested()`` returns a *coroutine* (not
    an async CM), so ``async with`` raises and every per-row upsert is swallowed
    by the worker's defensive guard — leaving nothing captured. Handing back a
    real async CM lets the upsert body actually run.
    """
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=None)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


def _recording_pg_insert(captured: list):
    """A pg_insert stand-in that records every values() payload it is handed."""

    def _pg_insert(_model):
        stmt = MagicMock()

        def _values(*args, **kwargs):
            if args and isinstance(args[0], dict):
                captured.append(args[0])
            elif args and isinstance(args[0], (list, tuple)):
                captured.extend(a for a in args[0] if isinstance(a, dict))
            if kwargs:
                captured.append(dict(kwargs))
            vstmt = MagicMock()
            vstmt.on_conflict_do_update = MagicMock(return_value=MagicMock())
            vstmt.on_conflict_do_nothing = MagicMock(return_value=MagicMock())
            return vstmt

        stmt.values = MagicMock(side_effect=_values)
        return stmt

    return _pg_insert


def _find_fit_score(payloads: list) -> float | None:
    for p in payloads:
        cf = p.get("custom_fields")
        if isinstance(cf, dict):
            disc = cf.get("discovery")
            if isinstance(disc, dict) and "fit_score" in disc:
                return disc["fit_score"]
    return None


def _run_worker(run, universe, subscores_by_name):
    """Drive _run_discovery with all seams patched; return (summary, mock_db, payloads)."""
    import app.workers.discovery as mod
    import app.services.discovery_research as research

    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()
    mock_db.begin_nested = MagicMock(return_value=_nested_cm())

    calls = {"n": 0}

    async def _execute(*_a, **_k):
        calls["n"] += 1
        if calls["n"] == 1:
            return _scalar_result(run)  # run-row load
        return MagicMock(rowcount=1)  # upserts / misc

    mock_db.execute = AsyncMock(side_effect=_execute)

    captured: list = []

    async def _fake_research(place, rubric, market_context, *, client=None):
        return {"subscores": subscores_by_name.get(place.name, {})}

    with patch.object(mod, "_get_async_session", return_value=_session_patch(mock_db)), \
         patch.object(mod, "discover_venue_universe", new=AsyncMock(return_value=universe)), \
         patch.object(mod, "pg_insert", new=_recording_pg_insert(captured)), \
         patch.object(research, "_research_venue", new=_fake_research):
        summary = asyncio.run(mod._run_discovery(_WS, str(run.id)))

    return summary, mock_db, captured


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------


def test_summary_has_exact_shared_key_set():
    """V7 — the ONE summary schema shared with the web poller (R2/C4)."""
    ws_id = uuid_mod.UUID(_WS)
    run = _make_run(uuid_mod.uuid4(), ws_id)
    universe = [_place("Rí Rá Irish Pub"), _place("ECHO")]
    subs = {
        "Rí Rá Irish Pub": {
            "traffic": 5, "social_photo": 5, "group_dwell": 5, "brand_fit": 4.5,
            "placement_feasibility": 4.5, "year_round": 5, "contactability": 5,
        },
        "ECHO": {
            "traffic": 4.5, "social_photo": 5, "group_dwell": 4.5, "brand_fit": 5,
            "placement_feasibility": 4.5, "year_round": 5, "contactability": 5,
        },
    }
    summary, _, _ = _run_worker(run, universe, subs)
    assert set(summary.keys()) == _EXPECTED_SUMMARY_KEYS


def test_summary_counts_and_status_on_clean_run():
    ws_id = uuid_mod.UUID(_WS)
    run = _make_run(uuid_mod.uuid4(), ws_id)
    universe = [_place("Rí Rá Irish Pub"), _place("Foam Brewers")]
    subs = {n: {"traffic": 4} for n in ("Rí Rá Irish Pub", "Foam Brewers")}
    summary, _, _ = _run_worker(run, universe, subs)

    assert summary["found"] == 2
    assert summary["scored"] == 2
    assert summary["locality"] == "Burlington, VT"
    assert summary["workspace_id"] == _WS
    assert summary["status"] in ("succeeded", "partial")


def test_fit_score_written_to_custom_fields_and_score_left_zero():
    """V11 — fit != engagement: fit lands in custom_fields.discovery.fit_score;
    lead.score is never set to the fit value (stays default 0)."""
    ws_id = uuid_mod.UUID(_WS)
    run = _make_run(uuid_mod.uuid4(), ws_id)
    universe = [_place("Rí Rá Irish Pub")]
    subs = {
        "Rí Rá Irish Pub": {
            "traffic": 5, "social_photo": 5, "group_dwell": 5, "brand_fit": 4.5,
            "placement_feasibility": 4.5, "year_round": 5, "contactability": 5,
        }
    }
    _, _, payloads = _run_worker(run, universe, subs)

    fit = _find_fit_score(payloads)
    assert fit is not None, "expected custom_fields.discovery.fit_score in the upsert payload"
    assert fit == pytest.approx(97.5, abs=0.1)

    # lead.score must NOT carry the fit score (R5). Either absent or 0.
    for p in payloads:
        if "score" in p:
            assert p["score"] in (0, None), "discovery must not write the fit score to lead.score"


def test_writes_activity_event_and_advances_run_row():
    from app.models.activity_event import ActivityEvent

    ws_id = uuid_mod.UUID(_WS)
    run = _make_run(uuid_mod.uuid4(), ws_id)
    universe = [_place("Rí Rá Irish Pub")]
    subs = {"Rí Rá Irish Pub": {"traffic": 4}}
    _, mock_db, _ = _run_worker(run, universe, subs)

    added_types = [type(c.args[0]) for c in mock_db.add.call_args_list if c.args]
    assert ActivityEvent in added_types
    # run row moved out of 'queued' and stamped complete
    assert run.status in ("running", "succeeded", "partial", "failed")
    assert run.completed_at is not None


def test_empty_universe_is_partial_with_zero_found():
    """Degradation (V9): no venues (e.g. no Places key) → partial, found=0, no crash."""
    ws_id = uuid_mod.UUID(_WS)
    run = _make_run(uuid_mod.uuid4(), ws_id)
    summary, _, payloads = _run_worker(run, [], {})
    assert summary["found"] == 0
    assert summary["inserted"] == 0
    assert summary["status"] in ("partial", "succeeded")
    assert payloads == []


def test_task_registered_under_conventional_name():
    import app.workers.discovery as mod

    assert "app.workers.discovery.run_market_discovery" in mod.celery_app.tasks


def test_task_wrapper_delegates_to_run_discovery():
    import app.workers.discovery as mod

    with patch.object(mod, "_run_discovery",
                      new=AsyncMock(return_value={"status": "succeeded"})) as m:
        out = mod.run_market_discovery.run(_WS, str(uuid_mod.uuid4()))
    assert out == {"status": "succeeded"}
    m.assert_awaited_once()
