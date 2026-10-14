"""Sentry Cron instrumentation at the scheduler boundary, never around providers."""

import logging
from functools import wraps
from typing import Any

from arq.cron import cron
from sentry_sdk.crons import capture_checkin

logger = logging.getLogger(__name__)


def _checkin(**values: Any) -> str | None:
    try:
        return capture_checkin(**values)
    except Exception:
        # Telemetry must never turn successful money work into a retry.
        logger.warning("event=cron_checkin_unavailable")
        return None


def _field(value: Any) -> str:
    if value is None:
        return "*"
    return ",".join(str(item) for item in sorted(value)) if isinstance(value, set) else str(value)


def monitored_cron(coroutine: Any, **options: Any) -> Any:
    slug = "cardvert-" + coroutine.__name__.replace("_", "-")
    schedule = " ".join(
        _field(options.get(key)) for key in ("minute", "hour", "day", "month", "weekday")
    )

    @wraps(coroutine)
    async def monitored(ctx: dict[str, Any]) -> Any:
        check_in_id = _checkin(
            monitor_slug=slug,
            status="in_progress",
            monitor_config={
                "schedule": {"type": "crontab", "value": schedule},
                "timezone": "UTC",
                "checkin_margin": 5,
                "max_runtime": 60,
            },
        )
        try:
            result = await coroutine(ctx)
        except BaseException:
            _checkin(monitor_slug=slug, check_in_id=check_in_id, status="error")
            raise
        _checkin(monitor_slug=slug, check_in_id=check_in_id, status="ok")
        return result

    return cron(monitored, **options)
