from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.errors import AppError
from app.models.driver import DriverProfile
from app.models.fraud_dispute import FraudDispute, FraudDisputeStatus
from app.models.notification import Notification
from app.models.trip import TripSession
from app.models.trip_analytics import FraudFlag
from app.services.audit import create_audit_event
from app.services.fraud_holds import (
    hold_active,
    lock_fraud_hold_scope,
    lock_fraud_reconciliation_gate,
)
from app.services.notifications import (
    create_fraud_dispute_replied_notice,
    notices_for_driver_flags,
)


@dataclass(frozen=True)
class DisputeMutationResult:
    dispute: FraudDispute
    changed: bool


PUBLIC_REASONS = {
    "insufficient_pings": (
        "location_data_incomplete",
        "Location data needs review",
        "Some location information for this trip could not be verified.",
    ),
    "impossible_speed": (
        "route_pattern_review",
        "Route needs review",
        "A route pattern for this trip needs a staff review.",
    ),
    "poor_accuracy": (
        "location_accuracy_review",
        "Location accuracy needs review",
        "The location accuracy for this trip needs a staff review.",
    ),
    "stationary_trip": (
        "movement_review",
        "Trip movement needs review",
        "The recorded movement for this trip needs a staff review.",
    ),
    "excessive_ping_gap": (
        "location_data_incomplete",
        "Location data needs review",
        "Some location information for this trip could not be verified.",
    ),
    "future_timestamp": (
        "location_time_review",
        "Location timing needs review",
        "The timing of location information for this trip needs a staff review.",
    ),
    "route_looping": (
        "route_pattern_review",
        "Route needs review",
        "A route pattern for this trip needs a staff review.",
    ),
    "route_replay": (
        "route_pattern_review",
        "Route needs review",
        "A route pattern for this trip needs a staff review.",
    ),
    "exclusion_zone_presence": (
        "route_area_review",
        "Trip area needs review",
        "The recorded trip area needs a staff review.",
    ),
}
GENERIC_PUBLIC_REASON = (
    "trip_review",
    "Trip needs review",
    "This trip needs a staff review before its earnings can be released.",
)
PUBLIC_STATUS = {
    "open": "assessment_pending",
    "acknowledged": "under_review",
    "confirmed": "issue_confirmed",
    "dismissed": "review_cleared",
}


def dispute_not_found() -> AppError:
    return AppError("FRAUD_DISPUTE_NOT_FOUND", "Fraud dispute was not found", status_code=404)


async def _owned_driver_profile(session: AsyncSession, user_id: UUID) -> DriverProfile:
    profile = await session.scalar(select(DriverProfile).where(DriverProfile.user_id == user_id))
    if profile is None:
        raise AppError("DRIVER_PROFILE_NOT_FOUND", "Driver profile was not found", status_code=404)
    return profile


async def create_driver_dispute(
    session: AsyncSession, *, flag_id: UUID, user_id: UUID, message: str
) -> DisputeMutationResult:
    normalized = message.strip()
    await lock_fraud_reconciliation_gate(session, exclusive=False)
    stub = (
        await session.execute(
            select(FraudFlag.trip_session_id, FraudFlag.driver_profile_id).where(
                FraudFlag.id == flag_id
            )
        )
    ).one_or_none()
    profile = await _owned_driver_profile(session, user_id)
    if stub is None or stub.driver_profile_id != profile.id:
        raise AppError("FRAUD_FLAG_NOT_FOUND", "Fraud flag was not found", status_code=404)
    await lock_fraud_hold_scope(session, stub.trip_session_id, reconciliation_gate_held=True)
    flag = await session.scalar(select(FraudFlag).where(FraudFlag.id == flag_id).with_for_update())
    if flag is None or flag.driver_profile_id != profile.id:
        raise AppError("FRAUD_FLAG_NOT_FOUND", "Fraud flag was not found", status_code=404)
    dispute = await session.scalar(
        select(FraudDispute).where(FraudDispute.fraud_flag_id == flag.id).with_for_update()
    )
    if dispute is not None:
        if dispute.submitted_by_user_id == user_id and dispute.message == normalized:
            return DisputeMutationResult(dispute, False)
        raise AppError(
            "FRAUD_DISPUTE_REPLAY_CONFLICT",
            "The existing dispute does not match this retry",
            status_code=status.HTTP_409_CONFLICT,
        )
    if not hold_active(flag):
        raise AppError(
            "FRAUD_FLAG_NOT_DISPUTABLE",
            "Only a current fraud hold can be disputed",
            status_code=status.HTTP_409_CONFLICT,
        )
    dispute = FraudDispute(
        fraud_flag_id=flag.id,
        driver_profile_id=profile.id,
        submitted_by_user_id=user_id,
        message=normalized,
        status=FraudDisputeStatus.OPEN.value,
    )
    try:
        async with session.begin_nested():
            session.add(dispute)
            await session.flush()
    except IntegrityError as exc:
        existing = await session.scalar(
            select(FraudDispute).where(FraudDispute.fraud_flag_id == flag.id)
        )
        if existing is None:
            raise
        if existing.submitted_by_user_id == user_id and existing.message == normalized:
            return DisputeMutationResult(existing, False)
        raise AppError(
            "FRAUD_DISPUTE_REPLAY_CONFLICT",
            "The existing dispute does not match this retry",
            status_code=409,
        ) from exc
    await create_audit_event(
        session,
        actor_user_id=user_id,
        action="driver.fraud_dispute.created",
        entity_type="fraud_dispute",
        entity_id=str(dispute.id),
        metadata={"fraud_flag_id": str(flag.id), "trip_session_id": str(flag.trip_session_id)},
    )
    await session.refresh(dispute)
    return DisputeMutationResult(dispute, True)


