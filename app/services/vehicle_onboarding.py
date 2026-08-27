import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from starlette import status

from app.core.errors import AppError
from app.models.audit import AuditEvent
from app.models.driver import DriverOnboardingStatus, DriverProfile
from app.models.driver_application import DriverApplication
from app.models.kyc import (
    DriverKycReviewDecision,
    DriverKycSubmission,
    KycSubmissionStatus,
    VehicleEvidenceDocument,
    VehicleEvidenceDocumentType,
    VehicleEvidenceReviewDecision,
    VehicleEvidenceSubmission,
    VehicleReviewReason,
)
from app.models.payee import PayeeBankAccountPayoutVerification
from app.models.stored_file import FilePurpose
from app.models.vehicle import Vehicle, VehicleStatus, VehicleType
from app.schemas.driver_onboarding import (
    ApplicantVehicleSubmissionCreate,
    VehicleReviewDecisionCreate,
)
from app.services.admin_authorization import require_active_admin
from app.services.audit import create_audit_event
from app.services.driver_applications import application_from_access_token
from app.services.driver_onboarding import application_from_reference
from app.services.kyc import _require_files
from app.services.payout_rule_serialization import database_clock
from app.services.vehicles import ensure_unique_plate, normalize_plate_number


@dataclass(frozen=True, slots=True)
class VehicleStageView:
    vehicle: Vehicle | None
    submission: VehicleEvidenceSubmission | None
    decision: VehicleEvidenceReviewDecision | None
    document_file_ids: dict[str, UUID]


def _error(code: str, message: str, status_code: int) -> AppError:
    return AppError(code, message, status_code=status_code)


def _aware_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _lock_key(identifier: UUID) -> int:
    return int.from_bytes(
        hashlib.sha256(f"driver-vehicle-eligibility-v1:{identifier}".encode()).digest()[:8],
        signed=True,
    )


async def acquire_work_eligibility_lock(
    session: AsyncSession, *, driver_profile_id: UUID, vehicle_id: UUID | None = None
) -> None:
    """Serialize every public-applicant eligibility producer before row locks.

    Campaign-scoped callers acquire campaign authority first, then this common
    profile/vehicle advisory suffix before assignment or evidence row locks.
    """

    if session.get_bind().dialect.name != "postgresql":
        return
    identifiers = {driver_profile_id}
    if vehicle_id is not None:
        identifiers.add(vehicle_id)
    for identifier in sorted(identifiers, key=str):
        await session.execute(
            text("SELECT pg_advisory_xact_lock(:lock_id)"),
            {"lock_id": _lock_key(identifier)},
        )


async def _documents(session: AsyncSession, submission_id: UUID) -> dict[str, UUID]:
    rows = list(
        (
            await session.scalars(
                select(VehicleEvidenceDocument).where(
                    VehicleEvidenceDocument.submission_id == submission_id
                )
            )
        ).all()
    )
    return {row.document_type: row.stored_file_id for row in rows}


async def _latest_decision(
    session: AsyncSession, submission_id: UUID, *, lock: bool
) -> VehicleEvidenceReviewDecision | None:
    query = (
        select(VehicleEvidenceReviewDecision)
        .where(VehicleEvidenceReviewDecision.submission_id == submission_id)
        .order_by(VehicleEvidenceReviewDecision.sequence.desc())
        .limit(1)
    )
    if lock:
        query = query.with_for_update()
    return await session.scalar(query)


async def _latest_submission(
    session: AsyncSession, vehicle_id: UUID, *, lock: bool
) -> VehicleEvidenceSubmission | None:
    query = (
        select(VehicleEvidenceSubmission)
        .where(VehicleEvidenceSubmission.vehicle_id == vehicle_id)
        .order_by(VehicleEvidenceSubmission.version.desc())
        .limit(1)
    )
    if lock:
        query = query.with_for_update()
    return await session.scalar(query)


def _snapshot_matches(vehicle: Vehicle, submission: VehicleEvidenceSubmission) -> bool:
    return (
        submission.snapshot_trusted
        and submission.plate_number_snapshot == vehicle.plate_number
        and submission.plate_number_normalized_snapshot == vehicle.plate_number_normalized
        and submission.plate_country_code_snapshot == vehicle.plate_country_code
        and submission.vehicle_type_snapshot == vehicle.vehicle_type
        and submission.make_snapshot == vehicle.make
        and submission.model_snapshot == vehicle.model
        and submission.year_snapshot == vehicle.year
        and submission.color_snapshot == vehicle.color
    )


