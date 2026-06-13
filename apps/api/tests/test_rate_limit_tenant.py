"""F5 — per-tenant rate limiting + per-workspace LLM spend cap.

Two halves:
  1. Rate-limit keying: with request.state.user set (which app/dependencies.py now
     does), two different authenticated principals arriving via the SAME proxy IP
     resolve to INDEPENDENT limiter buckets — no silent collapse to one shared IP
     bucket (the defect proven in evidence-cost-dos.md A1/A2).
  2. Spend cap: app/services/llm_budget.check_and_reserve reserves tokens against a
     per-workspace Redis counter and raises HTTP 429 once the window budget is
     exceeded; it is inert when disabled.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from httpx import AsyncClient, ASGITransport

from app.limiter import _rate_key
from app.config import settings
from app.services import llm_budget


# ---------------------------------------------------------------------------
# 1. Limiter key — per authenticated principal, never a shared IP fallback
# ---------------------------------------------------------------------------


def _request_for(user, proxy_ip: str = "100.64.0.7"):
    """Build a fake Starlette request that looks like it came via a shared proxy IP.

    request.state.user is set iff `user` is not None (mirrors what get_current_user
    now does for authenticated requests)."""
    req = MagicMock()
    req.client = MagicMock()
    req.client.host = proxy_ip  # behind Railway every tenant shares this peer IP
    state = MagicMock(spec=[])  # spec=[] => getattr(state, "user", None) is None by default
    if user is not None:
        state.user = user
    req.state = state
    return req


def _user(user_id):
    u = MagicMock()
    u.id = user_id
    return u


def test_two_principals_same_proxy_ip_get_independent_keys():
    """The core F5 fix: distinct authenticated users behind one proxy IP do NOT
    collapse to a single bucket."""
    a = _user(uuid.UUID("11111111-1111-1111-1111-111111111111"))
    b = _user(uuid.UUID("22222222-2222-2222-2222-222222222222"))

    key_a = _rate_key(_request_for(a, proxy_ip="100.64.0.7"))
    key_b = _rate_key(_request_for(b, proxy_ip="100.64.0.7"))  # SAME proxy IP

    assert key_a != key_b, "two authenticated users must get independent buckets"
    assert key_a == str(a.id)
    assert key_b == str(b.id)


def test_same_principal_is_stable_key_across_requests():
    a = _user(uuid.UUID("11111111-1111-1111-1111-111111111111"))
    assert _rate_key(_request_for(a)) == _rate_key(_request_for(a))


def test_unauthenticated_falls_back_to_ip_only_when_no_user():
    """When there is genuinely no principal (pre-auth), keying by IP is acceptable;
    what must NOT happen is an authenticated request silently using the shared IP."""
    req = _request_for(None, proxy_ip="100.64.0.7")
    assert _rate_key(req) == "100.64.0.7"


# ---------------------------------------------------------------------------
# 2. Spend cap — check_and_reserve over a per-workspace Redis counter
# ---------------------------------------------------------------------------


class _FakeRedis:
    """Minimal async Redis stand-in: per-key integer counter with INCRBY/DECRBY."""

    def __init__(self):
        self.store: dict[str, int] = {}
        self.expires: dict[str, int] = {}

    async def incrby(self, key, amount):
        self.store[key] = self.store.get(key, 0) + amount
        return self.store[key]

    async def decrby(self, key, amount):
        self.store[key] = self.store.get(key, 0) - amount
        return self.store[key]

    async def expire(self, key, ttl):
        self.expires[key] = ttl
        return True


@pytest.fixture
def _budget_settings():
    saved = (
        settings.LLM_BUDGET_ENABLED,
        settings.LLM_BUDGET_TOKENS_PER_WINDOW,
        settings.LLM_BUDGET_TOKENS_PER_MESSAGE,
    )
    yield
    (
        settings.LLM_BUDGET_ENABLED,
        settings.LLM_BUDGET_TOKENS_PER_WINDOW,
        settings.LLM_BUDGET_TOKENS_PER_MESSAGE,
    ) = saved


@pytest.mark.asyncio
async def test_budget_disabled_is_noop(_budget_settings):
    settings.LLM_BUDGET_ENABLED = False
    redis = _FakeRedis()

    out = await llm_budget.check_and_reserve("ws-1", 1_000_000, redis_client=redis)

    assert out == 0
    assert redis.store == {}, "disabled budget must not touch Redis (inert)"


@pytest.mark.asyncio
async def test_budget_allows_under_limit_and_sets_ttl(_budget_settings):
    settings.LLM_BUDGET_ENABLED = True
    settings.LLM_BUDGET_TOKENS_PER_WINDOW = 10_000
    redis = _FakeRedis()
    ws = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

    total = await llm_budget.check_and_reserve(ws, 4_000, redis_client=redis)

    assert total == 4_000
    # TTL set on the first write of the window so the budget rolls over.
    assert llm_budget._key(str(ws)) in redis.expires


@pytest.mark.asyncio
async def test_budget_blocks_with_429_when_exceeded(_budget_settings):
    settings.LLM_BUDGET_ENABLED = True
    settings.LLM_BUDGET_TOKENS_PER_WINDOW = 10_000
    redis = _FakeRedis()
    ws = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"

    # First reservation fits.
    await llm_budget.check_and_reserve(ws, 8_000, redis_client=redis)

    # Second reservation would push to 18,000 > 10,000 → 429.
    with pytest.raises(HTTPException) as exc:
        await llm_budget.check_and_reserve(ws, 8_000, redis_client=redis)

    assert exc.value.status_code == 429
    # The rejected reservation is rolled back so it doesn't burn headroom.
    assert redis.store[llm_budget._key(ws)] == 8_000


@pytest.mark.asyncio
async def test_budget_is_per_workspace_independent(_budget_settings):
    """One workspace exhausting its budget does not block a different workspace."""
    settings.LLM_BUDGET_ENABLED = True
    settings.LLM_BUDGET_TOKENS_PER_WINDOW = 10_000
    redis = _FakeRedis()

    # ws A exceeds.
    await llm_budget.check_and_reserve("ws-A", 9_000, redis_client=redis)
    with pytest.raises(HTTPException):
        await llm_budget.check_and_reserve("ws-A", 9_000, redis_client=redis)

    # ws B is unaffected and still has full headroom.
    total_b = await llm_budget.check_and_reserve("ws-B", 9_000, redis_client=redis)
    assert total_b == 9_000


@pytest.mark.asyncio
async def test_budget_fails_open_on_redis_error(_budget_settings):
    """A Redis outage must not hard-DoS the product: the cost guard fails open."""
    settings.LLM_BUDGET_ENABLED = True

    broken = MagicMock()
    broken.incrby = AsyncMock(side_effect=ConnectionError("redis down"))

    out = await llm_budget.check_and_reserve("ws-1", 5_000, redis_client=broken)
    assert out == 0  # allowed, not raised


@pytest.mark.asyncio
async def test_estimate_reprocess_tokens_scales_with_count(_budget_settings):
    settings.LLM_BUDGET_TOKENS_PER_MESSAGE = 4_000
    assert await llm_budget.estimate_reprocess_tokens(0) == 0
    assert await llm_budget.estimate_reprocess_tokens(10) == 40_000


# ---------------------------------------------------------------------------
# 3. Integration — independent buckets through the REAL middleware stack
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_two_principals_same_ip_independent_buckets_end_to_end():
    """Drive POST /messages/reprocess through the real app (SlowAPIMiddleware +
    the resolve_rate_principal middleware). Two principals on the SAME client IP
    must get independent rate buckets: throttling A must not throttle B.

    This is the decisive F5 proof — it exercises the actual ordering fix (the
    principal resolver runs BEFORE SlowAPIMiddleware evaluates the limiter key).
    """
    from app.main import app
    from app.dependencies import get_db, get_current_user

    ws = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    uid_a = uuid.UUID("11111111-1111-1111-1111-111111111111")
    uid_b = uuid.UUID("22222222-2222-2222-2222-222222222222")
    token_uid = {"tokA": uid_a, "tokB": uid_b}

    user = MagicMock()
    user.workspace_id = ws
    user.role = "admin"
    user.id = uuid.uuid4()
    user.supabase_uid = uid_a

    db = AsyncMock()
    count_res = MagicMock()
    count_res.scalar_one.return_value = 1
    db.execute = AsyncMock(return_value=count_res)

    async def _get_db():
        yield db

    async def _get_user():
        return user

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_current_user] = _get_user

    fake_task = MagicMock()
    fake_task.id = "job-x"

    # The principal-resolver middleware verifies the bearer token; map token->uid.
    def _verify(token):
        return {"sub": str(token_uid[token])}

    def _extract(payload):
        return uuid.UUID(payload["sub"])

    # Reset any limiter state carried from earlier tests so counts are clean.
    from app.limiter import limiter as _limiter
    if hasattr(_limiter, "reset"):
        _limiter.reset()

    try:
        with patch("app.services.auth.verify_supabase_jwt", side_effect=_verify), \
             patch("app.services.auth.extract_supabase_uid", side_effect=_extract), \
             patch("app.workers.ingest.reprocess_workspace_messages") as mock_task, \
             patch("app.routers.agents._mark_job_dispatched"):
            mock_task.apply_async.return_value = fake_task

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                # REPROCESS_RATE_LIMIT default is 3/minute. Fire enough as A to trip it.
                a_codes = []
                for _ in range(6):
                    r = await ac.post(
                        f"/workspaces/{ws}/messages/reprocess",
                        headers={"Authorization": "Bearer tokA"},
                    )
                    a_codes.append(r.status_code)

                # Same client IP, different principal — must NOT be pre-throttled by A.
                r_b = await ac.post(
                    f"/workspaces/{ws}/messages/reprocess",
                    headers={"Authorization": "Bearer tokB"},
                )

        assert 202 in a_codes
        assert 429 in a_codes, "principal A should hit its own limit"
        assert r_b.status_code == 202, (
            "principal B must have an independent bucket; a shared-IP fallback "
            f"would have 429'd it (got {r_b.status_code})"
        )
    finally:
        app.dependency_overrides.clear()
        if hasattr(_limiter, "reset"):
            _limiter.reset()


# ---------------------------------------------------------------------------
# 4. Long-queue routing is gated (deploy-safe by default)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled,expect_long", [(False, False), (True, True)])
async def test_reprocess_queue_routing_is_flag_gated(enabled, expect_long, monkeypatch):
    """LONG_QUEUE_ENABLED gates whether reprocess routes to the isolated `long`
    queue. Default OFF => no queue kwarg, so the task takes the default queue and
    the existing worker consumes it (deploy-safe without the `-Q default,long`
    worker change). ON => queue='long'."""
    from app.main import app
    from app.config import settings as _settings
    from app.dependencies import get_db, get_current_user

    monkeypatch.setattr(_settings, "LONG_QUEUE_ENABLED", enabled)

    ws = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    uid = uuid.UUID("33333333-3333-3333-3333-333333333333")
    user = MagicMock()
    user.workspace_id = ws
    user.role = "admin"
    user.id = uuid.uuid4()
    user.supabase_uid = uid

    db = AsyncMock()
    count_res = MagicMock()
    count_res.scalar_one.return_value = 1
    db.execute = AsyncMock(return_value=count_res)

    async def _get_db():
        yield db

    async def _get_user():
        return user

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_current_user] = _get_user

    fake_task = MagicMock()
    fake_task.id = "job-x"

    from app.limiter import limiter as _limiter
    if hasattr(_limiter, "reset"):
        _limiter.reset()

    try:
        with patch("app.services.auth.verify_supabase_jwt", side_effect=lambda t: {"sub": str(uid)}), \
             patch("app.services.auth.extract_supabase_uid", side_effect=lambda p: uuid.UUID(p["sub"])), \
             patch("app.workers.ingest.reprocess_workspace_messages") as mock_task, \
             patch("app.routers.agents._mark_job_dispatched"):
            mock_task.apply_async.return_value = fake_task
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                r = await ac.post(
                    f"/workspaces/{ws}/messages/reprocess",
                    headers={"Authorization": "Bearer tok"},
                )
        assert r.status_code == 202
        kwargs = mock_task.apply_async.call_args.kwargs
        if expect_long:
            assert kwargs.get("queue") == "long"
        else:
            assert kwargs.get("queue") != "long"
    finally:
        app.dependency_overrides.clear()
        if hasattr(_limiter, "reset"):
            _limiter.reset()
