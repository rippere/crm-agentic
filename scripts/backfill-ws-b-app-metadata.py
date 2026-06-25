#!/usr/bin/env python3
"""WS-B cutover backfill — bind every existing auth user's workspace into
server-only app_metadata.

Post WS-B, the API reads the workspace binding ONLY from app_metadata (or the
users table row). This script migrates existing users so nobody falls into the
fresh-workspace fallback:

  1. users-table row wins: app_metadata.workspace_id := users.workspace_id
  2. auth user with NO users row but a legacy user_metadata.workspace_id that
     points at a real workspace: import it (preserves pre-fix status quo).
  3. auth user with neither: leave untouched (fresh provision on next login is
     the correct outcome for a data-less account).

Env (never hardcode): SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY.
Usage: python backfill-ws-b-app-metadata.py [--apply]   (default: dry run)

Reads the users/workspaces tables via PostgREST (service role) rather than the
session-mode pooler — prod services hold all 15 pooler slots (EMAXCONNSESSION).
"""
from __future__ import annotations

import asyncio
import os
import sys

import httpx

APPLY = "--apply" in sys.argv


async def main() -> None:
    supabase_url = os.environ["SUPABASE_URL"].rstrip("/")
    service_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            f"{supabase_url}/rest/v1/users",
            headers=headers,
            params={"select": "supabase_uid,workspace_id,email"},
        )
        resp.raise_for_status()
        db_binding = {
            str(r["supabase_uid"]): str(r["workspace_id"])
            for r in resp.json()
            if r.get("workspace_id")
        }
        resp = await client.get(
            f"{supabase_url}/rest/v1/workspaces", headers=headers, params={"select": "id"}
        )
        resp.raise_for_status()
        known_ws = {str(r["id"]) for r in resp.json()}

    print(f"users table: {len(db_binding)} bound rows; workspaces: {len(known_ws)}")

    patched = skipped_ok = imported_legacy = untouched = 0
    async with httpx.AsyncClient(timeout=15.0) as client:
        page = 1
        while True:
            resp = await client.get(
                f"{supabase_url}/auth/v1/admin/users",
                headers=headers,
                params={"page": page, "per_page": 100},
            )
            resp.raise_for_status()
            users = resp.json().get("users", [])
            if not users:
                break

            for u in users:
                uid = u["id"]
                email = u.get("email", "?")
                app_ws = (u.get("app_metadata") or {}).get("workspace_id")
                user_ws = (u.get("user_metadata") or {}).get("workspace_id")

                target = db_binding.get(uid)
                origin = "users-table"
                if target is None and user_ws and user_ws in known_ws:
                    target = user_ws  # legacy binding import (pre-fix status quo)
                    origin = "legacy user_metadata"

                if target is None:
                    untouched += 1
                    print(f"  SKIP   {email}: no binding anywhere — fresh provision on next login")
                    continue
                if app_ws == target:
                    skipped_ok += 1
                    print(f"  OK     {email}: app_metadata already bound")
                    continue

                print(f"  {'PATCH' if APPLY else 'WOULD-PATCH':6} {email}: -> {target[:8]}… ({origin})")
                if APPLY:
                    r = await client.put(
                        f"{supabase_url}/auth/v1/admin/users/{uid}",
                        headers=headers,
                        json={"app_metadata": {"workspace_id": target}},
                    )
                    r.raise_for_status()
                if origin == "legacy user_metadata":
                    imported_legacy += 1
                patched += 1

            if len(users) < 100:
                break
            page += 1

    mode = "APPLIED" if APPLY else "DRY RUN"
    print(
        f"\n[{mode}] patched={patched} (legacy imports={imported_legacy}) "
        f"already-ok={skipped_ok} untouched={untouched}"
    )


if __name__ == "__main__":
    asyncio.run(main())
