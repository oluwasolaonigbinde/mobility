import hashlib
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.adapters.scanner import MalwareScanner, MalwareScanVerdict, ScannerUnavailable
from app.adapters.storage import (
    PresignedGet,
    PresignedPost,
    StorageObjectNotFound,
    StorageProvider,
    StorageUnavailable,
)
from app.core.config import Settings
from app.core.errors import AppError
from app.core.middleware import get_request_id
from app.models.campaign_assignment import CampaignAssignment
from app.models.driver import DriverProfile
from app.models.organization import (
    MembershipRole,
    MembershipStatus,
    OrganizationStatus,
)
from app.models.stored_file import (
    FilePurpose,
    FileScanStatus,
    FileUploadIntent,
    StoredFile,
    UploadIntentStatus,
)
from app.models.user import User, UserRole, UserStatus
from app.schemas.stored_files import FileUploadCreate
from app.services.admin_authorization import require_active_admin
from app.services.audit import create_audit_event
from app.services.organizations import get_advertiser_organization_for_user


def _error(code: str, message: str, status_code: int) -> AppError:
    return AppError(code, message, status_code=status_code)


def _storage_unavailable() -> AppError:
    return _error(
        "FILE_STORAGE_UNAVAILABLE",
        "Private file storage is unavailable",
        status.HTTP_503_SERVICE_UNAVAILABLE,
    )


@dataclass(frozen=True, slots=True)
class _FileScope:
    organization_id: UUID | None
    subject_user_id: UUID | None

    @property
    def identity(self) -> UUID:
        identity = self.organization_id or self.subject_user_id
        if identity is None:  # pragma: no cover
            raise RuntimeError("File scope has no identity")
        return identity

    @property
    def label(self) -> str:
        return "organization" if self.organization_id else "subject"

    @property
    def path(self) -> str:
        if self.organization_id is not None:
            return str(self.organization_id)
        return f"subject/{self.identity}"


async def _advertiser_scope(session: AsyncSession, *, actor_user_id: UUID, write: bool) -> UUID:
    context = await get_advertiser_organization_for_user(session, actor_user_id)
    if context is None:
        raise _error("FILE_SCOPE_NOT_FOUND", "File scope was not found", status.HTTP_404_NOT_FOUND)
    organization, membership = context
    if (
        membership.status != MembershipStatus.ACTIVE
        or organization.status != OrganizationStatus.ACTIVE
    ):
        raise _error("FILE_SCOPE_NOT_FOUND", "File scope was not found", status.HTTP_404_NOT_FOUND)
    if write and membership.role not in {MembershipRole.OWNER, MembershipRole.MANAGER}:
        raise _error(
            "ORGANIZATION_WRITE_FORBIDDEN",
            "Owner or manager access is required",
            status.HTTP_403_FORBIDDEN,
        )
    return organization.id


async def _driver_scope(session: AsyncSession, *, actor_user_id: UUID, write: bool) -> _FileScope:
    user_query = select(User).where(User.id == actor_user_id)
    profile_query = select(DriverProfile).where(DriverProfile.user_id == actor_user_id)
    if write:
        user_query = user_query.with_for_update()
        profile_query = profile_query.with_for_update()
    user = await session.scalar(user_query)
    profile = await session.scalar(profile_query)
    if (
        user is None
        or user.role != UserRole.DRIVER
        or user.status != UserStatus.ACTIVE
        or profile is None
    ):
        raise _error("FILE_SCOPE_NOT_FOUND", "File scope was not found", status.HTTP_404_NOT_FOUND)
    return _FileScope(organization_id=None, subject_user_id=user.id)


def _fingerprint(payload: FileUploadCreate) -> str:
    document = payload.model_dump(mode="json")
    return hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _scope_filters(model, scope: _FileScope):
    return (
        model.organization_id == scope.organization_id,
        model.subject_user_id == scope.subject_user_id,
    )


