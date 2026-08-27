import re
from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.adapters.crypto import (
    AssociatedData,
    CiphertextEnvelope,
    CryptoOperationError,
    CryptoProvider,
)
from app.core.errors import AppError
from app.models.driver import DriverProfile
from app.models.kyc import (
    DriverKycDocument,
    DriverKycDocumentType,
    DriverKycSubmission,
    KycSubmissionStatus,
    VehicleEvidenceDocument,
    VehicleEvidenceDocumentType,
    VehicleEvidenceSubmission,
)
from app.models.payee import Payee, PayeeBankAccount, PayeeBankAccountVersion, PayeeType
from app.models.stored_file import FilePurpose, FileScanStatus, StoredFile
from app.models.user import User, UserRole, UserStatus
from app.models.vehicle import Vehicle
from app.services.admin_authorization import require_active_admin
from app.services.audit import create_audit_event

DRIVER_NIN_FIELD = "driver_kyc.nin"
PURPOSE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{2,63}$")


@dataclass(frozen=True, slots=True)
class DriverKycView:
    submission: DriverKycSubmission
    document_file_ids: dict[str, UUID]


@dataclass(frozen=True, slots=True)
class VehicleEvidenceView:
    submission: VehicleEvidenceSubmission
    document_file_ids: dict[str, UUID]


def _error(code: str, message: str, status_code: int) -> AppError:
    return AppError(code, message, status_code=status_code)


