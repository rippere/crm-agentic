from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

# statement_cache_size=0 (asyncpg) + prepared_statement_cache_size=0 (dialect)
# make the engine safe behind Supabase's transaction-mode pooler (port 6543) —
# session mode's 15-connection cap was exhausted by api+worker+beat, locking
# out every other client (EMAXCONNSESSION).
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    connect_args={
        "statement_cache_size": 0,
        "prepared_statement_cache_size": 0,
    },
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
