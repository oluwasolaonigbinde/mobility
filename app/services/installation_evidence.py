import hashlib
import hmac
import json
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.config import Settings
from app.core.errors import AppError
from app.db.integrity import integrity_constraint_name
from app.models.campaign_assignment import CampaignAssignment, CampaignAssignmentStatus
from app.models.driver import DriverProfile
from app.models.installation_evidence import (
    DisplayProof,
    DisplayProofChallenge,
    InstallationEvidencePhoto,
    InstallationEvidenceStatus,
    InstallationEvidenceSubmission,
)
from app.models.stored_file import FilePurpose, FileScanStatus, StoredFile
from app.models.vehicle import Vehicle
from app.schemas.installation_evidence import (
    DisplayProofCreate,
    InstallationEvidenceCreate,
)
from app.services.admin_authorization import require_active_admin
from app.services.audit import create_audit_event
from app.services.payout_rule_serialization import acquire_campaign_terms_lock, database_clock


def _error(code: str, message: str, status_code: int) -> AppError:
    return AppError(code, message, status_code=status_code)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _require_evidence_policy(settings: Settings) -> tuple[tuple[str, ...], int]:
    views = settings.installation_evidence_views
    validity = settings.installation_evidence_validity_hours
    if not settings.installation_evidence_uploaders or not views or validity is None:
        raise _error(
            "INSTALLATION_EVIDENCE_POLICY_UNAVAILABLE",
            "Installation evidence policy is not configured",
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return views, validity


def _require_proof_policy(settings: Settings) -> tuple[int, int]:
    challenge_ttl = settings.display_proof_challenge_ttl_seconds
    proof_ttl = settings.display_proof_validity_seconds
    if challenge_ttl is None or proof_ttl is None:
        raise _error(
            "DISPLAY_PROOF_POLICY_UNAVAILABLE",
            "Display-proof policy is not configured",
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return challenge_ttl, proof_ttl


async def _assignment_context(
    session: AsyncSession,
    *,
    assignment_id: UUID,
    lock: bool,
) -> tuple[CampaignAssignment, DriverProfile, Vehicle]:
    query = select(CampaignAssignment).where(CampaignAssignment.id == assignment_id)
    if lock:
        query = query.with_for_update()
    assignment = await session.scalar(query)
    if assignment is None:
        raise _error(
            "CAMPAIGN_ASSIGNMENT_NOT_FOUND",
            "Campaign assignment was not found",
            status.HTTP_404_NOT_FOUND,
        )
    profile_query = select(DriverProfile).where(DriverProfile.id == assignment.driver_profile_id)
    vehicle_query = select(Vehicle).where(Vehicle.id == assignment.vehicle_id)
    if lock:
        profile_query = profile_query.with_for_update()
        vehicle_query = vehicle_query.with_for_update()
    profile = await session.scalar(profile_query)
    vehicle = await session.scalar(vehicle_query)
    if profile is None or vehicle is None or vehicle.driver_profile_id != profile.id:
        raise _error(
            "CAMPAIGN_ASSIGNMENT_NOT_FOUND",
            "Campaign assignment was not found",
            status.HTTP_404_NOT_FOUND,
        )
    return assignment, profile, vehicle


def _submission_fingerprint(payload: InstallationEvidenceCreate) -> str:
    document = {
        "device_id": str(payload.device_id),
        "captured_at": payload.captured_at.isoformat(),
        "photos": sorted(
            (
                {"view": photo.view, "stored_file_id": str(photo.stored_file_id)}
                for photo in payload.photos
            ),
            key=lambda row: row["view"],
        ),
        "metadata": payload.metadata,
    }
    return hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


async def submit_installation_evidence(
    session: AsyncSession,
    *,
    actor_user_id: UUID,
    actor_role: str,
    assignment_id: UUID,
    payload: InstallationEvidenceCreate,
    settings: Settings,
) -> InstallationEvidenceSubmission:
    views, _validity = _require_evidence_policy(settings)
    if actor_role not in settings.installation_evidence_uploaders:
        raise _error(
            "INSTALLATION_EVIDENCE_UPLOAD_FORBIDDEN",
            "This role is not configured to submit installation evidence",
            status.HTTP_403_FORBIDDEN,
        )
    if actor_role == "admin":
        await require_active_admin(session, actor_user_id)

    campaign_id = await session.scalar(
        select(CampaignAssignment.campaign_id).where(CampaignAssignment.id == assignment_id)
    )
    if campaign_id is None:
        raise _error(
            "CAMPAIGN_ASSIGNMENT_NOT_FOUND",
            "Campaign assignment was not found",
            status.HTTP_404_NOT_FOUND,
        )
    await acquire_campaign_terms_lock(session, campaign_id)
    assignment, profile, _vehicle = await _assignment_context(
        session, assignment_id=assignment_id, lock=True
    )
    if actor_role == "driver" and profile.user_id != actor_user_id:
        raise _error(
            "CAMPAIGN_ASSIGNMENT_NOT_FOUND",
            "Campaign assignment was not found",
            status.HTTP_404_NOT_FOUND,
        )
    if assignment.status not in {
        CampaignAssignmentStatus.ACCEPTED.value,
        CampaignAssignmentStatus.ACTIVE.value,
        CampaignAssignmentStatus.DEACTIVATED.value,
    }:
        raise _error(
            "INSTALLATION_EVIDENCE_NOT_ALLOWED",
            "Installation evidence is not allowed in this assignment state",
            status.HTTP_409_CONFLICT,
        )

    fingerprint = _submission_fingerprint(payload)
    existing = await session.scalar(
        select(InstallationEvidenceSubmission).where(
            InstallationEvidenceSubmission.assignment_id == assignment.id,
            InstallationEvidenceSubmission.submitted_by_user_id == actor_user_id,
            InstallationEvidenceSubmission.client_request_id == payload.client_request_id,
        )
    )
    if existing is not None:
        if existing.request_fingerprint != fingerprint:
            raise _error(
                "INSTALLATION_EVIDENCE_RETRY_CONFLICT",
                "The retry does not match the original evidence submission",
                status.HTTP_409_CONFLICT,
            )
        return existing

    pending = await session.scalar(
        select(InstallationEvidenceSubmission.id).where(
            InstallationEvidenceSubmission.assignment_id == assignment.id,
            InstallationEvidenceSubmission.status
            == InstallationEvidenceStatus.PENDING_REVIEW.value,
        )
    )
    if pending is not None:
        raise _error(
            "INSTALLATION_EVIDENCE_REVIEW_PENDING",
            "Installation evidence is already pending review",
            status.HTTP_409_CONFLICT,
        )
    submitted_views = [photo.view for photo in payload.photos]
    if len(submitted_views) != len(set(submitted_views)) or set(submitted_views) != set(views):
        raise _error(
            "INSTALLATION_EVIDENCE_VIEWS_INVALID",
            "Evidence must contain exactly the configured required views",
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    now = await database_clock(session)
    if _aware(payload.captured_at) > _aware(now):
        raise _error(
            "INSTALLATION_EVIDENCE_CAPTURE_TIME_INVALID",
            "Evidence capture time cannot be in the future",
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    file_ids = [photo.stored_file_id for photo in payload.photos]
    files = list(
        (
            await session.scalars(
                select(StoredFile)
                .where(StoredFile.id.in_(file_ids))
                .order_by(StoredFile.id)
                .with_for_update()
            )
        ).all()
    )
    if len(files) != len(file_ids) or any(
        stored_file.subject_user_id != profile.user_id
        or stored_file.purpose != FilePurpose.INSTALLATION_EVIDENCE.value
        or stored_file.scan_status != FileScanStatus.CLEAN.value
        or not stored_file.content_type.startswith("image/")
        for stored_file in files
    ):
        raise _error(
            "INSTALLATION_EVIDENCE_FILE_INVALID",
            "Every evidence photo must be a clean assignment-driver image",
            status.HTTP_409_CONFLICT,
        )
    revision = (
        await session.scalar(
            select(func.max(InstallationEvidenceSubmission.revision)).where(
                InstallationEvidenceSubmission.assignment_id == assignment.id
            )
        )
        or 0
    ) + 1
    submission = InstallationEvidenceSubmission(
        assignment_id=assignment.id,
        campaign_id=assignment.campaign_id,
        driver_profile_id=assignment.driver_profile_id,
        vehicle_id=assignment.vehicle_id,
        submitted_by_user_id=actor_user_id,
        revision=revision,
        client_request_id=payload.client_request_id,
        request_fingerprint=fingerprint,
        device_id=payload.device_id,
        captured_at=payload.captured_at,
        required_views=list(views),
        status=InstallationEvidenceStatus.PENDING_REVIEW.value,
        evidence_metadata=payload.metadata,
        submitted_at=now,
    )
    try:
        async with session.begin_nested():
            session.add(submission)
            await session.flush()
    except IntegrityError as exc:
        raced = await session.scalar(
            select(InstallationEvidenceSubmission).where(
                InstallationEvidenceSubmission.assignment_id == assignment.id,
                InstallationEvidenceSubmission.submitted_by_user_id == actor_user_id,
                InstallationEvidenceSubmission.client_request_id == payload.client_request_id,
            )
        )
        if raced is not None:
            if raced.request_fingerprint != fingerprint:
                raise _error(
                    "INSTALLATION_EVIDENCE_RETRY_CONFLICT",
                    "The retry does not match the original evidence submission",
                    status.HTTP_409_CONFLICT,
                ) from None
            return raced
        if integrity_constraint_name(exc) == "uq_installation_evidence_assignment_pending":
            raise _error(
                "INSTALLATION_EVIDENCE_REVIEW_PENDING",
                "Installation evidence is already pending review",
                status.HTTP_409_CONFLICT,
            ) from None
        raise
    for photo in payload.photos:
        session.add(
            InstallationEvidencePhoto(
                submission_id=submission.id,
                view_code=photo.view,
                stored_file_id=photo.stored_file_id,
            )
        )
    try:
        await session.flush()
    except IntegrityError as exc:
        if integrity_constraint_name(exc) == "uq_installation_evidence_photo_file":
            raise _error(
                "INSTALLATION_EVIDENCE_FILE_ALREADY_USED",
                "An evidence file is already bound to another immutable submission",
                status.HTTP_409_CONFLICT,
            ) from None
        raise
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="installation_evidence.submitted",
        entity_type="installation_evidence_submission",
        entity_id=str(submission.id),
        metadata={
            "assignment_id": str(assignment.id),
            "vehicle_id": str(assignment.vehicle_id),
            "revision": revision,
            "views": list(views),
        },
    )
    return submission


async def list_evidence(
    session: AsyncSession,
    *,
    assignment_id: UUID | None = None,
    pending_only: bool = False,
) -> list[InstallationEvidenceSubmission]:
    query = select(InstallationEvidenceSubmission)
    if assignment_id is not None:
        query = query.where(InstallationEvidenceSubmission.assignment_id == assignment_id)
    if pending_only:
        query = query.where(
            InstallationEvidenceSubmission.status == InstallationEvidenceStatus.PENDING_REVIEW.value
        )
    return list(
        (
            await session.scalars(
                query.order_by(
                    InstallationEvidenceSubmission.submitted_at,
                    InstallationEvidenceSubmission.id,
                )
            )
        ).all()
    )


async def list_photos(
    session: AsyncSession, submission_id: UUID
) -> list[InstallationEvidencePhoto]:
    return list(
        (
            await session.scalars(
                select(InstallationEvidencePhoto)
                .where(InstallationEvidencePhoto.submission_id == submission_id)
                .order_by(InstallationEvidencePhoto.view_code)
            )
        ).all()
    )


async def review_installation_evidence(
    session: AsyncSession,
    *,
    actor_user_id: UUID,
    submission_id: UUID,
    approve: bool,
    reason: str | None,
    settings: Settings,
) -> InstallationEvidenceSubmission:
    _views, validity_hours = _require_evidence_policy(settings)
    await require_active_admin(session, actor_user_id)
    campaign_id = await session.scalar(
        select(InstallationEvidenceSubmission.campaign_id).where(
            InstallationEvidenceSubmission.id == submission_id
        )
    )
    if campaign_id is None:
        raise _error(
            "INSTALLATION_EVIDENCE_NOT_FOUND",
            "Installation evidence was not found",
            status.HTTP_404_NOT_FOUND,
        )
    await acquire_campaign_terms_lock(session, campaign_id)
    submission = await session.scalar(
        select(InstallationEvidenceSubmission)
        .where(InstallationEvidenceSubmission.id == submission_id)
        .with_for_update()
    )
    assert submission is not None
    await _assignment_context(session, assignment_id=submission.assignment_id, lock=True)
    if submission.status != InstallationEvidenceStatus.PENDING_REVIEW.value:
        raise _error(
            "INSTALLATION_EVIDENCE_ALREADY_REVIEWED",
            "Installation evidence has already been reviewed",
            status.HTTP_409_CONFLICT,
        )
    if not approve and not reason:
        raise _error(
            "INSTALLATION_EVIDENCE_REJECTION_REASON_REQUIRED",
            "A rejection reason is required",
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    photos = await list_photos(session, submission.id)
    files = list(
        (
            await session.scalars(
                select(StoredFile)
                .where(StoredFile.id.in_([photo.stored_file_id for photo in photos]))
                .order_by(StoredFile.id)
                .with_for_update()
            )
        ).all()
    )
    subject_user_id = await session.scalar(
        select(DriverProfile.user_id).where(DriverProfile.id == submission.driver_profile_id)
    )
    if approve and (
        len(files) != len(photos)
        or any(
            stored_file.subject_user_id != subject_user_id
            or stored_file.purpose != FilePurpose.INSTALLATION_EVIDENCE.value
            or stored_file.scan_status != FileScanStatus.CLEAN.value
            or not stored_file.content_type.startswith("image/")
            for stored_file in files
        )
    ):
        raise _error(
            "INSTALLATION_EVIDENCE_FILE_INVALID",
            "The exact submitted evidence files are no longer clean and valid",
            status.HTTP_409_CONFLICT,
        )
    now = await database_clock(session)
    if approve:
        prior = list(
            (
                await session.scalars(
                    select(InstallationEvidenceSubmission)
                    .where(
                        InstallationEvidenceSubmission.assignment_id == submission.assignment_id,
                        InstallationEvidenceSubmission.status
                        == InstallationEvidenceStatus.APPROVED.value,
                    )
                    .order_by(InstallationEvidenceSubmission.id)
                    .with_for_update()
                )
            ).all()
        )
        for old_submission in prior:
            old_submission.status = InstallationEvidenceStatus.EXPIRED.value
        submission.status = InstallationEvidenceStatus.APPROVED.value
        submission.approved_until = now + timedelta(hours=validity_hours)
        action = "installation_evidence.approved"
    else:
        submission.status = InstallationEvidenceStatus.REJECTED.value
        submission.rejection_reason = reason
        action = "installation_evidence.rejected"
    submission.reviewed_by_user_id = actor_user_id
    submission.reviewed_at = now
    await session.flush()
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action=action,
        entity_type="installation_evidence_submission",
        entity_id=str(submission.id),
        metadata={
            "assignment_id": str(submission.assignment_id),
            "revision": submission.revision,
            "reason": reason if not approve else None,
        },
    )
    return submission


async def ensure_current_approved_installation_evidence(
    session: AsyncSession,
    *,
    assignment: CampaignAssignment,
    settings: Settings,
    now: datetime,
    lock: bool = False,
) -> InstallationEvidenceSubmission:
    _require_evidence_policy(settings)
    query = (
        select(InstallationEvidenceSubmission)
        .where(
            InstallationEvidenceSubmission.assignment_id == assignment.id,
            InstallationEvidenceSubmission.campaign_id == assignment.campaign_id,
            InstallationEvidenceSubmission.driver_profile_id == assignment.driver_profile_id,
            InstallationEvidenceSubmission.vehicle_id == assignment.vehicle_id,
            InstallationEvidenceSubmission.status == InstallationEvidenceStatus.APPROVED.value,
        )
        .order_by(
            InstallationEvidenceSubmission.revision.desc(),
            InstallationEvidenceSubmission.id.desc(),
        )
        .limit(1)
    )
    if lock:
        query = query.with_for_update()
    evidence = await session.scalar(query)
    if evidence is None or evidence.approved_until is None:
        raise _error(
            "APPROVED_INSTALLATION_EVIDENCE_REQUIRED",
            "Current approved installation evidence is required",
            status.HTTP_409_CONFLICT,
        )
    if _aware(evidence.approved_until) <= _aware(now):
        raise _error(
            "INSTALLATION_EVIDENCE_EXPIRED",
            "Installation evidence has expired",
            status.HTTP_409_CONFLICT,
        )
    return evidence


async def create_display_proof_challenge(
    session: AsyncSession,
    *,
    actor_user_id: UUID,
    assignment_id: UUID,
    device_id: UUID,
    settings: Settings,
) -> tuple[DisplayProofChallenge, str]:
    challenge_ttl, _proof_ttl = _require_proof_policy(settings)
    campaign_id = await session.scalar(
        select(CampaignAssignment.campaign_id).where(CampaignAssignment.id == assignment_id)
    )
    if campaign_id is None:
        raise _error(
            "CAMPAIGN_ASSIGNMENT_NOT_FOUND",
            "Campaign assignment was not found",
            status.HTTP_404_NOT_FOUND,
        )
    await acquire_campaign_terms_lock(session, campaign_id)
    assignment, profile, _vehicle = await _assignment_context(
        session, assignment_id=assignment_id, lock=True
    )
    if profile.user_id != actor_user_id:
        raise _error(
            "CAMPAIGN_ASSIGNMENT_NOT_FOUND",
            "Campaign assignment was not found",
            status.HTTP_404_NOT_FOUND,
        )
    if assignment.status != CampaignAssignmentStatus.ACTIVE.value:
        raise _error(
            "CAMPAIGN_ASSIGNMENT_NOT_ACTIVE",
            "Campaign assignment must be active for a display proof",
            status.HTTP_409_CONFLICT,
        )
    now = await database_clock(session)
    evidence = await ensure_current_approved_installation_evidence(
        session, assignment=assignment, settings=settings, now=now, lock=True
    )
    if evidence.device_id != device_id:
        raise _error(
            "DISPLAY_PROOF_DEVICE_MISMATCH",
            "The device does not match the approved installation evidence",
            status.HTTP_409_CONFLICT,
        )
    nonce = secrets.token_urlsafe(32)
    challenge = DisplayProofChallenge(
        assignment_id=assignment.id,
        evidence_submission_id=evidence.id,
        driver_profile_id=assignment.driver_profile_id,
        vehicle_id=assignment.vehicle_id,
        device_id=device_id,
        nonce_sha256=hashlib.sha256(nonce.encode()).hexdigest(),
        expires_at=now + timedelta(seconds=challenge_ttl),
        created_at=now,
    )
    session.add(challenge)
    await session.flush()
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="display_proof.challenge_issued",
        entity_type="display_proof_challenge",
        entity_id=str(challenge.id),
        metadata={
            "assignment_id": str(assignment.id),
            "evidence_submission_id": str(evidence.id),
            "expires_at": challenge.expires_at.isoformat(),
        },
    )
    return challenge, nonce


async def submit_display_proof(
    session: AsyncSession,
    *,
    actor_user_id: UUID,
    assignment_id: UUID,
    payload: DisplayProofCreate,
    settings: Settings,
) -> DisplayProof:
    _challenge_ttl, proof_ttl = _require_proof_policy(settings)
    campaign_id = await session.scalar(
        select(CampaignAssignment.campaign_id).where(CampaignAssignment.id == assignment_id)
    )
    if campaign_id is None:
        raise _error(
            "CAMPAIGN_ASSIGNMENT_NOT_FOUND",
            "Campaign assignment was not found",
            status.HTTP_404_NOT_FOUND,
        )
    await acquire_campaign_terms_lock(session, campaign_id)
    assignment, profile, _vehicle = await _assignment_context(
        session, assignment_id=assignment_id, lock=True
    )
    if profile.user_id != actor_user_id:
        raise _error(
            "CAMPAIGN_ASSIGNMENT_NOT_FOUND",
            "Campaign assignment was not found",
            status.HTTP_404_NOT_FOUND,
        )
    challenge = await session.scalar(
        select(DisplayProofChallenge)
        .where(
            DisplayProofChallenge.id == payload.challenge_id,
            DisplayProofChallenge.assignment_id == assignment.id,
        )
        .with_for_update()
    )
    if challenge is None:
        raise _error(
            "DISPLAY_PROOF_CHALLENGE_NOT_FOUND",
            "Display-proof challenge was not found",
            status.HTTP_404_NOT_FOUND,
        )
    existing = await session.scalar(
        select(DisplayProof).where(DisplayProof.challenge_id == challenge.id)
    )
    if existing is not None or challenge.consumed_at is not None:
        raise _error(
            "DISPLAY_PROOF_CHALLENGE_REPLAYED",
            "Display-proof challenge has already been consumed",
            status.HTTP_409_CONFLICT,
        )
    now = await database_clock(session)
    if _aware(challenge.expires_at) <= _aware(now):
        raise _error(
            "DISPLAY_PROOF_CHALLENGE_EXPIRED",
            "Display-proof challenge has expired",
            status.HTTP_410_GONE,
        )
    supplied_hash = hashlib.sha256(payload.nonce.encode()).hexdigest()
    if not hmac.compare_digest(supplied_hash, challenge.nonce_sha256):
        raise _error(
            "DISPLAY_PROOF_NONCE_INVALID",
            "Display-proof nonce is invalid",
            status.HTTP_409_CONFLICT,
        )
    if payload.device_id != challenge.device_id:
        raise _error(
            "DISPLAY_PROOF_DEVICE_MISMATCH",
            "The proof device does not match its challenge",
            status.HTTP_409_CONFLICT,
        )
    evidence = await ensure_current_approved_installation_evidence(
        session, assignment=assignment, settings=settings, now=now, lock=True
    )
    if evidence.id != challenge.evidence_submission_id:
        raise _error(
            "DISPLAY_PROOF_EVIDENCE_CHANGED",
            "Approved installation evidence changed after the challenge",
            status.HTTP_409_CONFLICT,
        )
    stored_file = await session.scalar(
        select(StoredFile).where(StoredFile.id == payload.stored_file_id).with_for_update()
    )
    if (
        stored_file is None
        or stored_file.subject_user_id != profile.user_id
        or stored_file.purpose != FilePurpose.INSTALLATION_EVIDENCE.value
        or stored_file.scan_status != FileScanStatus.CLEAN.value
        or not stored_file.content_type.startswith("image/")
        or _aware(stored_file.created_at) <= _aware(challenge.created_at)
    ):
        raise _error(
            "DISPLAY_PROOF_FILE_INVALID",
            "Proof must be a fresh clean image for the assigned driver",
            status.HTTP_409_CONFLICT,
        )
    proof = DisplayProof(
        challenge_id=challenge.id,
        assignment_id=assignment.id,
        evidence_submission_id=evidence.id,
        driver_profile_id=assignment.driver_profile_id,
        vehicle_id=assignment.vehicle_id,
        device_id=payload.device_id,
        stored_file_id=payload.stored_file_id,
        verified_at=now,
        valid_until=now + timedelta(seconds=proof_ttl),
        proof_metadata=payload.metadata,
    )
    session.add(proof)
    challenge.consumed_at = now
    await session.flush()
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="display_proof.verified",
        entity_type="display_proof",
        entity_id=str(proof.id),
        metadata={
            "assignment_id": str(assignment.id),
            "evidence_submission_id": str(evidence.id),
            "valid_until": proof.valid_until.isoformat(),
        },
    )
    from app.services.evidence_verification import satisfy_pending_evidence_challenges

    await satisfy_pending_evidence_challenges(
        session,
        assignment_id=assignment.id,
        proof=proof,
        actor_user_id=actor_user_id,
    )
    return proof


async def ensure_current_display_proof(
    session: AsyncSession,
    *,
    assignment: CampaignAssignment,
    settings: Settings,
    now: datetime,
    lock: bool = False,
) -> DisplayProof:
    _require_proof_policy(settings)
    evidence = await ensure_current_approved_installation_evidence(
        session, assignment=assignment, settings=settings, now=now, lock=lock
    )
    query = (
        select(DisplayProof)
        .where(
            DisplayProof.assignment_id == assignment.id,
            DisplayProof.evidence_submission_id == evidence.id,
            DisplayProof.driver_profile_id == assignment.driver_profile_id,
            DisplayProof.vehicle_id == assignment.vehicle_id,
        )
        .order_by(DisplayProof.verified_at.desc(), DisplayProof.id.desc())
        .limit(1)
    )
    if lock:
        query = query.with_for_update()
    proof = await session.scalar(query)
    if proof is None or _aware(proof.valid_until) <= _aware(now):
        raise _error(
            "CURRENT_DISPLAY_PROOF_REQUIRED",
            "A current display proof is required before earning can start",
            status.HTTP_409_CONFLICT,
        )
    return proof