def _scope_metadata(scope: _FileScope) -> dict[str, str]:
    return {f"{scope.label}_id": str(scope.identity)}


def _file_scope(stored_file: StoredFile | FileUploadIntent) -> _FileScope:
    return _FileScope(
        organization_id=stored_file.organization_id,
        subject_user_id=stored_file.subject_user_id,
    )


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _detected_content_type(prefix: bytes) -> str | None:
    if prefix.startswith(b"%PDF-"):
        return "application/pdf"
    if prefix.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if prefix.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(prefix) >= 12 and prefix.startswith(b"RIFF") and prefix[8:12] == b"WEBP":
        return "image/webp"
    if len(prefix) >= 12 and prefix[4:8] == b"ftyp":
        return "video/mp4"
    return None


async def create_advertiser_upload_intent(
    session: AsyncSession,
    *,
    actor_user_id: UUID,
    payload: FileUploadCreate,
    storage: StorageProvider,
    settings: Settings,
) -> tuple[FileUploadIntent, PresignedPost]:
    if payload.purpose != FilePurpose.CREATIVE:
        raise _error(
            "FILE_PURPOSE_FORBIDDEN",
            "The requested file purpose is not allowed for this role",
            status.HTTP_403_FORBIDDEN,
        )
    organization_id = await _advertiser_scope(session, actor_user_id=actor_user_id, write=True)
    return await _create_upload_intent(
        session,
        actor_user_id=actor_user_id,
        payload=payload,
        scope=_FileScope(organization_id=organization_id, subject_user_id=None),
        storage=storage,
        settings=settings,
    )


async def create_driver_upload_intent(
    session: AsyncSession,
    *,
    actor_user_id: UUID,
    payload: FileUploadCreate,
    storage: StorageProvider,
    settings: Settings,
) -> tuple[FileUploadIntent, PresignedPost]:
    allowed_purposes = {FilePurpose.DRIVER_KYC, FilePurpose.VEHICLE_EVIDENCE}
    if "driver" in settings.installation_evidence_uploaders:
        allowed_purposes.add(FilePurpose.INSTALLATION_EVIDENCE)
    if payload.purpose not in allowed_purposes:
        raise _error(
            "FILE_PURPOSE_FORBIDDEN",
            "The requested file purpose is not allowed for this role",
            status.HTTP_403_FORBIDDEN,
        )
    scope = await _driver_scope(session, actor_user_id=actor_user_id, write=True)
    return await _create_upload_intent(
        session,
        actor_user_id=actor_user_id,
        payload=payload,
        scope=scope,
        stored_filename=_safe_subject_filename(payload),
        storage=storage,
        settings=settings,
    )


async def create_application_driver_upload_intent(
    session: AsyncSession,
    *,
    actor_user_id: UUID,
    payload: FileUploadCreate,
    storage: StorageProvider,
    settings: Settings,
) -> tuple[FileUploadIntent, PresignedPost]:
    """Use the shared private upload authority for a referenced invited driver."""

    if payload.purpose != FilePurpose.DRIVER_KYC:
        raise _error(
            "FILE_PURPOSE_FORBIDDEN",
            "Public onboarding accepts driver KYC files only",
            status.HTTP_403_FORBIDDEN,
        )
    user = await session.scalar(select(User).where(User.id == actor_user_id).with_for_update())
    profile = await session.scalar(
        select(DriverProfile).where(DriverProfile.user_id == actor_user_id).with_for_update()
    )
    if (
        user is None
        or user.role != UserRole.DRIVER
        or user.status != UserStatus.INVITED
        or profile is None
    ):
        raise _error("FILE_SCOPE_NOT_FOUND", "File scope was not found", status.HTTP_404_NOT_FOUND)
    scope = _FileScope(organization_id=None, subject_user_id=user.id)
    return await _create_upload_intent(
        session,
        actor_user_id=user.id,
        payload=payload,
        scope=scope,
        stored_filename=_safe_subject_filename(payload),
        storage=storage,
        settings=settings,
    )


