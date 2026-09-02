import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import case, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette import status

from app.adapters.storage import StorageObjectNotFound, StorageProvider, StorageUnavailable
from app.core.errors import AppError
from app.models.campaign import CampaignCreative
from app.models.kyc import (
    DriverKycDocument,
    DriverKycSubmission,
    KycSubmissionStatus,
    VehicleEvidenceDocument,
    VehicleEvidenceSubmission,
)
from app.models.stored_file import (
    FileUploadIntent,
    StoredFile,
    StoredObjectDeletion,
    StoredObjectDeletionState,
    UploadIntentStatus,
)
from app.services.audit import create_audit_event

_TERMINAL_KYC_STATUSES = {
    KycSubmissionStatus.REJECTED.value,
    KycSubmissionStatus.EXPIRED.value,
}


def _fingerprint(document: dict[str, str]) -> str:
    return hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


async def ensure_stored_object_deletion(
    session: AsyncSession,
    *,
    storage_key: str,
    object_checksum_sha256: str,
    reason: str,
    owner_type: str,
    owner_id: UUID,
    organization_id: UUID | None,
    subject_user_id: UUID | None,
    stored_file_id: UUID | None = None,
    upload_intent_id: UUID | None = None,
) -> StoredObjectDeletion:
    document = {
        "storage_key": storage_key,
        "object_checksum_sha256": object_checksum_sha256,
        "reason": reason,
        "owner_type": owner_type,
        "owner_id": str(owner_id),
        "organization_id": str(organization_id) if organization_id else None,
        "subject_user_id": str(subject_user_id) if subject_user_id else None,
    }
    request_fingerprint = _fingerprint(document)
    existing = await session.scalar(
        select(StoredObjectDeletion).where(
            StoredObjectDeletion.request_fingerprint == request_fingerprint
        )
    )
    if existing is not None:
        return existing
    intent = StoredObjectDeletion(
        stored_file_id=stored_file_id,
        upload_intent_id=upload_intent_id,
        organization_id=organization_id,
        subject_user_id=subject_user_id,
        owner_type=owner_type,
        owner_id=owner_id,
        storage_key=storage_key,
        storage_key_sha256=hashlib.sha256(storage_key.encode()).hexdigest(),
        object_checksum_sha256=object_checksum_sha256.lower(),
        reason=reason,
        request_fingerprint=request_fingerprint,
    )
    session.add(intent)
    await session.flush()
    return intent


async def delete_stored_object(
    session: AsyncSession,
    *,
    intent: StoredObjectDeletion,
    storage: StorageProvider,
) -> None:
    locked = await session.scalar(
        select(StoredObjectDeletion).where(StoredObjectDeletion.id == intent.id).with_for_update()
    )
    if locked is None:
        return
    intent = locked
    if intent.state in {
        StoredObjectDeletionState.PROVIDER_DELETED.value,
        StoredObjectDeletionState.COMPLETED.value,
    }:
        return
    intent.attempts += 1
    intent.last_error_code = None
    try:
        await storage.delete(intent.storage_key)
    except StorageObjectNotFound:
        pass
    except StorageUnavailable:
        intent.last_error_code = "storage_unavailable"
        await session.commit()
        raise AppError(
            "FILE_STORAGE_UNAVAILABLE",
            "Private file storage is unavailable",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        ) from None
    intent.state = StoredObjectDeletionState.PROVIDER_DELETED.value
    intent.provider_deleted_at = datetime.now(UTC)
    await session.commit()


async def _file_is_referenced(session: AsyncSession, file_id: UUID) -> bool:
    checks = (
        select(DriverKycDocument.id).where(DriverKycDocument.stored_file_id == file_id),
        select(VehicleEvidenceDocument.id).where(VehicleEvidenceDocument.stored_file_id == file_id),
        select(CampaignCreative.id).where(CampaignCreative.stored_file_id == file_id),
    )
    for statement in checks:
        if await session.scalar(statement.limit(1)) is not None:
            return True
    return False


async def _finalize_kyc_owner(
    session: AsyncSession,
    *,
    intent: StoredObjectDeletion,
    actor_user_id: UUID | None,
) -> bool:
    owner_config = {
        "driver_kyc_submission": (
            DriverKycSubmission,
            DriverKycDocument,
            "driver.kyc.purged",
        ),
        "vehicle_evidence_submission": (
            VehicleEvidenceSubmission,
            VehicleEvidenceDocument,
            "driver.vehicle_evidence.purged",
        ),
    }.get(intent.owner_type)
    if owner_config is None:
        return False
    submission_model, document_model, audit_action = owner_config
    siblings = list(
        await session.scalars(
            select(StoredObjectDeletion)
            .where(
                StoredObjectDeletion.owner_type == intent.owner_type,
                StoredObjectDeletion.owner_id == intent.owner_id,
            )
            .order_by(StoredObjectDeletion.id)
            .with_for_update()
        )
    )
    if any(
        sibling.state
        not in {
            StoredObjectDeletionState.PROVIDER_DELETED.value,
            StoredObjectDeletionState.COMPLETED.value,
        }
        for sibling in siblings
    ):
        return False
    submission = await session.scalar(
        select(submission_model)
        .where(
            submission_model.id == intent.owner_id,
            submission_model.status.in_(_TERMINAL_KYC_STATUSES),
        )
        .with_for_update()
    )
    if submission is None:
        return False
    documents = list(
        await session.scalars(
            select(document_model)
            .where(document_model.submission_id == submission.id)
            .order_by(document_model.id)
            .with_for_update()
        )
    )
    for document in documents:
        await session.delete(document)
    await session.flush()
    await session.delete(submission)
    await session.flush()
    upload_intent_ids = {
        sibling.upload_intent_id
        for sibling in siblings
        if sibling.upload_intent_id is not None
    }
    for sibling in siblings:
        if sibling.stored_file_id is None:
            continue
        stored_file = await session.scalar(
            select(StoredFile).where(StoredFile.id == sibling.stored_file_id).with_for_update()
        )
        if stored_file is not None and not await _file_is_referenced(session, stored_file.id):
            await create_audit_event(
                session,
                actor_user_id=actor_user_id,
                action="stored_file.purged",
                entity_type="stored_file",
                entity_id=str(stored_file.id),
                metadata={"purpose": stored_file.purpose, "reason": sibling.reason},
            )
            await session.delete(stored_file)
    await session.flush()
    for sibling in siblings:
        sibling.stored_file_id = None
        sibling.upload_intent_id = None
    await session.flush()
    if upload_intent_ids:
        deletion_result = await session.execute(
            delete(FileUploadIntent).where(FileUploadIntent.id.in_(upload_intent_ids))
        )
        if deletion_result.rowcount != len(upload_intent_ids):
            raise RuntimeError("KYC purge could not remove every owned upload intent")
    for sibling in siblings:
        sibling.state = StoredObjectDeletionState.COMPLETED.value
        sibling.completed_at = datetime.now(UTC)
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action=audit_action,
        entity_type=intent.owner_type,
        entity_id=str(submission.id),
        metadata={
            "status": submission.status,
            "version": submission.version,
            "reason": intent.reason,
        },
    )
    return True


