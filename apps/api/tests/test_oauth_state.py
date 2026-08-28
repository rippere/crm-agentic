"""Tests for oauth_state.py — signed OAuth-state build/verify round-trip + the
four rejection branches of verify_state (malformed, tampered, corrupt, expired).

Pure unit tests: no DB, no network. Relies on the 32+ char SECRET_KEY that the
root-level conftest injects into the environment before app.config is imported.
"""

from __future__ import annotations

import uuid

import pytest

from app.services.oauth_state import build_state, verify_state


# ---------------------------------------------------------------------------
# happy path
# ---------------------------------------------------------------------------


def test_build_verify_roundtrip_returns_same_workspace_id():
    wid = uuid.uuid4()
    state = build_state(wid)
    assert verify_state(state) == wid


# ---------------------------------------------------------------------------
# rejection branches — each raises ValueError
# ---------------------------------------------------------------------------


def test_verify_rejects_malformed_state_without_separator():
    # No "." separator between payload and signature.
    with pytest.raises(ValueError, match="malformed state"):
        verify_state("no-separator-here")


def test_verify_rejects_tampered_signature():
    wid = uuid.uuid4()
    payload_b64, _sig = build_state(wid).split(".", 1)
    forged = f"{payload_b64}.{'A' * 43}"
    with pytest.raises(ValueError, match="invalid state signature"):
        verify_state(forged)


def test_verify_rejects_corrupt_payload():
    # A validly *signed* but non-JSON/non-uuid payload trips the payload branch.
    import app.services.oauth_state as oauth_state_mod

    bad_payload_b64 = oauth_state_mod._b64encode(b"not-json")
    signed = f"{bad_payload_b64}.{oauth_state_mod._sign(bad_payload_b64)}"
    with pytest.raises(ValueError, match="invalid state payload"):
        verify_state(signed)


def test_verify_rejects_expired_state():
    wid = uuid.uuid4()
    expired = build_state(wid, ttl_seconds=-1)
    with pytest.raises(ValueError, match="expired state"):
        verify_state(expired)
