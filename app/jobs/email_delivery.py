"""Only queued delivery sends mail; recovery re-enqueues durable outbox rows."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from arq import Retry
from sqlalchemy import or_, select

from app.adapters.messaging import build_email_adapter
from app.core.config import Settings, get_settings
from app.core.outbox_enqueue import enqueue_outbox_jobs
from app.models.notification import Notification, NotificationChannel, NotificationStatus
from app.services.email_delivery import process_email_notification, record_unexpected_email_failure


async def deliver_email(ctx: dict[str, Any], notification_id: str) -> str:
    settings = ctx["settings"]
    identity = UUID(notification_id)
    current = datetime.now(UTC)
    try:
        result = await process_email_notification(
            ctx["sessionmaker"],
            notification_id=identity,
            settings=settings,
            email_adapter=ctx.get("email_adapter") or build_email_adapter(settings),
            now=current,
        )
    except Exception as exc:
        await record_unexpected_email_failure(
            ctx["sessionmaker"],
            notification_id=identity,
            error=exc,
        )
        # A crash may leave an uncertain send claimed. Never race its lease.
        raise Retry(defer=settings.email_delivery_claim_seconds) from None
    if result == "retry_scheduled":
        async with ctx["sessionmaker"]() as session:
            retry_at = await session.scalar(
                select(Notification.next_attempt_at).where(Notification.id == identity)
            )
        if retry_at is not None:
            raise Retry(defer=max(0, (retry_at - datetime.now(UTC)).total_seconds()))
    return result


async def enqueue_pending_email(
    ctx: dict[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, int]:
    """Recover lost Redis hints, including a crash after committing the SQL outbox.

    This never calls an email adapter, sends SMTP, or decides retries. A single
    stable queue ID and the delivery claim fence concurrent recovery/dispatch.
    """
    settings: Settings = ctx.get("settings") or get_settings()
    current = now or datetime.now(UTC)
    async with ctx["sessionmaker"]() as session:
        identities = list(
            await session.scalars(
                select(Notification.id)
                .where(
                    Notification.channel == NotificationChannel.TRANSACTIONAL_EMAIL.value,
                    Notification.status == NotificationStatus.PENDING.value,
                    or_(
                        Notification.next_attempt_at.is_(None),
                        Notification.next_attempt_at <= current,
                    ),
                    or_(
                        Notification.delivery_claim_expires_at.is_(None),
                        Notification.delivery_claim_expires_at <= current,
                    ),
                )
                .order_by(Notification.created_at, Notification.id)
                .limit(settings.worker_sweep_batch_size)
            )
        )
    await enqueue_outbox_jobs(settings, {("deliver_email", identity) for identity in identities})
    return {"selected": len(identities)}
