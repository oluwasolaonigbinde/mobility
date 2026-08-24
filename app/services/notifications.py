from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.driver import DriverProfile
from app.models.notification import Notification, NotificationType
from app.models.trip_analytics import FraudFlag


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
    existing = await session.scalar(
        select(Notification).where(Notification.dedupe_key == dedupe_key)
    )
    if existing is not None:
        return existing
    notice = Notification(
        recipient_user_id=recipient_user_id,
        type_key=type_key.value,
        template_version="v1",
        payload=payload,
        dedupe_key=dedupe_key,
    )
    try:
        async with session.begin_nested():
            session.add(notice)
            await session.flush()
    except IntegrityError:
        existing = await session.scalar(
            select(Notification).where(Notification.dedupe_key == dedupe_key)
        )
        if existing is None:
            raise
        return existing
    await session.refresh(notice)
    return notice


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


async def notices_for_driver_flags(
    session: AsyncSession, *, recipient_user_id: UUID, flag_ids: set[UUID]
) -> dict[UUID, list[Notification]]:
    if not flag_ids:
        return {}
    rows = list(
        (
            await session.scalars(
                select(Notification)
                .where(Notification.recipient_user_id == recipient_user_id)
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