async def _assignment_subject_scope(
    session: AsyncSession,
    *,
    assignment_id: UUID,
) -> _FileScope:
    subject_user_id = await session.scalar(
        select(DriverProfile.user_id)
        .join(CampaignAssignment, CampaignAssignment.driver_profile_id == DriverProfile.id)
        .where(CampaignAssignment.id == assignment_id)
    )
    if subject_user_id is None:
        raise _error(
            "CAMPAIGN_ASSIGNMENT_NOT_FOUND",
            "Campaign assignment was not found",
            status.HTTP_404_NOT_FOUND,
        )
    return _FileScope(organization_id=None, subject_user_id=subject_user_id)


async def create_admin_installation_upload_intent(
    session: AsyncSession,
    *,
    actor_user_id: UUID,
    assignment_id: UUID,
    payload: FileUploadCreate,
    storage: StorageProvider,
    settings: Settings,
) -> tuple[FileUploadIntent, PresignedPost]:
    await require_active_admin(session, actor_user_id)
    if (
        "admin" not in settings.installation_evidence_uploaders
        or payload.purpose != FilePurpose.INSTALLATION_EVIDENCE
    ):
        raise _error(
            "FILE_PURPOSE_FORBIDDEN",
            "The requested file purpose is not allowed for this role",
            status.HTTP_403_FORBIDDEN,
        )
    scope = await _assignment_subject_scope(session, assignment_id=assignment_id)
    return await _create_upload_intent(
        session,
        actor_user_id=actor_user_id,
        payload=payload,
        scope=scope,
        stored_filename=_safe_subject_filename(payload),
        storage=storage,
        settings=settings,
    )


def _safe_subject_filename(payload: FileUploadCreate) -> str:
    extensions = {
        "application/pdf": "pdf",
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
        "video/mp4": "mp4",
    }
    return f"{payload.purpose.value.replace('_', '-')}.{extensions[payload.content_type]}"


async def _create_upload_intent(
    session: AsyncSession,
    *,
    actor_user_id: UUID,
    payload: FileUploadCreate,
    scope: _FileScope,
    stored_filename: str | None = None,
    storage: StorageProvider,
    settings: Settings,
) -> tuple[FileUploadIntent, PresignedPost]:
    fingerprint = _fingerprint(payload)
    existing = await session.scalar(
        select(FileUploadIntent).where(
            *_scope_filters(FileUploadIntent, scope),
            FileUploadIntent.uploader_user_id == actor_user_id,
            FileUploadIntent.client_request_id == payload.client_request_id,
        )
    )
    if existing is not None:
        if existing.request_fingerprint != fingerprint:
            raise _error(
                "FILE_UPLOAD_RETRY_CONFLICT",
                "The upload retry does not match the original request",
                status.HTTP_409_CONFLICT,
            )
        if existing.status != UploadIntentStatus.PENDING:
            raise _error(
                "FILE_UPLOAD_ALREADY_CLOSED",
                "The upload request is already closed",
                status.HTTP_409_CONFLICT,
            )
        intent = existing
    else:
        intent_id = uuid4()
        intent = FileUploadIntent(
            id=intent_id,
            organization_id=scope.organization_id,
            subject_user_id=scope.subject_user_id,
            uploader_user_id=actor_user_id,
            client_request_id=payload.client_request_id,
            request_fingerprint=fingerprint,
            purpose=payload.purpose.value,
            # Sensitive subject filenames may themselves contain an identifier;
            # retain only a generated display label while fingerprinting the
            # exact client request for retry conflict detection.
            original_filename=stored_filename or payload.filename,
            declared_content_type=payload.content_type,
            declared_size_bytes=payload.size_bytes,
            declared_sha256=payload.sha256,
            object_key=f"unconfirmed/{scope.path}/{intent_id}",
            expires_at=datetime.now(UTC)
            + timedelta(seconds=settings.object_storage_presign_ttl_seconds),
            status=UploadIntentStatus.PENDING,
        )
        post = await _presign_intent(intent, storage=storage, settings=settings)
        try:
            async with session.begin_nested():
                session.add(intent)
                await session.flush()
        except IntegrityError:
            existing = await session.scalar(
                select(FileUploadIntent).where(
                    *_scope_filters(FileUploadIntent, scope),
                    FileUploadIntent.uploader_user_id == actor_user_id,
                    FileUploadIntent.client_request_id == payload.client_request_id,
                )
            )
            if existing is None:
                raise
            if existing.request_fingerprint != fingerprint:
                raise _error(
                    "FILE_UPLOAD_RETRY_CONFLICT",
                    "The upload retry does not match the original request",
                    status.HTTP_409_CONFLICT,
                ) from None
            intent = existing
            post = await _presign_intent(intent, storage=storage, settings=settings)
        else:
            await create_audit_event(
                session,
                actor_user_id=actor_user_id,
                action="stored_file.upload_requested",
                entity_type="file_upload_intent",
                entity_id=str(intent.id),
                metadata={
                    **_scope_metadata(scope),
                    "purpose": intent.purpose,
                    "size_bytes": intent.declared_size_bytes,
                    "checksum_sha256": intent.declared_sha256,
                },
            )
        return intent, post
    return intent, await _presign_intent(intent, storage=storage, settings=settings)


