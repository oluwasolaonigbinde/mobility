import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.config import Settings
from app.core.errors import AppError
from app.models.campaign_assignment import CampaignAssignment, CampaignAssignmentStatus
from app.models.driver import DriverProfile
from app.models.evidence_verification import (
    EvidenceVerification,
    EvidenceVerificationStatus,
    EvidenceVerificationType,
)
from app.models.installation_evidence import DisplayProof
from app.models.payout import (
    EarningsLedgerEntry,
    EarningsLedgerEntryStatus,
    EarningsLedgerEntryType,
)
from app.models.trip import TripSession, TripSessionStatus
from app.models.trip_analytics import FraudFlag, FraudFlagSeverity, FraudFlagStatus, FraudFlagType
from app.services.audit import create_audit_event
from app.services.fraud_holds import fraud_hold_active_clause, lock_fraud_hold_scope
from app.services.notifications import create_fraud_hold_raised_notice
from app.services.payout_rule_serialization import acquire_campaign_terms_lock, database_clock

LAGOS = ZoneInfo("Africa/Lagos")


@dataclass(frozen=True)
class EvidenceRenewalPolicy:
    threshold_ngn: Decimal
    lookback_days: int
    response_hours: int


@dataclass(frozen=True)
class VerificationSweepResult:
    high_earner_issued: int = 0
    missed_challenges: int = 0
    concurrent_holds: int = 0
    policy_error: str | None = None


def _utc(value: datetime) -> datetime:
    return (value.replace(tzinfo=UTC) if value.tzinfo is None else value).astimezone(UTC)


