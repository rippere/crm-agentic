"""Shared test fixtures — async mock session + pre-built fake records."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.dependencies import get_db, get_current_user
from app.models.user import User


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def workspace_id() -> uuid.UUID:
    return uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


@pytest.fixture
def other_workspace_id() -> uuid.UUID:
    return uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


@pytest.fixture
def test_user(workspace_id: uuid.UUID) -> MagicMock:
    user = MagicMock(spec=User)
    user.workspace_id = workspace_id
    user.role = "admin"
    return user


@pytest.fixture
def mock_db() -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.delete = AsyncMock()
    db.flush = AsyncMock()
    return db


@pytest.fixture
def app_client(test_user: MagicMock, mock_db: AsyncMock):
    """FastAPI app with auth + DB overridden; yields (app, mock_db, workspace_id)."""
    async def _get_db():
        yield mock_db

    async def _get_current_user():
        return test_user

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_current_user] = _get_current_user
    yield app, mock_db, test_user.workspace_id
    app.dependency_overrides.clear()


def _make_scalar_result(obj):
    """Return a mock execute() result for a single-row query."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = obj
    return result


def _make_scalars_result(objs):
    """Return a mock execute() result for a multi-row query."""
    result = MagicMock()
    result.scalars.return_value.all.return_value = objs
    return result
