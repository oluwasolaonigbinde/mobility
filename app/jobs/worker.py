from typing import Any

from arq.connections import RedisSettings
from arq.cron import cron
from arq.worker import func
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.adapters.storage import build_storage_provider
from app.core.config import Settings, get_settings
from app.core.observability import configure_logging, init_error_tracking
from app.jobs.assignment_activity import sweep_assignment_activity_flags
from app.jobs.budget_enforcement import sweep_campaign_budget_enforcement
from app.jobs.campaign_assignments import sweep_campaign_assignment_expiries
from app.jobs.data_lifecycle import (
    check_ping_partition_coverage,
    premake_ping_partitions,
    purge_expired_ping_partitions,
)
from app.jobs.disclosure_retention import purge_expired_disclosure_query_history
from app.jobs.earnings_release import sweep_earnings_release_reviews
from app.jobs.email_delivery import sweep_email_notifications
from app.jobs.evidence_verification import sweep_evidence_verifications
from app.jobs.exposure_segments import materialize_exposure_segment_job
from app.jobs.file_lifecycle import (
    purge_expired_file_kyc,
    purge_orphaned_file_uploads,
    recover_stored_object_deletions,
)
from app.jobs.file_scanning import scan_pending_files
from app.jobs.payment_gateway import (
    process_payment_gateway_event_job,
    sweep_payment_gateway_events,
)
from app.jobs.trip_processing import (
    process_trip,
    process_unprocessed_trips,
    seal_ended_trips_job,
)
from app.jobs.vehicle_approvals import sweep_vehicle_approval_expiries
from app.services.report_issuances import sweep_report_issuances


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
    configure_logging(settings, service="worker")
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
    ctx["storage"] = build_storage_provider(settings)
    init_error_tracking(settings)


async def on_shutdown(ctx: dict[str, Any]) -> None:
    engine = ctx.get("engine")
    if engine is not None:
        await engine.dispose()


class WorkerSettings:
    health_check_interval = 30
    # arq reads worker options from this class's raw __dict__ (arq.worker.get_kwargs), so
    # redis_settings cannot be a lazy property. It resolves at import when REDIS_URL is set
    # and stays None otherwise (unconfigured test imports never need a broker).
    # keep_result=0: a deterministic job id must never suppress catch-up via a
    # stale result key — dedup applies only while queued/running (D4).
    functions: list = [
        func(process_trip, name="process_trip", keep_result=0),
        func(
            materialize_exposure_segment_job,
            name="materialize_exposure_segment",
            keep_result=0,
        ),
        func(
            process_payment_gateway_event_job,
            name="process_payment_gateway_event",
            keep_result=0,
        ),
    ]
    cron_jobs: list = [
        cron(
            process_unprocessed_trips,
            minute=sweep_cron_minutes(get_settings().worker_sweep_interval_minutes),
            unique=True,
        ),
        # Evidence-grace sweep records expiry for operations; exact manifest
        # reconciliation remains the only v2 sealing authority.
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
        cron(
            sweep_payment_gateway_events,
            minute=sweep_cron_minutes(get_settings().worker_sweep_interval_minutes),
            unique=True,
        ),
        cron(
            sweep_campaign_assignment_expiries,
            minute=sweep_cron_minutes(get_settings().worker_sweep_interval_minutes),
            unique=True,
        ),
        cron(
            sweep_vehicle_approval_expiries,
            minute=sweep_cron_minutes(get_settings().worker_sweep_interval_minutes),
            unique=True,
        ),
        cron(
            sweep_assignment_activity_flags,
            minute=sweep_cron_minutes(get_settings().worker_sweep_interval_minutes),
            unique=True,
        ),
        cron(
            sweep_evidence_verifications,
            minute=sweep_cron_minutes(get_settings().worker_sweep_interval_minutes),
            unique=True,
        ),
        cron(
            sweep_email_notifications,
            minute=sweep_cron_minutes(get_settings().worker_sweep_interval_minutes),
            unique=True,
        ),
        cron(
            sweep_campaign_budget_enforcement,
            minute=sweep_cron_minutes(get_settings().worker_sweep_interval_minutes),
            unique=True,
        ),
        cron(
            scan_pending_files,
            minute=sweep_cron_minutes(get_settings().worker_sweep_interval_minutes),
            unique=True,
        ),
        cron(
            sweep_report_issuances,
            minute=sweep_cron_minutes(get_settings().worker_sweep_interval_minutes),
            unique=True,
        ),
        # Data lifecycle (S4): daily, staggered hours so DDL never stacks.
        cron(premake_ping_partitions, hour={1}, minute={10}, unique=True),
        cron(check_ping_partition_coverage, hour={7}, minute={20}, unique=True),
        cron(purge_expired_ping_partitions, hour={3}, minute={30}, unique=True),
        cron(purge_expired_disclosure_query_history, hour={4}, minute={40}, unique=True),
        cron(
            recover_stored_object_deletions,
            minute=sweep_cron_minutes(get_settings().worker_sweep_interval_minutes),
            unique=True,
        ),
        cron(purge_orphaned_file_uploads, hour={5}, minute={50}, unique=True),
        cron(purge_expired_file_kyc, hour={6}, minute={0}, unique=True),
    ]
    # Worker-level too: finish_failed_job stores max-retries failures under the
    # deterministic job id using this value (func-level keep_result not consulted).
    keep_result = 0
    on_startup = on_startup
    on_shutdown = on_shutdown
    redis_settings = _optional_redis_settings()