async def _current_person_payee_approved(
    session: AsyncSession, *, driver_profile_id: UUID, lock: bool
) -> bool:
    query = (
        select(DriverKycSubmission)
        .where(DriverKycSubmission.driver_profile_id == driver_profile_id)
        .order_by(DriverKycSubmission.version.desc())
        .limit(1)
    )
    if lock:
        query = query.with_for_update()
    submission = await session.scalar(query)
    if submission is None or submission.status != KycSubmissionStatus.APPROVED.value:
        return False
    decision = await session.scalar(
        select(DriverKycReviewDecision).where(
            DriverKycReviewDecision.submission_id == submission.id,
            DriverKycReviewDecision.decision == KycSubmissionStatus.APPROVED.value,
        )
    )
    verification = await session.scalar(
        select(PayeeBankAccountPayoutVerification.id).where(
            PayeeBankAccountPayoutVerification.bank_account_version_id
            == submission.bank_account_version_id
        )
    )
    return decision is not None and verification is not None


async def _vehicle_approved(
    session: AsyncSession, *, vehicle: Vehicle, now: datetime, lock: bool
) -> tuple[bool, VehicleEvidenceSubmission | None, VehicleEvidenceReviewDecision | None]:
    submission = await _latest_submission(session, vehicle.id, lock=lock)
    if submission is None or not _snapshot_matches(vehicle, submission):
        return False, submission, None
    decision = await _latest_decision(session, submission.id, lock=lock)
    approved = bool(
        submission.status == KycSubmissionStatus.APPROVED.value
        and decision is not None
        and decision.decision == KycSubmissionStatus.APPROVED.value
        and decision.valid_until is not None
        and decision.valid_until > now
        and vehicle.vehicle_type == VehicleType.CAR.value
    )
    return approved, submission, decision


async def reconcile_driver_work_eligibility(
    session: AsyncSession, *, driver_profile_id: UUID, now: datetime | None = None
) -> bool:
    """Project current applicant approvals into the existing work-gate statuses."""

    application_id = await session.scalar(
        select(DriverApplication.id).where(DriverApplication.driver_profile_id == driver_profile_id)
    )
    if application_id is None:
        return False
    await acquire_work_eligibility_lock(session, driver_profile_id=driver_profile_id)
    profile = await session.scalar(
        select(DriverProfile).where(DriverProfile.id == driver_profile_id).with_for_update()
    )
    if profile is None:
        raise RuntimeError("Driver profile authority disappeared")
    now = now or await database_clock(session)
    person_approved = await _current_person_payee_approved(
        session, driver_profile_id=profile.id, lock=True
    )
    vehicles = list(
        (
            await session.scalars(
                select(Vehicle)
                .where(Vehicle.driver_profile_id == profile.id)
                .order_by(Vehicle.id)
                .with_for_update()
            )
        ).all()
    )
    has_active_vehicle = False
    for vehicle in vehicles:
        approved, _, _ = await _vehicle_approved(session, vehicle=vehicle, now=now, lock=True)
        if vehicle.status not in {VehicleStatus.SUSPENDED.value, VehicleStatus.INACTIVE.value}:
            vehicle.status = VehicleStatus.ACTIVE.value if approved else VehicleStatus.PENDING.value
        has_active_vehicle = has_active_vehicle or (
            approved and vehicle.status == VehicleStatus.ACTIVE.value
        )
    eligible = person_approved and has_active_vehicle
    if profile.onboarding_status not in {
        DriverOnboardingStatus.SUSPENDED.value,
        DriverOnboardingStatus.REJECTED.value,
    }:
        profile.onboarding_status = (
            DriverOnboardingStatus.ACTIVE.value
            if eligible
            else DriverOnboardingStatus.PENDING.value
        )
    await session.flush()
    return eligible and profile.onboarding_status == DriverOnboardingStatus.ACTIVE.value


