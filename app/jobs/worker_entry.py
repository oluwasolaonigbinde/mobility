from collections.abc import Awaitable, Callable
from typing import ClassVar

from app.jobs.worker import WorkerSettings as ImportSafeWorkerSettings
from app.jobs.worker import build_redis_settings

REDIS_SETTINGS = build_redis_settings()


class WorkerSettings:
    """Production CLI boundary; configuration fails before arq opens a Redis pool."""

    functions = ImportSafeWorkerSettings.functions
    max_jobs = ImportSafeWorkerSettings.max_jobs
    job_timeout = ImportSafeWorkerSettings.job_timeout
    cron_jobs = ImportSafeWorkerSettings.cron_jobs
    keep_result = ImportSafeWorkerSettings.keep_result
    health_check_interval = ImportSafeWorkerSettings.health_check_interval
    on_startup = ImportSafeWorkerSettings.on_startup
    on_shutdown = ImportSafeWorkerSettings.on_shutdown
    on_job_start: ClassVar[Callable[[dict], Awaitable[None]]] = (
        ImportSafeWorkerSettings.on_job_start
    )
    on_job_end: ClassVar[Callable[[dict], Awaitable[None]]] = ImportSafeWorkerSettings.on_job_end
    redis_settings = REDIS_SETTINGS
