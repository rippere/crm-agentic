import json
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

# statement_cache_size=0 (asyncpg) + prepared_statement_cache_size=0 (dialect)
# make the engine safe behind Supabase's transaction-mode pooler (port 6543) —
# session mode's 15-connection cap was exhausted by api+worker+beat, locking
# out every other client (EMAXCONNSESSION).
#
# Caching off is NOT enough: asyncpg still names every prepared statement with
# a per-connection counter (__asyncpg_stmt_N__), and the pooler multiplexes
# many client connections onto one server connection — counters collide and
# raise DuplicatePreparedStatementError, 500ing every DB-backed endpoint.
# Randomizing the names (per SQLAlchemy's asyncpg/pgbouncer guidance) makes
# collisions impossible. Shared here so the worker engines use it too.
PGBOUNCER_CONNECT_ARGS = {
    "statement_cache_size": 0,
    "prepared_statement_cache_size": 0,
    "prepared_statement_name_func": lambda: f"__asyncpg_{uuid4()}__",
}

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    connect_args=PGBOUNCER_CONNECT_ARGS,
)

AsyncSessionFactory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def set_tenant_context(session: AsyncSession, workspace_id, supabase_uid=None) -> None:
    """F3 RLS backstop: bind the tenant identity to the current DB transaction.

    Emits ``SET LOCAL`` statements so the workspace RLS policies from migration
    013 resolve when (and only when) the API connects as a non-BYPASSRLS role:

      * ``SET LOCAL <DB_RLS_GUC_KEY> = '<workspace_id>'`` — a direct GUC alias a
        future policy can read with ``current_setting(...)``.
      * ``SET LOCAL request.jwt.claims = '{"sub": "<uid>"}'`` — what the existing
        013 policies actually read via ``auth.uid()`` (Supabase maps auth.uid()
        to ``request.jwt.claim.sub`` / the ``sub`` of ``request.jwt.claims``).

    Gating + pooler safety:
      * No-op unless ``settings.DB_RLS_CONTEXT_ENABLED`` is True (default False),
        so this is INERT in prod until the ops role-swap cutover.
      * ``SET LOCAL`` is transaction-scoped, so it MUST run inside the same
        transaction as the queries it should constrain. Under Supabase's
        transaction-mode pooler a fresh server connection is leased per
        transaction; binding it here (before the request's queries, within the
        request session's transaction) is exactly the supported pattern.

    Idempotent and side-effect-free when the flag is off; callers may invoke it
    unconditionally.
    """
    if not settings.DB_RLS_CONTEXT_ENABLED:
        return
    if workspace_id is None:
        return

    ws = str(workspace_id)
    # GUC keys cannot be bound as parameters; the key is from trusted config and
    # the value is a parameter, so this is not injectable.
    await session.execute(
        text(f"SET LOCAL {settings.DB_RLS_GUC_KEY} = :ws"), {"ws": ws}
    )
    # request.jwt.claims must be valid JSON for auth.uid() (->> 'sub') to resolve.
    claims = {"sub": str(supabase_uid)} if supabase_uid is not None else {}
    # Mirror workspace into the claims too (harmless, aids debugging / future policies).
    claims["workspace_id"] = ws
    await session.execute(
        text("SET LOCAL request.jwt.claims = :claims"),
        {"claims": json.dumps(claims)},
    )


async def get_db() -> AsyncSession:  # type: ignore[misc]
    async with AsyncSessionFactory() as session:
        yield session