async def _presign_intent(
    intent: FileUploadIntent,
    *,
    storage: StorageProvider,
    settings: Settings,
) -> PresignedPost:
    remaining_seconds = max(
        1,
        min(
            settings.object_storage_presign_ttl_seconds,
            int((_aware(intent.expires_at) - datetime.now(UTC)).total_seconds()),
        ),
    )
    if _aware(intent.expires_at) <= datetime.now(UTC):
        raise _error("FILE_UPLOAD_EXPIRED", "The upload request has expired", status.HTTP_410_GONE)
    try:
        return await storage.presign_post(
            object_key=intent.object_key,
            content_type=intent.declared_content_type,
            size_bytes=intent.declared_size_bytes,
            checksum_sha256=intent.declared_sha256,
            expires_in_seconds=remaining_seconds,
        )
    except StorageUnavailable:
        raise _storage_unavailable() from None


def _metadata_error(intent: FileUploadIntent, observed) -> AppError | None:
    if observed.size_bytes != intent.declared_size_bytes:
        return _error(
            "FILE_UPLOAD_SIZE_MISMATCH",
            "Uploaded file size does not match the request",
            status.HTTP_409_CONFLICT,
        )
    if observed.content_type.lower() != intent.declared_content_type:
        return _error(
            "FILE_UPLOAD_TYPE_MISMATCH",
            "Uploaded file type does not match the request",
            status.HTTP_409_CONFLICT,
        )
    if observed.checksum_sha256.lower() != intent.declared_sha256:
        return _error(
            "FILE_UPLOAD_CHECKSUM_MISMATCH",
            "Uploaded file checksum does not match the request",
            status.HTTP_409_CONFLICT,
        )
    return None


async def confirm_advertiser_upload(
    session: AsyncSession,
    *,
    actor_user_id: UUID,
    upload_id: UUID,
    storage: StorageProvider,
) -> StoredFile:
    organization_id = await _advertiser_scope(session, actor_user_id=actor_user_id, write=True)
    return await _confirm_upload(
        session,
        actor_user_id=actor_user_id,
        upload_id=upload_id,
        scope=_FileScope(organization_id=organization_id, subject_user_id=None),
        storage=storage,
    )


