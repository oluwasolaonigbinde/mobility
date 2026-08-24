from typing import Any

from arq.connections import RedisSettings
from arq.cron import cron
from arq.worker import func
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import Settings, get_settings
from app.core.observability import init_error_tracking
from app.jobs.data_lifecycle import (
    check_ping_partition_coverage,
    premake_ping_partitions,
    purge_expired_ping_partitions,
)
from app.jobs.earnings_release import sweep_earnings_release_reviews
from app.jobs.trip_processing import (
    process_trip,
    process_unprocessed_trips,
    seal_ended_trips_job,
)


def sweep_cron_minutes(interval_minutes: int) -> set[int]:
    return set(range(0, 60, interval_minutes))


def build_redis_settings(settings: Settings | None = None) -> RedisSettings:
    settings = settings or get_settings()
    if not settings.redis_url:
        raise RuntimeError("REDIS_URL must be configured to run the arq worker")
    return RedisSettings.from_dsn(settings.redis_url)


def _optional_redis_settings() -> RedisSettings | None:
    return build_redis_settings() if get_settings().redis_url else None


async def on_startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    # Guard the redis_settings=None import fallback: never run against arq's
    # implicit localhost default.
    if not settings.redis_url:
        raise RuntimeError("REDIS_URL must be configured to run the arq worker")
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is not configured")
    # Created here (not at import) so the engine binds to the worker process's event loop.
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    ctx["settings"] = settings
    ctx["engine"] = engine
    ctx["sessionmaker"] = async_sessionmaker(engine, expire_on_commit=False)
    init_error_tracking(settings)


async def on_shutdown(ctx: dict[str, Any]) -> None:
    engine = ctx.get("engine")
    if engine is not None:
        await engine.dispose()


class WorkerSettings:
    # arq reads worker options from this class's raw __dict__ (arq.worker.get_kwargs), so
    # redis_settings cannot be a lazy property. It resolves at import when REDIS_URL is set
    # and stays None otherwise (unconfigured test imports never need a broker).
    # keep_result=0: a deterministic job id must never suppress catch-up via a
    # stale result key — dedup applies only while queued/running (D4).
    functions: list = [func(process_trip, name="process_trip", keep_result=0)]
    cron_jobs: list = [
        cron(
            process_unprocessed_trips,
            minute=sweep_cron_minutes(get_settings().worker_sweep_interval_minutes),
            unique=True,
        ),
        # Seal sweep (RM3): force-seals ended trips past the recovery grace so
        # the money chain (sealed-only) can pick them up. Same cadence as the
        # processing sweep.
        cron(
            seal_ended_trips_job,
            minute=sweep_cron_minutes(get_settings().worker_sweep_interval_minutes),
            unique=True,
        ),
        cron(
            sweep_earnings_release_reviews,
            minute=sweep_cron_minutes(get_settings().worker_sweep_interval_minutes),
            unique=True,
        ),
        # Data lifecycle (S4): daily, staggered hours so DDL never stacks.
        cron(premake_ping_partitions, hour={1}, minute={10}, unique=True),
        cron(check_ping_partition_coverage, hour={7}, minute={20}, unique=True),
        cron(purge_expired_ping_partitions, hour={3}, minute={30}, unique=True),
    ]
    # Worker-level too: finish_failed_job stores max-retries failures under the
    # deterministic job id using this value (func-level keep_result not consulted).
    keep_result = 0
    on_startup = on_startup
    on_shutdown = on_shutdown
    redis_settings = _optional_redis_settings()
