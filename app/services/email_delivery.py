import logging
from datetime import UTC, datetime, timedelta
from urllib.parse import quote, urlsplit
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.adapters.messaging import EmailAdapter, EmailMessage, EmailSendError
from app.core.config import Settings
from app.models.campaign_assignment import CampaignAssignment
from app.models.contact import PasswordResetToken
from app.models.driver_application import (
    DriverAccountSetupToken,
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
from app.services.audit import create_audit_event
from app.services.email_templates import render_email_template


def public_action_url(settings: Settings, path: str) -> str:
    origin = settings.public_origin.strip()
    if not origin and settings.environment in {"local", "dev", "development", "test", "testing"}:
        origin = "http://localhost:3000"
    parsed = urlsplit(origin)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
        or not path.startswith("/")
        or path.startswith("//")
    ):
        raise ValueError("email_public_origin_missing")
    return origin.rstrip("/") + path


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


async def _driver_business_email_allowed(session: AsyncSession, notice: Notification):
    from app.services.driver_review_notifications import REVIEW_TYPES, review_notice_context
    from app.services.notifications import notification_campaign_context

    user = await session.get(User, notice.recipient_user_id)
    if user is None:
        return False, "email_recipient_inactive"
    if notice.type_key == NotificationType.ASSIGNMENT_OFFERED:
        try:
            assignment_id = UUID(str(notice.payload["assignment_id"]))
        except (KeyError, TypeError, ValueError):
            return False, "email_assignment_missing"
        assignment = await session.get(CampaignAssignment, assignment_id)
        if (
            assignment is None
            or assignment.status != "offered"
            or (
                assignment.expires_at is not None
                and _utc(assignment.expires_at) <= datetime.now(UTC)
            )
        ):
            return False, "email_offer_inactive"
    context = (
        await review_notice_context(session, notice, user)
        if notice.type_key in REVIEW_TYPES
        else await notification_campaign_context(session, notice=notice, user=user)
    )
    if context is None or user.role != UserRole.DRIVER:
        return False, "email_recipient_or_review_inactive"
    return True, user.email


async def _preference_allows_delivery(
    session: AsyncSession, notice: Notification
) -> tuple[bool, str | None]:
    from app.services.driver_review_notifications import REVIEW_TYPES

    if notice.type_key in REVIEW_TYPES or notice.type_key == NotificationType.ASSIGNMENT_OFFERED:
        return await _driver_business_email_allowed(session, notice)
    if notice.type_key in {
        NotificationType.PASSWORD_RESET_REQUESTED.value,
        NotificationType.DRIVER_ONBOARDING_ACCESS_REQUESTED.value,
        NotificationType.DRIVER_ACCOUNT_SETUP_REQUESTED.value,
    }:
        user = await session.get(User, notice.recipient_user_id)
        password_reset_recipient = (
            notice.type_key == NotificationType.PASSWORD_RESET_REQUESTED.value
            and user is not None
            and (
                (
                    user.role in {UserRole.ADMIN.value, UserRole.ADVERTISER.value}
                    and user.status in {UserStatus.ACTIVE.value, UserStatus.INVITED.value}
                )
                or (user.role == UserRole.DRIVER.value and user.status == UserStatus.ACTIVE.value)
            )
        )
        onboarding_recipient = (
            notice.type_key == NotificationType.DRIVER_ONBOARDING_ACCESS_REQUESTED.value
            and user is not None
            and user.role == UserRole.DRIVER.value
            and user.status == UserStatus.INVITED.value
        )
        setup_recipient = (
            notice.type_key == NotificationType.DRIVER_ACCOUNT_SETUP_REQUESTED.value
            and user is not None
            and user.role == UserRole.DRIVER.value
            and user.status == UserStatus.INVITED.value
        )
        if not (password_reset_recipient or onboarding_recipient or setup_recipient):
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
        if notice.attempt_count >= settings.email_delivery_max_attempts:
            notice.status = NotificationStatus.FAILED.value
            notice.failed_at = now
            notice.last_error_code = "email_attempts_exhausted"
            notice.next_attempt_at = None
            notice.delivery_claim_token = None
            notice.delivery_claim_expires_at = None
            await session.commit()
            return None
        allowed, recipient_or_error = await _preference_allows_delivery(session, notice)
        if not allowed:
            notice.status = NotificationStatus.FAILED.value
            notice.failed_at = now
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