async def ensure_current_driver_vehicle_eligibility(
    session: AsyncSession,
    *,
    driver_profile: DriverProfile,
    vehicle: Vehicle,
    now: datetime,
    lock: bool,
) -> None:
    """Fail closed for public applicants; preserve pre-existing operator flow."""

    application_id = await session.scalar(
        select(DriverApplication.id).where(DriverApplication.driver_profile_id == driver_profile.id)
    )
    if application_id is None:
        return
    if not await _current_person_payee_approved(
        session, driver_profile_id=driver_profile.id, lock=lock
    ):
        raise _error(
            "DRIVER_PERSON_PAYEE_NOT_APPROVED",
            "Current person and payee approval is required for work",
            status.HTTP_409_CONFLICT,
        )
    approved, _, _ = await _vehicle_approved(session, vehicle=vehicle, now=now, lock=lock)
    if not approved or vehicle.status != VehicleStatus.ACTIVE.value:
        raise _error(
            "VEHICLE_APPROVAL_REQUIRED",
            "A current approved active owned car is required for work",
            status.HTTP_409_CONFLICT,
        )


def _submission_facts(
    *, payload: ApplicantVehicleSubmissionCreate, documents: dict[str, UUID]
) -> dict[str, object]:
    return {
        "vehicle_id": str(payload.vehicle_id) if payload.vehicle_id else None,
        "plate_number": payload.plate_number.strip(),
        "plate_country_code": payload.plate_country_code.strip().upper(),
        "vehicle_type": payload.vehicle_type.value,
        "make": payload.make.strip() if payload.make else None,
        "model": payload.model.strip() if payload.model else None,
        "year": payload.year,
        "color": payload.color.strip() if payload.color else None,
        "documents": {key: str(value) for key, value in sorted(documents.items())},
    }


def _submission_matches(
    submission: VehicleEvidenceSubmission,
    documents: dict[str, UUID],
    facts: dict[str, object],
) -> bool:
    return (
        (facts["vehicle_id"] is None or facts["vehicle_id"] == str(submission.vehicle_id))
        and facts["plate_number"] == submission.plate_number_snapshot
        and facts["plate_country_code"] == submission.plate_country_code_snapshot
        and facts["vehicle_type"] == submission.vehicle_type_snapshot
        and facts["make"] == submission.make_snapshot
        and facts["model"] == submission.model_snapshot
        and facts["year"] == submission.year_snapshot
        and facts["color"] == submission.color_snapshot
        and documents == facts["documents"]
    )


