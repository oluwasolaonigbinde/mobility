import hashlib
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
from app.models.driver import DriverProfile
from app.models.notification import (
    Notification,
    NotificationChannel,
    NotificationStatus,
    NotificationType,
)
from app.models.trip_analytics import FraudFlag


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
