from datetime import UTC, datetime, timedelta
from urllib.parse import quote
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.adapters.messaging import EmailAdapter, EmailMessage, EmailSendError
from app.core.config import Settings
from app.models.contact import PasswordResetToken
from app.models.driver_application import (
    DriverApplication,
    DriverApplicationAccessToken,
    DriverApplicationStatus,
)
from app.models.notification import (
    Notification,
    NotificationChannel,
    NotificationStatus,
    NotificationType,
)
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
    if notice.type_key in {
        NotificationType.PASSWORD_RESET_REQUESTED.value,
        NotificationType.DRIVER_ONBOARDING_ACCESS_REQUESTED.value,
    }:
        user = await session.get(User, notice.recipient_user_id)
        password_reset_recipient = (
            notice.type_key == NotificationType.PASSWORD_RESET_REQUESTED.value
            and user is not None
            and user.role in {UserRole.ADMIN.value, UserRole.ADVERTISER.value}
            and user.status in {UserStatus.ACTIVE.value, UserStatus.INVITED.value}
        )
        onboarding_recipient = (
            notice.type_key == NotificationType.DRIVER_ONBOARDING_ACCESS_REQUESTED.value
            and user is not None
            and user.role == UserRole.DRIVER.value
            and user.status == UserStatus.INVITED.value
        )
        if not (password_reset_recipient or onboarding_recipient):
            return False, "email_recipient_inactive"
        assert user is not None
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
            or (notice.next_attempt_at is not None and _utc(notice.next_attempt_at) > _utc(now))
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
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    notification_id: UUID,
    settings: Settings,
    email_adapter: EmailAdapter,
    now: datetime,
) -> str:
    claimed = await _claim(
        sessionmaker,
        notification_id=notification_id,
        settings=settings,
        now=now,
    )
    if claimed is None:
        return "skipped"
    token, notice, recipient = claimed
    try:
        runtime_payload = dict(notice.payload)
        if notice.type_key == NotificationType.PASSWORD_RESET_REQUESTED.value:
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
                or _utc(reset.expires_at) <= _utc(now)
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
        elif notice.type_key == NotificationType.DRIVER_ONBOARDING_ACCESS_REQUESTED.value:
            try:
                access_id = UUID(str(notice.payload["driver_application_access_id"]))
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError("driver_onboarding_access_request_missing") from exc
            async with sessionmaker() as session:
                access = await session.get(DriverApplicationAccessToken, access_id)
                application = (
                    await session.get(DriverApplication, access.application_id)
                    if access is not None
                    else None
                )
                user = await session.get(User, notice.recipient_user_id)
            if (
                access is None
                or application is None
                or user is None
                or application.user_id != user.id
                or application.status != DriverApplicationStatus.PENDING.value
                or _utc(access.expires_at) <= _utc(now)
            ):
                raise ValueError("driver_onboarding_access_request_inactive")
            from app.services.driver_applications import (
                driver_application_access_token_for_delivery,
            )

            try:
                runtime_payload["access_code"] = driver_application_access_token_for_delivery(
                    access, settings
                )
            except RuntimeError:
                raise ValueError("driver_onboarding_access_evidence_mismatch") from None
        rendered = render_email_template(notice.type_key, notice.template_version, runtime_payload)
        submission = await email_adapter.send(
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
            locked.sent_at = now
            locked.next_attempt_at = None
            locked.last_error_code = None
            result = "sent"
        else:
            locked.last_error_code = failure.code
            if failure.retryable and locked.attempt_count < settings.email_delivery_max_attempts:
                locked.next_attempt_at = now + timedelta(
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