def _purpose(value: str) -> str:
    normalized = value.strip().lower()
    if not PURPOSE_PATTERN.fullmatch(normalized):
        raise _error(
            "KYC_REVEAL_PURPOSE_INVALID",
            "A valid KYC reveal purpose is required",
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    return normalized


async def _acquire_work_eligibility_authority(
    session: AsyncSession, *, driver_profile_id: UUID
) -> None:
    # Local import avoids the KYC/vehicle evidence module cycle while keeping
    # every person/vehicle producer on the shared advisory-lock authority.
    from app.services.vehicle_onboarding import acquire_work_eligibility_lock

    await acquire_work_eligibility_lock(session, driver_profile_id=driver_profile_id)


async def _driver_profile(
    session: AsyncSession,
    *,
    actor_user_id: UUID,
    lock: bool,
    allow_invited: bool = False,
) -> DriverProfile:
    user_query = select(User).where(User.id == actor_user_id)
    query = select(DriverProfile).where(DriverProfile.user_id == actor_user_id)
    if lock:
        user_query = user_query.with_for_update()
        query = query.with_for_update()
    user = await session.scalar(user_query)
    profile = await session.scalar(query)
    allowed_statuses = {UserStatus.ACTIVE}
    if allow_invited:
        allowed_statuses.add(UserStatus.INVITED)
    if (
        user is None
        or user.role != UserRole.DRIVER
        or user.status not in allowed_statuses
        or profile is None
    ):
        raise _error("KYC_SCOPE_NOT_FOUND", "KYC scope was not found", status.HTTP_404_NOT_FOUND)
    return profile


async def _require_files(
    session: AsyncSession,
    *,
    file_ids: dict[str, UUID],
    actor_user_id: UUID,
    purpose: FilePurpose,
) -> None:
    if len(set(file_ids.values())) != len(file_ids):
        raise _error(
            "KYC_DOCUMENTS_INVALID",
            "Each required document must use a distinct managed file",
            status.HTTP_409_CONFLICT,
        )
    files = list(
        (
            await session.scalars(
                select(StoredFile)
                .where(StoredFile.id.in_(sorted(file_ids.values(), key=str)))
                .order_by(StoredFile.id)
                .with_for_update()
            )
        ).all()
    )
    if len(files) != len(file_ids) or any(
        stored_file.subject_user_id != actor_user_id
        or stored_file.organization_id is not None
        or stored_file.purpose != purpose
        or stored_file.scan_status != FileScanStatus.CLEAN
        for stored_file in files
    ):
        raise _error(
            "KYC_DOCUMENT_NOT_CLEARED",
            "Every KYC document must be an owned managed file that passed security checks",
            status.HTTP_409_CONFLICT,
        )


async def _require_driver_bank_version(
    session: AsyncSession,
    *,
    bank_account_version_id: UUID,
    profile: DriverProfile,
) -> None:
    result = await session.execute(
        select(PayeeBankAccountVersion, PayeeBankAccount, Payee)
        .join(PayeeBankAccount, PayeeBankAccount.id == PayeeBankAccountVersion.bank_account_id)
        .join(Payee, Payee.id == PayeeBankAccount.payee_id)
        .where(PayeeBankAccountVersion.id == bank_account_version_id)
    )
    row = result.one_or_none()
    if row is None:
        raise _error(
            "KYC_BANK_VERSION_INVALID",
            "The verified bank-account version is not valid for this driver",
            status.HTTP_409_CONFLICT,
        )
    _, _, payee = row
    if (
        payee.payee_type != PayeeType.DRIVER
        or payee.subject_id != profile.id
        or payee.tenant_id != profile.user_id
    ):
        raise _error(
            "KYC_BANK_VERSION_INVALID",
            "The verified bank-account version is not valid for this driver",
            status.HTTP_409_CONFLICT,
        )


def _envelope(value: dict) -> CiphertextEnvelope:
    try:
        return CiphertextEnvelope.from_mapping(value)
    except CryptoOperationError:
        raise _error(
            "KYC_DECRYPTION_FAILED",
            "KYC identity data could not be authenticated",
            status.HTTP_409_CONFLICT,
        ) from None


async def _driver_documents(session: AsyncSession, submission_id: UUID) -> dict[str, UUID]:
    rows = list(
        (
            await session.scalars(
                select(DriverKycDocument).where(DriverKycDocument.submission_id == submission_id)
            )
        ).all()
    )
    return {row.document_type: row.stored_file_id for row in rows}


async def _vehicle_documents(session: AsyncSession, submission_id: UUID) -> dict[str, UUID]:
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


async def submit_driver_kyc(
    session: AsyncSession,
    *,
    actor_user_id: UUID,
    client_request_id: UUID,
    nin: str,
    bank_account_version_id: UUID,
    document_file_ids: dict[str, UUID],
    crypto: CryptoProvider,
    allow_invited_actor: bool = False,
) -> DriverKycView:
    if len(nin) != 11 or not nin.isascii() or not nin.isdigit():
        raise _error("KYC_NIN_INVALID", "NIN must contain exactly 11 digits", 422)
    required = {item.value for item in DriverKycDocumentType}
    if set(document_file_ids) != required:
        raise _error("KYC_DOCUMENTS_INVALID", "All required KYC documents are required", 422)
    driver_profile_id = await session.scalar(
        select(DriverProfile.id).where(DriverProfile.user_id == actor_user_id)
    )
    if driver_profile_id is not None:
        await _acquire_work_eligibility_authority(session, driver_profile_id=driver_profile_id)
    profile = await _driver_profile(
        session,
        actor_user_id=actor_user_id,
        lock=True,
        allow_invited=allow_invited_actor,
    )
    existing = await session.scalar(
        select(DriverKycSubmission).where(
            DriverKycSubmission.driver_profile_id == profile.id,
            DriverKycSubmission.client_request_id == client_request_id,
        )
    )
    if existing is not None:
        existing_docs = await _driver_documents(session, existing.id)
        try:
            existing_nin = crypto.decrypt(
                _envelope(existing.encrypted_nin),
                AssociatedData(
                    tenant_id=profile.user_id,
                    record_id=existing.nin_record_id,
                    field_name=DRIVER_NIN_FIELD,
                ),
            ).decode("ascii")
        except (CryptoOperationError, UnicodeDecodeError):
            raise _error(
                "KYC_DECRYPTION_FAILED",
                "KYC identity data could not be authenticated",
                status.HTTP_409_CONFLICT,
            ) from None
        await create_audit_event(
            session,
            actor_user_id=actor_user_id,
            action="driver.kyc.retry_read",
            entity_type="driver_kyc_submission",
            entity_id=str(existing.id),
            metadata={"version": existing.version},
        )
        if (
            existing_nin != nin
            or existing.bank_account_version_id != bank_account_version_id
            or existing_docs != document_file_ids
        ):
            raise _error(
                "KYC_RETRY_CONFLICT",
                "The KYC retry does not match the original request",
                status.HTTP_409_CONFLICT,
            )
        return DriverKycView(existing, existing_docs)

    await _require_driver_bank_version(
        session,
        bank_account_version_id=bank_account_version_id,
        profile=profile,
    )
    await _require_files(
        session,
        file_ids=document_file_ids,
        actor_user_id=actor_user_id,
        purpose=FilePurpose.DRIVER_KYC,
    )
    current_version = await session.scalar(
        select(DriverKycSubmission.version)
        .where(DriverKycSubmission.driver_profile_id == profile.id)
        .order_by(DriverKycSubmission.version.desc())
        .limit(1)
    )
    nin_record_id = uuid4()
    try:
        envelope = crypto.encrypt(
            nin.encode("ascii"),
            AssociatedData(
                tenant_id=profile.user_id,
                record_id=nin_record_id,
                field_name=DRIVER_NIN_FIELD,
            ),
        )
    except CryptoOperationError:
        raise _error(
            "KYC_ENCRYPTION_UNAVAILABLE",
            "KYC identity protection is unavailable",
            status.HTTP_503_SERVICE_UNAVAILABLE,
        ) from None
    submission = DriverKycSubmission(
        id=uuid4(),
        driver_profile_id=profile.id,
        nin_record_id=nin_record_id,
        version=(current_version or 0) + 1,
        client_request_id=client_request_id,
        status=KycSubmissionStatus.PENDING_REVIEW,
        encrypted_nin=envelope.to_mapping(),
        encryption_algorithm=envelope.data_algorithm,
        encryption_key_version=envelope.key_version,
        nin_last_four=nin[-4:],
        bank_account_version_id=bank_account_version_id,
        created_by_user_id=actor_user_id,
    )
    session.add(submission)
    await session.flush()
    session.add_all(
        DriverKycDocument(
            submission_id=submission.id,
            document_type=document_type,
            stored_file_id=file_id,
        )
        for document_type, file_id in document_file_ids.items()
    )
    await session.flush()
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="driver.kyc.submitted",
        entity_type="driver_kyc_submission",
        entity_id=str(submission.id),
        metadata={"version": submission.version, "key_version": envelope.key_version},
    )
    return DriverKycView(submission, document_file_ids)


