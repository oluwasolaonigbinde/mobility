import asyncio
from typing import Any

import pytest
import sentry_sdk
from arq.connections import RedisSettings
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.core.config import Settings
from app.jobs import worker
from app.jobs.worker import WorkerSettings, build_redis_settings, sweep_cron_minutes


def test_worker_settings_defaults() -> None:
    settings = Settings()

    assert settings.worker_sweep_interval_minutes == 5
    assert settings.worker_sweep_batch_size == 25


@pytest.mark.parametrize("invalid_value", [0, 7, 13, 61, -5])
def test_worker_sweep_interval_rejects_non_divisors_of_60(invalid_value: int) -> None:
    with pytest.raises(ValidationError):
        Settings(worker_sweep_interval_minutes=invalid_value)


@pytest.mark.parametrize("valid_value", [1, 5, 6, 10, 12, 15, 20, 30, 60])
def test_worker_sweep_interval_accepts_divisors_of_60(valid_value: int) -> None:
    settings = Settings(worker_sweep_interval_minutes=valid_value)

    assert settings.worker_sweep_interval_minutes == valid_value


@pytest.mark.parametrize("invalid_value", [0, -1])
def test_worker_sweep_batch_size_must_be_positive(invalid_value: int) -> None:
    with pytest.raises(ValidationError):
        Settings(worker_sweep_batch_size=invalid_value)


def test_sweep_cron_minutes_tiles_the_hour() -> None:
    assert sweep_cron_minutes(5) == {0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55}
    assert sweep_cron_minutes(15) == {0, 15, 30, 45}
    assert sweep_cron_minutes(60) == {0}


def test_on_startup_and_on_shutdown_lifecycle(tmp_path, monkeypatch) -> None:
    # redis_url is required by the on_startup guard; no connection is made here.
    settings = Settings(
        environment="test",
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'worker.db'}",
        redis_url="redis://localhost:6380/8",
    )
    monkeypatch.setattr(worker, "get_settings", lambda: settings)
    sentry_init_calls: list[dict[str, Any]] = []
    monkeypatch.setattr(sentry_sdk, "init", lambda **kwargs: sentry_init_calls.append(kwargs))

    ctx: dict[str, Any] = {}

    async def exercise() -> None:
        await worker.on_startup(ctx)
        assert ctx["settings"] is settings
        assert isinstance(ctx["engine"], AsyncEngine)
        assert isinstance(ctx["sessionmaker"], async_sessionmaker)
        async with ctx["sessionmaker"]() as session:
            result = await session.execute(text("SELECT 1"))
            assert result.scalar_one() == 1

        # engine.dispose() closes checked-in connections and swaps in a fresh pool.
        pool_before = ctx["engine"].sync_engine.pool
        assert pool_before.checkedin() == 1
        await worker.on_shutdown(ctx)
        assert ctx["engine"].sync_engine.pool is not pool_before
        assert pool_before.checkedin() == 0

    asyncio.run(exercise())

    assert sentry_init_calls == []


def test_on_startup_requires_database_url(monkeypatch) -> None:
    settings = Settings(
        environment="test",
        database_url=None,
        redis_url="redis://localhost:6380/8",
    )
    monkeypatch.setattr(worker, "get_settings", lambda: settings)

    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        asyncio.run(worker.on_startup({}))


def test_on_startup_requires_redis_url(monkeypatch) -> None:
    settings = Settings(environment="test", database_url=None, redis_url=None)
    monkeypatch.setattr(worker, "get_settings", lambda: settings)

    with pytest.raises(RuntimeError, match="REDIS_URL"):
        asyncio.run(worker.on_startup({}))


def test_on_shutdown_tolerates_missing_engine() -> None:
    asyncio.run(worker.on_shutdown({}))


def test_worker_settings_importable_without_broker_or_database() -> None:
    assert len(WorkerSettings.functions) == 1
    assert len(WorkerSettings.cron_jobs) == 1
    assert WorkerSettings.keep_result == 0
    assert WorkerSettings.on_startup is worker.on_startup
    assert WorkerSettings.on_shutdown is worker.on_shutdown


def test_build_redis_settings_requires_redis_url() -> None:
    settings = Settings(environment="test", redis_url=None)

    with pytest.raises(RuntimeError):
        build_redis_settings(settings)


def test_build_redis_settings_parses_dsn() -> None:
    settings = Settings(redis_url="redis://localhost:6380/8")

    redis_settings = build_redis_settings(settings)

    assert isinstance(redis_settings, RedisSettings)
    assert redis_settings.host == "localhost"
    assert redis_settings.port == 6380
    assert redis_settings.database == 8