async def process_email_notification(  # noqa: C901
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
        # Display copy and links never come from immutable event payload text.
        runtime_payload = {
            key: value
            for key, value in notice.payload.items()
            if key not in {"campaign_name", "action_url", "title", "body"}
        }
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
                runtime_payload["reset_action"] = public_action_url(
                    settings, f"/reset-password?token={quote(reset_token)}"
                )
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
                from app.services.driver_applications import current_application_step

                step = (
                    await current_application_step(session, application)
                    if application
                    else "details"
                )
            if (
                access is None
                or application is None
                or user is None
                or access.invalidated_at is not None
                or application.user_id != user.id
                or application.status != DriverApplicationStatus.PENDING.value
                or _utc(access.expires_at) <= _utc(now)
            ):
                raise ValueError("driver_onboarding_access_request_inactive")
            from app.services.driver_applications import (
                driver_application_access_token_for_delivery,
            )

            try:
                access_token = driver_application_access_token_for_delivery(access, settings)
                runtime_payload["action_url"] = public_action_url(
                    settings, f"/apply?step={step}#application_access_token={quote(access_token)}"
                )
            except RuntimeError:
                raise ValueError("driver_onboarding_access_evidence_mismatch") from None
        elif notice.type_key == NotificationType.DRIVER_ACCOUNT_SETUP_REQUESTED.value:
            try:
                setup_id = UUID(str(notice.payload["driver_account_setup_id"]))
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError("driver_account_setup_request_missing") from exc
            async with sessionmaker() as session:
                setup = await session.get(DriverAccountSetupToken, setup_id)
                application = (
                    await session.get(DriverApplication, setup.application_id)
                    if setup is not None
                    else None
                )
                user = await session.get(User, notice.recipient_user_id)
            if (
                setup is None
                or application is None
                or user is None
                or setup.user_id != user.id
                or application.user_id != user.id
                or setup.used_at is not None
                or setup.superseded_at is not None
                or application.status != DriverApplicationStatus.APPROVED.value
                or user.status != UserStatus.INVITED.value
                or setup.session_version != user.session_version
                or _utc(setup.expires_at) <= _utc(now)
            ):
                raise ValueError("driver_account_setup_request_inactive")
            from app.services.driver_account_setup import driver_account_setup_token_for_delivery

            try:
                setup_token = driver_account_setup_token_for_delivery(setup, settings)
            except RuntimeError:
                raise ValueError("driver_account_setup_evidence_mismatch") from None
            if settings.driver_account_setup_public_url:
                separator = "&" if "?" in settings.driver_account_setup_public_url else "?"
                runtime_payload["setup_action"] = (
                    f"{settings.driver_account_setup_public_url}{separator}token={quote(setup_token)}"
                )
            else:
                # A bare token is unusable and must never be sent in its place.
                runtime_payload["setup_action"] = None
        else:
            from app.services.driver_review_notifications import REVIEW_TYPES, review_notice_context
            from app.services.notifications import notification_campaign_context

            async with sessionmaker() as session:
                user = await session.get(User, notice.recipient_user_id)
                if notice.type_key in REVIEW_TYPES:
                    context = await review_notice_context(session, notice, user) if user else None
                    if context is None:
                        raise ValueError("driver_review_inactive")
                    runtime_payload.update(context)
                    runtime_payload["action_url"] = public_action_url(
                        settings, context["action_path"]
                    )
                else:
                    context = (
                        await notification_campaign_context(session, notice=notice, user=user)
                        if user
                        else None
                    )
                    runtime_payload["action_url"] = public_action_url(
                        settings, context[1] if context else "/login"
                    )
                    if context:
                        runtime_payload["campaign_name"] = context[0]
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
                locked.failed_at = now
                locked.next_attempt_at = None
                result = "failed"
        await session.commit()
        return result


logger = logging.getLogger(__name__)


async def record_unexpected_email_failure(
    sessionmaker: async_sessionmaker[AsyncSession], *, notification_id: UUID, error: Exception
) -> None:
    error_code = type(error).__name__
    logger.warning(
        "Email delivery item failed",
        extra={"notification_id": str(notification_id), "error_code": error_code},
    )
    async with sessionmaker() as session:
        await create_audit_event(
            session,
            actor_user_id=None,
            action="worker.email_delivery.failed",
            entity_type="notification",
            entity_id=str(notification_id),
            metadata={"error_code": error_code},
        )
        await session.commit()