async def submit_application_vehicle(
    session: AsyncSession,
    *,
    payload: ApplicantVehicleSubmissionCreate,
    settings,
) -> VehicleStageView:
    application = await application_from_access_token(
        session,
        token=payload.application_access_token.get_secret_value(),
        settings=settings,
        lock=True,
    )
    await acquire_work_eligibility_lock(
        session,
        driver_profile_id=application.driver_profile_id,
        vehicle_id=payload.vehicle_id,
    )
    profile = await session.scalar(
        select(DriverProfile)
        .where(DriverProfile.id == application.driver_profile_id)
        .with_for_update()
    )
    if profile is None or profile.user_id != application.user_id:
        raise _error(
            "VEHICLE_ONBOARDING_AUTHORITY_INVALID",
            "Vehicle onboarding authority is unavailable",
            status.HTTP_409_CONFLICT,
        )
    if not await _current_person_payee_approved(session, driver_profile_id=profile.id, lock=True):
        raise _error(
            "PERSON_PAYEE_APPROVAL_REQUIRED",
            "Person and payee approval is required before vehicle onboarding",
            status.HTTP_409_CONFLICT,
        )
    documents = {
        VehicleEvidenceDocumentType.REGISTRATION.value: payload.registration_file_id,
        VehicleEvidenceDocumentType.INSURANCE.value: payload.insurance_file_id,
        VehicleEvidenceDocumentType.VEHICLE_PHOTO.value: payload.vehicle_photo_file_id,
    }
    facts = _submission_facts(payload=payload, documents=documents)
    existing = await session.scalar(
        select(VehicleEvidenceSubmission).where(
            VehicleEvidenceSubmission.created_by_user_id == application.user_id,
            VehicleEvidenceSubmission.client_request_id == payload.client_request_id,
        )
    )
    if existing is not None:
        existing_documents = await _documents(session, existing.id)
        rendered_documents = {key: str(value) for key, value in existing_documents.items()}
        if not _submission_matches(existing, rendered_documents, facts):
            raise _error(
                "VEHICLE_SUBMISSION_RETRY_CONFLICT",
                "The vehicle retry does not match the original request",
                status.HTTP_409_CONFLICT,
            )
        vehicle = await session.get(Vehicle, existing.vehicle_id)
        return VehicleStageView(
            vehicle,
            existing,
            await _latest_decision(session, existing.id, lock=False),
            existing_documents,
        )
    await _require_files(
        session,
        file_ids=documents,
        actor_user_id=application.user_id,
        purpose=FilePurpose.VEHICLE_EVIDENCE,
    )
    if payload.vehicle_id is None:
        normalized_plate = normalize_plate_number(payload.plate_number)
        country_code = payload.plate_country_code.strip().upper()
        await ensure_unique_plate(
            session,
            plate_country_code=country_code,
            plate_number_normalized=normalized_plate,
        )
        vehicle = Vehicle(
            id=uuid4(),
            driver_profile_id=profile.id,
            plate_number=payload.plate_number.strip(),
            plate_number_normalized=normalized_plate,
            plate_country_code=country_code,
            vehicle_type=payload.vehicle_type.value,
            make=payload.make.strip() if payload.make else None,
            model=payload.model.strip() if payload.model else None,
            year=payload.year,
            color=payload.color.strip() if payload.color else None,
            status=VehicleStatus.PENDING.value,
            vehicle_metadata={},
        )
        session.add(vehicle)
        await session.flush()
    else:
        vehicle = await session.scalar(
            select(Vehicle)
            .where(
                Vehicle.id == payload.vehicle_id,
                Vehicle.driver_profile_id == profile.id,
            )
            .with_for_update()
        )
        if vehicle is None:
            raise _error("VEHICLE_NOT_FOUND", "Vehicle was not found", status.HTTP_404_NOT_FOUND)
        current = await _latest_submission(session, vehicle.id, lock=True)
        if current is not None and current.status == KycSubmissionStatus.PENDING_REVIEW.value:
            raise _error(
                "VEHICLE_REVIEW_PENDING",
                "The current vehicle revision is already pending review",
                status.HTTP_409_CONFLICT,
            )
        normalized_plate = normalize_plate_number(payload.plate_number)
        country_code = payload.plate_country_code.strip().upper()
        await ensure_unique_plate(
            session,
            plate_country_code=country_code,
            plate_number_normalized=normalized_plate,
            exclude_vehicle_id=vehicle.id,
        )
        vehicle.plate_number = payload.plate_number.strip()
        vehicle.plate_number_normalized = normalized_plate
        vehicle.plate_country_code = country_code
        vehicle.vehicle_type = payload.vehicle_type.value
        vehicle.make = payload.make.strip() if payload.make else None
        vehicle.model = payload.model.strip() if payload.model else None
        vehicle.year = payload.year
        vehicle.color = payload.color.strip() if payload.color else None
        if vehicle.status == VehicleStatus.ACTIVE.value:
            vehicle.status = VehicleStatus.PENDING.value
    current_version = await session.scalar(
        select(func.max(VehicleEvidenceSubmission.version)).where(
            VehicleEvidenceSubmission.vehicle_id == vehicle.id
        )
    )
    submission = VehicleEvidenceSubmission(
        id=uuid4(),
        vehicle_id=vehicle.id,
        version=int(current_version or 0) + 1,
        client_request_id=payload.client_request_id,
        status=KycSubmissionStatus.PENDING_REVIEW.value,
        snapshot_trusted=True,
        plate_number_snapshot=vehicle.plate_number,
        plate_number_normalized_snapshot=vehicle.plate_number_normalized,
        plate_country_code_snapshot=vehicle.plate_country_code,
        vehicle_type_snapshot=vehicle.vehicle_type,
        make_snapshot=vehicle.make,
        model_snapshot=vehicle.model,
        year_snapshot=vehicle.year,
        color_snapshot=vehicle.color,
        created_by_user_id=application.user_id,
    )
    session.add(submission)
    await session.flush()
    session.add_all(
        VehicleEvidenceDocument(
            submission_id=submission.id,
            document_type=document_type,
            stored_file_id=file_id,
        )
        for document_type, file_id in documents.items()
    )
    await reconcile_driver_work_eligibility(
        session, driver_profile_id=profile.id, now=await database_clock(session)
    )
    await create_audit_event(
        session,
        actor_user_id=application.user_id,
        action="driver.vehicle_profile.submitted",
        entity_type="vehicle_evidence_submission",
        entity_id=str(submission.id),
        metadata={"vehicle_id": str(vehicle.id), "version": submission.version},
    )
    return VehicleStageView(vehicle, submission, None, documents)


