import hashlib
import hmac
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.errors import AppError
from app.models.assignment_activity import (
    AssignmentActivityFlag,
    AssignmentActivityFlagEventType,
    AssignmentActivityFlagType,
)
from app.models.billing import BudgetCampaignTransition, BudgetPolicyEvaluation
from app.models.campaign import Campaign
from app.models.contact import PasswordResetToken
from app.models.driver import DriverProfile
from app.models.notification import (
    Notification,
    NotificationChannel,
    NotificationDeliveryReceipt,
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
from app.models.trip_analytics import FraudFlag
from app.models.user import User, UserRole, UserStatus


def _canonical_payload(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return json.loads(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    except (TypeError, ValueError) as exc:
        raise AppError(
            "INVALID_NOTIFICATION_PAYLOAD",
            "Notification payload must be JSON-compatible",
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc


def notification_dedupe_fingerprint(
    *,
    recipient_user_id: UUID,
    type_key: NotificationType,
    template_version: str,
    channel: NotificationChannel,
    payload: dict[str, Any],
) -> str:
    document = {
        "recipient_user_id": str(recipient_user_id),
        "type_key": type_key.value,
        "template_version": template_version,
        "channel": channel.value,
        "payload": _canonical_payload(payload),
    }
    return hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _dedupe_conflict() -> AppError:
    return AppError(
        "NOTIFICATION_DEDUPE_CONFLICT",
        "The notification retry does not match the original delivery",
        status_code=status.HTTP_409_CONFLICT,
    )


def _not_found() -> AppError:
    return AppError(
        "NOTIFICATION_NOT_FOUND",
        "Notification was not found",
        status_code=status.HTTP_404_NOT_FOUND,
    )


async def create_notification(
    session: AsyncSession,
    *,
    recipient_user_id: UUID,
    type_key: NotificationType,
    payload: dict[str, Any],
    dedupe_key: str | None,
    channel: NotificationChannel = NotificationChannel.IN_APP,
    template_version: str = "v1",
) -> Notification:
    """Persist one logical recipient/channel delivery in the caller's transaction."""
    channel = NotificationChannel(channel)
    canonical_payload = _canonical_payload(payload)
    fingerprint = notification_dedupe_fingerprint(
        recipient_user_id=recipient_user_id,
        type_key=type_key,
        template_version=template_version,
        channel=channel,
        payload=canonical_payload,
    )
    existing = None
    if dedupe_key is not None:
        existing = await session.scalar(
            select(Notification).where(
                Notification.recipient_user_id == recipient_user_id,
                Notification.channel == channel.value,
                Notification.dedupe_key == dedupe_key,
            )
        )
    if existing is not None:
        if existing.dedupe_fingerprint != fingerprint:
            raise _dedupe_conflict()
        return existing

    is_in_app = channel is NotificationChannel.IN_APP
    notice = Notification(
        recipient_user_id=recipient_user_id,
        type_key=type_key.value,
        template_version=template_version,
        channel=channel.value,
        status=(NotificationStatus.SENT if is_in_app else NotificationStatus.PENDING).value,
        payload=canonical_payload,
        dedupe_key=dedupe_key,
        dedupe_fingerprint=fingerprint,
        sent_at=datetime.now(UTC) if is_in_app else None,
    )
    try:
        async with session.begin_nested():
            session.add(notice)
            await session.flush()
    except IntegrityError:
        if dedupe_key is None:
            raise
        existing = await session.scalar(
            select(Notification).where(
                Notification.recipient_user_id == recipient_user_id,
                Notification.channel == channel.value,
                Notification.dedupe_key == dedupe_key,
            )
        )
        if existing is None:
            raise
        if existing.dedupe_fingerprint != fingerprint:
            raise _dedupe_conflict() from None
        return existing
    return notice


async def create_advertiser_email_notification(
    session: AsyncSession,
    *,
    advertiser_organization_id: UUID,
    recipient_user_id: UUID,
    type_key: NotificationType,
    payload: dict[str, Any],
    dedupe_key: str,
    template_version: str = "v1",
) -> Notification | None:
    """Create an email row only for an active member while the org preference permits it."""
    member = await session.scalar(
        select(OrganizationMembership.id)
        .join(User, User.id == OrganizationMembership.user_id)
        .join(
            AdvertiserOrganization,
            AdvertiserOrganization.id == OrganizationMembership.organization_id,
        )
        .where(
            OrganizationMembership.organization_id == advertiser_organization_id,
            OrganizationMembership.user_id == recipient_user_id,
            OrganizationMembership.status == MembershipStatus.ACTIVE.value,
            AdvertiserOrganization.status == OrganizationStatus.ACTIVE.value,
            User.role == UserRole.ADVERTISER.value,
            User.status == UserStatus.ACTIVE.value,
        )
    )
    if member is None:
        raise AppError(
            "INVALID_EMAIL_RECIPIENT",
            "Email recipient is not an active member of this advertiser organization",
            status_code=status.HTTP_409_CONFLICT,
        )
    enabled = await session.scalar(
        select(AdvertiserOrganizationNotificationPreference.transactional_email_enabled).where(
            AdvertiserOrganizationNotificationPreference.advertiser_organization_id
            == advertiser_organization_id
        )
    )
    if enabled is False:
        return None
    bounded_payload = dict(payload)
    bounded_payload["advertiser_organization_id"] = str(advertiser_organization_id)
    return await create_notification(
        session,
        recipient_user_id=recipient_user_id,
        type_key=type_key,
        payload=bounded_payload,
        dedupe_key=dedupe_key,
        channel=NotificationChannel.TRANSACTIONAL_EMAIL,
        template_version=template_version,
    )


def email_receipt_fingerprint(payload: dict[str, Any]) -> tuple[bytes, str]:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return canonical, hashlib.sha256(canonical).hexdigest()


async def record_email_delivery_receipt(
    session: AsyncSession,
    *,
    payload: dict[str, Any],
    signature: str,
    signing_key_id: str,
    signing_secret: bytes | None,
    configured_key_id: str,
) -> NotificationDeliveryReceipt:
    if not signing_secret or not configured_key_id:
        raise AppError(
            "EMAIL_RECEIPTS_UNCONFIGURED",
            "Email delivery receipts are not configured",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    canonical, fingerprint = email_receipt_fingerprint(payload)
    supplied = signature.removeprefix("sha256=")
    expected = hmac.new(signing_secret, canonical, hashlib.sha256).hexdigest()
    if signing_key_id != configured_key_id or not hmac.compare_digest(expected, supplied):
        raise AppError(
            "INVALID_EMAIL_RECEIPT_SIGNATURE",
            "Email delivery receipt signature is invalid",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    existing_event = await session.scalar(
        select(NotificationDeliveryReceipt).where(
            NotificationDeliveryReceipt.provider_event_id == payload["provider_event_id"]
        )
    )
    if existing_event is not None:
        if existing_event.evidence_fingerprint != fingerprint:
            raise AppError(
                "EMAIL_RECEIPT_REPLAY_CONFLICT",
                "Email delivery receipt retry does not match the original event",
                status_code=status.HTTP_409_CONFLICT,
            )
        return existing_event
    notice = await session.scalar(
        select(Notification)
        .where(Notification.provider_message_id == payload["provider_message_id"])
        .with_for_update()
    )
    if notice is None:
        raise AppError(
            "EMAIL_NOTIFICATION_NOT_FOUND",
            "Email delivery receipt does not match a notification",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    existing_notice = await session.scalar(
        select(NotificationDeliveryReceipt).where(
            NotificationDeliveryReceipt.notification_id == notice.id
        )
    )
    if existing_notice is not None:
        raise AppError(
            "EMAIL_RECEIPT_TERMINAL_CONFLICT",
            "A terminal receipt already exists for this notification",
            status_code=status.HTTP_409_CONFLICT,
        )
    if notice.status != NotificationStatus.SENT.value:
        raise AppError(
            "EMAIL_RECEIPT_INVALID_STATE",
            "Email notification is not awaiting a delivery receipt",
            status_code=status.HTTP_409_CONFLICT,
        )
    receipt = NotificationDeliveryReceipt(
        notification_id=notice.id,
        provider_event_id=payload["provider_event_id"],
        provider_message_id=payload["provider_message_id"],
        outcome=payload["outcome"],
        occurred_at=(
            datetime.fromisoformat(payload["occurred_at"].replace("Z", "+00:00"))
            if isinstance(payload["occurred_at"], str)
            else payload["occurred_at"]
        ),
        evidence_fingerprint=fingerprint,
        signing_key_id=signing_key_id,
    )
    try:
        async with session.begin_nested():
            session.add(receipt)
            notice.status = payload["outcome"]
            if payload["outcome"] == NotificationStatus.DELIVERED.value:
                notice.delivered_at = receipt.occurred_at
            else:
                notice.last_error_code = "provider_delivery_failed"
            await session.flush()
    except IntegrityError:
        concurrent = await session.scalar(
            select(NotificationDeliveryReceipt).where(
                NotificationDeliveryReceipt.provider_event_id == payload["provider_event_id"]
            )
        )
        if concurrent is None or concurrent.evidence_fingerprint != fingerprint:
            raise AppError(
                "EMAIL_RECEIPT_REPLAY_CONFLICT",
                "Email delivery receipt conflicts with an accepted receipt",
                status_code=status.HTTP_409_CONFLICT,
            ) from None
        return concurrent
    return receipt


async def _recipient_for_flag(session: AsyncSession, flag: FraudFlag) -> UUID:
    user_id = await session.scalar(
        select(DriverProfile.user_id).where(DriverProfile.id == flag.driver_profile_id)
    )
    if user_id is None:
        raise RuntimeError("fraud flag driver profile is missing")
    return user_id


async def _create_notice(
    session: AsyncSession,
    *,
    recipient_user_id: UUID,
    type_key: NotificationType,
    payload: dict[str, str],
    dedupe_key: str,
) -> Notification:
    return await create_notification(
        session,
        recipient_user_id=recipient_user_id,
        type_key=type_key,
        payload=payload,
        dedupe_key=dedupe_key,
    )


async def create_advertiser_business_notifications(
    session: AsyncSession,
    *,
    advertiser_organization_id: UUID,
    type_key: NotificationType,
    event_key: str,
    payload: dict[str, Any],
) -> list[Notification]:
    """Create in-app plus preference-governed email rows from one authoritative event key."""
    recipients = list(
        await session.scalars(
            select(User)
            .join(OrganizationMembership, OrganizationMembership.user_id == User.id)
            .join(
                AdvertiserOrganization,
                AdvertiserOrganization.id == OrganizationMembership.organization_id,
            )
            .where(
                OrganizationMembership.organization_id == advertiser_organization_id,
                OrganizationMembership.status == MembershipStatus.ACTIVE.value,
                AdvertiserOrganization.status == OrganizationStatus.ACTIVE.value,
                User.role == UserRole.ADVERTISER.value,
                User.status == UserStatus.ACTIVE.value,
            )
            .order_by(User.id)
        )
    )
    notices: list[Notification] = []
    for recipient in recipients:
        notices.append(
            await create_notification(
                session,
                recipient_user_id=recipient.id,
                type_key=type_key,
                payload=payload,
                dedupe_key=f"{event_key}:in_app",
            )
        )
        email = await create_advertiser_email_notification(
            session,
            advertiser_organization_id=advertiser_organization_id,
            recipient_user_id=recipient.id,
            type_key=type_key,
            payload=payload,
            dedupe_key=f"{event_key}:transactional_email",
        )
        if email is not None:
            notices.append(email)
    return notices


async def create_driver_business_notification(
    session: AsyncSession,
    *,
    driver_profile_id: UUID,
    type_key: NotificationType,
    event_key: str,
    payload: dict[str, Any],
    manual_contact_purpose: str | None = None,
) -> Notification:
    recipient_user_id = await session.scalar(
        select(DriverProfile.user_id).where(DriverProfile.id == driver_profile_id)
    )
    if recipient_user_id is None:
        raise RuntimeError("driver business notification has no driver profile")
    notice = await create_notification(
        session,
        recipient_user_id=recipient_user_id,
        type_key=type_key,
        payload=payload,
        dedupe_key=f"{event_key}:in_app",
    )
    if manual_contact_purpose is not None:
        from app.services.contacts import create_manual_driver_contact_task

        await create_manual_driver_contact_task(
            session,
            driver_profile_id=driver_profile_id,
            event_key=event_key,
            purpose=manual_contact_purpose,
        )
    return notice


async def create_budget_policy_notices(
    session: AsyncSession, *, campaign: Campaign, evaluation: BudgetPolicyEvaluation
) -> list[Notification]:
    if evaluation.state == "alert_threshold":
        type_key = NotificationType.BUDGET_ALERT
    elif evaluation.state == "pause_threshold":
        type_key = NotificationType.CAMPAIGN_BUDGET_PAUSED
    else:
        return []
    return await create_advertiser_business_notifications(
        session,
        advertiser_organization_id=campaign.organization_id,
        type_key=type_key,
        event_key=f"budget:{evaluation.state}:v1:{evaluation.id}",
        payload={
            "campaign_id": str(campaign.id),
            "budget_evaluation_id": str(evaluation.id),
            "budget_state": evaluation.state,
            "currency": evaluation.currency,
        },
    )


async def create_budget_resume_notices(
    session: AsyncSession, *, campaign: Campaign, transition: BudgetCampaignTransition
) -> list[Notification]:
    return await create_advertiser_business_notifications(
        session,
        advertiser_organization_id=campaign.organization_id,
        type_key=NotificationType.CAMPAIGN_BUDGET_RESUMED,
        event_key=f"budget:resume:v1:{transition.id}",
        payload={
            "campaign_id": str(campaign.id),
            "budget_transition_id": str(transition.id),
            "campaign_status": transition.new_status,
        },
    )


async def create_password_reset_notification(
    session: AsyncSession, *, user: User, reset: PasswordResetToken
) -> Notification:
    payload = {"password_reset_request_id": str(reset.id)}
    dedupe_key = f"password_reset:v1:{reset.id}:transactional_email"
    return await create_notification(
        session,
        recipient_user_id=user.id,
        type_key=NotificationType.PASSWORD_RESET_REQUESTED,
        payload=payload,
        dedupe_key=dedupe_key,
        channel=NotificationChannel.TRANSACTIONAL_EMAIL,
    )


async def create_fraud_hold_raised_notice(session: AsyncSession, flag: FraudFlag) -> Notification:
    return await _create_notice(
        session,
        recipient_user_id=await _recipient_for_flag(session, flag),
        type_key=NotificationType.FRAUD_HOLD_RAISED,
        payload={"fraud_flag_id": str(flag.id), "trip_session_id": str(flag.trip_session_id)},
        dedupe_key=f"fraud_hold_raised:v1:{flag.id}",
    )


async def create_fraud_review_resolved_notice(
    session: AsyncSession, flag: FraudFlag
) -> Notification:
    return await _create_notice(
        session,
        recipient_user_id=await _recipient_for_flag(session, flag),
        type_key=NotificationType.FRAUD_REVIEW_RESOLVED,
        payload={
            "fraud_flag_id": str(flag.id),
            "trip_session_id": str(flag.trip_session_id),
            "outcome": flag.status,
        },
        dedupe_key=f"fraud_review_resolved:v1:{flag.id}:{flag.status}",
    )


async def create_fraud_dispute_replied_notice(
    session: AsyncSession, *, flag: FraudFlag, dispute_id: UUID
) -> Notification:
    return await _create_notice(
        session,
        recipient_user_id=await _recipient_for_flag(session, flag),
        type_key=NotificationType.FRAUD_DISPUTE_REPLIED,
        payload={
            "fraud_flag_id": str(flag.id),
            "trip_session_id": str(flag.trip_session_id),
            "fraud_dispute_id": str(dispute_id),
        },
        dedupe_key=f"fraud_dispute_replied:v1:{dispute_id}",
    )


async def create_activity_flag_notice(
    session: AsyncSession,
    *,
    flag: AssignmentActivityFlag,
    event_type: AssignmentActivityFlagEventType,
    event_sequence: int,
) -> Notification:
    """Create one typed driver notice for an activity occurrence/recovery."""
    if event_type == AssignmentActivityFlagEventType.OPENED:
        type_key = (
            NotificationType.ACTIVITY_FLOOR_BREACHED
            if flag.flag_type == AssignmentActivityFlagType.VERIFIED_HOURS_FLOOR.value
            else NotificationType.ASSIGNMENT_INACTIVE
        )
    else:
        type_key = (
            NotificationType.ACTIVITY_FLOOR_RECOVERED
            if flag.flag_type == AssignmentActivityFlagType.VERIFIED_HOURS_FLOOR.value
            else NotificationType.ASSIGNMENT_ACTIVITY_RECOVERED
        )
    recipient_user_id = await session.scalar(
        select(DriverProfile.user_id).where(DriverProfile.id == flag.driver_profile_id)
    )
    if recipient_user_id is None:
        raise RuntimeError("activity flag driver profile is missing")
    return await _create_notice(
        session,
        recipient_user_id=recipient_user_id,
        type_key=type_key,
        payload={
            "activity_flag_id": str(flag.id),
            "assignment_id": str(flag.assignment_id),
            "activity_flag_type": flag.flag_type,
            "activity_event": event_type.value,
            "activity_event_sequence": event_sequence,
        },
        dedupe_key=(
            f"assignment_activity:{event_type.value}:v2:{flag.id}:{event_sequence}"
        ),
    )


async def list_current_user_notifications(
    session: AsyncSession, *, recipient_user_id: UUID, limit: int, offset: int
) -> tuple[list[Notification], int]:
    query = select(Notification).where(
        Notification.recipient_user_id == recipient_user_id,
        Notification.channel == NotificationChannel.IN_APP.value,
    )
    total = int(await session.scalar(select(func.count()).select_from(query.subquery())) or 0)
    notices = list(
        (
            await session.scalars(
                query.order_by(Notification.created_at.desc(), Notification.id.desc())
                .limit(limit)
                .offset(offset)
            )
        ).all()
    )
    return notices, total


async def unread_notification_count(session: AsyncSession, *, recipient_user_id: UUID) -> int:
    return int(
        await session.scalar(
            select(func.count())
            .select_from(Notification)
            .where(
                Notification.recipient_user_id == recipient_user_id,
                Notification.channel == NotificationChannel.IN_APP.value,
                Notification.read_at.is_(None),
            )
        )
        or 0
    )


async def mark_notification_read(
    session: AsyncSession, *, recipient_user_id: UUID, notification_id: UUID
) -> Notification:
    read_at = (
        func.statement_timestamp()
        if session.get_bind().dialect.name == "postgresql"
        else func.current_timestamp()
    )
    notice = await session.scalar(
        update(Notification)
        .where(
            Notification.id == notification_id,
            Notification.recipient_user_id == recipient_user_id,
            Notification.channel == NotificationChannel.IN_APP.value,
            Notification.read_at.is_(None),
        )
        .values(read_at=read_at)
        .returning(Notification)
    )
    if notice is not None:
        return notice
    notice = await session.scalar(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.recipient_user_id == recipient_user_id,
            Notification.channel == NotificationChannel.IN_APP.value,
        )
    )
    if notice is None:
        raise _not_found()
    return notice


async def mark_all_notifications_read(
    session: AsyncSession, *, recipient_user_id: UUID
) -> int:
    read_at = (
        func.statement_timestamp()
        if session.get_bind().dialect.name == "postgresql"
        else func.current_timestamp()
    )
    result = await session.execute(
        update(Notification)
        .where(
            Notification.recipient_user_id == recipient_user_id,
            Notification.channel == NotificationChannel.IN_APP.value,
            Notification.read_at.is_(None),
        )
        .values(read_at=read_at)
    )
    return int(result.rowcount or 0)


async def notices_for_driver_flags(
    session: AsyncSession, *, recipient_user_id: UUID, flag_ids: set[UUID]
) -> dict[UUID, list[Notification]]:
    if not flag_ids:
        return {}
    rows = list(
        (
            await session.scalars(
                select(Notification)
                .where(
                    Notification.recipient_user_id == recipient_user_id,
                    Notification.channel == NotificationChannel.IN_APP.value,
                )
                .order_by(Notification.created_at, Notification.id)
            )
        ).all()
    )
    result: dict[UUID, list[Notification]] = {flag_id: [] for flag_id in flag_ids}
    for notice in rows:
        raw_id = notice.payload.get("fraud_flag_id")
        try:
            flag_id = UUID(raw_id) if isinstance(raw_id, str) else None
        except ValueError:
            flag_id = None
        if flag_id in result:
            result[flag_id].append(notice)
    return result
