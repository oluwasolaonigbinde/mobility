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
    notification_campaign_context,
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


def notification_feed_response(
    notice: Notification, context: tuple[str, str] | None = None
) -> NotificationFeedItemRead:
    """Render from the small approved type allowlist, never from JSON payload."""
    rendered = {
        NotificationType.ASSIGNMENT_OFFERED.value: (
            "Assignment offered",
            "A campaign assignment is ready for your review.",
        ),
        NotificationType.ASSIGNMENT_ACCEPTED.value: (
            "Assignment accepted",
            "Your campaign assignment acceptance was recorded.",
        ),
        NotificationType.CAMPAIGN_APPROVED.value: (
            "Campaign approved",
            "Your campaign has been approved.",
        ),
        NotificationType.CAMPAIGN_REJECTED.value: (
            "Campaign needs changes",
            "Your campaign was not approved. Open it to read the reason, update it and resubmit.",
        ),
        NotificationType.CREATIVE_APPROVED.value: (
            "Artwork approved",
            "Campaign artwork has been approved.",
        ),
        NotificationType.CREATIVE_REJECTED.value: (
            "Artwork needs changes",
            "Campaign artwork was not approved. Open the campaign to read the reason.",
        ),
        NotificationType.QUOTATION_READY.value: (
            "Quotation ready",
            "A quotation is ready for your review in the campaign.",
        ),
        NotificationType.FUNDING_CONFIRMED.value: (
            "Funding confirmed",
            "Campaign funding has been confirmed.",
        ),
        NotificationType.BUDGET_ALERT.value: (
            "Campaign budget warning",
            "A campaign has used most of its budget.",
        ),
        NotificationType.BUDGET_URGENT_ALERT.value: (
            "Campaign budget nearly used",
            "A campaign has almost used its budget and will pause when it runs out.",
        ),
        NotificationType.CAMPAIGN_BUDGET_PAUSED.value: (
            "Campaign paused",
            "Cardvert paused a campaign because its budget is used up.",
        ),
        NotificationType.CAMPAIGN_BUDGET_RESUMED.value: (
            "Campaign resumed",
            "Terrax Media resumed a campaign that was paused for budget.",
        ),
        NotificationType.CAMPAIGN_CANCELLED.value: (
            "Campaign cancelled",
            "A campaign cancellation has been recorded.",
        ),
        NotificationType.PAYOUT_RELEASED.value: (
            "Pay ready",
            "A hold on some of your pay has been lifted. "
            "Open Earnings to check its payment status.",
        ),
        NotificationType.FRAUD_HOLD_RAISED.value: (
            "Trip pay on hold",
            "Pay for one of your trips is on hold while Terrax Media checks it. "
            "Open Earnings to see why.",
        ),
        NotificationType.FRAUD_REVIEW_RESOLVED.value: (
            "Trip check finished",
            "Terrax Media finished checking your trip. Open Earnings to see the result.",
        ),
        NotificationType.FRAUD_DISPUTE_REPLIED.value: (
            "Reply about your trip",
            "Terrax Media replied to what you said about your trip. Open Earnings to read it.",
        ),
        NotificationType.ACTIVITY_FLOOR_BREACHED.value: (
            "Not enough driving this week",
            "You drove less than this job's weekly minimum. Terrax Media will look at your job.",
        ),
        NotificationType.ACTIVITY_FLOOR_RECOVERED.value: (
            "Weekly driving back on track",
            "You're back above this job's weekly minimum.",
        ),
        NotificationType.ASSIGNMENT_INACTIVE.value: (
            "No trips for 7 days",
            "No trips were recorded on your job for 7 days. Terrax Media will look at it.",
        ),
        NotificationType.ASSIGNMENT_ACTIVITY_RECOVERED.value: (
            "Trips started again",
            "Trips are being recorded on your job again.",
        ),
        NotificationType.PAYOUT_AUTOMATIC_ALERT.value: (
            "Automatic payout needs attention",
            "Cardvert found a problem with automatic driver payouts. "
            "Open Automatic payouts to follow it up.",
        ),
        NotificationType.PAYOUT_AUTOMATIC_PAUSED.value: (
            "Automatic payouts paused",
            "Terrax Media paused automatic driver payouts. Open Automatic payouts to see why.",
        ),
        NotificationType.PAYOUT_AUTOMATIC_RESUMED.value: (
            "Automatic payouts resumed",
            "Terrax Media resumed automatic driver payouts.",
        ),
        NotificationType.COMPLAINT_RECEIVED.value: (
            "Complaint waiting",
            "A driver or advertiser raised or followed up a complaint for Customer Service.",
        ),
        NotificationType.COMPLAINT_REPLIED.value: (
            "Reply to your complaint",
            "Terrax Media replied to your complaint. Open Help to read it.",
        ),
        NotificationType.COMPLAINT_RESOLVED.value: (
            "Complaint resolved",
            "Terrax Media marked your complaint as resolved. Open Help to read it or reply.",
        ),
        NotificationType.COMPLAINT_ASSIGNED.value: (
            "Complaint assigned to you",
            "A complaint in the Customer Service inbox was assigned to you.",
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
        title=f"{context[0]} · {title}" if context else title,
        body=body,
        campaign_name=context[0] if context else None,
        action_url=context[1] if context else None,
        created_at=notice.created_at,
        read_at=notice.read_at,
    )


async def current_feed_item(session, notice, user) -> NotificationFeedItemRead:
    from app.core.errors import AppError
    from app.services.driver_review_notifications import REVIEW_TYPES, review_notice_context

    review = await review_notice_context(session, notice, user)
    if notice.type_key in REVIEW_TYPES and review is None:
        raise AppError("NOTIFICATION_NOT_FOUND", "Notification was not found", status_code=404)
    item = notification_feed_response(
        notice, await notification_campaign_context(session, notice=notice, user=user)
    )
    if review:
        return item.model_copy(
            update={
                "title": review["title"],
                "body": review["body"],
                "action_url": review["action_path"],
            }
        )
    return item


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
        items=[await current_feed_item(session, notice, user) for notice in notices],
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
    return await current_feed_item(session, notice, user)


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