async def application_vehicle_view(
    session: AsyncSession, *, application: DriverApplication
) -> VehicleStageView:
    vehicle = await session.scalar(
        select(Vehicle)
        .where(Vehicle.driver_profile_id == application.driver_profile_id)
        .order_by(Vehicle.updated_at.desc(), Vehicle.id)
        .limit(1)
    )
    if vehicle is None:
        return VehicleStageView(None, None, None, {})
    submission = await _latest_submission(session, vehicle.id, lock=False)
    if submission is None:
        return VehicleStageView(vehicle, None, None, {})
    decision = await _latest_decision(session, submission.id, lock=False)
    return VehicleStageView(vehicle, submission, decision, await _documents(session, submission.id))


async def vehicle_status_by_reference(session: AsyncSession, *, reference: str) -> VehicleStageView:
    try:
        application = await application_from_reference(session, reference=reference, lock=False)
    except AppError:
        return VehicleStageView(None, None, None, {})
    return await application_vehicle_view(session, application=application)


def _decision_fingerprint(
    *, application_id: UUID, submission_id: UUID, payload: VehicleReviewDecisionCreate
) -> str:
    document = {
        "application_id": str(application_id),
        "submission_id": str(submission_id),
        **payload.model_dump(mode="json"),
    }
    return hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _validate_decision(payload: VehicleReviewDecisionCreate, *, now: datetime) -> None:
    confirmations = (
        payload.owner_match_confirmed,
        payload.vehicle_identity_confirmed,
        payload.roadworthy_confirmed,
        payload.pilot_car_confirmed,
        payload.documents_readable_confirmed,
    )
    if payload.decision == KycSubmissionStatus.APPROVED:
        if (
            payload.reason_code != VehicleReviewReason.COMPLETE_CURRENT_EVIDENCE
            or not all(confirmations)
            or payload.valid_until is None
            or payload.valid_until <= now
        ):
            raise _error(
                "VEHICLE_APPROVAL_FACTS_REQUIRED",
                "Approval requires complete current vehicle facts and future validity",
                status.HTTP_409_CONFLICT,
            )
    elif payload.reason_code == VehicleReviewReason.COMPLETE_CURRENT_EVIDENCE:
        raise _error(
            "VEHICLE_DECISION_REASON_INVALID",
            "A terminal vehicle evidence reason is required",
            status.HTTP_409_CONFLICT,
        )


async def _require_review_reads(
    session: AsyncSession,
    *,
    submission: VehicleEvidenceSubmission,
    actor_user_id: UUID,
    document_file_ids: dict[str, UUID],
) -> None:
    events = list(
        (
            await session.scalars(
                select(AuditEvent).where(
                    AuditEvent.actor_user_id == actor_user_id,
                    AuditEvent.action == "stored_file.read",
                )
            )
        ).all()
    )
    reviewed = {
        UUID(event.entity_id)
        for event in events
        if event.entity_id is not None
        and event.event_metadata.get("file_purpose") == FilePurpose.VEHICLE_EVIDENCE.value
        and event.event_metadata.get("access_purpose") == "kyc_review"
        and event.event_metadata.get("reason") == f"vehicle_approval:{submission.id}"
    }
    if not set(document_file_ids.values()).issubset(reviewed):
        raise _error(
            "VEHICLE_REVIEW_EVIDENCE_INCOMPLETE",
            "Approval requires audited reads of every exact current vehicle document",
            status.HTTP_409_CONFLICT,
        )


async def _decision_retry_view(
    session: AsyncSession,
    *,
    submission_id: UUID,
    client_request_id: UUID,
    fingerprint: str,
) -> VehicleStageView | None:
    retry = await session.scalar(
        select(VehicleEvidenceReviewDecision).where(
            VehicleEvidenceReviewDecision.client_request_id == client_request_id
        )
    )
    if retry is None:
        return None
    original = await session.get(VehicleEvidenceSubmission, retry.submission_id)
    if original is None or original.id != submission_id or retry.request_fingerprint != fingerprint:
        raise _error(
            "VEHICLE_DECISION_RETRY_CONFLICT",
            "The vehicle decision retry does not match the original request",
            status.HTTP_409_CONFLICT,
        )
    vehicle = await session.get(Vehicle, original.vehicle_id)
    return VehicleStageView(vehicle, original, retry, await _documents(session, original.id))


