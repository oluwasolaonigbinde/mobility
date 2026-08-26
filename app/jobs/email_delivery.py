from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote
from uuid import UUID, uuid4

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.adapters.messaging import EmailAdapter, EmailMessage, EmailSendError, build_email_adapter
from app.core.config import Settings, get_settings
from app.models.contact import PasswordResetToken
from app.models.notification import Notification, NotificationChannel, NotificationStatus
from app.models.organization import (
    AdvertiserOrganization,
    AdvertiserOrganizationNotificationPreference,
    MembershipStatus,
    OrganizationMembership,
    OrganizationStatus,
)
from app.models.user import User, UserRole, UserStatus
from app.services.email_templates import render_email_template


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


async def _preference_allows_delivery(
    session: AsyncSession, notice: Notification
) -> tuple[bool, str | None]:
    if notice.type_key == "password_reset_requested":
        user = await session.get(User, notice.recipient_user_id)
        if (
            user is None
            or user.role not in {UserRole.ADMIN.value, UserRole.ADVERTISER.value}
            or user.status not in {UserStatus.ACTIVE.value, UserStatus.INVITED.value}
        ):
            return False, "email_recipient_inactive"
        return True, user.email
    try:
        organization_id = UUID(str(notice.payload["advertiser_organization_id"]))
    except (KeyError, TypeError, ValueError):
        return False, "email_organization_context_missing"
    row = (
        await session.execute(
            select(User, AdvertiserOrganizationNotificationPreference.transactional_email_enabled)
            .join(
                OrganizationMembership,
                (OrganizationMembership.user_id == User.id)
                & (OrganizationMembership.organization_id == organization_id),
            )
            .join(
                AdvertiserOrganization,
                AdvertiserOrganization.id == OrganizationMembership.organization_id,
            )
            .outerjoin(
                AdvertiserOrganizationNotificationPreference,
                AdvertiserOrganizationNotificationPreference.advertiser_organization_id
                == organization_id,
            )
            .where(
                User.id == notice.recipient_user_id,
                User.role == UserRole.ADVERTISER.value,
                User.status == UserStatus.ACTIVE.value,
                OrganizationMembership.status == MembershipStatus.ACTIVE.value,
                AdvertiserOrganization.status == OrganizationStatus.ACTIVE.value,
            )
        )
    ).first()
    if row is None:
        return False, "email_recipient_inactive"
    user, enabled = row
    if enabled is False:
        return False, "email_preference_disabled"
    return True, user.email


async def _claim(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    notification_id: UUID,
    settings: Settings,
    now: datetime,
) -> tuple[UUID, Notification, str] | None:
    token = uuid4()
    async with sessionmaker() as session:
        notice = await session.scalar(
            select(Notification).where(Notification.id == notification_id).with_for_update()
        )
        if (
            notice is None
            or notice.channel != NotificationChannel.TRANSACTIONAL_EMAIL.value
            or notice.status != NotificationStatus.PENDING.value
            or (
                notice.next_attempt_at is not None
                and _utc(notice.next_attempt_at) > _utc(now)
            )
            or (
                notice.delivery_claim_expires_at is not None
                and _utc(notice.delivery_claim_expires_at) > _utc(now)
            )
        ):
            return None
        allowed, recipient_or_error = await _preference_allows_delivery(session, notice)
        if not allowed:
            notice.status = NotificationStatus.FAILED.value
            notice.last_error_code = recipient_or_error
            notice.delivery_claim_token = None
            notice.delivery_claim_expires_at = None
            await session.commit()
            return None
        notice.attempt_count += 1
        notice.delivery_claim_token = token
        notice.delivery_claim_expires_at = now + timedelta(
            seconds=settings.email_delivery_claim_seconds
        )
        notice.last_error_code = None
        await session.commit()
        return token, notice, str(recipient_or_error)


async def process_email_notification(
    ctx: dict[str, Any], notification_id: str, *, now: datetime | None = None
) -> str:
    settings: Settings = ctx.get("settings") or get_settings()
    sessionmaker: async_sessionmaker[AsyncSession] = ctx["sessionmaker"]
    current = now or datetime.now(UTC)
    claimed = await _claim(
        sessionmaker,
        notification_id=UUID(notification_id),
        settings=settings,
        now=current,
    )
    if claimed is None:
        return "skipped"
    token, notice, recipient = claimed
    try:
        runtime_payload = dict(notice.payload)
        if notice.type_key == "password_reset_requested":
            try:
                reset_id = UUID(str(notice.payload["password_reset_request_id"]))
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError("password_reset_request_missing") from exc
            async with sessionmaker() as session:
                reset = await session.get(PasswordResetToken, reset_id)
                user = await session.get(User, notice.recipient_user_id)
            if (
                reset is None
                or user is None
                or reset.used_at is not None
                or _utc(reset.expires_at) <= _utc(current)
                or reset.session_version != user.session_version
            ):
                raise ValueError("password_reset_request_inactive")
            from app.services.account_recovery import password_reset_token_for_delivery

            reset_token = password_reset_token_for_delivery(reset, user, settings)
            if settings.password_reset_public_url:
                separator = "&" if "?" in settings.password_reset_public_url else "?"
                runtime_payload["reset_action"] = (
                    f"{settings.password_reset_public_url}{separator}token={quote(reset_token)}"
                )
            elif settings.environment in {"local", "dev", "development", "test", "testing"}:
                runtime_payload["reset_action"] = reset_token
            else:
                raise ValueError("password_reset_public_url_missing")
        rendered = render_email_template(notice.type_key, notice.template_version, runtime_payload)
        adapter: EmailAdapter = ctx.get("email_adapter") or build_email_adapter(settings)
        submission = await adapter.send(
            EmailMessage(
                recipient=recipient,
                subject=rendered.subject,
                text_body=rendered.text_body,
                html_body=rendered.html_body,
                idempotency_key=str(notice.id),
            )
        )
    except ValueError as exc:
        failure = EmailSendError(str(exc), retryable=False)
    except EmailSendError as exc:
        failure = exc
    else:
        failure = None

    async with sessionmaker() as session:
        locked = await session.scalar(
            select(Notification).where(Notification.id == notice.id).with_for_update()
        )
        if locked is None or locked.delivery_claim_token != token:
            return "stale_claim"
        locked.delivery_claim_token = None
        locked.delivery_claim_expires_at = None
        if failure is None:
            locked.status = NotificationStatus.SENT.value
            locked.provider_message_id = submission.provider_message_id
            locked.sent_at = current
            locked.next_attempt_at = None
            locked.last_error_code = None
            result = "sent"
        else:
            locked.last_error_code = failure.code
            if failure.retryable and locked.attempt_count < settings.email_delivery_max_attempts:
                locked.next_attempt_at = current + timedelta(
                    seconds=settings.email_delivery_retry_base_seconds
                    * (2 ** (locked.attempt_count - 1))
                )
                result = "retry_scheduled"
            else:
                locked.status = NotificationStatus.FAILED.value
                locked.next_attempt_at = None
                result = "failed"
        await session.commit()
        return result


async def sweep_email_notifications(
    ctx: dict[str, Any], *, now: datetime | None = None
) -> dict[str, int]:
    settings: Settings = ctx.get("settings") or get_settings()
    sessionmaker: async_sessionmaker[AsyncSession] = ctx["sessionmaker"]
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
        result = await process_email_notification(ctx, str(notification_id), now=current)
        counts[result] = counts.get(result, 0) + 1
    return counts
