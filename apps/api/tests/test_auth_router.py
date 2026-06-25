"""Tests for app/routers/auth.py — /auth/verify, /me, /invite."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

from tests.conftest import _make_scalar_result


# ---------------------------------------------------------------------------
# GET /me
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_me_returns_current_user(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.get("/me")

    assert resp.status_code == 200
    data = resp.json()
    assert "id" in data
    assert "workspace_id" in data
    assert data["role"] == "admin"


# ---------------------------------------------------------------------------
# POST /auth/verify
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_invalid_jwt_returns_401(app_client):
    fastapi_app, mock_db, _ = app_client

    with patch("app.routers.auth.verify_supabase_jwt", side_effect=ValueError("Invalid token")):
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post("/auth/verify", headers={"Authorization": "Bearer bad_token"})

    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_verify_existing_user_returns_200(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    user_id = uuid.uuid4()
    existing_user = MagicMock()
    existing_user.id = user_id
    existing_user.workspace_id = workspace_id

    mock_db.execute = AsyncMock(return_value=_make_scalar_result(existing_user))

    supabase_uid = str(uuid.uuid4())
    payload = {
        "sub": supabase_uid,
        "email": "existing@example.com",
        "user_metadata": {"workspace_id": str(workspace_id)},
    }

    with patch("app.routers.auth.verify_supabase_jwt", return_value=payload):
        with patch("app.routers.auth.extract_supabase_uid", return_value=uuid.UUID(supabase_uid)):
            async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
                resp = await ac.post("/auth/verify", headers={"Authorization": "Bearer good_token"})

    assert resp.status_code == 200
    assert resp.json()["user_id"] == str(user_id)


@pytest.mark.asyncio
async def test_verify_no_bearer_token_returns_401(app_client):
    fastapi_app, mock_db, _ = app_client

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post("/auth/verify")

    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /workspaces/{wid}/invite
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_invalid_workspace_id_in_metadata_is_silently_ignored(app_client):
    """workspace_id in JWT metadata that isn't a valid UUID is silently swallowed."""
    fastapi_app, mock_db, workspace_id = app_client

    existing_user = MagicMock()
    existing_user.id = uuid.uuid4()
    existing_user.workspace_id = workspace_id

    mock_db.execute = AsyncMock(return_value=_make_scalar_result(existing_user))

    supabase_uid = str(uuid.uuid4())
    payload = {
        "sub": supabase_uid,
        "email": "user@example.com",
        "user_metadata": {"workspace_id": "not-a-valid-uuid"},
    }

    with patch("app.routers.auth.verify_supabase_jwt", return_value=payload):
        with patch("app.routers.auth.extract_supabase_uid", return_value=uuid.UUID(supabase_uid)):
            async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
                resp = await ac.post("/auth/verify", headers={"Authorization": "Bearer token"})

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_invite_wrong_workspace_returns_403(app_client):
    fastapi_app, mock_db, _ = app_client
    wrong_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/workspaces/{wrong_id}/invite",
            json={"email": "someone@example.com"},
        )

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_invite_non_admin_returns_403(app_client):
    fastapi_app, mock_db, workspace_id = app_client
    from app.dependencies import get_current_user

    member = MagicMock()
    member.workspace_id = workspace_id
    member.role = "member"

    async def override_member():
        return member

    fastapi_app.dependency_overrides[get_current_user] = override_member
    try:
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(
                f"/workspaces/{workspace_id}/invite",
                json={"email": "someone@example.com"},
            )
    finally:
        from app.dependencies import get_current_user as gcu
        async def _restore():
            return member
        # app_client's cleanup (dependency_overrides.clear()) will handle the rest

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_invite_happy_path(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    mock_http = AsyncMock()
    mock_http.post = AsyncMock(return_value=MagicMock(is_success=True))
    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_http)
    mock_cm.__aexit__ = AsyncMock(return_value=None)

    with patch("app.routers.auth.httpx.AsyncClient", return_value=mock_cm):
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(
                f"/workspaces/{workspace_id}/invite",
                json={"email": "newperson@example.com"},
            )

    assert resp.status_code == 200
    assert resp.json()["status"] == "invited"
    assert resp.json()["email"] == "newperson@example.com"


