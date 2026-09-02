from app.jobs.worker import WorkerSettings as ImportSafeWorkerSettings
from app.jobs.worker import build_redis_settings

REDIS_SETTINGS = build_redis_settings()


class WorkerSettings:
    """Production CLI boundary; configuration fails before arq opens a Redis pool."""

    functions = ImportSafeWorkerSettings.functions
    cron_jobs = ImportSafeWorkerSettings.cron_jobs
    keep_result = ImportSafeWorkerSettings.keep_result
    health_check_interval = ImportSafeWorkerSettings.health_check_interval
    on_startup = ImportSafeWorkerSettings.on_startup
    on_shutdown = ImportSafeWorkerSettings.on_shutdown
    redis_settings = REDIS_SETTINGS
