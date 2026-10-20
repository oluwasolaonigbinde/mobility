import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.errors import AppError
from app.models.campaign_assignment import CampaignAssignment
from app.models.driver import DriverProfile
from app.models.evidence_verification import (
    EvidenceVerification,
    EvidenceVerificationStatus,
    EvidenceVerificationType,
)
from app.models.trip import TripSession
from app.models.trip_analytics import FraudFlag, FraudFlagSeverity, FraudFlagStatus, FraudFlagType
from app.services.audit import create_audit_event
from app.services.fraud_holds import fraud_hold_active_clause, lock_fraud_hold_scope
from app.services.notifications import create_fraud_hold_raised_notice
from app.services.payout_rule_serialization import acquire_campaign_terms_lock, database_clock


def _utc(value: datetime) -> datetime:
    return (value.replace(tzinfo=UTC) if value.tzinfo is None else value).astimezone(UTC)


def _fingerprint(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


async def _locked_assignment(
    session: AsyncSession, assignment_id: UUID
) -> CampaignAssignment | None:
    campaign_id = await session.scalar(
        select(CampaignAssignment.campaign_id).where(CampaignAssignment.id == assignment_id)
    )
    if campaign_id is None:
        return None
    await acquire_campaign_terms_lock(session, campaign_id)
    assignment = await session.scalar(
        select(CampaignAssignment).where(CampaignAssignment.id == assignment_id).with_for_update()
    )
    if assignment is not None:
        await session.execute(
            select(DriverProfile.id)
            .where(DriverProfile.id == assignment.driver_profile_id)
            .with_for_update()
        )
    return assignment


async def _fraud_flag_for_verification(
    session: AsyncSession,
    *,
    verification: EvidenceVerification,
    flag_type: FraudFlagType,
    description: str,
    evidence: dict,
    now: datetime,
) -> FraudFlag:
    await lock_fraud_hold_scope(session, verification.source_trip_session_id)
    existing = await session.scalar(
        select(FraudFlag).where(
            FraudFlag.trip_session_id == verification.source_trip_session_id,
            FraudFlag.flag_type == flag_type.value,
            fraud_hold_active_clause(),
        )
    )
    if existing is not None:
        return existing
    trip = await session.get(TripSession, verification.source_trip_session_id)
    if trip is None:
        raise RuntimeError("verification source trip disappeared")
    flag = FraudFlag(
        trip_session_id=trip.id,
        trip_analytics_id=None,
        assignment_id=trip.assignment_id,
        campaign_id=trip.campaign_id,
        driver_profile_id=trip.driver_profile_id,
        vehicle_id=trip.vehicle_id,
        flag_type=flag_type.value,
        severity=FraudFlagSeverity.HIGH.value,
        status=FraudFlagStatus.OPEN.value,
        description=description,
        evidence=evidence,
        detected_at=now,
    )
    session.add(flag)
    await session.flush()
    await create_fraud_hold_raised_notice(session, flag)
    return flag


def _not_found() -> AppError:
    return AppError(
        "EVIDENCE_VERIFICATION_NOT_FOUND",
        "Evidence verification was not found",
        status_code=status.HTTP_404_NOT_FOUND,
    )


async def queue_physical_spot_check(
    session: AsyncSession,
    *,
    actor_user_id: UUID,
    assignment_id: UUID,
    trip_session_id: UUID,
    client_request_id: UUID,
    note: str,
    metadata: dict,
    now: datetime | None = None,
) -> EvidenceVerification:
    payload = {
        "assignment_id": str(assignment_id),
        "trip_session_id": str(trip_session_id),
        "note": note.strip(),
        "metadata": metadata,
    }
    fingerprint = _fingerprint(payload)
    request_filter = (
        EvidenceVerification.issued_by_user_id == actor_user_id,
        EvidenceVerification.client_request_id == client_request_id,
    )
    existing = await session.scalar(
        select(EvidenceVerification).where(
            *request_filter,
        )
    )
    if existing is not None:
        if existing.request_fingerprint != fingerprint:
            raise AppError(
                "EVIDENCE_VERIFICATION_REPLAY_CONFLICT",
                "The spot-check retry does not match the original request",
                status_code=status.HTTP_409_CONFLICT,
            )
        return existing
    assignment = await _locked_assignment(session, assignment_id)
    if assignment is None:
        raise _not_found()
    existing = await session.scalar(select(EvidenceVerification).where(*request_filter))
    if existing is not None:
        if existing.request_fingerprint != fingerprint:
            raise AppError(
                "EVIDENCE_VERIFICATION_REPLAY_CONFLICT",
                "The spot-check retry does not match the original request",
                status_code=status.HTTP_409_CONFLICT,
            )
        return existing
    trip = await session.get(TripSession, trip_session_id)
    if (
        trip is None
        or trip.assignment_id != assignment.id
        or trip.campaign_id != assignment.campaign_id
        or trip.driver_profile_id != assignment.driver_profile_id
        or trip.vehicle_id != assignment.vehicle_id
    ):
        raise _not_found()
    issued_at = _utc(now or await database_clock(session))
    row = EvidenceVerification(
        assignment_id=assignment.id,
        campaign_id=assignment.campaign_id,
        driver_profile_id=assignment.driver_profile_id,
        vehicle_id=assignment.vehicle_id,
        source_trip_session_id=trip.id,
        verification_type=EvidenceVerificationType.PHYSICAL_SPOT_CHECK.value,
        status=EvidenceVerificationStatus.PENDING.value,
        issued_by_user_id=actor_user_id,
        client_request_id=client_request_id,
        request_fingerprint=fingerprint,
        result_note=note.strip(),
        verification_metadata={**metadata, "gps_claim": "none"},
        issued_at=issued_at,
    )
    session.add(row)
    await session.flush()
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="evidence_verification.spot_check_queued",
        entity_type="evidence_verification",
        entity_id=str(row.id),
        metadata={"assignment_id": str(assignment.id), "trip_session_id": str(trip.id)},
    )
    return row


