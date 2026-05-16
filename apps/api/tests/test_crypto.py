"""Tests for crypto.py — Fernet encrypt/decrypt round-trip."""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

import app.services.crypto as crypto_mod
from app.services.crypto import encrypt_token, decrypt_token


def _fake_settings(secret_key: str = "test-secret-key-for-testing-only"):
    s = MagicMock()
    s.SECRET_KEY = secret_key
    return s


# ---------------------------------------------------------------------------
# round-trip
# ---------------------------------------------------------------------------


def test_encrypt_decrypt_roundtrip():
    with patch.object(crypto_mod, "settings", _fake_settings()):
        ciphertext = encrypt_token("my-oauth-token")
        plaintext = decrypt_token(ciphertext)
    assert plaintext == "my-oauth-token"


def test_encrypt_produces_different_bytes_each_call():
    with patch.object(crypto_mod, "settings", _fake_settings()):
        c1 = encrypt_token("same-token")
        c2 = encrypt_token("same-token")
    # Fernet uses random IV so ciphertexts differ
    assert c1 != c2


def test_encrypt_output_is_string():
    with patch.object(crypto_mod, "settings", _fake_settings()):
        result = encrypt_token("hello")
    assert isinstance(result, str)


def test_decrypt_with_wrong_key_raises():
    with patch.object(crypto_mod, "settings", _fake_settings("key-a")):
        ciphertext = encrypt_token("secret")

    from cryptography.fernet import InvalidToken
    with patch.object(crypto_mod, "settings", _fake_settings("key-b")):
        with pytest.raises(InvalidToken):
            decrypt_token(ciphertext)
