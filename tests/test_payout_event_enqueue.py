"""Payout provider event enqueue behavior without a live Redis service."""

import asyncio
from types import SimpleNamespace
from uuid import uuid4

from app.core import payout_event_enqueue


class FakePool:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    async def enqueue_job(self, name: str, event_id: str, *, _job_id: str) -> None:
        self.calls.append((name, event_id, _job_id))


def test_unconfigured_payout_event_enqueue_is_deferred(monkeypatch) -> None:
    warnings = []
    monkeypatch.setattr(
        payout_event_enqueue.logger,
        "warning",
        lambda message, *args: warnings.append((message, args)),
    )
    event_id = uuid4()
    enqueuer = payout_event_enqueue.build_payout_event_enqueuer(SimpleNamespace(redis_url=""))

    asyncio.run(enqueuer.enqueue_payout_event(event_id))

    assert isinstance(enqueuer, payout_event_enqueue.UnconfiguredPayoutEventEnqueuer)
    assert warnings == [
        (
            "event=payout_event_enqueue_deferred event_id=%s error_class=RedisUrlNotConfigured",
            (event_id,),
        )
    ]


def test_redis_payout_event_enqueue_reuses_pool_and_uses_stable_event_job_id(
    monkeypatch,
) -> None:
    pool = FakePool()
    pools_created = 0

    async def create_pool(_settings):
        nonlocal pools_created
        pools_created += 1
        return pool

    monkeypatch.setattr(payout_event_enqueue, "create_pool", create_pool)
    event_id = uuid4()
    enqueuer = payout_event_enqueue.RedisPayoutEventEnqueuer("redis://localhost:6379/0")

    asyncio.run(enqueuer.enqueue_payout_event(event_id))
    asyncio.run(enqueuer.enqueue_payout_event(event_id))

    assert pools_created == 1
    assert pool.calls == [
        (
            payout_event_enqueue.PAYOUT_EVENT_JOB_NAME,
            str(event_id),
            f"payout-provider-event:{event_id}",
        ),
        (
            payout_event_enqueue.PAYOUT_EVENT_JOB_NAME,
            str(event_id),
            f"payout-provider-event:{event_id}",
        ),
    ]


def test_redis_payout_event_enqueue_logs_and_defers_connection_failure(monkeypatch) -> None:
    async def fail(_event_id):
        raise TimeoutError("synthetic Redis timeout")

    warnings = []
    monkeypatch.setattr(
        payout_event_enqueue.logger,
        "warning",
        lambda message, *args: warnings.append((message, args)),
    )
    event_id = uuid4()
    enqueuer = payout_event_enqueue.RedisPayoutEventEnqueuer("redis://localhost:6379/0")
    monkeypatch.setattr(enqueuer, "_enqueue", fail)

    asyncio.run(enqueuer.enqueue_payout_event(event_id))

    assert warnings == [
        (
            "event=payout_event_enqueue_deferred event_id=%s error_class=%s",
            (event_id, "TimeoutError"),
        )
    ]


def test_configured_payout_event_enqueuer_is_cached_by_redis_url() -> None:
    payout_event_enqueue._enqueuers.clear()
    first = payout_event_enqueue.build_payout_event_enqueuer(
        SimpleNamespace(redis_url="redis://cache-one:6379/0")
    )
    second = payout_event_enqueue.build_payout_event_enqueuer(
        SimpleNamespace(redis_url="redis://cache-one:6379/0")
    )
    other = payout_event_enqueue.build_payout_event_enqueuer(
        SimpleNamespace(redis_url="redis://cache-two:6379/0")
    )

    assert first is second
    assert first is not other
