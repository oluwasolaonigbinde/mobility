import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from test_email_delivery import RecordingEmailAdapter, _seed_advertiser, _settings

from app.jobs import email_delivery as job
from app.models.audit import AuditEvent, AuditEventSubjectResolution
from app.models.notification import Notification, NotificationChannel, NotificationType
from app.services import email_delivery as delivery_service
from app.services.notifications import notification_dedupe_fingerprint


async def notices(maker, count):
    user_id, organization_id = await _seed_advertiser(maker)
    async with maker() as session:
        rows = []
        for index in range(count):
            payload = {
                "fraud_flag_id": f"flag-{index}",
                "advertiser_organization_id": str(organization_id),
            }
            notice = Notification(
                recipient_user_id=user_id,
                type_key=NotificationType.FRAUD_HOLD_RAISED.value,
                template_version="v1",
                channel=NotificationChannel.TRANSACTIONAL_EMAIL.value,
                status="pending",
                payload=payload,
                dedupe_key=f"fairness-{index}",
                dedupe_fingerprint=notification_dedupe_fingerprint(
                    recipient_user_id=user_id,
                    type_key=NotificationType.FRAUD_HOLD_RAISED,
                    template_version="v1",
                    channel=NotificationChannel.TRANSACTIONAL_EMAIL,
                    payload=payload,
                ),
                created_at=datetime.now(UTC) - timedelta(days=count - index),
            )
            session.add(notice)
            rows.append(notice)
        await session.commit()
        return rows


@pytest.mark.parametrize("database", ["db_sessionmaker", "postgis_db_sessionmaker"])
def test_full_failing_email_prefix_rotates_to_later_notices(request, database, monkeypatch, caplog):
    # In-process migration fileConfig disables previously imported worker loggers.
    monkeypatch.setattr(delivery_service.logger, "disabled", False)
    maker = request.getfixturevalue(database)

    async def run():
        rows = await notices(maker, 3)
        adapter = RecordingEmailAdapter()
        process = job.process_email_notification

        async def failing(*args, notification_id, **kwargs):
            if notification_id in {rows[0].id, rows[1].id}:
                raise RuntimeError("private-provider-detail-must-not-be-logged")
            return await process(*args, notification_id=notification_id, **kwargs)

        monkeypatch.setattr(job, "process_email_notification", failing)
        ctx = {
            "sessionmaker": maker,
            "settings": _settings(worker_sweep_batch_size=2),
            "email_adapter": adapter,
        }
        first = await job.sweep_email_notifications(ctx)
        assert first == {"unexpected_failure": 2}
        second = await job.sweep_email_notifications(ctx)
        assert second == {"sent": 1, "unexpected_failure": 1}
        assert len(adapter.messages) == 1
        async with maker() as session:
            journal = list(
                await session.scalars(
                    select(AuditEvent).where(AuditEvent.action == "worker.email_delivery.failed")
                )
            )
            assert len(journal) == 3
            subjects = set(
                await session.scalars(
                    select(AuditEventSubjectResolution.subject_user_id).where(
                        AuditEventSubjectResolution.audit_event_id.in_([row.id for row in journal]),
                        AuditEventSubjectResolution.role == "target",
                        AuditEventSubjectResolution.outcome == "resolved",
                    )
                )
            )
            assert subjects == {rows[0].recipient_user_id}
            assert all(row.event_metadata == {"error_code": "RuntimeError"} for row in journal)
            pending = await session.get(Notification, rows[0].id)
            assert pending.status == "pending" and pending.attempt_count == 0
        assert "Email delivery item failed" in caplog.text
        assert "private-provider-detail" not in caplog.text

    asyncio.run(run())


def test_unexpected_provider_failure_keeps_uncertain_claim_recoverable_above_cap(
    postgis_db_sessionmaker, caplog
):
    maker = postgis_db_sessionmaker

    async def run():
        rows = await notices(maker, 2)
        settings = _settings(email_delivery_max_attempts=1)
        now = datetime.now(UTC)

        class CrashOnce(RecordingEmailAdapter):
            async def send(self, message):
                if message.idempotency_key == str(rows[0].id) and not self.messages:
                    self.messages.append(message)
                    raise RuntimeError("uncertain send")
                return await super().send(message)

        adapter = CrashOnce()
        ctx = {"sessionmaker": maker, "settings": settings, "email_adapter": adapter}
        assert await job.sweep_email_notifications(ctx, now=now) == {
            "unexpected_failure": 1,
            "sent": 1,
        }
        async with maker() as session:
            pending = await session.get(Notification, rows[0].id)
            claim = pending.delivery_claim_token
            assert pending.status == "pending" and pending.attempt_count == 1
            assert claim is not None and pending.delivery_claim_expires_at > now
        assert await job.sweep_email_notifications(ctx, now=now + timedelta(seconds=1)) == {}
        assert await job.sweep_email_notifications(ctx, now=now + timedelta(seconds=31)) == {
            "sent": 1
        }
        assert adapter.messages[0].idempotency_key == adapter.messages[-1].idempotency_key
        async with maker() as session:
            settled = await session.get(Notification, rows[0].id)
            assert settled.status == "sent" and settled.attempt_count == 2
            assert settled.delivery_claim_token is None

    asyncio.run(run())


def test_failed_email_failure_journal_is_not_swallowed(db_sessionmaker, monkeypatch):
    async def run():
        await notices(db_sessionmaker, 1)

        async def fail(*args, **kwargs):
            raise RuntimeError("unexpected item failure")

        async def journal_fail(*args, **kwargs):
            raise OSError("journal unavailable")

        monkeypatch.setattr(job, "process_email_notification", fail)
        monkeypatch.setattr(delivery_service, "create_audit_event", journal_fail)
        with pytest.raises(OSError, match="journal unavailable"):
            await job.sweep_email_notifications(
                {
                    "sessionmaker": db_sessionmaker,
                    "settings": _settings(),
                    "email_adapter": RecordingEmailAdapter(),
                }
            )

    asyncio.run(run())