async def review_application_vehicle(
    session: AsyncSession,
    *,
    application_id: UUID,
    vehicle_id: UUID,
    submission_id: UUID,
    actor_user_id: UUID,
    payload: VehicleReviewDecisionCreate,
) -> VehicleStageView:
    await require_active_admin(session, actor_user_id)
    now = await database_clock(session)
    fingerprint = _decision_fingerprint(
        application_id=application_id, submission_id=submission_id, payload=payload
    )
    retry_view = await _decision_retry_view(
        session,
        submission_id=submission_id,
        client_request_id=payload.client_request_id,
        fingerprint=fingerprint,
    )
    if retry_view is not None:
        return retry_view
    _validate_decision(payload, now=now)
    application = await session.scalar(
        select(DriverApplication).where(DriverApplication.id == application_id).with_for_update()
    )
    if application is None:
        raise _error(
            "DRIVER_APPLICATION_NOT_FOUND",
            "Driver application was not found",
            status.HTTP_404_NOT_FOUND,
        )
    await acquire_work_eligibility_lock(
        session, driver_profile_id=application.driver_profile_id, vehicle_id=vehicle_id
    )
    profile = await session.scalar(
        select(DriverProfile)
        .where(DriverProfile.id == application.driver_profile_id)
        .with_for_update()
    )
    vehicle = await session.scalar(
        select(Vehicle)
        .where(Vehicle.id == vehicle_id, Vehicle.driver_profile_id == application.driver_profile_id)
        .with_for_update()
    )
    submission = await session.scalar(
        select(VehicleEvidenceSubmission)
        .where(
            VehicleEvidenceSubmission.id == submission_id,
            VehicleEvidenceSubmission.vehicle_id == vehicle_id,
        )
        .with_for_update()
    )
    if profile is None or vehicle is None or submission is None:
        raise _error("VEHICLE_NOT_FOUND", "Vehicle was not found", status.HTTP_404_NOT_FOUND)
    current = await _latest_submission(session, vehicle.id, lock=True)
    if current is None or current.id != submission.id:
        raise _error(
            "VEHICLE_REVISION_STALE",
            "Only the current vehicle revision can be reviewed",
            status.HTTP_409_CONFLICT,
        )
    previous = await _latest_decision(session, submission.id, lock=True)
    retry_view = await _decision_retry_view(
        session,
        submission_id=submission_id,
        client_request_id=payload.client_request_id,
        fingerprint=fingerprint,
    )
    if retry_view is not None:
        return retry_view
    if previous is None:
        if submission.status != KycSubmissionStatus.PENDING_REVIEW.value:
            raise _error(
                "VEHICLE_LEGACY_REVISION_UNTRUSTED",
                "Legacy vehicle evidence requires a fresh revision",
                status.HTTP_409_CONFLICT,
            )
        sequence = 1
    elif (
        previous.decision == KycSubmissionStatus.APPROVED.value
        and payload.decision == KycSubmissionStatus.EXPIRED
    ):
        sequence = previous.sequence + 1
    else:
        raise _error(
            "VEHICLE_ALREADY_DECIDED",
            "The current vehicle revision already has a terminal decision",
            status.HTTP_409_CONFLICT,
        )
    documents = await _documents(session, submission.id)
    if payload.decision == KycSubmissionStatus.APPROVED:
        if vehicle.vehicle_type != VehicleType.CAR.value or not _snapshot_matches(
            vehicle, submission
        ):
            raise _error(
                "VEHICLE_CURRENT_EVIDENCE_MISMATCH",
                "Approval requires the current owned pilot car revision",
                status.HTTP_409_CONFLICT,
            )
        await _require_files(
            session,
            file_ids=documents,
            actor_user_id=profile.user_id,
            purpose=FilePurpose.VEHICLE_EVIDENCE,
        )
        await _require_review_reads(
            session,
            submission=submission,
            actor_user_id=actor_user_id,
            document_file_ids=documents,
        )
    decision = VehicleEvidenceReviewDecision(
        submission_id=submission.id,
        sequence=sequence,
        client_request_id=payload.client_request_id,
        request_fingerprint=fingerprint,
        decision=payload.decision.value,
        reason_code=payload.reason_code.value,
        owner_match_confirmed=payload.owner_match_confirmed,
        vehicle_identity_confirmed=payload.vehicle_identity_confirmed,
        roadworthy_confirmed=payload.roadworthy_confirmed,
        pilot_car_confirmed=payload.pilot_car_confirmed,
        documents_readable_confirmed=payload.documents_readable_confirmed,
        valid_until=payload.valid_until,
        decided_by_user_id=actor_user_id,
    )
    session.add(decision)
    submission.status = payload.decision.value
    await session.flush()
    await reconcile_driver_work_eligibility(session, driver_profile_id=profile.id, now=now)
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action=f"admin.driver_vehicle.{payload.decision.value}",
        entity_type="vehicle_evidence_submission",
        entity_id=str(submission.id),
        metadata={
            "application_id": str(application.id),
            "vehicle_id": str(vehicle.id),
            "version": submission.version,
            "sequence": sequence,
            "reason_code": payload.reason_code.value,
            "valid_until": payload.valid_until.isoformat() if payload.valid_until else None,
        },
    )
    return VehicleStageView(vehicle, submission, decision, documents)