async def finalize_stored_object_deletion(
    session: AsyncSession,
    *,
    intent: StoredObjectDeletion,
    actor_user_id: UUID | None = None,
) -> bool:
    if intent.state == StoredObjectDeletionState.COMPLETED.value:
        return True
    if intent.state != StoredObjectDeletionState.PROVIDER_DELETED.value:
        return False
    if await _finalize_kyc_owner(
        session,
        intent=intent,
        actor_user_id=actor_user_id,
    ):
        return True
    now = datetime.now(UTC)
    if intent.stored_file_id is not None:
        stored_file = await session.scalar(
            select(StoredFile).where(StoredFile.id == intent.stored_file_id).with_for_update()
        )
        if stored_file is not None:
            if await _file_is_referenced(session, stored_file.id):
                return False
            upload_intent_id = stored_file.upload_intent_id
            await create_audit_event(
                session,
                actor_user_id=actor_user_id,
                action="stored_file.purged",
                entity_type="stored_file",
                entity_id=str(stored_file.id),
                metadata={"purpose": stored_file.purpose, "reason": intent.reason},
            )
            await session.delete(stored_file)
            await session.flush()
            if upload_intent_id is not None:
                other_file_count = int(
                    await session.scalar(
                        select(func.count(StoredFile.id)).where(
                            StoredFile.upload_intent_id == upload_intent_id
                        )
                    )
                    or 0
                )
                if other_file_count == 0:
                    upload_intent = await session.get(FileUploadIntent, upload_intent_id)
                    if upload_intent is not None:
                        await session.delete(upload_intent)
    elif intent.upload_intent_id is not None:
        siblings = list(
            await session.scalars(
                select(StoredObjectDeletion).where(
                    StoredObjectDeletion.owner_type == intent.owner_type,
                    StoredObjectDeletion.owner_id == intent.owner_id,
                ).with_for_update()
            )
        )
        if any(
            sibling.state
            not in {
                StoredObjectDeletionState.PROVIDER_DELETED.value,
                StoredObjectDeletionState.COMPLETED.value,
            }
            for sibling in siblings
        ):
            return False
        upload_intent = await session.scalar(
            select(FileUploadIntent)
            .where(FileUploadIntent.id == intent.upload_intent_id)
            .with_for_update()
        )
        if upload_intent is not None:
            upload_intent.status = UploadIntentStatus.EXPIRED.value
            await create_audit_event(
                session,
                actor_user_id=actor_user_id,
                action="stored_file.upload_expired",
                entity_type="file_upload_intent",
                entity_id=str(upload_intent.id),
                metadata={"purpose": upload_intent.purpose},
            )
        for sibling in siblings:
            sibling.state = StoredObjectDeletionState.COMPLETED.value
            sibling.completed_at = now
        return True
    intent.state = StoredObjectDeletionState.COMPLETED.value
    intent.completed_at = now
    return True


async def process_stored_object_deletions(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    storage: StorageProvider,
    limit: int,
) -> int:
    completed = 0
    for _ in range(limit):
        async with sessionmaker() as session:
            intent = await session.scalar(
                select(StoredObjectDeletion)
                .where(
                    StoredObjectDeletion.state.in_(
                        [
                            StoredObjectDeletionState.PENDING.value,
                            StoredObjectDeletionState.PROVIDER_DELETED.value,
                        ]
                    )
                )
                .order_by(
                    case(
                        (StoredObjectDeletion.state == StoredObjectDeletionState.PENDING.value, 0),
                        else_=1,
                    ),
                    StoredObjectDeletion.created_at,
                    StoredObjectDeletion.id,
                )
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if intent is None:
                break
            await delete_stored_object(session, intent=intent, storage=storage)
            intent = await session.scalar(
                select(StoredObjectDeletion)
                .where(StoredObjectDeletion.id == intent.id)
                .with_for_update()
            )
            if intent is not None and await finalize_stored_object_deletion(session, intent=intent):
                completed += 1
            await session.commit()
    return completed
