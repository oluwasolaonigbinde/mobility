import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.adapters.storage import StorageProvider, StorageUnavailable
from app.core.errors import AppError
from app.models.campaign import CampaignCreative
from app.models.driver import DriverProfile
from app.models.kyc import (
    DriverKycDocument,
    DriverKycSubmission,
    KycSubmissionStatus,
    VehicleEvidenceDocument,
    VehicleEvidenceSubmission,
)
from app.models.stored_file import FileUploadIntent, StoredFile
from app.models.vehicle import Vehicle
from app.services.audit import create_audit_event

FILE_KYC_RETENTION_LOCK = 0x46494C454B5943
TERMINAL_RETENTION_STATUSES = {
    KycSubmissionStatus.REJECTED.value,
    KycSubmissionStatus.EXPIRED.value,
}
REASON_PATTERN = re.compile(r"^[a-z][a-z0-9_]{2,63}$")


@dataclass(frozen=True, slots=True)
class FileKycPurgeResult:
    policy_configured: bool
    dry_run: bool
    lock_acquired: bool
    eligible_submissions: int
    purged_submissions: int
    purged_files: int


def _reason(value: str) -> str:
    normalized = value.strip().lower()
    if not REASON_PATTERN.fullmatch(normalized):
        raise AppError(
            "FILE_KYC_RETENTION_REASON_INVALID",
            "A valid file/KYC retention reason is required",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    return normalized


async def _acquire_retention_lock(session: AsyncSession) -> bool:
    bind = session.get_bind()
    if bind.dialect.name != "postgresql":
        return True
    return bool(
        await session.scalar(
            text("SELECT pg_try_advisory_xact_lock(:lock_id)"),
            {"lock_id": FILE_KYC_RETENTION_LOCK},
        )
    )


async def _candidate_ids(
    session: AsyncSession, *, cutoff: datetime, limit: int
) -> tuple[list[UUID], list[UUID]]:
    driver_ids = list(
        (
            await session.scalars(
                select(DriverKycSubmission.id)
                .where(
                    DriverKycSubmission.status.in_(TERMINAL_RETENTION_STATUSES),
                    DriverKycSubmission.created_at < cutoff,
                )
                .order_by(DriverKycSubmission.created_at, DriverKycSubmission.id)
                .limit(limit)
            )
        ).all()
    )
    remaining = max(limit - len(driver_ids), 0)
    vehicle_ids: list[UUID] = []
    if remaining:
        vehicle_ids = list(
            (
                await session.scalars(
                    select(VehicleEvidenceSubmission.id)
                    .where(
                        VehicleEvidenceSubmission.status.in_(TERMINAL_RETENTION_STATUSES),
                        VehicleEvidenceSubmission.created_at < cutoff,
                    )
                    .order_by(
                        VehicleEvidenceSubmission.created_at,
                        VehicleEvidenceSubmission.id,
                    )
                    .limit(remaining)
                )
            ).all()
        )
    return driver_ids, vehicle_ids


async def _file_is_referenced(session: AsyncSession, file_id: UUID) -> bool:
    checks = (
        select(DriverKycDocument.id).where(DriverKycDocument.stored_file_id == file_id),
        select(VehicleEvidenceDocument.id).where(
            VehicleEvidenceDocument.stored_file_id == file_id
        ),
        select(CampaignCreative.id).where(CampaignCreative.stored_file_id == file_id),
    )
    for query in checks:
        if await session.scalar(query.limit(1)) is not None:
            return True
    return False


async def _purge_unreferenced_file(
    session: AsyncSession,
    *,
    file_id: UUID,
    storage: StorageProvider,
    actor_user_id: UUID | None,
    reason: str,
) -> int:
    stored_file = await session.scalar(
        select(StoredFile).where(StoredFile.id == file_id).with_for_update()
    )
    if stored_file is None or await _file_is_referenced(session, file_id):
        return 0
    intent = await session.scalar(
        select(FileUploadIntent)
        .where(FileUploadIntent.id == stored_file.upload_intent_id)
        .with_for_update()
    )
    try:
        await storage.delete(stored_file.storage_key)
    except StorageUnavailable:
        raise AppError(
            "FILE_STORAGE_UNAVAILABLE",
            "Private file storage is unavailable",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        ) from None
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="stored_file.purged",
        entity_type="stored_file",
        entity_id=str(stored_file.id),
        metadata={"purpose": stored_file.purpose, "reason": reason},
    )
    await session.delete(stored_file)
    await session.flush()
    if intent is not None:
        await session.delete(intent)
        await session.flush()
    return 1


async def _purge_driver_submission(
    session: AsyncSession,
    *,
    submission_id: UUID,
    cutoff: datetime,
    storage: StorageProvider,
    actor_user_id: UUID | None,
    reason: str,
) -> tuple[int, int]:
    profile_id = await session.scalar(
        select(DriverKycSubmission.driver_profile_id).where(
            DriverKycSubmission.id == submission_id
        )
    )
    if profile_id is None:
        return 0, 0
    await session.scalar(
        select(DriverProfile.id).where(DriverProfile.id == profile_id).with_for_update()
    )
    submission = await session.scalar(
        select(DriverKycSubmission)
        .where(
            DriverKycSubmission.id == submission_id,
            DriverKycSubmission.status.in_(TERMINAL_RETENTION_STATUSES),
            DriverKycSubmission.created_at < cutoff,
        )
        .with_for_update()
    )
    if submission is None:
        return 0, 0
    documents = list(
        (
            await session.scalars(
                select(DriverKycDocument)
                .where(DriverKycDocument.submission_id == submission.id)
                .order_by(DriverKycDocument.stored_file_id)
                .with_for_update()
            )
        ).all()
    )
    file_ids = [document.stored_file_id for document in documents]
    for document in documents:
        await session.delete(document)
    await session.flush()
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="driver.kyc.purged",
        entity_type="driver_kyc_submission",
        entity_id=str(submission.id),
        metadata={"status": submission.status, "version": submission.version, "reason": reason},
    )
    await session.delete(submission)
    await session.flush()
    purged_files = 0
    for file_id in sorted(file_ids, key=str):
        purged_files += await _purge_unreferenced_file(
            session,
            file_id=file_id,
            storage=storage,
            actor_user_id=actor_user_id,
            reason=reason,
        )
    return 1, purged_files


