import asyncio
import logging
from typing import Protocol
from uuid import UUID

from arq.connections import ArqRedis, RedisSettings, create_pool

from app.core.config import Settings

logger = logging.getLogger(__name__)
PAYOUT_EVENT_JOB_NAME = "process_payout_provider_event"
ENQUEUE_TIMEOUT_SECONDS = 1.0
_enqueuers: dict[str, "RedisPayoutEventEnqueuer"] = {}


class PayoutEventEnqueuer(Protocol):
    async def enqueue_payout_event(self, event_id: UUID) -> None: ...


class UnconfiguredPayoutEventEnqueuer:
    async def enqueue_payout_event(self, event_id: UUID) -> None:
        logger.warning(
            "event=payout_event_enqueue_deferred event_id=%s error_class=RedisUrlNotConfigured",
            event_id,
        )


class RedisPayoutEventEnqueuer:
    def __init__(self, redis_url: str) -> None:
        self.redis_url = redis_url
        self._pool: ArqRedis | None = None

    async def _get_pool(self) -> ArqRedis:
        if self._pool is None:
            settings = RedisSettings.from_dsn(self.redis_url)
            settings.conn_timeout = 1
            settings.conn_retries = 1
            self._pool = await create_pool(settings)
        return self._pool

    async def _enqueue(self, event_id: UUID) -> None:
        pool = await self._get_pool()
        await pool.enqueue_job(
            PAYOUT_EVENT_JOB_NAME,
            str(event_id),
            _job_id=f"payout-provider-event:{event_id}",
        )

    async def enqueue_payout_event(self, event_id: UUID) -> None:
        try:
            await asyncio.wait_for(self._enqueue(event_id), timeout=ENQUEUE_TIMEOUT_SECONDS)
        except Exception as exc:
            logger.warning(
                "event=payout_event_enqueue_deferred event_id=%s error_class=%s",
                event_id,
                type(exc).__name__,
            )


def build_payout_event_enqueuer(settings: Settings) -> PayoutEventEnqueuer:
    if not settings.redis_url:
        return UnconfiguredPayoutEventEnqueuer()
    existing = _enqueuers.get(settings.redis_url)
    if existing is not None:
        return existing
    enqueuer = RedisPayoutEventEnqueuer(settings.redis_url)
    _enqueuers[settings.redis_url] = enqueuer
    return enqueuer