async def validate_driver_kyc_for_approval(
    session: AsyncSession,
    *,
    submission: DriverKycSubmission,
    profile: DriverProfile,
) -> dict[str, UUID]:
    """Recheck current clean owned evidence and payee binding under caller locks."""

    documents = await _driver_documents(session, submission.id)
    required = {item.value for item in DriverKycDocumentType}
    if set(documents) != required:
        raise _error(
            "PERSON_PAYEE_INCOMPLETE",
            "All current person/payee evidence is required",
            status.HTTP_409_CONFLICT,
        )
    await _require_files(
        session,
        file_ids=documents,
        actor_user_id=profile.user_id,
        purpose=FilePurpose.DRIVER_KYC,
    )
    await _require_driver_bank_version(
        session,
        bank_account_version_id=submission.bank_account_version_id,
        profile=profile,
    )
    return documents


async def current_driver_kyc(session: AsyncSession, *, actor_user_id: UUID) -> DriverKycView:
    profile = await _driver_profile(session, actor_user_id=actor_user_id, lock=False)
    submission = await session.scalar(
        select(DriverKycSubmission)
        .where(DriverKycSubmission.driver_profile_id == profile.id)
        .order_by(DriverKycSubmission.version.desc())
        .limit(1)
    )
    if submission is None:
        raise _error("KYC_NOT_FOUND", "KYC submission was not found", status.HTTP_404_NOT_FOUND)
    return DriverKycView(submission, await _driver_documents(session, submission.id))


