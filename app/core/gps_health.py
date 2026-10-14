"""Aggregate GPS attempt telemetry. Never accepts identifiers or payloads."""

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from redis.asyncio import Redis

from app.core.config import Settings

logger = logging.getLogger(__name__)
PREFIX = "cardvert:health:gps:"
GPS_REJECTIONS = frozenset({"INVALID_RECORDED_AT", "INVALID_ACCURACY", "INVALID_SPEED"})


@dataclass
class GPSAttempt:
    rejected: bool = False


def minute_key(now: datetime) -> str:
    return PREFIX + now.astimezone(UTC).strftime("%Y%m%d%H%M")


async def record_attempt(redis: Any, *, rejected: bool, now: datetime) -> None:
    key = minute_key(now)
    async with redis.pipeline(transaction=True) as pipe:
        pipe.hincrby(key, "attempts", 1)
        pipe.hincrby(key, "rejected", int(rejected))
        pipe.expire(key, 3600)
        await pipe.execute()


async def record_gps_attempt(settings: Settings, attempt: GPSAttempt) -> None:
    # Independent of the evidence transaction, including wholly rejected batches.
    # No error text, identifiers, request payload, URL or coordinates in logs.
    if not settings.redis_url:
        logger.warning("event=gps_health_telemetry_unavailable")
        return
    try:
        async with asyncio.timeout(1):
            async with Redis.from_url(settings.redis_url) as redis:
                await record_attempt(redis, rejected=attempt.rejected, now=datetime.now(UTC))
    except Exception:
        logger.warning("event=gps_health_telemetry_unavailable")


async def gps_window(redis: Any, *, now: datetime) -> tuple[int, int] | None:
    if redis is None:
        return None
    end = now.astimezone(UTC).replace(second=0, microsecond=0)
    try:
        async with asyncio.timeout(1):
            async with redis.pipeline(transaction=False) as pipe:
                for minute in range(1, 16):
                    pipe.hmget(minute_key(end - timedelta(minutes=minute)), "attempts", "rejected")
                values = await pipe.execute()
        if not any(attempts is not None for attempts, _ in values):
            return None
        attempts = sum(int(a or 0) for a, _ in values)
        rejected = sum(int(r or 0) for _, r in values)
        if rejected > attempts or rejected < 0 or attempts < 0:
            return None
        return attempts, rejected
    except Exception:
        logger.warning("event=gps_health_telemetry_unavailable")
        return None
