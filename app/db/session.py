from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings, get_settings

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine(settings: Settings | None = None) -> AsyncEngine:
    global _engine, _sessionmaker
    settings = settings or get_settings()
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is not configured")
    if _engine is None:
        _engine = create_async_engine(settings.database_url, pool_pre_ping=True)
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
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
