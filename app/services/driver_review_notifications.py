"""Review messages resolve current recipient-owned facts, never payload copy/URLs."""

from datetime import datetime
from typing import cast as type_cast
from uuid import UUID

from sqlalchemy import String, and_, cast, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.driver import DriverProfile
from app.models.kyc import (
    DriverKycReviewDecision,
    DriverKycSubmission,
    VehicleEvidenceReviewDecision,
    VehicleEvidenceSubmission,
)
from app.models.notification import Notification, NotificationChannel, NotificationType
from app.models.user import User, UserRole, UserStatus
from app.models.vehicle import Vehicle

REVIEW_TYPES = {
    NotificationType.DRIVER_ID_APPROVED,
    NotificationType.DRIVER_ID_REJECTED,
    NotificationType.DRIVER_CAR_APPROVED,
    NotificationType.DRIVER_CAR_REJECTED,
}
type ReviewDecision = DriverKycReviewDecision | VehicleEvidenceReviewDecision
type ReviewSubmission = DriverKycSubmission | VehicleEvidenceSubmission

REASONS: dict[str | None, str] = {
    "missing_evidence": "Some documents are missing.",
    "rejected_evidence": "Please replace the documents we could not approve.",
    "expired_evidence": "Some documents have expired. Please send current copies.",
    "unsafe_evidence": "A file could not be accepted. Please send a new copy.",
    "identity_mismatch": "Your ID details do not match. Please check them.",
    "bank_account_mismatch": "Your bank details do not match. Please check them.",
    "unreadable_evidence": "We could not read a document. Please send a clearer copy.",
    "owner_mismatch": "The car ownership details do not match. Please check them.",
    "vehicle_identity_mismatch": "The car details do not match. Please check them.",
    "not_roadworthy": "The car did not pass the roadworthiness check.",
    "not_pilot_eligible": "This car does not meet the pilot requirements.",
}


def applicant_reason(reason_code: str | None) -> str:
    return REASONS.get(reason_code, "Please check your documents and try again.")


async def create_driver_review_notices(
    session: AsyncSession,
    *,
    profile: DriverProfile,
    decision_id: UUID,
    vehicle: bool,
    decision: str,
) -> None:
    from app.services.notifications import create_notification

    if decision not in {"approved", "rejected"}:
        return
    approved = decision == "approved"
    type_key = (
        (NotificationType.DRIVER_CAR_APPROVED if approved else NotificationType.DRIVER_CAR_REJECTED)
        if vehicle
        else (
            NotificationType.DRIVER_ID_APPROVED if approved else NotificationType.DRIVER_ID_REJECTED
        )
    )
    for channel in NotificationChannel:
        await create_notification(
            session,
            recipient_user_id=profile.user_id,
            type_key=type_key,
            payload={"review_decision_id": str(decision_id)},
            channel=channel,
            dedupe_key=f"driver-review:{type_key}:{decision_id}:{channel}",
        )


async def review_notice_context(
    session: AsyncSession,
    notice: Notification,
    user: User,
    *,
    now: datetime | None = None,
) -> dict[str, str] | None:
    if (
        notice.type_key not in REVIEW_TYPES
        or user.id != notice.recipient_user_id
        or user.role != UserRole.DRIVER
        or user.status not in {UserStatus.INVITED, UserStatus.ACTIVE}
    ):
        return None
    vehicle = notice.type_key in {
        NotificationType.DRIVER_CAR_APPROVED,
        NotificationType.DRIVER_CAR_REJECTED,
    }
    decision_model: type[ReviewDecision] = (
        VehicleEvidenceReviewDecision if vehicle else DriverKycReviewDecision
    )
    submission_model: type[ReviewSubmission] = (
        VehicleEvidenceSubmission if vehicle else DriverKycSubmission
    )
    scope_column = "vehicle_id" if vehicle else "driver_profile_id"
    order_column = "sequence" if vehicle else "created_at"
    try:
        decision_id = UUID(str(notice.payload["review_decision_id"]))
    except (KeyError, TypeError, ValueError):
        return None
    decision: ReviewDecision | None = await session.get(decision_model, decision_id)
    submission: ReviewSubmission | None = (
        await session.get(submission_model, decision.submission_id) if decision else None
    )
    scope_id = getattr(submission, scope_column) if submission else None
    car = await session.get(Vehicle, scope_id) if vehicle and submission else None
    profile_id = (
        car.driver_profile_id if car else (scope_id if submission and not vehicle else None)
    )
    profile = await session.get(DriverProfile, profile_id) if profile_id else None
    # A profile is resolved only through an existing decision/submission pair above.
    if (
        profile is None
        or profile.user_id != user.id
        or type_cast(ReviewSubmission, submission).purged_at is not None
    ):
        return None
    submission = type_cast(ReviewSubmission, submission)
    decision = type_cast(ReviewDecision, decision)
    scope = (
        [getattr(submission_model, scope_column) == type_cast(Vehicle, car).id]
        if vehicle
        else [getattr(submission_model, scope_column) == profile.id]
    )
    latest = await session.scalar(
        select(submission_model.id).where(*scope).order_by(submission_model.version.desc()).limit(1)
    )
    last_decision = await session.scalar(
        select(decision_model.id)
        .where(decision_model.submission_id == submission.id)
        .order_by(
            getattr(decision_model, order_column).desc(),
            decision_model.id.desc(),
        )
        .limit(1)
    )
    approved = notice.type_key in {
        NotificationType.DRIVER_ID_APPROVED,
        NotificationType.DRIVER_CAR_APPROVED,
    }
    if (
        latest != submission.id
        or last_decision != decision.id
        or decision.decision != ("approved" if approved else "rejected")
        or submission.status != decision.decision
    ):
        return None
    if approved:
        from app.services.document_reviews import document_outcomes
        from app.services.payout_rule_serialization import database_clock

        now = now or await database_clock(session)
        outcomes = document_outcomes(decision, decision.document_reviews, now)
        if any(item["status"] == "expired" for item in outcomes.values()):
            return None
        if vehicle:
            from app.services.vehicle_onboarding import _aware_utc, _snapshot_matches

            vehicle_decision = type_cast(VehicleEvidenceReviewDecision, decision)
            if (
                vehicle_decision.valid_until is None
                or _aware_utc(vehicle_decision.valid_until) <= now
                or not _snapshot_matches(
                    type_cast(Vehicle, car), type_cast(VehicleEvidenceSubmission, submission)
                )
            ):
                return None
    title = (
        ("Your car is approved" if approved else "Your car needs changes")
        if vehicle
        else ("Your ID and bank details are approved" if approved else "Your details need changes")
    )
    body = (
        "Your updated car documents have been approved. Open your profile to check them."
        if vehicle and approved and user.status == UserStatus.ACTIVE
        else "Your updated ID and bank details have been approved. Open your profile to check them."
        if approved and user.status == UserStatus.ACTIVE
        else "Terrax Media will email you when your account setup link is ready."
        if vehicle and approved
        else "You can now add your car and its documents."
        if approved
        else applicant_reason(decision.reason_code)
    )
    path = (
        "/driver/profile"
        if user.status == UserStatus.ACTIVE
        else ("/apply?step=car" if vehicle or approved else "/apply?step=details")
    )
    if user.status == UserStatus.INVITED:
        body += " If you need a new link, request one on the application page."
    return {"title": title, "body": body, "action_path": path}


