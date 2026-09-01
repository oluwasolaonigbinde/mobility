from datetime import UTC, datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.adapters.messaging import EmailAdapter, build_email_adapter
from app.core.config import Settings, get_settings
from app.models.notification import (
    Notification,
    NotificationChannel,
    NotificationStatus,
)
from app.services.email_delivery import process_email_notification


async def sweep_email_notifications(
    ctx: dict[str, Any], *, now: datetime | None = None
) -> dict[str, int]:
    settings: Settings = ctx.get("settings") or get_settings()
    sessionmaker: async_sessionmaker[AsyncSession] = ctx["sessionmaker"]
    email_adapter: EmailAdapter = ctx.get("email_adapter") or build_email_adapter(settings)
    current = now or datetime.now(UTC)
    async with sessionmaker() as session:
        ids = list(
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
    counts: dict[str, int] = {}
    for notification_id in ids:
        result = await process_email_notification(
            sessionmaker,
            notification_id=notification_id,
            settings=settings,
            email_adapter=email_adapter,
            now=current,
        )
        counts[result] = counts.get(result, 0) + 1
    return counts
