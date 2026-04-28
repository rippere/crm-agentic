"""
Supabase JWT verification for FastAPI.

User access_tokens are signed with ES256 (ECDSA P-256).
The public key is fetched lazily from the project's JWKS endpoint and cached
for 300 s. SUPABASE_JWT_SECRET is not used here (it only covers the static
anon/service-role tokens).
"""

import sys
import uuid
from typing import Any

import jwt as pyjwt
from jwt import PyJWKClient, PyJWKClientConnectionError, PyJWKClientError

from app.config import settings

_JWKS_URL = f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1/.well-known/jwks.json"
_jwks_client = PyJWKClient(_JWKS_URL, cache_jwk_set=True, lifespan=300)


def verify_supabase_jwt(token: str) -> dict[str, Any]:
    """
    Verify a Supabase user access_token via the project's JWKS endpoint.
    Returns the decoded payload dict. Raises ValueError on any failure.
    """
    try:
        unverified_header = pyjwt.get_unverified_header(token)
        print(f"[auth] token header: {unverified_header}", file=sys.stderr)
    except Exception as header_err:
        print(f"[auth] could not decode token header: {header_err}", file=sys.stderr)

    try:
        signing_key = _jwks_client.get_signing_key_from_jwt(token)
    except PyJWKClientConnectionError as exc:
        raise ValueError(f"Could not reach Supabase JWKS endpoint: {exc}") from exc
    except PyJWKClientError as exc:
        raise ValueError(f"JWKS key lookup failed: {exc}") from exc

    try:
        payload: dict[str, Any] = pyjwt.decode(
            token,
            signing_key,
            algorithms=["ES256", "RS256"],
            options={
                "verify_aud": False,
                "require": ["sub", "exp", "iat"],
            },
        )
        return payload
    except pyjwt.ExpiredSignatureError as exc:
        raise ValueError("Token has expired") from exc
    except pyjwt.PyJWTError as exc:
        raise ValueError(f"Invalid token: {exc}") from exc


def extract_supabase_uid(payload: dict[str, Any]) -> uuid.UUID:
    """Extract the user UUID from the 'sub' claim."""
    sub = payload.get("sub")
    if not sub:
        raise ValueError("Token payload missing 'sub' claim")
    return uuid.UUID(sub)