async def _purge_vehicle_submission(
    session: AsyncSession,
    *,
    submission_id: UUID,
    cutoff: datetime,
    storage: StorageProvider,
    actor_user_id: UUID | None,
    reason: str,
) -> tuple[int, int]:
    ownership = (
        await session.execute(
            select(VehicleEvidenceSubmission.vehicle_id, Vehicle.driver_profile_id)
            .join(Vehicle, Vehicle.id == VehicleEvidenceSubmission.vehicle_id)
            .where(VehicleEvidenceSubmission.id == submission_id)
        )
    ).one_or_none()
    if ownership is None:
        return 0, 0
    vehicle_id, profile_id = ownership
    await session.scalar(
        select(DriverProfile.id).where(DriverProfile.id == profile_id).with_for_update()
    )
    await session.scalar(select(Vehicle.id).where(Vehicle.id == vehicle_id).with_for_update())
    submission = await session.scalar(
        select(VehicleEvidenceSubmission)
        .where(
            VehicleEvidenceSubmission.id == submission_id,
            VehicleEvidenceSubmission.status.in_(TERMINAL_RETENTION_STATUSES),
            VehicleEvidenceSubmission.created_at < cutoff,
        )
        .with_for_update()
    )
    if submission is None:
        return 0, 0
    documents = list(
        (
            await session.scalars(
                select(VehicleEvidenceDocument)
                .where(VehicleEvidenceDocument.submission_id == submission.id)
                .order_by(VehicleEvidenceDocument.stored_file_id)
                .with_for_update()
            )
        ).all()
    )
    file_ids = [document.stored_file_id for document in documents]
    for document in documents:
        await session.delete(document)
    await session.flush()
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="driver.vehicle_evidence.purged",
        entity_type="vehicle_evidence_submission",
        entity_id=str(submission.id),
        metadata={"status": submission.status, "version": submission.version, "reason": reason},
    )
    await session.delete(submission)
    await session.flush()
    purged_files = 0
    for file_id in sorted(file_ids, key=str):
        purged_files += await _purge_unreferenced_file(
            session,
            file_id=file_id,
            storage=storage,
            actor_user_id=actor_user_id,
            reason=reason,
        )
    return 1, purged_files


async def purge_terminal_file_kyc(
    session: AsyncSession,
    *,
    storage: StorageProvider,
    retention_days: int | None,
    limit: int,
    dry_run: bool,
    actor_user_id: UUID | None,
    reason: str,
    now: datetime | None = None,
) -> FileKycPurgeResult:
    reason = _reason(reason)
    if limit < 1:
        raise ValueError("File/KYC retention limit must be positive")
    if retention_days is None:
        if not dry_run:
            raise AppError(
                "FILE_KYC_RETENTION_POLICY_REQUIRED",
                "File/KYC retention execution requires an approved configured policy",
                status_code=status.HTTP_409_CONFLICT,
            )
        result = FileKycPurgeResult(False, True, False, 0, 0, 0)
        if actor_user_id is not None:
            await _audit_run(session, result=result, actor_user_id=actor_user_id, reason=reason)
        return result
    if retention_days < 1:
        raise ValueError("File/KYC retention days must be positive")
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(days=retention_days)
    driver_ids, vehicle_ids = await _candidate_ids(session, cutoff=cutoff, limit=limit)
    eligible = len(driver_ids) + len(vehicle_ids)
    if dry_run:
        result = FileKycPurgeResult(True, True, False, eligible, 0, 0)
        await _audit_run(session, result=result, actor_user_id=actor_user_id, reason=reason)
        return result
    if not await _acquire_retention_lock(session):
        return FileKycPurgeResult(True, False, False, eligible, 0, 0)
    purged_submissions = 0
    purged_files = 0
    for submission_id in driver_ids:
        submissions, files = await _purge_driver_submission(
            session,
            submission_id=submission_id,
            cutoff=cutoff,
            storage=storage,
            actor_user_id=actor_user_id,
            reason=reason,
        )
        purged_submissions += submissions
        purged_files += files
    for submission_id in vehicle_ids:
        submissions, files = await _purge_vehicle_submission(
            session,
            submission_id=submission_id,
            cutoff=cutoff,
            storage=storage,
            actor_user_id=actor_user_id,
            reason=reason,
        )
        purged_submissions += submissions
        purged_files += files
    result = FileKycPurgeResult(
        True,
        False,
        True,
        eligible,
        purged_submissions,
        purged_files,
    )
    await _audit_run(session, result=result, actor_user_id=actor_user_id, reason=reason)
    return result


async def _audit_run(
    session: AsyncSession,
    *,
    result: FileKycPurgeResult,
    actor_user_id: UUID | None,
    reason: str,
) -> None:
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action=(
            "file_kyc.retention_dry_run" if result.dry_run else "file_kyc.retention_executed"
        ),
        entity_type="file_kyc_retention",
        entity_id=None,
        metadata={
            "policy_configured": result.policy_configured,
            "eligible_submissions": result.eligible_submissions,
            "purged_submissions": result.purged_submissions,
            "purged_files": result.purged_files,
            "reason": reason,
        },
    )