async def confirm_driver_upload(
    session: AsyncSession,
    *,
    actor_user_id: UUID,
    upload_id: UUID,
    storage: StorageProvider,
) -> StoredFile:
    scope = await _driver_scope(session, actor_user_id=actor_user_id, write=True)
    return await _confirm_upload(
        session,
        actor_user_id=actor_user_id,
        upload_id=upload_id,
        scope=scope,
        storage=storage,
    )


async def confirm_application_driver_upload(
    session: AsyncSession,
    *,
    actor_user_id: UUID,
    upload_id: UUID,
    storage: StorageProvider,
) -> StoredFile:
    user = await session.scalar(select(User).where(User.id == actor_user_id))
    profile = await session.scalar(
        select(DriverProfile).where(DriverProfile.user_id == actor_user_id)
    )
    if (
        user is None
        or user.role != UserRole.DRIVER
        or user.status != UserStatus.INVITED
        or profile is None
    ):
        raise _error("FILE_SCOPE_NOT_FOUND", "File scope was not found", status.HTTP_404_NOT_FOUND)
    return await _confirm_upload(
        session,
        actor_user_id=user.id,
        upload_id=upload_id,
        scope=_FileScope(organization_id=None, subject_user_id=user.id),
        storage=storage,
    )


async def get_application_driver_file(
    session: AsyncSession,
    *,
    actor_user_id: UUID,
    file_id: UUID,
) -> StoredFile:
    user = await session.scalar(select(User).where(User.id == actor_user_id))
    profile = await session.scalar(
        select(DriverProfile).where(DriverProfile.user_id == actor_user_id)
    )
    if (
        user is None
        or user.role != UserRole.DRIVER
        or user.status != UserStatus.INVITED
        or profile is None
    ):
        raise _error("FILE_SCOPE_NOT_FOUND", "File scope was not found", status.HTTP_404_NOT_FOUND)
    stored_file = await session.scalar(
        select(StoredFile).where(
            StoredFile.id == file_id,
            StoredFile.subject_user_id == actor_user_id,
            StoredFile.organization_id.is_(None),
            StoredFile.purpose == FilePurpose.DRIVER_KYC,
        )
    )
    if stored_file is None:
        raise _error("FILE_NOT_FOUND", "Managed file was not found", status.HTTP_404_NOT_FOUND)
    return stored_file


async def confirm_admin_installation_upload(
    session: AsyncSession,
    *,
    actor_user_id: UUID,
    assignment_id: UUID,
    upload_id: UUID,
    storage: StorageProvider,
    settings: Settings,
) -> StoredFile:
    await require_active_admin(session, actor_user_id)
    if "admin" not in settings.installation_evidence_uploaders:
        raise _error(
            "FILE_PURPOSE_FORBIDDEN",
            "The requested file purpose is not allowed for this role",
            status.HTTP_403_FORBIDDEN,
        )
    scope = await _assignment_subject_scope(session, assignment_id=assignment_id)
    intent = await session.scalar(
        select(FileUploadIntent).where(
            FileUploadIntent.id == upload_id,
            *_scope_filters(FileUploadIntent, scope),
            FileUploadIntent.uploader_user_id == actor_user_id,
            FileUploadIntent.purpose == FilePurpose.INSTALLATION_EVIDENCE.value,
        )
    )
    if intent is None:
        raise _error(
            "FILE_UPLOAD_NOT_FOUND", "File upload was not found", status.HTTP_404_NOT_FOUND
        )
    return await _confirm_upload(
        session,
        actor_user_id=actor_user_id,
        upload_id=upload_id,
        scope=scope,
        storage=storage,
    )


