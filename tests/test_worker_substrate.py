import asyncio
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import sentry_sdk
import yaml
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
    assert settings.fraud_review_sla_days == 7


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


@pytest.mark.parametrize("invalid_value", [0, -1])
def test_fraud_review_sla_days_must_be_positive(invalid_value: int) -> None:
    with pytest.raises(ValidationError, match="FRAUD_REVIEW_SLA_DAYS must be positive"):
        Settings(fraud_review_sla_days=invalid_value)


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
    assert len(WorkerSettings.functions) == 2
    assert len(WorkerSettings.cron_jobs) == 10
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


def test_worker_entry_fails_before_worker_construction_without_redis_url(tmp_path: Path) -> None:
    repo_root = Path(__file__).parents[1]
    env = os.environ.copy()
    env.pop("REDIS_URL", None)
    env["PYTHONPATH"] = os.pathsep.join(
        path for path in (str(repo_root), env.get("PYTHONPATH", "")) if path
    )
    result = subprocess.run(
        [sys.executable, "-c", "import app.jobs.worker_entry"],
        # Keep a developer's gitignored .env from satisfying the missing-config case.
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert result.returncode != 0
    assert "REDIS_URL must be configured to run the arq worker" in result.stderr
    assert "localhost:6379" not in result.stderr


def test_worker_entry_exposes_configured_worker_settings() -> None:
    env = os.environ.copy()
    env["REDIS_URL"] = "redis://redis.example:6380/8"
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from app.jobs.worker_entry import WorkerSettings; "
            "print(WorkerSettings.redis_settings.host, WorkerSettings.redis_settings.database)",
        ],
        cwd=Path(__file__).parents[1],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "redis.example 8"


def test_compose_worker_uses_strict_entry_and_passes_sweep_settings() -> None:
    compose_path = Path(__file__).parents[1] / "docker-compose.yml"
    compose = yaml.safe_load(compose_path.read_text())

    backend_env = compose["x-backend-env"]
    assert backend_env["WORKER_SWEEP_INTERVAL_MINUTES"] == ("${WORKER_SWEEP_INTERVAL_MINUTES:-5}")
    assert backend_env["WORKER_SWEEP_BATCH_SIZE"] == "${WORKER_SWEEP_BATCH_SIZE:-25}"
    assert backend_env["FRAUD_REVIEW_SLA_DAYS"] == "${FRAUD_REVIEW_SLA_DAYS:-7}"
    assert compose["services"]["worker"]["command"] == ("arq app.jobs.worker_entry.WorkerSettings")
    assert "ports" not in compose["services"]["worker"]
