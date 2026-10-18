"""Disposable arq hints for durable file/email work; PostgreSQL sweeps recover loss."""

import asyncio
import logging
from typing import Literal
from uuid import UUID

from arq.connections import ArqRedis, RedisSettings, create_pool
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings

JobKind = Literal["scan_file", "deliver_email"]
logger = logging.getLogger(__name__)
_pools: dict[str, ArqRedis] = {}
ENQUEUE_TIMEOUT_SECONDS = 1.0


def pending_job(session: AsyncSession, kind: JobKind, identity: UUID) -> None:
    session.info.setdefault("outbox_jobs", set()).add((kind, identity))


async def enqueue_outbox_jobs(settings: Settings, jobs: set[tuple[JobKind, UUID]]) -> None:
    if not jobs or not settings.redis_url:
        return

    async def enqueue() -> None:
        assert settings.redis_url is not None
        pool = _pools.get(settings.redis_url)
        if pool is None:
            config = RedisSettings.from_dsn(settings.redis_url)
            config.conn_timeout = 1
            config.conn_retries = 1
            pool = await create_pool(config)
            _pools[settings.redis_url] = pool
        for kind, identity in sorted(jobs):
            await pool.enqueue_job(kind, str(identity), _job_id=f"{kind}:{identity}")

    try:
        await asyncio.wait_for(enqueue(), timeout=ENQUEUE_TIMEOUT_SECONDS)
    except Exception as exc:
        # No tokens, addresses, filenames or provider exception text in logs.
        logger.warning("event=outbox_enqueue_failed error_class=%s", type(exc).__name__)
