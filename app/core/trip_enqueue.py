import asyncio
import logging
from typing import Protocol
from uuid import UUID

from arq.connections import ArqRedis, RedisSettings, create_pool

from app.core.config import Settings

logger = logging.getLogger(__name__)
_enqueuers: dict[str, "RedisTripProcessingEnqueuer"] = {}

# The job name is the only coupling to app/jobs — never import from there (§29.2).
TRIP_PROCESSING_JOB_NAME = "process_trip"
ENQUEUE_TIMEOUT_SECONDS = 1.0


class TripProcessingEnqueuer(Protocol):
    async def enqueue_trip_processing(self, trip_id: UUID) -> None: ...


class UnconfiguredTripProcessingEnqueuer:
    async def enqueue_trip_processing(self, trip_id: UUID) -> None:
        logger.warning(
            "event=trip_enqueue_failed trip_id=%s error_class=RedisUrlNotConfigured",
            trip_id,
        )


class RedisTripProcessingEnqueuer:
    def __init__(self, redis_url: str) -> None:
        self.redis_url = redis_url
        self._pool: ArqRedis | None = None

    async def _get_pool(self) -> ArqRedis:
        # Only a successfully created pool is cached; a failed attempt leaves
        # _pool unset so the next request retries within the same time budget.
        if self._pool is None:
            redis_settings = RedisSettings.from_dsn(self.redis_url)
            redis_settings.conn_timeout = 1
            redis_settings.conn_retries = 1
            self._pool = await create_pool(redis_settings)
        return self._pool

    async def _enqueue(self, trip_id: UUID) -> None:
        pool = await self._get_pool()
        await pool.enqueue_job(
            TRIP_PROCESSING_JOB_NAME,
            str(trip_id),
            _job_id=f"trip-process:{trip_id}",
        )

    async def enqueue_trip_processing(self, trip_id: UUID) -> None:
        try:
            await asyncio.wait_for(self._enqueue(trip_id), timeout=ENQUEUE_TIMEOUT_SECONDS)
        except Exception as exc:  # fail-open: never break the trip-end request
            logger.warning(
                "event=trip_enqueue_failed trip_id=%s error_class=%s",
                trip_id,
                type(exc).__name__,
            )


def build_trip_enqueuer(settings: Settings) -> TripProcessingEnqueuer:
    if not settings.redis_url:
        return UnconfiguredTripProcessingEnqueuer()
    existing = _enqueuers.get(settings.redis_url)
    if existing is not None:
        return existing
    enqueuer = RedisTripProcessingEnqueuer(settings.redis_url)
    _enqueuers[settings.redis_url] = enqueuer
    return enqueuer