async def expire_due_vehicle_approvals(session: AsyncSession, *, limit: int = 100) -> int:
    now = await database_clock(session)
    later = aliased(VehicleEvidenceReviewDecision)
    rows = list(
        (
            await session.scalars(
                select(VehicleEvidenceReviewDecision)
                .where(
                    VehicleEvidenceReviewDecision.decision == KycSubmissionStatus.APPROVED.value,
                    VehicleEvidenceReviewDecision.valid_until <= now,
                    ~select(later.id)
                    .where(
                        later.submission_id == VehicleEvidenceReviewDecision.submission_id,
                        later.sequence > VehicleEvidenceReviewDecision.sequence,
                    )
                    .exists(),
                )
                .order_by(
                    VehicleEvidenceReviewDecision.valid_until,
                    VehicleEvidenceReviewDecision.id,
                )
                .limit(limit)
            )
        ).all()
    )
    expired = 0
    for approved in rows:
        submission = await session.get(VehicleEvidenceSubmission, approved.submission_id)
        if submission is None:
            continue
        vehicle = await session.get(Vehicle, submission.vehicle_id)
        if vehicle is None:
            continue
        profile = await session.get(DriverProfile, vehicle.driver_profile_id)
        if profile is None:
            continue
        await acquire_work_eligibility_lock(
            session, driver_profile_id=profile.id, vehicle_id=vehicle.id
        )
        submission = await session.scalar(
            select(VehicleEvidenceSubmission)
            .where(VehicleEvidenceSubmission.id == submission.id)
            .with_for_update()
        )
        latest = await _latest_decision(session, approved.submission_id, lock=True)
        if (
            submission is None
            or submission.status != KycSubmissionStatus.APPROVED.value
            or latest is None
            or latest.id != approved.id
            or latest.valid_until is None
            or _aware_utc(latest.valid_until) > _aware_utc(now)
        ):
            continue
        application_id = await session.scalar(
            select(DriverApplication.id).where(DriverApplication.driver_profile_id == profile.id)
        )
        if application_id is None:
            continue
        request_id = uuid4()
        payload = VehicleReviewDecisionCreate(
            client_request_id=request_id,
            decision=KycSubmissionStatus.EXPIRED,
            reason_code=VehicleReviewReason.EXPIRED_EVIDENCE,
        )
        fingerprint = _decision_fingerprint(
            application_id=application_id,
            submission_id=submission.id,
            payload=payload,
        )
        session.add(
            VehicleEvidenceReviewDecision(
                submission_id=submission.id,
                sequence=approved.sequence + 1,
                client_request_id=request_id,
                request_fingerprint=fingerprint,
                decision=KycSubmissionStatus.EXPIRED.value,
                reason_code=VehicleReviewReason.EXPIRED_EVIDENCE.value,
                owner_match_confirmed=False,
                vehicle_identity_confirmed=False,
                roadworthy_confirmed=False,
                pilot_car_confirmed=False,
                documents_readable_confirmed=False,
                valid_until=None,
                decided_by_user_id=None,
            )
        )
        submission.status = KycSubmissionStatus.EXPIRED.value
        await reconcile_driver_work_eligibility(session, driver_profile_id=profile.id, now=now)
        await create_audit_event(
            session,
            actor_user_id=None,
            action="system.driver_vehicle.expired",
            entity_type="vehicle_evidence_submission",
            entity_id=str(submission.id),
            metadata={
                "application_id": str(application_id),
                "vehicle_id": str(vehicle.id),
                "version": submission.version,
                "sequence": latest.sequence + 1,
            },
        )
        expired += 1
    return expired