async def _confirm_upload(
    session: AsyncSession,
    *,
    actor_user_id: UUID,
    upload_id: UUID,
    scope: _FileScope,
    storage: StorageProvider,
) -> StoredFile:
    intent = await session.scalar(
        select(FileUploadIntent)
        .where(
            FileUploadIntent.id == upload_id,
            *_scope_filters(FileUploadIntent, scope),
        )
        .with_for_update()
    )
    if intent is None:
        raise _error(
            "FILE_UPLOAD_NOT_FOUND", "File upload was not found", status.HTTP_404_NOT_FOUND
        )
    existing = await session.scalar(
        select(StoredFile).where(StoredFile.upload_intent_id == intent.id)
    )
    if existing is not None:
        return existing
    if intent.status == UploadIntentStatus.EXPIRED or _aware(intent.expires_at) <= datetime.now(
        UTC
    ):
        raise _error("FILE_UPLOAD_EXPIRED", "The upload request has expired", status.HTTP_410_GONE)
    try:
        observed = await storage.stat(intent.object_key)
    except StorageObjectNotFound:
        raise _error(
            "FILE_UPLOAD_OBJECT_MISSING",
            "The uploaded file was not found",
            status.HTTP_409_CONFLICT,
        ) from None
    except StorageUnavailable:
        raise _storage_unavailable() from None
    mismatch = _metadata_error(intent, observed)
    if mismatch is not None:
        raise mismatch
    destination_key = f"managed/{scope.path}/{intent.id}"
    try:
        promoted = await storage.promote(
            source_key=intent.object_key,
            destination_key=destination_key,
        )
    except StorageObjectNotFound:
        raise _error(
            "FILE_UPLOAD_OBJECT_MISSING",
            "The uploaded file was not found",
            status.HTTP_409_CONFLICT,
        ) from None
    except StorageUnavailable:
        raise _storage_unavailable() from None
    mismatch = _metadata_error(intent, promoted)
    if mismatch is not None:
        raise mismatch
    stored_file = StoredFile(
        id=uuid4(),
        upload_intent_id=intent.id,
        organization_id=scope.organization_id,
        subject_user_id=scope.subject_user_id,
        uploader_user_id=actor_user_id,
        purpose=intent.purpose,
        original_filename=intent.original_filename,
        storage_key=destination_key,
        content_type=promoted.content_type.lower(),
        size_bytes=promoted.size_bytes,
        checksum_sha256=promoted.checksum_sha256.lower(),
        scan_status=FileScanStatus.PENDING,
    )
    session.add(stored_file)
    intent.status = UploadIntentStatus.CONFIRMED
    await session.flush()
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="stored_file.confirmed",
        entity_type="stored_file",
        entity_id=str(stored_file.id),
        metadata={
            **_scope_metadata(scope),
            "purpose": stored_file.purpose,
            "size_bytes": stored_file.size_bytes,
            "checksum_sha256": stored_file.checksum_sha256,
        },
    )
    return stored_file


async def get_advertiser_stored_file(
    session: AsyncSession, *, actor_user_id: UUID, file_id: UUID
) -> StoredFile:
    organization_id = await _advertiser_scope(session, actor_user_id=actor_user_id, write=False)
    stored_file = await session.scalar(
        select(StoredFile).where(
            StoredFile.id == file_id,
            StoredFile.organization_id == organization_id,
        )
    )
    if stored_file is None:
        raise _error(
            "STORED_FILE_NOT_FOUND", "Stored file was not found", status.HTTP_404_NOT_FOUND
        )
    return stored_file


async def get_driver_stored_file(
    session: AsyncSession, *, actor_user_id: UUID, file_id: UUID
) -> StoredFile:
    scope = await _driver_scope(session, actor_user_id=actor_user_id, write=False)
    stored_file = await session.scalar(
        select(StoredFile).where(StoredFile.id == file_id, *_scope_filters(StoredFile, scope))
    )
    if stored_file is None:
        raise _error(
            "STORED_FILE_NOT_FOUND", "Stored file was not found", status.HTTP_404_NOT_FOUND
        )
    return stored_file


