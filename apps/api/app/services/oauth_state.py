"""
Signed OAuth state for connect flows (Gmail + Slack).

The `state` parameter on OAuth initiate/callback is otherwise an unauthenticated,
forgeable value. We sign a compact payload {wid, exp, nonce} with an HMAC keyed by
SECRET_KEY so the callback can recover a *verified* workspace_id without trusting the
raw redirect, and reject forged/expired/tampered state.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import uuid as uuid_mod

from app.config import settings

# State validity window (seconds). The OAuth round-trip is interactive but may
# include a consent screen, so allow a generous-but-bounded lifetime.
STATE_TTL_SECONDS = 600


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _sign(payload_b64: str) -> str:
    sig = hmac.new(
        settings.SECRET_KEY.encode(),
        payload_b64.encode(),
        hashlib.sha256,
    ).digest()
    return _b64encode(sig)


def build_state(workspace_id: uuid_mod.UUID, ttl_seconds: int = STATE_TTL_SECONDS) -> str:
    """Build a signed, expiring state string bound to `workspace_id`."""
    payload = {
        "wid": str(workspace_id),
        "exp": int(time.time()) + ttl_seconds,
        "nonce": str(uuid_mod.uuid4()),
    }
    payload_b64 = _b64encode(json.dumps(payload, separators=(",", ":")).encode())
    return f"{payload_b64}.{_sign(payload_b64)}"


def verify_state(state: str) -> uuid_mod.UUID:
    """Verify HMAC signature + expiry and return the workspace_id from the
    *verified* payload. Raises ValueError on any tampering, malformation, or
    expiry — callers should map that to HTTP 400.
    """
    try:
        payload_b64, sig = state.split(".", 1)
    except ValueError:
        raise ValueError("malformed state")

    expected_sig = _sign(payload_b64)
    if not hmac.compare_digest(sig, expected_sig):
        raise ValueError("invalid state signature")

    try:
        payload = json.loads(_b64decode(payload_b64).decode())
        workspace_id = uuid_mod.UUID(payload["wid"])
        exp = int(payload["exp"])
    except Exception:
        raise ValueError("invalid state payload")

    if time.time() > exp:
        raise ValueError("expired state")

    return workspace_id
