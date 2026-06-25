from uuid import uuid4

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


async def get_db() -> AsyncSession:  # type: ignore[misc]
    async with AsyncSessionFactory() as session:
        yield session
