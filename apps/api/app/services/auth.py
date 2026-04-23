import uuid
from typing import Any

from jose import jwt, JWTError

from app.config import settings


def verify_supabase_jwt(token: str) -> dict[str, Any]:
    """
    Verify a Supabase-issued JWT using the project's JWT secret.
    Returns the full payload if valid, raises ValueError on failure.
    """
    try:
        payload = jwt.decode(
            token,
            settings.SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            options={"verify_aud": False},  # Supabase JWTs may have custom audience
        )
        return payload
    except JWTError as exc:
        raise ValueError(f"Invalid token: {exc}") from exc


def extract_supabase_uid(payload: dict[str, Any]) -> uuid.UUID:
    """Extract the user UUID from the 'sub' claim."""
    sub = payload.get("sub")
    if not sub:
        raise ValueError("Token payload missing 'sub' claim")
    return uuid.UUID(sub)