async def reply_to_dispute(
    session: AsyncSession,
    *,
    dispute_id: UUID,
    actor_user_id: UUID,
    reply: str,
    now: datetime | None = None,
) -> DisputeMutationResult:
    normalized = reply.strip()
    await lock_fraud_reconciliation_gate(session, exclusive=False)
    stub = (
        await session.execute(
            select(FraudDispute.fraud_flag_id, FraudFlag.trip_session_id)
            .join(FraudFlag, FraudFlag.id == FraudDispute.fraud_flag_id)
            .where(FraudDispute.id == dispute_id)
        )
    ).one_or_none()
    if stub is None:
        raise dispute_not_found()
    await lock_fraud_hold_scope(session, stub.trip_session_id, reconciliation_gate_held=True)
    flag = await session.scalar(
        select(FraudFlag).where(FraudFlag.id == stub.fraud_flag_id).with_for_update()
    )
    dispute = await session.scalar(
        select(FraudDispute).where(FraudDispute.id == dispute_id).with_for_update()
    )
    if flag is None or dispute is None:
        raise dispute_not_found()
    if dispute.status == FraudDisputeStatus.REPLIED.value:
        if dispute.replied_by_user_id == actor_user_id and dispute.reply_text == normalized:
            return DisputeMutationResult(dispute, False)
        raise AppError(
            "FRAUD_DISPUTE_REPLY_REPLAY_CONFLICT",
            "The completed dispute reply does not match this retry",
            status_code=409,
        )
    replied_at = now or datetime.now(UTC)
    dispute.status = FraudDisputeStatus.REPLIED.value
    dispute.replied_by_user_id = actor_user_id
    dispute.replied_at = replied_at
    dispute.reply_text = normalized
    dispute.updated_at = replied_at
    await session.flush()
    await create_fraud_dispute_replied_notice(session, flag=flag, dispute_id=dispute.id)
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="admin.fraud_dispute.replied",
        entity_type="fraud_dispute",
        entity_id=str(dispute.id),
        metadata={"fraud_flag_id": str(flag.id), "trip_session_id": str(flag.trip_session_id)},
    )
    await session.refresh(dispute)
    return DisputeMutationResult(dispute, True)


async def list_admin_disputes(
    session: AsyncSession,
    *,
    flag_ids: list[UUID] | None,
    dispute_status: str | None,
    limit: int,
    offset: int,
) -> tuple[list[FraudDispute], int]:
    filters = []
    if flag_ids:
        filters.append(FraudDispute.fraud_flag_id.in_(flag_ids))
    if dispute_status:
        filters.append(FraudDispute.status == dispute_status)
    total = int(
        await session.scalar(select(func.count()).select_from(FraudDispute).where(*filters)) or 0
    )
    items = list(
        (
            await session.scalars(
                select(FraudDispute)
                .where(*filters)
                .order_by(FraudDispute.created_at.desc(), FraudDispute.id.desc())
                .limit(limit)
                .offset(offset)
            )
        ).all()
    )
    return items, total


async def list_driver_holds(
    session: AsyncSession, *, user_id: UUID, trip_session_id: UUID | None
) -> list[tuple[FraudFlag, FraudDispute | None, list[Notification]]]:
    profile = await _owned_driver_profile(session, user_id)
    if trip_session_id is not None:
        owned_trip = await session.scalar(
            select(TripSession.id).where(
                TripSession.id == trip_session_id,
                TripSession.driver_profile_id == profile.id,
            )
        )
        if owned_trip is None:
            raise AppError("TRIP_NOT_FOUND", "Trip was not found", status_code=404)
    filters = [
        FraudFlag.driver_profile_id == profile.id,
        FraudFlag.status.in_(tuple(PUBLIC_STATUS)),
    ]
    if trip_session_id is not None:
        filters.append(FraudFlag.trip_session_id == trip_session_id)
    flags = list(
        (
            await session.scalars(
                select(FraudFlag)
                .where(*filters)
                .order_by(FraudFlag.detected_at.desc(), FraudFlag.id)
            )
        ).all()
    )
    flag_ids = {flag.id for flag in flags}
    disputes = (
        {
            item.fraud_flag_id: item
            for item in (
                await session.scalars(
                    select(FraudDispute).where(FraudDispute.fraud_flag_id.in_(flag_ids))
                )
            ).all()
        }
        if flag_ids
        else {}
    )
    notices = await notices_for_driver_flags(session, recipient_user_id=user_id, flag_ids=flag_ids)
    return [(flag, disputes.get(flag.id), notices.get(flag.id, [])) for flag in flags]
