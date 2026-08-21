"""Thin arq wrappers for the data-lifecycle service (§14.3.3).

Logic lives in app/services/data_lifecycle.py; these functions only unpack
worker context, call the service, and log/observe outcomes.
"""

import logging
import time
from typing import Any

from app.core.observability import capture_exception
from app.services.data_lifecycle import (
    check_partition_coverage,
    premake_partitions,
    run_ping_retention,
)

logger = logging.getLogger(__name__)


class PartitionCoverageError(RuntimeError):
    pass


async def premake_ping_partitions(ctx: dict[str, Any]) -> dict[str, Any]:
    started = time.monotonic()
    sessionmaker = ctx["sessionmaker"]
    settings = ctx["settings"]
    async with sessionmaker() as session:
        result = await premake_partitions(session, settings=settings)
    duration_ms = int((time.monotonic() - started) * 1000)
    logger.info(
        "job=premake_ping_partitions created=%s duration_ms=%d",
        result["created"],
        duration_ms,
    )
    # A premake bug must surface immediately, not a month later.
    await check_ping_partition_coverage(ctx)
    return {**result, "duration_ms": duration_ms}


async def check_ping_partition_coverage(ctx: dict[str, Any]) -> dict[str, Any]:
    sessionmaker = ctx["sessionmaker"]
    async with sessionmaker() as session:
        covered, upper = await check_partition_coverage(session)
    if not covered:
        logger.error(
            "job=check_ping_partition_coverage status=uncovered covered_until=%s",
            upper.isoformat() if upper else None,
        )
        exc = PartitionCoverageError(
            "location_pings partition coverage does not reach now() + 1 month"
            f" (covered_until={upper.isoformat() if upper else None})"
        )
        # Capture explicitly, then re-raise so arq also records the failure.
        capture_exception(exc)
        raise exc
    logger.info(
        "job=check_ping_partition_coverage status=ok covered_until=%s",
        upper.isoformat() if upper else None,
    )
    return {"covered_until": upper.isoformat() if upper else None}


async def purge_expired_ping_partitions(ctx: dict[str, Any]) -> dict[str, Any]:
    started = time.monotonic()
    engine = ctx["engine"]
    sessionmaker = ctx["sessionmaker"]
    settings = ctx["settings"]
    result = await run_ping_retention(engine, sessionmaker, settings=settings)
    duration_ms = int((time.monotonic() - started) * 1000)
    logger.info("job=purge_expired_ping_partitions duration_ms=%d", duration_ms)
    return {**result, "duration_ms": duration_ms}
