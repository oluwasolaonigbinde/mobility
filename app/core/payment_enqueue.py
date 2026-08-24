import asyncio
import logging
from typing import Protocol
from uuid import UUID

from arq.connections import ArqRedis, RedisSettings, create_pool

from app.core.config import Settings

logger = logging.getLogger(__name__)
PAYMENT_PROCESSING_JOB_NAME = "process_payment_gateway_event"
ENQUEUE_TIMEOUT_SECONDS = 1.0
_enqueuers: dict[str, "RedisPaymentEventEnqueuer"] = {}


class PaymentEventEnqueuer(Protocol):
    async def enqueue_payment_event(self, event_id: UUID) -> None: ...


class UnconfiguredPaymentEventEnqueuer:
    async def enqueue_payment_event(self, event_id: UUID) -> None:
        logger.warning(
            "event=payment_enqueue_deferred event_id=%s error_class=RedisUrlNotConfigured",
            event_id,
        )


class RedisPaymentEventEnqueuer:
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
            PAYMENT_PROCESSING_JOB_NAME,
            str(event_id),
            _job_id=f"payment-event:{event_id}",
        )

    async def enqueue_payment_event(self, event_id: UUID) -> None:
        try:
            await asyncio.wait_for(self._enqueue(event_id), timeout=ENQUEUE_TIMEOUT_SECONDS)
        except Exception as exc:
            # The committed event remains the recovery truth; duplicate delivery
            # or a recovery sweep may safely enqueue it again.
            logger.warning(
                "event=payment_enqueue_deferred event_id=%s error_class=%s",
                event_id,
                type(exc).__name__,
            )


def build_payment_event_enqueuer(settings: Settings) -> PaymentEventEnqueuer:
    if not settings.redis_url:
        return UnconfiguredPaymentEventEnqueuer()
    existing = _enqueuers.get(settings.redis_url)
    if existing is not None:
        return existing
    enqueuer = RedisPaymentEventEnqueuer(settings.redis_url)
    _enqueuers[settings.redis_url] = enqueuer
    return enqueuer
