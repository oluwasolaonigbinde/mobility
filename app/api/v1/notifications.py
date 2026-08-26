from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Query

from app.api.v1.dependencies import (
    AdvertiserUserDependency,
    CurrentUserDependency,
    SessionDependency,
    SettingsDependency,
)
from app.models.notification import Notification, NotificationType
from app.schemas.notifications import (
    AdvertiserNotificationPreferenceRead,
    AdvertiserNotificationPreferenceUpdate,
    DriverNotificationRead,
    EmailDeliveryReceiptCreate,
    EmailDeliveryReceiptRead,
    NotificationFeedItemRead,
    NotificationFeedListRead,
    NotificationUnreadCountRead,
)
from app.services.notifications import (
    list_current_user_notifications,
    mark_all_notifications_read,
    mark_notification_read,
    record_email_delivery_receipt,
    unread_notification_count,
)
from app.services.organizations import (
    get_notification_preference,
    update_notification_preference,
)

router = APIRouter(tags=["Notifications"])


@router.post(
    "/notifications/email/delivery-receipts",
    response_model=EmailDeliveryReceiptRead,
)
async def email_delivery_receipt(
    payload: EmailDeliveryReceiptCreate,
    session: SessionDependency,
    settings: SettingsDependency,
    x_email_receipt_signature: Annotated[str, Header()],
    x_email_receipt_key_id: Annotated[str, Header()],
) -> EmailDeliveryReceiptRead:
    secret = (
        settings.email_receipt_signing_secret.get_secret_value().encode()
        if settings.email_receipt_signing_secret is not None
        else None
    )
    receipt = await record_email_delivery_receipt(
        session,
        payload=payload.model_dump(mode="json"),
        signature=x_email_receipt_signature,
        signing_key_id=x_email_receipt_key_id,
        signing_secret=secret,
        configured_key_id=settings.email_receipt_key_id,
    )
    await session.commit()
    return EmailDeliveryReceiptRead.model_validate(receipt)


def driver_notification_response(notice: Notification) -> DriverNotificationRead:
    # Persisted JSON is never returned wholesale. Legacy or malformed payloads
    # fail closed at the DTO boundary instead of leaking future/internal keys.
    return DriverNotificationRead(
        id=notice.id,
        type_key=notice.type_key,
        template_version=notice.template_version,
        fraud_flag_id=notice.payload.get("fraud_flag_id"),
        trip_session_id=notice.payload.get("trip_session_id"),
        activity_flag_id=notice.payload.get("activity_flag_id"),
        assignment_id=notice.payload.get("assignment_id"),
        outcome=(
            notice.payload.get("outcome")
            if notice.payload.get("outcome") in {"confirmed", "dismissed"}
            else None
        ),
        fraud_dispute_id=notice.payload.get("fraud_dispute_id"),
        created_at=notice.created_at,
    )


def notification_feed_response(notice: Notification) -> NotificationFeedItemRead:
    """Render from the small approved type allowlist, never from JSON payload."""
    rendered = {
        NotificationType.FRAUD_HOLD_RAISED.value: (
            "Trip payment on hold",
            "A trip payment is on hold while it is reviewed.",
        ),
        NotificationType.FRAUD_REVIEW_RESOLVED.value: (
            "Fraud review resolved",
            "Your fraud review has been resolved.",
        ),
        NotificationType.FRAUD_DISPUTE_REPLIED.value: (
            "Fraud dispute update",
            "Your fraud dispute has received a reply.",
        ),
        NotificationType.ACTIVITY_FLOOR_BREACHED.value: (
            "Verified activity below floor",
            "Your verified activity was below the configured weekly floor. "
            "Operations will review the assignment.",
        ),
        NotificationType.ACTIVITY_FLOOR_RECOVERED.value: (
            "Verified activity recovered",
            "Your verified activity has recovered to the configured weekly floor.",
        ),
        NotificationType.ASSIGNMENT_INACTIVE.value: (
            "Assignment inactive",
            "No verified activity was recorded for this assignment for seven "
            "consecutive days. Operations will review it.",
        ),
        NotificationType.ASSIGNMENT_ACTIVITY_RECOVERED.value: (
            "Assignment activity resumed",
            "Verified activity resumed for this assignment. The operations flag "
            "has been recovered.",
        ),
    }
    title, body = rendered.get(
        notice.type_key,
        ("Account notification", "You have a new account notification."),
    )
    return NotificationFeedItemRead(
        id=notice.id,
        type_key=notice.type_key,
        channel=notice.channel,
        title=title,
        body=body,
        created_at=notice.created_at,
        read_at=notice.read_at,
    )


@router.get("/notifications", response_model=NotificationFeedListRead)
async def current_user_notifications(
    user: CurrentUserDependency,
    session: SessionDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> NotificationFeedListRead:
    notices, total = await list_current_user_notifications(
        session,
        recipient_user_id=user.id,
        limit=limit,
        offset=offset,
    )
    return NotificationFeedListRead(
        items=[notification_feed_response(notice) for notice in notices],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/notifications/unread-count", response_model=NotificationUnreadCountRead)
async def current_user_unread_notification_count(
    user: CurrentUserDependency, session: SessionDependency
) -> NotificationUnreadCountRead:
    return NotificationUnreadCountRead(
        unread_count=await unread_notification_count(session, recipient_user_id=user.id)
    )


@router.post("/notifications/{notification_id}/read", response_model=NotificationFeedItemRead)
async def read_notification(
    notification_id: UUID,
    user: CurrentUserDependency,
    session: SessionDependency,
) -> NotificationFeedItemRead:
    notice = await mark_notification_read(
        session,
        recipient_user_id=user.id,
        notification_id=notification_id,
    )
    await session.commit()
    return notification_feed_response(notice)


@router.post("/notifications/read-all", response_model=NotificationUnreadCountRead)
async def read_all_notifications(
    user: CurrentUserDependency, session: SessionDependency
) -> NotificationUnreadCountRead:
    await mark_all_notifications_read(session, recipient_user_id=user.id)
    remaining = await unread_notification_count(session, recipient_user_id=user.id)
    await session.commit()
    return NotificationUnreadCountRead(unread_count=remaining)


@router.get(
    "/advertiser/notification-preferences",
    response_model=AdvertiserNotificationPreferenceRead,
)
async def advertiser_notification_preferences(
    user: AdvertiserUserDependency, session: SessionDependency
) -> AdvertiserNotificationPreferenceRead:
    preference = await get_notification_preference(session, actor_user_id=user.id)
    await session.commit()
    return AdvertiserNotificationPreferenceRead.model_validate(preference)


@router.patch(
    "/advertiser/notification-preferences",
    response_model=AdvertiserNotificationPreferenceRead,
)
async def advertiser_update_notification_preferences(
    payload: AdvertiserNotificationPreferenceUpdate,
    user: AdvertiserUserDependency,
    session: SessionDependency,
) -> AdvertiserNotificationPreferenceRead:
    preference = await update_notification_preference(
        session,
        actor_user_id=user.id,
        organization_id=None,
        transactional_email_enabled=payload.transactional_email_enabled,
    )
    await session.commit()
    return AdvertiserNotificationPreferenceRead.model_validate(preference)