def _fingerprint(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def parse_evidence_renewal_policy(
    settings: Settings,
) -> tuple[EvidenceRenewalPolicy | None, str | None]:
    raw = settings.evidence_high_earner_threshold_ngn
    if (
        raw is None
        or (isinstance(raw, str) and not raw.strip())
        or settings.evidence_renewal_lookback_days is None
        or settings.evidence_challenge_response_hours is None
    ):
        return None, "missing_configuration"
    try:
        threshold = Decimal(str(raw).strip())
    except (InvalidOperation, ValueError):
        return None, "invalid_configuration"
    if not threshold.is_finite() or threshold <= 0:
        return None, "invalid_configuration"
    return (
        EvidenceRenewalPolicy(
            threshold_ngn=threshold.quantize(Decimal("0.01")),
            lookback_days=settings.evidence_renewal_lookback_days,
            response_hours=settings.evidence_challenge_response_hours,
        ),
        None,
    )


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


async def _expire_due_challenges(
    session: AsyncSession, *, assignment: CampaignAssignment, now: datetime
) -> int:
    rows = list(
        (
            await session.scalars(
                select(EvidenceVerification)
                .where(
                    EvidenceVerification.assignment_id == assignment.id,
                    EvidenceVerification.verification_type
                    == EvidenceVerificationType.HIGH_EARNER_RENEWAL.value,
                    EvidenceVerification.status == EvidenceVerificationStatus.PENDING.value,
                    EvidenceVerification.due_at <= now,
                )
                .order_by(EvidenceVerification.due_at, EvidenceVerification.id)
                .with_for_update()
            )
        ).all()
    )
    for row in rows:
        flag = await _fraud_flag_for_verification(
            session,
            verification=row,
            flag_type=FraudFlagType.MISSED_DISPLAY_CHALLENGE,
            description="A required recurring display-proof challenge was not completed in time.",
            evidence={
                "verification_id": str(row.id),
                "issued_at": _utc(row.issued_at).isoformat(),
                "due_at": _utc(row.due_at).isoformat() if row.due_at else None,
                "proof_scope": "assignment-bound fresh image",
            },
            now=now,
        )
        row.status = EvidenceVerificationStatus.MISSED.value
        row.fraud_flag_id = flag.id
        row.result_note = "Challenge response window elapsed."
        row.resolved_at = now
        await create_audit_event(
            session,
            actor_user_id=None,
            action="evidence_verification.challenge_missed",
            entity_type="evidence_verification",
            entity_id=str(row.id),
            metadata={"fraud_flag_id": str(flag.id), "assignment_id": str(row.assignment_id)},
        )
    await session.flush()
    return len(rows)


async def _issue_high_earner_challenge(
    session: AsyncSession,
    *,
    assignment: CampaignAssignment,
    policy: EvidenceRenewalPolicy,
    now: datetime,
) -> int:
    window_start = now - timedelta(days=policy.lookback_days)
    rows = list(
        (
            await session.scalars(
                select(EarningsLedgerEntry)
                .where(
                    EarningsLedgerEntry.driver_profile_id == assignment.driver_profile_id,
                    EarningsLedgerEntry.campaign_id == assignment.campaign_id,
                    EarningsLedgerEntry.vehicle_id == assignment.vehicle_id,
                    EarningsLedgerEntry.currency == "NGN",
                    EarningsLedgerEntry.trip_session_id.is_not(None),
                    EarningsLedgerEntry.occurred_at >= window_start,
                    EarningsLedgerEntry.occurred_at <= now,
                    EarningsLedgerEntry.status.not_in(
                        (
                            EarningsLedgerEntryStatus.VOIDED.value,
                            EarningsLedgerEntryStatus.REVERSED.value,
                        )
                    ),
                    EarningsLedgerEntry.entry_type.in_(
                        (
                            EarningsLedgerEntryType.TRIP_PAYOUT.value,
                            EarningsLedgerEntryType.ADJUSTMENT.value,
                            EarningsLedgerEntryType.REVERSAL.value,
                        )
                    ),
                )
                .order_by(EarningsLedgerEntry.occurred_at, EarningsLedgerEntry.id)
            )
        ).all()
    )
    if not rows:
        return 0
    observed = sum(
        (-row.amount if row.entry_type == EarningsLedgerEntryType.REVERSAL.value else row.amount)
        for row in rows
    )
    if observed < policy.threshold_ngn:
        return 0
    source = rows[-1]
    if source.trip_session_id is None:
        return 0
    source_trip = await session.get(TripSession, source.trip_session_id)
    if (
        source_trip is None
        or source_trip.assignment_id != assignment.id
        or source_trip.campaign_id != assignment.campaign_id
        or source_trip.driver_profile_id != assignment.driver_profile_id
        or source_trip.vehicle_id != assignment.vehicle_id
    ):
        return 0
    latest_proof = await session.scalar(
        select(DisplayProof)
        .where(DisplayProof.assignment_id == assignment.id)
        .order_by(DisplayProof.verified_at.desc(), DisplayProof.id.desc())
        .limit(1)
    )
    if latest_proof is not None and _utc(latest_proof.verified_at) > _utc(source.occurred_at):
        return 0
    existing = await session.scalar(
        select(EvidenceVerification.id).where(
            EvidenceVerification.verification_type
            == EvidenceVerificationType.HIGH_EARNER_RENEWAL.value,
            EvidenceVerification.source_trip_session_id == source.trip_session_id,
        )
    )
    if existing is not None:
        return 0
    row = EvidenceVerification(
        assignment_id=assignment.id,
        campaign_id=assignment.campaign_id,
        driver_profile_id=assignment.driver_profile_id,
        vehicle_id=assignment.vehicle_id,
        source_trip_session_id=source.trip_session_id,
        verification_type=EvidenceVerificationType.HIGH_EARNER_RENEWAL.value,
        status=EvidenceVerificationStatus.PENDING.value,
        due_at=now + timedelta(hours=policy.response_hours),
        verification_metadata={
            "threshold_ngn": str(policy.threshold_ngn),
            "observed_net_earnings_ngn": str(observed.quantize(Decimal("0.01"))),
            "lookback_started_at": window_start.isoformat(),
            "source_ledger_entry_id": str(source.id),
            "gps_claim": "none",
        },
        issued_at=now,
    )
    session.add(row)
    await session.flush()
    await create_audit_event(
        session,
        actor_user_id=None,
        action="evidence_verification.high_earner_challenge_issued",
        entity_type="evidence_verification",
        entity_id=str(row.id),
        metadata={"assignment_id": str(assignment.id), "due_at": row.due_at.isoformat()},
    )
    return 1


async def _detect_concurrent_sessions(
    session: AsyncSession,
    *,
    assignment: CampaignAssignment,
    lookback_days: int,
    now: datetime,
) -> int:
    window_start = now - timedelta(days=lookback_days)
    source_trips = list(
        (
            await session.scalars(
                select(TripSession).where(
                    TripSession.assignment_id == assignment.id,
                    TripSession.driver_profile_id == assignment.driver_profile_id,
                    TripSession.status.in_(
                        (TripSessionStatus.ENDED.value, TripSessionStatus.SEALED.value)
                    ),
                    TripSession.ended_at.is_not(None),
                    TripSession.started_at >= window_start,
                    TripSession.started_at <= now,
                )
            )
        ).all()
    )
    created = 0
    for source in source_trips:
        if source.ended_at is None:
            continue
        overlap = await session.scalar(
            select(TripSession)
            .where(
                TripSession.id != source.id,
                TripSession.driver_profile_id == source.driver_profile_id,
                TripSession.status.in_(
                    (TripSessionStatus.ENDED.value, TripSessionStatus.SEALED.value)
                ),
                TripSession.ended_at.is_not(None),
                TripSession.started_at < source.ended_at,
                TripSession.ended_at > source.started_at,
            )
            .order_by(TripSession.started_at, TripSession.id)
            .limit(1)
        )
        if overlap is None:
            continue
        if (source.started_at, source.id) < (overlap.started_at, overlap.id):
            continue
        existing = await session.scalar(
            select(EvidenceVerification.id).where(
                EvidenceVerification.verification_type
                == EvidenceVerificationType.CONCURRENT_SESSION.value,
                EvidenceVerification.source_trip_session_id == source.id,
            )
        )
        if existing is not None:
            continue
        row = EvidenceVerification(
            assignment_id=assignment.id,
            campaign_id=assignment.campaign_id,
            driver_profile_id=assignment.driver_profile_id,
            vehicle_id=assignment.vehicle_id,
            source_trip_session_id=source.id,
            verification_type=EvidenceVerificationType.CONCURRENT_SESSION.value,
            status=EvidenceVerificationStatus.PENDING.value,
            result_note="Concurrent session evidence requires staff review.",
            verification_metadata={
                "overlapping_trip_session_id": str(overlap.id),
                "source_started_at": _utc(source.started_at).isoformat(),
                "source_ended_at": _utc(source.ended_at).isoformat(),
                "overlap_started_at": _utc(overlap.started_at).isoformat(),
                "overlap_ended_at": (
                    _utc(overlap.ended_at).isoformat() if overlap.ended_at else None
                ),
                "lagos_day": _utc(source.started_at).astimezone(LAGOS).date().isoformat(),
                "gps_claim": "none",
            },
            issued_at=now,
        )
        session.add(row)
        await session.flush()
        flag = await _fraud_flag_for_verification(
            session,
            verification=row,
            flag_type=FraudFlagType.CONCURRENT_SESSION_DAY,
            description="Overlapping trip sessions for one driver require staff review.",
            evidence={"verification_id": str(row.id), **row.verification_metadata},
            now=now,
        )
        row.fraud_flag_id = flag.id
        row.status = EvidenceVerificationStatus.FAILED.value
        row.resolved_at = now
        await create_audit_event(
            session,
            actor_user_id=None,
            action="evidence_verification.concurrent_session_detected",
            entity_type="evidence_verification",
            entity_id=str(row.id),
            metadata={"fraud_flag_id": str(flag.id), "assignment_id": str(assignment.id)},
        )
        created += 1
    await session.flush()
    return created


async def evaluate_assignment_verification(
    session: AsyncSession,
    *,
    assignment_id: UUID,
    settings: Settings,
    now: datetime | None = None,
) -> VerificationSweepResult:
    assignment = await _locked_assignment(session, assignment_id)
    if assignment is None or assignment.status != CampaignAssignmentStatus.ACTIVE.value:
        return VerificationSweepResult()
    now = _utc(now or await database_clock(session))
    missed = await _expire_due_challenges(session, assignment=assignment, now=now)
    # A two-day technical scan covers the current and immediately completed
    # Lagos day across the UTC boundary. It is not a configurable earnings policy.
    concurrent = await _detect_concurrent_sessions(
        session, assignment=assignment, lookback_days=2, now=now
    )
    policy, error = parse_evidence_renewal_policy(settings)
    if policy is None:
        return VerificationSweepResult(
            missed_challenges=missed,
            concurrent_holds=concurrent,
            policy_error=error,
        )
    issued = await _issue_high_earner_challenge(
        session, assignment=assignment, policy=policy, now=now
    )
    return VerificationSweepResult(
        high_earner_issued=issued,
        missed_challenges=missed,
        concurrent_holds=concurrent,
    )


async def satisfy_pending_evidence_challenges(
    session: AsyncSession,
    *,
    assignment_id: UUID,
    proof: DisplayProof,
    actor_user_id: UUID,
) -> int:
    rows = list(
        (
            await session.scalars(
                select(EvidenceVerification)
                .where(
                    EvidenceVerification.assignment_id == assignment_id,
                    EvidenceVerification.verification_type
                    == EvidenceVerificationType.HIGH_EARNER_RENEWAL.value,
                    EvidenceVerification.status == EvidenceVerificationStatus.PENDING.value,
                    EvidenceVerification.issued_at <= proof.verified_at,
                    EvidenceVerification.due_at > proof.verified_at,
                )
                .order_by(EvidenceVerification.issued_at, EvidenceVerification.id)
                .with_for_update()
            )
        ).all()
    )
    for row in rows:
        row.status = EvidenceVerificationStatus.SATISFIED.value
        row.display_proof_id = proof.id
        row.resolved_at = proof.verified_at
        row.result_note = "Fresh assignment-bound display proof completed."
        await create_audit_event(
            session,
            actor_user_id=actor_user_id,
            action="evidence_verification.challenge_satisfied",
            entity_type="evidence_verification",
            entity_id=str(row.id),
            metadata={"display_proof_id": str(proof.id), "assignment_id": str(assignment_id)},
        )
    await session.flush()
    return len(rows)


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


async def list_driver_pending_verifications(
    session: AsyncSession, *, user_id: UUID
) -> list[EvidenceVerification]:
    return list(
        (
            await session.scalars(
                select(EvidenceVerification)
                .join(DriverProfile, DriverProfile.id == EvidenceVerification.driver_profile_id)
                .where(
                    DriverProfile.user_id == user_id,
                    EvidenceVerification.status == EvidenceVerificationStatus.PENDING.value,
                    EvidenceVerification.verification_type
                    == EvidenceVerificationType.HIGH_EARNER_RENEWAL.value,
                )
                .order_by(EvidenceVerification.issued_at, EvidenceVerification.id)
                .limit(100)
            )
        ).all()
    )


async def list_admin_verifications(
    session: AsyncSession, *, verification_status: str | None = None
) -> list[EvidenceVerification]:
    query = select(EvidenceVerification)
    if verification_status is not None:
        query = query.where(EvidenceVerification.status == verification_status)
    return list(
        (
            await session.scalars(
                query.order_by(EvidenceVerification.issued_at.desc()).limit(100)
            )
        ).all()
    )
