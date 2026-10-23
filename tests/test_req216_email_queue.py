"""Queued dispatch, durable Redis recovery and crash/attempt bounds (D117)."""

import asyncio
import os
from datetime import UTC, datetime, timedelta

import pytest
from arq import Retry
from arq.connections import RedisSettings, create_pool
from arq.worker import Worker, func
from test_email_delivery import RecordingEmailAdapter, _seed_advertiser

from app.adapters.messaging import EmailSendError
from app.adapters.messaging.email import SmtpEmailAdapter
from app.core import outbox_enqueue
from app.jobs import email_delivery as job
from app.models.audit import AuditEvent
from app.models.notification import Notification, NotificationType
from app.services.notifications import create_advertiser_email_notification


async def create_notice(sessionmaker, key):
    user_id, organization_id = await _seed_advertiser(sessionmaker)
    async with sessionmaker() as session:
        notice = await create_advertiser_email_notification(
            session,
            advertiser_organization_id=organization_id,
            recipient_user_id=user_id,
            type_key=NotificationType.FRAUD_HOLD_RAISED,
            payload={},
            dedupe_key=key,
        )
        await session.commit()
        return notice.id


@pytest.mark.parametrize("unexpected", [False, True])
def test_queue_retries_after_failure_without_racing_claims(
    db_sessionmaker, settings, monkeypatch, unexpected
):
    class Clock(datetime):
        current = datetime.now(UTC)

        @classmethod
        def now(cls, tz=None):
            return cls.current

    monkeypatch.setattr(job, "datetime", Clock)

    async def run():
        identity = await create_notice(db_sessionmaker, f"queue-retry:{unexpected}")

        class Adapter(RecordingEmailAdapter):
            async def send(self, message):
                if unexpected and not self.messages:
                    self.messages.append(message)
                    raise RuntimeError("private provider exception text")
                return await super().send(message)

        adapter = Adapter(
            [] if unexpected else [EmailSendError("synthetic_outage", retryable=True)]
        )
        ctx = {"sessionmaker": db_sessionmaker, "settings": settings, "email_adapter": adapter}
        with pytest.raises(Retry) as retry:
            await job.deliver_email(ctx, str(identity))
        expected_delay = 120 if unexpected else 60
        assert (expected_delay - 1) * 1000 <= retry.value.defer_score <= expected_delay * 1000
        assert await job.deliver_email(ctx, str(identity)) == "skipped"
        assert len(adapter.messages) == 1
        Clock.current += timedelta(seconds=expected_delay + 1)
        assert await job.deliver_email(ctx, str(identity)) == "sent"
        assert [message.idempotency_key for message in adapter.messages] == [str(identity)] * 2
        async with db_sessionmaker() as session:
            stored = await session.get(Notification, identity)
            assert stored.status == "sent"
            assert stored.attempt_count == 2
            assert stored.delivery_claim_token is None
            assert stored.delivery_claim_expires_at is None
            if unexpected:
                from sqlalchemy import select

                audit = await session.scalar(
                    select(AuditEvent).where(
                        AuditEvent.action == "worker.email_delivery.failed",
                        AuditEvent.entity_id == str(identity),
                    )
                )
                assert audit.event_metadata == {"error_code": "RuntimeError"}

    asyncio.run(run())


def test_queue_delivery_submits_real_local_smtp_and_records_sent(db_sessionmaker, settings):
    async def run():
        received = []

        async def smtp(reader, writer):
            writer.write(b"220 local test SMTP\r\n")
            await writer.drain()
            try:
                while line := await reader.readline():
                    command = line.split(b" ", 1)[0].strip().upper()
                    if command == b"DATA":
                        writer.write(b"354 End with a dot\r\n")
                        await writer.drain()
                        data = bytearray()
                        while (line := await reader.readline()) not in (b".\r\n", b""):
                            data.extend(line)
                        received.append(bytes(data))
                        writer.write(b"250 accepted\r\n")
                    elif command == b"QUIT":
                        writer.write(b"221 bye\r\n")
                        await writer.drain()
                        break
                    else:
                        writer.write(b"250 OK\r\n")
                    await writer.drain()
            finally:
                writer.close()
                await writer.wait_closed()

        server = await asyncio.start_server(smtp, "127.0.0.1", 0)
        async with server:
            identity = await create_notice(db_sessionmaker, "local-smtp")
            configured = settings.model_copy(
                update={
                    "email_smtp_host": "127.0.0.1",
                    "email_smtp_port": server.sockets[0].getsockname()[1],
                    "email_sender_address": "notices@cardvert.test",
                    "email_smtp_starttls": False,
                }
            )
            assert (
                await job.deliver_email(
                    {
                        "sessionmaker": db_sessionmaker,
                        "settings": configured,
                        "email_adapter": SmtpEmailAdapter(configured),
                    },
                    str(identity),
                )
                == "sent"
            )
            assert len(received) == 1
            assert f"X-Cardvert-Idempotency-Key: {identity}".encode() in received[0]
            async with db_sessionmaker() as session:
                stored = await session.get(Notification, identity)
                assert stored.status == "sent"
                assert stored.provider_message_id == f"<{identity}@cardvert.test>"
                assert stored.attempt_count == 1

    asyncio.run(run())


def test_real_redis_recovers_lost_hint_and_burst_worker_sends_once(
    postgis_db_sessionmaker, settings, monkeypatch
):
    redis_url = os.environ.get("ARQ_TEST_REDIS_URL")
    if not redis_url:
        pytest.fail("This queue integration test requires ARQ_TEST_REDIS_URL")

    async def run():
        identity = await create_notice(postgis_db_sessionmaker, "lost-queue-hint")
        pool = await create_pool(RedisSettings.from_dsn(redis_url))
        await pool.flushdb()
        pools = {}
        monkeypatch.setattr(outbox_enqueue, "_pools", pools)
        adapter = RecordingEmailAdapter()
        configured = settings.model_copy(update={"redis_url": redis_url})
        ctx = {"sessionmaker": postgis_db_sessionmaker, "settings": configured}
        unavailable = settings.model_copy(update={"redis_url": "redis://127.0.0.1:6399/0"})
        try:
            assert await job.enqueue_pending_email({**ctx, "settings": unavailable}) == {
                "selected": 1
            }
            assert adapter.messages == []
            assert await job.enqueue_pending_email(ctx) == {"selected": 1}
            assert await job.enqueue_pending_email(ctx) == {"selected": 1}
            assert await pool.zcard("arq:queue") == 1
            assert await pool.zscore("arq:queue", f"deliver_email:{identity}") is not None

            async def startup(worker_ctx):
                worker_ctx.update(ctx)
                worker_ctx["email_adapter"] = adapter

            worker = Worker(
                functions=[func(job.deliver_email, name="deliver_email", keep_result=0)],
                redis_settings=RedisSettings.from_dsn(redis_url),
                burst=True,
                poll_delay=0,
                on_startup=startup,
            )
            try:
                assert await worker.run_check() == 1
            finally:
                await worker.close()
            assert len(adapter.messages) == 1
            assert await job.enqueue_pending_email(ctx) == {"selected": 0}
            async with postgis_db_sessionmaker() as session:
                stored = await session.get(Notification, identity)
                assert stored.status == "sent"
                assert stored.attempt_count == 1
        finally:
            await pool.flushdb()
            await pool.aclose()
            for cached in pools.values():
                await cached.aclose()

    asyncio.run(run())
