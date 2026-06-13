"""F3 — RLS per-request tenant context (app/database.set_tenant_context).

Proves that:
  * With DB_RLS_CONTEXT_ENABLED=True, the request session emits a transaction-
    scoped SET LOCAL carrying the authenticated user's workspace_id (and a
    request.jwt.claims SET LOCAL so auth.uid() resolves under a non-BYPASSRLS
    role), so migration 013's workspace policies can evaluate.
  * With the flag OFF (the prod default), set_tenant_context is a no-op — nothing
    is emitted and behaviour is unchanged (inert backstop).

Zero real DB: the session is a mock that records the SQL text passed to execute().
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app import database as db_mod
from app.config import settings


_WS = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_UID = uuid.UUID("99999999-9999-9999-9999-999999999999")


def _recording_session():
    """A mock AsyncSession whose execute() records the compiled SQL + params."""
    calls: list[tuple[str, dict]] = []

    async def _execute(clause, params=None):
        calls.append((str(clause), params or {}))
        return MagicMock()

    session = AsyncMock()
    session.execute = _execute
    return session, calls


@pytest.fixture
def _restore_flag():
    """Snapshot/restore the two RLS settings so toggles don't leak across tests."""
    saved = (settings.DB_RLS_CONTEXT_ENABLED, settings.DB_RLS_GUC_KEY)
    yield
    settings.DB_RLS_CONTEXT_ENABLED, settings.DB_RLS_GUC_KEY = saved


@pytest.mark.asyncio
async def test_flag_off_is_noop(_restore_flag):
    settings.DB_RLS_CONTEXT_ENABLED = False
    session, calls = _recording_session()

    await db_mod.set_tenant_context(session, _WS, _UID)

    assert calls == [], "flag OFF must emit no SET LOCAL (inert default)"


@pytest.mark.asyncio
async def test_flag_on_emits_set_local_with_workspace(_restore_flag):
    settings.DB_RLS_CONTEXT_ENABLED = True
    settings.DB_RLS_GUC_KEY = "app.current_workspace_id"
    session, calls = _recording_session()

    await db_mod.set_tenant_context(session, _WS, _UID)

    sqls = [sql for sql, _ in calls]
    assert any("SET LOCAL" in s and "app.current_workspace_id" in s for s in sqls), \
        "expected a SET LOCAL of the workspace GUC"
    assert any("SET LOCAL request.jwt.claims" in s for s in sqls), \
        "expected request.jwt.claims SET LOCAL so auth.uid() resolves"

    # The workspace id must be carried as the bound param (not interpolated).
    params = [p for _, p in calls]
    assert any(p.get("ws") == str(_WS) for p in params), \
        "the workspace_id must be bound as the GUC value"

    # request.jwt.claims must be valid JSON carrying the user's sub (auth.uid()).
    claims_param = next(p["claims"] for _, p in calls if "claims" in p)
    decoded = json.loads(claims_param)
    assert decoded["sub"] == str(_UID)
    assert decoded["workspace_id"] == str(_WS)


@pytest.mark.asyncio
async def test_flag_on_none_workspace_emits_nothing(_restore_flag):
    """A user with no workspace yet must not emit a malformed SET LOCAL."""
    settings.DB_RLS_CONTEXT_ENABLED = True
    session, calls = _recording_session()

    await db_mod.set_tenant_context(session, None, _UID)

    assert calls == []


@pytest.mark.asyncio
async def test_uses_configured_guc_key(_restore_flag):
    """The GUC key is taken from config (so a future policy can read it)."""
    settings.DB_RLS_CONTEXT_ENABLED = True
    settings.DB_RLS_GUC_KEY = "request.workspace_id"
    session, calls = _recording_session()

    await db_mod.set_tenant_context(session, _WS, _UID)

    sqls = [sql for sql, _ in calls]
    assert any("request.workspace_id" in s for s in sqls)
    assert not any("app.current_workspace_id" in s for s in sqls)


@pytest.mark.asyncio
async def test_get_current_user_sets_request_state_and_binds_context(_restore_flag, monkeypatch):
    """Integration-ish: get_current_user sets request.state.user AND calls
    set_tenant_context for the resolved user (the two seams F5 + F3 depend on)."""
    from app import dependencies as deps

    settings.DB_RLS_CONTEXT_ENABLED = True

    user = MagicMock()
    user.id = uuid.uuid4()
    user.workspace_id = _WS
    user.supabase_uid = _UID

    # Short-circuit JWT verification + the DB user lookup to return our user.
    monkeypatch.setattr(deps, "verify_supabase_jwt", lambda token: {"sub": str(_UID)})
    monkeypatch.setattr(deps, "extract_supabase_uid", lambda payload: _UID)

    db = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=user)))

    recorded = {}

    async def _fake_set_ctx(session, workspace_id, supabase_uid=None):
        recorded["ws"] = workspace_id
        recorded["uid"] = supabase_uid

    monkeypatch.setattr(deps, "set_tenant_context", _fake_set_ctx)

    request = MagicMock()
    request.state = MagicMock()

    returned = await deps.get_current_user(request=request, token="tok", db=db)

    assert returned is user
    assert request.state.user is user, "request.state.user must be set for the limiter key"
    assert recorded == {"ws": _WS, "uid": _UID}, "tenant context must be bound for the user"