@pytest.mark.asyncio
async def test_verify_new_user_auto_provisions(app_client):
    fastapi_app, mock_db, _ = app_client

    new_user_id = uuid.uuid4()
    new_ws_id = uuid.uuid4()

    mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))

    async def fake_refresh(obj):
        obj.id = new_user_id
        obj.workspace_id = new_ws_id

    mock_db.refresh.side_effect = fake_refresh

    supabase_uid = str(uuid.uuid4())
    payload = {"sub": supabase_uid, "email": "newbie@example.com", "user_metadata": {}}

    with patch("app.routers.auth.verify_supabase_jwt", return_value=payload):
        with patch("app.routers.auth.extract_supabase_uid", return_value=uuid.UUID(supabase_uid)):
            with patch("app.routers.auth._sync_workspace_metadata", new=AsyncMock()):
                async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
                    resp = await ac.post("/auth/verify", headers={"Authorization": "Bearer token"})

    assert resp.status_code == 200
    assert resp.json()["user_id"] == str(new_user_id)
    mock_db.flush.assert_awaited()
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_verify_ignores_client_writable_workspace_id(app_client):
    """WS-B: an existing user's workspace binding must NOT move when the JWT
    carries a different workspace_id in user-writable metadata (the old
    reconciliation branch was a cross-tenant IDOR)."""
    fastapi_app, mock_db, workspace_id = app_client

    old_ws_id = workspace_id
    forged_ws_id = uuid.uuid4()

    existing_user = MagicMock()
    existing_user.id = uuid.uuid4()
    existing_user.workspace_id = old_ws_id

    mock_db.execute = AsyncMock(return_value=_make_scalar_result(existing_user))

    supabase_uid = str(uuid.uuid4())
    payload = {
        "sub": supabase_uid,
        "email": "user@example.com",
        "user_metadata": {"workspace_id": str(forged_ws_id)},
    }

    with patch("app.routers.auth.verify_supabase_jwt", return_value=payload):
        with patch("app.routers.auth.extract_supabase_uid", return_value=uuid.UUID(supabase_uid)):
            async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
                resp = await ac.post("/auth/verify", headers={"Authorization": "Bearer token"})

    assert resp.status_code == 200
    # Binding stays on the DB row's workspace; the forged claim is ignored.
    assert resp.json()["workspace_id"] == str(old_ws_id)
    # No write happens for an existing user — reconciliation is gone.
    mock_db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_invite_supabase_error_returns_502(app_client):
    fastapi_app, mock_db, workspace_id = app_client

    mock_http = AsyncMock()
    mock_response = MagicMock()
    mock_response.is_success = False
    mock_response.json.return_value = {"message": "User already invited"}
    mock_http.post = AsyncMock(return_value=mock_response)
    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_http)
    mock_cm.__aexit__ = AsyncMock(return_value=None)

    with patch("app.routers.auth.httpx.AsyncClient", return_value=mock_cm):
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
            resp = await ac.post(
                f"/workspaces/{workspace_id}/invite",
                json={"email": "dup@example.com"},
            )

    assert resp.status_code == 502
    assert "invited" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# _sync_workspace_metadata — direct unit tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_workspace_metadata_happy_path():
    from app.routers.auth import _sync_workspace_metadata

    mock_client = AsyncMock()
    mock_client.patch = AsyncMock(return_value=MagicMock(status_code=200))
    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
    mock_cm.__aexit__ = AsyncMock(return_value=None)

    with patch("app.routers.auth.httpx.AsyncClient", return_value=mock_cm):
        await _sync_workspace_metadata("uid-123", "ws-456")

    mock_client.patch.assert_awaited_once()
    call_kwargs = mock_client.patch.call_args
    assert "uid-123" in call_kwargs[0][0]  # URL contains supabase_uid


@pytest.mark.asyncio
async def test_sync_workspace_metadata_exception_is_swallowed():
    from app.routers.auth import _sync_workspace_metadata

    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(side_effect=Exception("network error"))
    mock_cm.__aexit__ = AsyncMock(return_value=None)

    with patch("app.routers.auth.httpx.AsyncClient", return_value=mock_cm):
        # Should not raise — exceptions are caught and suppressed
        await _sync_workspace_metadata("uid-xyz", "ws-xyz")