async def submit_vehicle_evidence(
    session: AsyncSession,
    *,
    actor_user_id: UUID,
    vehicle_id: UUID,
    client_request_id: UUID,
    document_file_ids: dict[str, UUID],
) -> VehicleEvidenceView:
    required = {item.value for item in VehicleEvidenceDocumentType}
    if set(document_file_ids) != required:
        raise _error("VEHICLE_EVIDENCE_INVALID", "All vehicle evidence is required", 422)
    profile = await _driver_profile(session, actor_user_id=actor_user_id, lock=True)
    vehicle = await session.scalar(
        select(Vehicle)
        .where(Vehicle.id == vehicle_id, Vehicle.driver_profile_id == profile.id)
        .with_for_update()
    )
    if vehicle is None:
        raise _error("VEHICLE_NOT_FOUND", "Vehicle was not found", status.HTTP_404_NOT_FOUND)
    existing = await session.scalar(
        select(VehicleEvidenceSubmission).where(
            VehicleEvidenceSubmission.vehicle_id == vehicle.id,
            VehicleEvidenceSubmission.client_request_id == client_request_id,
        )
    )
    if existing is not None:
        existing_docs = await _vehicle_documents(session, existing.id)
        if existing_docs != document_file_ids:
            raise _error(
                "VEHICLE_EVIDENCE_RETRY_CONFLICT",
                "The evidence retry does not match the original request",
                status.HTTP_409_CONFLICT,
            )
        return VehicleEvidenceView(existing, existing_docs)
    await _require_files(
        session,
        file_ids=document_file_ids,
        actor_user_id=actor_user_id,
        purpose=FilePurpose.VEHICLE_EVIDENCE,
    )
    current_version = await session.scalar(
        select(VehicleEvidenceSubmission.version)
        .where(VehicleEvidenceSubmission.vehicle_id == vehicle.id)
        .order_by(VehicleEvidenceSubmission.version.desc())
        .limit(1)
    )
    submission = VehicleEvidenceSubmission(
        id=uuid4(),
        vehicle_id=vehicle.id,
        version=(current_version or 0) + 1,
        client_request_id=client_request_id,
        status=KycSubmissionStatus.PENDING_REVIEW,
        snapshot_trusted=True,
        plate_number_snapshot=vehicle.plate_number,
        plate_number_normalized_snapshot=vehicle.plate_number_normalized,
        plate_country_code_snapshot=vehicle.plate_country_code,
        vehicle_type_snapshot=vehicle.vehicle_type,
        make_snapshot=vehicle.make,
        model_snapshot=vehicle.model,
        year_snapshot=vehicle.year,
        color_snapshot=vehicle.color,
        created_by_user_id=actor_user_id,
    )
    session.add(submission)
    await session.flush()
    session.add_all(
        VehicleEvidenceDocument(
            submission_id=submission.id,
            document_type=document_type,
            stored_file_id=file_id,
        )
        for document_type, file_id in document_file_ids.items()
    )
    await session.flush()
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="driver.vehicle_evidence.submitted",
        entity_type="vehicle_evidence_submission",
        entity_id=str(submission.id),
        metadata={"vehicle_id": str(vehicle.id), "version": submission.version},
    )
    return VehicleEvidenceView(submission, document_file_ids)


async def current_vehicle_evidence(
    session: AsyncSession, *, actor_user_id: UUID, vehicle_id: UUID
) -> VehicleEvidenceView:
    profile = await _driver_profile(session, actor_user_id=actor_user_id, lock=False)
    vehicle = await session.scalar(
        select(Vehicle).where(Vehicle.id == vehicle_id, Vehicle.driver_profile_id == profile.id)
    )
    if vehicle is None:
        raise _error("VEHICLE_NOT_FOUND", "Vehicle was not found", status.HTTP_404_NOT_FOUND)
    submission = await session.scalar(
        select(VehicleEvidenceSubmission)
        .where(VehicleEvidenceSubmission.vehicle_id == vehicle.id)
        .order_by(VehicleEvidenceSubmission.version.desc())
        .limit(1)
    )
    if submission is None:
        raise _error(
            "VEHICLE_EVIDENCE_NOT_FOUND",
            "Vehicle evidence was not found",
            status.HTTP_404_NOT_FOUND,
        )
    return VehicleEvidenceView(submission, await _vehicle_documents(session, submission.id))


async def reveal_driver_nin(
    session: AsyncSession,
    *,
    submission_id: UUID,
    actor_user_id: UUID,
    purpose: str,
    crypto: CryptoProvider,
) -> str:
    await require_active_admin(session, actor_user_id)
    purpose = _purpose(purpose)
    submission = await session.get(DriverKycSubmission, submission_id)
    if submission is None:
        raise _error("KYC_NOT_FOUND", "KYC submission was not found", status.HTTP_404_NOT_FOUND)
    profile = await session.get(DriverProfile, submission.driver_profile_id)
    if profile is None:  # pragma: no cover
        raise RuntimeError("KYC profile authority disappeared")
    try:
        nin = crypto.decrypt(
            _envelope(submission.encrypted_nin),
            AssociatedData(
                tenant_id=profile.user_id,
                record_id=submission.nin_record_id,
                field_name=DRIVER_NIN_FIELD,
            ),
        ).decode("ascii")
    except (CryptoOperationError, UnicodeDecodeError):
        raise _error(
            "KYC_DECRYPTION_FAILED",
            "KYC identity data could not be authenticated",
            status.HTTP_409_CONFLICT,
        ) from None
    if len(nin) != 11 or not nin.isdigit():
        raise _error(
            "KYC_DECRYPTION_FAILED",
            "KYC identity data could not be authenticated",
            status.HTTP_409_CONFLICT,
        )
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="admin.kyc.nin_read",
        entity_type="driver_kyc_submission",
        entity_id=str(submission.id),
        metadata={"purpose": purpose},
    )
    return nin


