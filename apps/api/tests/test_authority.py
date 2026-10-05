"""Tests for the shared authority resolver (app/services/authority.py, R11/R12).

The resolver reads stage_controls + workspace_autonomy. Here db.execute is mocked
to return controlled rows so the fail-closed contract is exercised with no DB:
autonomy OFF never yields 'auto'; 'off' always survives; autonomy ON honors the
per-stage cap, defaulting to 'ask' when no row exists.
"""
from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock

from app.services.authority import resolve_authority

_WS = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


def _result(first_value):
    """A mock execute() result whose .first() returns first_value (a tuple or None)."""
    r = MagicMock()
    r.first.return_value = first_value
    return r


def _db(*, stage_mode_row, autonomy_row):
    """Mock db whose two execute() calls return (stage_mode, then autonomy) results.

    resolve_authority queries stage_controls first, then workspace_autonomy.
    """
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_result(stage_mode_row), _result(autonomy_row)])
    return db


def _resolve(stage_mode_row, autonomy_row, stage="contacted"):
    db = _db(stage_mode_row=stage_mode_row, autonomy_row=autonomy_row)
    return asyncio.run(resolve_authority(_WS, stage, "send", db))


# ── Autonomy OFF (default / no row) — fail closed (R12) ─────────────────────────
def test_autonomy_off_no_rows_returns_ask():
    """Fresh workspace: no stage row, no autonomy row -> 'ask' (never 'auto')."""
    assert _resolve(stage_mode_row=None, autonomy_row=None) == "ask"


def test_autonomy_off_downgrades_per_stage_auto_to_ask():
    """R12 keystone: per-stage 'auto' but master switch off -> 'ask'."""
    assert _resolve(stage_mode_row=("auto",), autonomy_row=(False,)) == "ask"


def test_autonomy_off_keeps_off():
    """A stage explicitly 'off' stays 'off' even with the master switch off."""
    assert _resolve(stage_mode_row=("off",), autonomy_row=(False,)) == "off"


# ── Autonomy ON — per-stage cap governs ─────────────────────────────────────────
def test_autonomy_on_honors_per_stage_auto():
    assert _resolve(stage_mode_row=("auto",), autonomy_row=(True,)) == "auto"


def test_autonomy_on_honors_per_stage_ask():
    assert _resolve(stage_mode_row=("ask",), autonomy_row=(True,)) == "ask"


def test_autonomy_on_honors_per_stage_off():
    assert _resolve(stage_mode_row=("off",), autonomy_row=(True,)) == "off"


def test_autonomy_on_no_stage_row_defaults_to_ask():
    """Master switch on but no per-stage row -> DEFAULT_STAGE_MODE ('ask')."""
    assert _resolve(stage_mode_row=None, autonomy_row=(True,)) == "ask"