async def purge_expired_upload_intents(
    session: AsyncSession,
    *,
    storage: StorageProvider,
    limit: int,
) -> int:
    now = datetime.now(UTC)
    intents = list(
        (
            await session.scalars(
                select(FileUploadIntent)
                .where(
                    FileUploadIntent.status == UploadIntentStatus.PENDING,
                    FileUploadIntent.expires_at <= now,
                )
                .order_by(FileUploadIntent.expires_at, FileUploadIntent.id)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        ).all()
    )
    for intent in intents:
        scope = _file_scope(intent)
        try:
            await storage.delete(intent.object_key)
            await storage.delete(f"managed/{scope.path}/{intent.id}")
        except StorageUnavailable:
            raise _storage_unavailable() from None
        intent.status = UploadIntentStatus.EXPIRED
        await create_audit_event(
            session,
            actor_user_id=None,
            action="stored_file.upload_expired",
            entity_type="file_upload_intent",
            entity_id=str(intent.id),
            metadata=_scope_metadata(scope),
        )
    await session.flush()
    return len(intents)


async def scan_stored_file(
    session: AsyncSession,
    *,
    file_id: UUID,
    storage: StorageProvider,
    scanner: MalwareScanner,
) -> FileScanStatus | None:
    stored_file = await session.scalar(
        select(StoredFile).where(StoredFile.id == file_id).with_for_update(skip_locked=True)
    )
    if stored_file is None:
        return None
    current_status = FileScanStatus(stored_file.scan_status)
    if current_status in {
        FileScanStatus.CLEAN,
        FileScanStatus.INFECTED,
        FileScanStatus.REJECTED,
    }:
        return current_status

    prefix = bytearray()
    observed_size = 0

    async def observed_chunks() -> AsyncIterator[bytes]:
        nonlocal observed_size
        async for chunk in storage.stream(stored_file.storage_key):
            observed_size += len(chunk)
            if len(prefix) < 32:
                prefix.extend(chunk[: 32 - len(prefix)])
            yield chunk

    stored_file.scan_attempts += 1
    stored_file.scan_error_code = None
    stored_file.malware_signature = None
    stored_file.next_scan_at = None
    try:
        result = await scanner.scan(observed_chunks())
    except (ScannerUnavailable, StorageUnavailable, StorageObjectNotFound) as exc:
        stored_file.scan_status = FileScanStatus.ERROR
        stored_file.scan_error_code = (
            "stored_object_missing"
            if isinstance(exc, StorageObjectNotFound)
            else "scanner_or_storage_unavailable"
        )
        stored_file.next_scan_at = datetime.now(UTC) + timedelta(
            seconds=min(60 * (2 ** min(stored_file.scan_attempts - 1, 5)), 3600)
        )
    else:
        actual_type = _detected_content_type(bytes(prefix))
        stored_file.actual_content_type = actual_type
        if result.verdict == MalwareScanVerdict.INFECTED:
            stored_file.scan_status = FileScanStatus.INFECTED
            stored_file.malware_signature = result.signature
            stored_file.scanned_at = datetime.now(UTC)
        elif (
            observed_size != stored_file.size_bytes
            or actual_type is None
            or actual_type != stored_file.content_type
        ):
            stored_file.scan_status = FileScanStatus.REJECTED
            stored_file.scan_error_code = "observed_metadata_mismatch"
            stored_file.scanned_at = datetime.now(UTC)
        else:
            stored_file.scan_status = FileScanStatus.CLEAN
            stored_file.scanned_at = datetime.now(UTC)

    await create_audit_event(
        session,
        actor_user_id=None,
        action="stored_file.scan_completed",
        entity_type="stored_file",
        entity_id=str(stored_file.id),
        metadata={
            **_scope_metadata(_file_scope(stored_file)),
            "status": stored_file.scan_status,
            "attempt": stored_file.scan_attempts,
            "error_code": stored_file.scan_error_code,
        },
    )
    await session.flush()
    return FileScanStatus(stored_file.scan_status)


def _require_cleared(stored_file: StoredFile) -> None:
    if stored_file.scan_status != FileScanStatus.CLEAN:
        raise _error(
            "STORED_FILE_NOT_CLEARED",
            "The stored file has not passed mandatory security checks",
            status.HTTP_409_CONFLICT,
        )


async def _issue_download(
    session: AsyncSession,
    *,
    stored_file: StoredFile,
    actor_user_id: UUID,
    access_purpose: str,
    reason: str,
    storage: StorageProvider,
    settings: Settings,
) -> PresignedGet:
    _require_cleared(stored_file)
    try:
        download = await storage.presign_get(
            object_key=stored_file.storage_key,
            expires_in_seconds=settings.object_storage_download_ttl_seconds,
        )
    except StorageUnavailable:
        raise _storage_unavailable() from None
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="stored_file.read",
        entity_type="stored_file",
        entity_id=str(stored_file.id),
        metadata={
            **_scope_metadata(_file_scope(stored_file)),
            "file_purpose": stored_file.purpose,
            "access_purpose": access_purpose,
            "reason": reason,
            "request_id": get_request_id(),
        },
    )
    return download


