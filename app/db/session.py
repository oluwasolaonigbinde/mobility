from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings, get_settings
from app.db.outbox_session import OutboxSession

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None

# Fixed pilot-workload bounds, not deployment configuration. Recalculate the
# connection budget when API process count or worker replicas change.
DATABASE_STATEMENT_TIMEOUT_MS = 120_000
DATABASE_LOCK_TIMEOUT_MS = 10_000
DATABASE_IDLE_TRANSACTION_TIMEOUT_MS = 60_000
DATABASE_POOL_WAIT_SECONDS = 10
DATABASE_POOL_SIZE = 5
API_POOL_OVERFLOW = 5
WORKER_POOL_OVERFLOW = 6


def create_database_engine(database_url: str, *, worker: bool = False) -> AsyncEngine:
    return create_async_engine(
        database_url,
        pool_pre_ping=True,
        pool_size=DATABASE_POOL_SIZE,
        max_overflow=WORKER_POOL_OVERFLOW if worker else API_POOL_OVERFLOW,
        pool_timeout=DATABASE_POOL_WAIT_SECONDS,
        connect_args={
            "server_settings": {
                "statement_timeout": str(DATABASE_STATEMENT_TIMEOUT_MS),
                "lock_timeout": str(DATABASE_LOCK_TIMEOUT_MS),
                "idle_in_transaction_session_timeout": str(DATABASE_IDLE_TRANSACTION_TIMEOUT_MS),
            }
        },
    )


def get_engine(settings: Settings | None = None) -> AsyncEngine:
    global _engine, _sessionmaker
    settings = settings or get_settings()
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is not configured")
    if _engine is None:
        _engine = create_database_engine(settings.database_url)
        _sessionmaker = async_sessionmaker(
            _engine,
            class_=OutboxSession,
            expire_on_commit=False,
            info={"enqueue_settings": settings},
        )
    return _engine


async def get_session() -> AsyncIterator[AsyncSession]:
    if _sessionmaker is None:
        get_engine()
    if _sessionmaker is None:
        raise RuntimeError("Database sessionmaker is not configured")
    async with _sessionmaker() as session:
        yield session


async def check_database(settings: Settings | None = None) -> bool:
    try:
        engine = get_engine(settings)
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
