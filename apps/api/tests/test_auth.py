"""Tests for auth.py — JWT helpers."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

import app.services.auth as auth_mod
from app.services.auth import extract_supabase_uid


# ---------------------------------------------------------------------------
# extract_supabase_uid (pure function)
# ---------------------------------------------------------------------------


def test_extract_supabase_uid_valid_sub():
    uid = uuid.uuid4()
    payload = {"sub": str(uid), "exp": 9999999999}
    result = extract_supabase_uid(payload)
    assert result == uid


def test_extract_supabase_uid_missing_sub_raises():
    with pytest.raises(ValueError, match="sub"):
        extract_supabase_uid({"exp": 9999999999})


def test_extract_supabase_uid_empty_sub_raises():
    with pytest.raises(ValueError):
        extract_supabase_uid({"sub": "", "exp": 9999999999})


# ---------------------------------------------------------------------------
# verify_supabase_jwt (mocked JWKS client)
# ---------------------------------------------------------------------------


def test_verify_supabase_jwt_connection_error_raises():
    from jwt import PyJWKClientConnectionError

    with patch.object(auth_mod._jwks_client, "get_signing_key_from_jwt",
                      side_effect=PyJWKClientConnectionError("unreachable")):
        with pytest.raises(ValueError, match="JWKS"):
            auth_mod.verify_supabase_jwt("fake.jwt.token")


def test_verify_supabase_jwt_key_error_raises():
    from jwt import PyJWKClientError

    with patch.object(auth_mod._jwks_client, "get_signing_key_from_jwt",
                      side_effect=PyJWKClientError("bad key")):
        with pytest.raises(ValueError, match="JWKS"):
            auth_mod.verify_supabase_jwt("fake.jwt.token")
