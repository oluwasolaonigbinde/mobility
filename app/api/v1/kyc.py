from uuid import UUID

from fastapi import APIRouter, Response, status

from app.adapters.crypto import EnvelopeCryptoProvider
from app.api.v1.dependencies import (
    AdminUserDependency,
    DriverUserDependency,
    SessionDependency,
    SettingsDependency,
    StorageDependency,
)
from app.schemas.kyc import (
    DriverKycSubmissionCreate,
    DriverKycSubmissionRead,
    FileKycRetentionRead,
    FileKycRetentionRequest,
    NinRevealRead,
    SensitiveRevealRequest,
    VehicleEvidenceSubmissionCreate,
    VehicleEvidenceSubmissionRead,
)
from app.services.file_kyc_lifecycle import purge_terminal_file_kyc
from app.services.kyc import (
    DriverKycView,
    VehicleEvidenceView,
    current_driver_kyc,
    current_vehicle_evidence,
    reveal_driver_nin,
    rewrap_driver_nin,
    submit_driver_kyc,
    submit_vehicle_evidence,
)
from app.services.privacy_authority import require_collection_authority

router = APIRouter(tags=["Protected KYC"])


def _crypto(settings: SettingsDependency) -> EnvelopeCryptoProvider:
    return EnvelopeCryptoProvider(
        keys=settings.payout_crypto_keys,
        active_key_version=settings.payout_crypto_key_version,
    )


def _driver_response(view: DriverKycView) -> DriverKycSubmissionRead:
    submission = view.submission
    return DriverKycSubmissionRead(
        id=submission.id,
        driver_profile_id=submission.driver_profile_id,
        version=submission.version,
        status=submission.status,
        masked_nin=f"*******{submission.nin_last_four}",
        bank_account_version_id=submission.bank_account_version_id,
        document_file_ids=view.document_file_ids,
        encryption_algorithm=submission.encryption_algorithm,
        encryption_key_version=submission.encryption_key_version,
        created_at=submission.created_at,
    )


def _vehicle_response(view: VehicleEvidenceView) -> VehicleEvidenceSubmissionRead:
    submission = view.submission
    return VehicleEvidenceSubmissionRead(
        id=submission.id,
        vehicle_id=submission.vehicle_id,
        version=submission.version,
        status=submission.status,
        snapshot_trusted=submission.snapshot_trusted,
        plate_number=submission.plate_number_snapshot,
        plate_country_code=submission.plate_country_code_snapshot,
        vehicle_type=submission.vehicle_type_snapshot,
        make=submission.make_snapshot,
        model=submission.model_snapshot,
        year=submission.year_snapshot,
        color=submission.color_snapshot,
        document_file_ids=view.document_file_ids,
        created_at=submission.created_at,
    )


@router.post(
    "/driver/kyc/submissions",
    response_model=DriverKycSubmissionRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_driver_kyc_submission(
    payload: DriverKycSubmissionCreate,
    user: DriverUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> DriverKycSubmissionRead:
    require_collection_authority(settings)
    view = await submit_driver_kyc(
        session,
        actor_user_id=user.id,
        client_request_id=payload.client_request_id,
        nin=payload.nin.get_secret_value(),
        bank_account_version_id=payload.bank_account_version_id,
        document_file_ids={
            "driver_license": payload.driver_license_file_id,
            "driver_photo": payload.driver_photo_file_id,
            "signed_agreement": payload.signed_agreement_file_id,
        },
        crypto=_crypto(settings),
        settings=settings,
    )
    await session.commit()
    return _driver_response(view)


@router.get("/driver/kyc/current", response_model=DriverKycSubmissionRead)
async def get_current_driver_kyc(
    user: DriverUserDependency,
    session: SessionDependency,
) -> DriverKycSubmissionRead:
    return _driver_response(await current_driver_kyc(session, actor_user_id=user.id))


@router.post(
    "/driver/vehicles/{vehicle_id}/evidence-submissions",
    response_model=VehicleEvidenceSubmissionRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_vehicle_evidence_submission(
    vehicle_id: UUID,
    payload: VehicleEvidenceSubmissionCreate,
    user: DriverUserDependency,
    session: SessionDependency,
) -> VehicleEvidenceSubmissionRead:
    view = await submit_vehicle_evidence(
        session,
        actor_user_id=user.id,
        vehicle_id=vehicle_id,
        client_request_id=payload.client_request_id,
        document_file_ids={
            "registration": payload.registration_file_id,
            "insurance": payload.insurance_file_id,
            "vehicle_photo": payload.vehicle_photo_file_id,
        },
    )
    await session.commit()
    return _vehicle_response(view)


@router.get(
    "/driver/vehicles/{vehicle_id}/evidence-current",
    response_model=VehicleEvidenceSubmissionRead,
)
async def get_current_vehicle_evidence(
    vehicle_id: UUID,
    user: DriverUserDependency,
    session: SessionDependency,
) -> VehicleEvidenceSubmissionRead:
    return _vehicle_response(
        await current_vehicle_evidence(
            session,
            actor_user_id=user.id,
            vehicle_id=vehicle_id,
        )
    )


@router.post(
    "/admin/kyc/submissions/{submission_id}/nin/reveal",
    response_model=NinRevealRead,
)
async def admin_reveal_driver_nin(
    submission_id: UUID,
    payload: SensitiveRevealRequest,
    response: Response,
    user: AdminUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> NinRevealRead:
    nin = await reveal_driver_nin(
        session,
        submission_id=submission_id,
        actor_user_id=user.id,
        purpose=payload.purpose,
        crypto=_crypto(settings),
    )
    await session.commit()
    response.headers["Cache-Control"] = "no-store"
    return NinRevealRead(nin=nin)


@router.post(
    "/admin/kyc/submissions/{submission_id}/nin/rewrap",
    response_model=DriverKycSubmissionRead,
)
async def admin_rewrap_driver_nin(
    submission_id: UUID,
    user: AdminUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> DriverKycSubmissionRead:
    view = await rewrap_driver_nin(
        session,
        submission_id=submission_id,
        actor_user_id=user.id,
        crypto=_crypto(settings),
    )
    await session.commit()
    return _driver_response(view)


@router.post(
    "/admin/operations/file-kyc-retention",
    response_model=FileKycRetentionRead,
    summary="Plan or execute terminal file/KYC retention",
)
async def admin_file_kyc_retention(
    payload: FileKycRetentionRequest,
    user: AdminUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
    storage: StorageDependency,
) -> FileKycRetentionRead:
    result = await purge_terminal_file_kyc(
        session,
        storage=storage,
        retention_days=settings.file_kyc_retention_days,
        limit=settings.worker_sweep_batch_size,
        dry_run=payload.dry_run,
        actor_user_id=user.id,
        reason=payload.reason,
    )
    await session.commit()
    return FileKycRetentionRead(
        policy_configured=result.policy_configured,
        dry_run=result.dry_run,
        lock_acquired=result.lock_acquired,
        eligible_submissions=result.eligible_submissions,
        purged_submissions=result.purged_submissions,
        purged_files=result.purged_files,
    )