def _current_review_reference(*, vehicle: bool):
    """Restrict candidates to current revisions before resolving time-sensitive copy."""
    decision = VehicleEvidenceReviewDecision if vehicle else DriverKycReviewDecision
    submission = VehicleEvidenceSubmission if vehicle else DriverKycSubmission
    newer_submission = aliased(submission)
    newer_decision = aliased(decision)
    scope_column = "vehicle_id" if vehicle else "driver_profile_id"
    order_column = "sequence" if vehicle else "created_at"
    newer_order = getattr(newer_decision, order_column)
    current_order = getattr(decision, order_column)
    query = select(decision.id).join(submission, submission.id == decision.submission_id)
    if vehicle:
        query = query.join(Vehicle, Vehicle.id == getattr(submission, scope_column)).join(
            DriverProfile, DriverProfile.id == Vehicle.driver_profile_id
        )
    else:
        query = query.join(DriverProfile, DriverProfile.id == getattr(submission, scope_column))
    query = query.where(
        cast(decision.id, String) == Notification.payload["review_decision_id"].as_string(),
        DriverProfile.user_id == Notification.recipient_user_id,
        submission.purged_at.is_(None),
        submission.status == decision.decision,
        ~select(newer_submission.id)
        .where(
            getattr(newer_submission, scope_column) == getattr(submission, scope_column),
            newer_submission.version > submission.version,
        )
        .correlate(submission)
        .exists(),
        ~select(newer_decision.id)
        .where(
            newer_decision.submission_id == submission.id,
            newer_order > current_order
            if vehicle
            else or_(
                newer_order > current_order,
                and_(
                    newer_order == current_order,
                    newer_decision.id > decision.id,
                ),
            ),
        )
        .correlate(submission, decision)
        .exists(),
        or_(
            and_(
                Notification.type_key
                == (
                    NotificationType.DRIVER_CAR_APPROVED
                    if vehicle
                    else NotificationType.DRIVER_ID_APPROVED
                ),
                decision.decision == "approved",
            ),
            and_(
                Notification.type_key
                == (
                    NotificationType.DRIVER_CAR_REJECTED
                    if vehicle
                    else NotificationType.DRIVER_ID_REJECTED
                ),
                decision.decision == "rejected",
            ),
        ),
    )
    return query.correlate(Notification).exists()


async def review_notification_visibility(session: AsyncSession, recipient_user_id: UUID):
    """One filter for feed paging, totals, unread counts and individual commands.

    Only current KYC/per-vehicle candidates are materialized, never generic or
    historical notice pages. Persisted outbox facts remain immutable.
    """
    candidates = list(
        await session.scalars(
            select(Notification).where(
                Notification.recipient_user_id == recipient_user_id,
                Notification.channel == NotificationChannel.IN_APP,
                or_(
                    _current_review_reference(vehicle=False),
                    _current_review_reference(vehicle=True),
                ),
            )
        )
    )
    user = await session.get(User, recipient_user_id) if candidates else None
    from app.services.payout_rule_serialization import database_clock

    now = await database_clock(session) if candidates else None
    visible = []
    for notice in candidates:
        if (
            user is not None
            and await review_notice_context(session, notice, user, now=now) is not None
        ):
            visible.append(notice.id)
    return or_(Notification.type_key.not_in(REVIEW_TYPES), Notification.id.in_(visible))