async def resolve_physical_spot_check(
    session: AsyncSession,
    *,
    verification_id: UUID,
    actor_user_id: UUID,
    outcome: str,
    note: str,
    evidence: dict,
    now: datetime | None = None,
) -> EvidenceVerification:
    if outcome not in {"passed", "failed"}:
        raise AppError(
            "EVIDENCE_VERIFICATION_OUTCOME_INVALID",
            "Spot-check outcome must be passed or failed",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    result_fingerprint = _fingerprint(
        {
            "actor_user_id": str(actor_user_id),
            "outcome": outcome,
            "note": note.strip(),
            "evidence": evidence,
        }
    )
    campaign_id = await session.scalar(
        select(EvidenceVerification.campaign_id).where(EvidenceVerification.id == verification_id)
    )
    if campaign_id is None:
        raise _not_found()
    await acquire_campaign_terms_lock(session, campaign_id)
    row = await session.scalar(
        select(EvidenceVerification)
        .where(EvidenceVerification.id == verification_id)
        .with_for_update()
    )
    if row is None or row.verification_type != EvidenceVerificationType.PHYSICAL_SPOT_CHECK.value:
        raise _not_found()
    if row.status != EvidenceVerificationStatus.PENDING.value:
        if row.status == outcome and row.result_fingerprint == result_fingerprint:
            return row
        raise AppError(
            "EVIDENCE_VERIFICATION_REPLAY_CONFLICT",
            "The completed spot check does not match this retry",
            status_code=status.HTTP_409_CONFLICT,
        )
    resolved_at = _utc(now or await database_clock(session))
    flag = None
    if outcome == EvidenceVerificationStatus.FAILED.value:
        flag = await _fraud_flag_for_verification(
            session,
            verification=row,
            flag_type=FraudFlagType.PHYSICAL_SPOT_CHECK_FAILED,
            description="A physical display spot check failed and requires staff review.",
            evidence={"verification_id": str(row.id), "result": evidence, "gps_claim": "none"},
            now=resolved_at,
        )
    row.status = outcome
    row.resolved_by_user_id = actor_user_id
    row.resolved_at = resolved_at
    row.result_note = note.strip()
    row.result_fingerprint = result_fingerprint
    row.verification_metadata = {**row.verification_metadata, "result": evidence}
    row.fraud_flag_id = flag.id if flag is not None else None
    await session.flush()
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="evidence_verification.spot_check_resolved",
        entity_type="evidence_verification",
        entity_id=str(row.id),
        metadata={"outcome": outcome, "fraud_flag_id": str(flag.id) if flag else None},
    )
    return row


async def list_admin_verifications(
    session: AsyncSession,
    *,
    verification_status: str | None = None,
    verification_type: str | None = None,
    limit: int = 100,
    offset: int = 0,
    oldest_first: bool = False,
    verification_id: UUID | None = None,
    driver_profile_id: UUID | None = None,
    campaign_id: UUID | None = None,
    trip_session_id: UUID | None = None,
) -> tuple[list[EvidenceVerification], int]:
    query = select(EvidenceVerification)
    if verification_status is not None:
        query = query.where(EvidenceVerification.status == verification_status)
    if verification_type is not None:
        query = query.where(EvidenceVerification.verification_type == verification_type)
    for field, value in (
        (EvidenceVerification.id, verification_id),
        (EvidenceVerification.driver_profile_id, driver_profile_id),
        (EvidenceVerification.campaign_id, campaign_id),
        (EvidenceVerification.source_trip_session_id, trip_session_id),
    ):
        if value is not None:
            query = query.where(field == value)
    total = int(await session.scalar(select(func.count()).select_from(query.subquery())) or 0)
    rows = list(
        (
            await session.scalars(
                query.order_by(
                    EvidenceVerification.issued_at.asc()
                    if oldest_first
                    else EvidenceVerification.issued_at.desc(),
                    EvidenceVerification.id.desc(),
                )
                .limit(limit)
                .offset(offset)
            )
        ).all()
    )
    return rows, total