async def rewrap_driver_nin(
    session: AsyncSession,
    *,
    submission_id: UUID,
    actor_user_id: UUID,
    crypto: CryptoProvider,
) -> DriverKycView:
    await require_active_admin(session, actor_user_id)
    probe = await session.get(DriverKycSubmission, submission_id)
    if probe is None:
        raise _error("KYC_NOT_FOUND", "KYC submission was not found", status.HTTP_404_NOT_FOUND)
    await _acquire_work_eligibility_authority(session, driver_profile_id=probe.driver_profile_id)
    profile = await session.scalar(
        select(DriverProfile).where(DriverProfile.id == probe.driver_profile_id).with_for_update()
    )
    if profile is None:  # pragma: no cover
        raise RuntimeError("KYC profile authority disappeared")
    current = await session.scalar(
        select(DriverKycSubmission)
        .where(DriverKycSubmission.driver_profile_id == profile.id)
        .order_by(DriverKycSubmission.version.desc())
        .limit(1)
    )
    if current is None:  # pragma: no cover
        raise RuntimeError("KYC encryption chain disappeared")
    if current.nin_record_id != probe.nin_record_id:
        raise _error(
            "KYC_REWRAP_STALE",
            "Only the current KYC identity version can be rewrapped",
            status.HTTP_409_CONFLICT,
        )
    current_docs = await _driver_documents(session, current.id)
    if current.encryption_key_version == crypto.active_key_version:
        return DriverKycView(current, current_docs)
    try:
        rotated = crypto.rotate(
            _envelope(current.encrypted_nin),
            AssociatedData(
                tenant_id=profile.user_id,
                record_id=current.nin_record_id,
                field_name=DRIVER_NIN_FIELD,
            ),
        )
    except CryptoOperationError:
        raise _error(
            "KYC_REWRAP_FAILED",
            "KYC identity encryption could not be rotated",
            status.HTTP_409_CONFLICT,
        ) from None
    latest_version = await session.scalar(
        select(DriverKycSubmission.version)
        .where(DriverKycSubmission.driver_profile_id == profile.id)
        .order_by(DriverKycSubmission.version.desc())
        .limit(1)
    )
    new_submission = DriverKycSubmission(
        id=uuid4(),
        driver_profile_id=profile.id,
        nin_record_id=current.nin_record_id,
        version=(latest_version or 0) + 1,
        client_request_id=uuid4(),
        # A new ciphertext-bearing version becomes the current authority. An
        # earlier approval remains immutable history but cannot silently cover
        # the new record; approval must be re-established against this version.
        status=(
            KycSubmissionStatus.PENDING_REVIEW
            if current.status == KycSubmissionStatus.APPROVED
            else current.status
        ),
        encrypted_nin=rotated.to_mapping(),
        encryption_algorithm=rotated.data_algorithm,
        encryption_key_version=rotated.key_version,
        nin_last_four=current.nin_last_four,
        bank_account_version_id=current.bank_account_version_id,
        created_by_user_id=actor_user_id,
    )
    session.add(new_submission)
    await session.flush()
    session.add_all(
        DriverKycDocument(
            submission_id=new_submission.id,
            document_type=document_type,
            stored_file_id=file_id,
        )
        for document_type, file_id in current_docs.items()
    )
    await session.flush()
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="admin.kyc.nin_rewrapped",
        entity_type="driver_kyc_submission",
        entity_id=str(new_submission.id),
        metadata={
            "from_version": current.version,
            "to_version": new_submission.version,
            "from_key_version": current.encryption_key_version,
            "to_key_version": new_submission.encryption_key_version,
            "review_reset": current.status == KycSubmissionStatus.APPROVED,
        },
    )
    from app.services.vehicle_onboarding import reconcile_driver_work_eligibility

    await reconcile_driver_work_eligibility(session, driver_profile_id=profile.id)
    return DriverKycView(new_submission, current_docs)
