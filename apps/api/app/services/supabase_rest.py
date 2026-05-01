"""
Supabase REST API client using the service role key.
Used as a fallback when local Postgres doesn't have a record (DB split between
local dev Docker and Supabase cloud).
"""
from __future__ import annotations

import os
from typing import Any

import httpx

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")


def _headers() -> dict[str, str]:
    return {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


async def get_row(table: str, filters: dict[str, str]) -> dict[str, Any] | None:
    """Fetch the first matching row from a Supabase table via REST."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        return None
    params = {k: f"eq.{v}" for k, v in filters.items()}
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers=_headers(),
            params=params,
        )
    if resp.status_code != 200:
        return None
    data = resp.json()
    return data[0] if data else None


async def list_rows(table: str, filters: dict[str, str], limit: int = 100) -> list[dict[str, Any]]:
    """Fetch matching rows from a Supabase table via REST."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        return []
    params = {k: f"eq.{v}" for k, v in filters.items()}
    params["limit"] = str(limit)
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers=_headers(),
            params=params,
        )
    if resp.status_code != 200:
        return []
    return resp.json() if isinstance(resp.json(), list) else []