async def issue_advertiser_file_download(
    session: AsyncSession,
    *,
    actor_user_id: UUID,
    file_id: UUID,
    access_purpose: str,
    reason: str,
    storage: StorageProvider,
    settings: Settings,
) -> PresignedGet:
    if access_purpose != "campaign_preview":
        raise _error(
            "FILE_ACCESS_PURPOSE_FORBIDDEN",
            "The requested file-access purpose is not allowed for this role",
            status.HTTP_403_FORBIDDEN,
        )
    organization_id = await _advertiser_scope(session, actor_user_id=actor_user_id, write=False)
    stored_file = await session.scalar(
        select(StoredFile).where(
            StoredFile.id == file_id,
            StoredFile.organization_id == organization_id,
        )
    )
    if stored_file is None:
        raise _error(
            "STORED_FILE_NOT_FOUND", "Stored file was not found", status.HTTP_404_NOT_FOUND
        )
    return await _issue_download(
        session,
        stored_file=stored_file,
        actor_user_id=actor_user_id,
        access_purpose=access_purpose,
        reason=reason,
        storage=storage,
        settings=settings,
    )


async def issue_admin_file_download(
    session: AsyncSession,
    *,
    actor_user_id: UUID,
    file_id: UUID,
    access_purpose: str,
    reason: str,
    storage: StorageProvider,
    settings: Settings,
) -> PresignedGet:
    await require_active_admin(session, actor_user_id)
    if access_purpose not in {
        "creative_review",
        "kyc_review",
        "installation_review",
        "security_review",
        "incident_response",
    }:
        raise _error(
            "FILE_ACCESS_PURPOSE_FORBIDDEN",
            "The requested file-access purpose is not allowed for this role",
            status.HTTP_403_FORBIDDEN,
        )
    stored_file = await session.scalar(select(StoredFile).where(StoredFile.id == file_id))
    if stored_file is None:
        raise _error(
            "STORED_FILE_NOT_FOUND", "Stored file was not found", status.HTTP_404_NOT_FOUND
        )
    if (
        (access_purpose == "creative_review" and stored_file.purpose != FilePurpose.CREATIVE)
        or (
            access_purpose == "kyc_review"
            and stored_file.purpose not in {FilePurpose.DRIVER_KYC, FilePurpose.VEHICLE_EVIDENCE}
        )
        or (
            access_purpose == "installation_review"
            and stored_file.purpose != FilePurpose.INSTALLATION_EVIDENCE
        )
    ):
        raise _error(
            "FILE_ACCESS_PURPOSE_FORBIDDEN",
            "The requested file-access purpose does not match this file",
            status.HTTP_403_FORBIDDEN,
        )
    return await _issue_download(
        session,
        stored_file=stored_file,
        actor_user_id=actor_user_id,
        access_purpose=access_purpose,
        reason=reason,
        storage=storage,
        settings=settings,
    )
