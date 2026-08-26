import hashlib
import json
from collections.abc import AsyncIterator
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
from app.models.organization import (
    MembershipRole,
    MembershipStatus,
    OrganizationStatus,
)
from app.models.stored_file import (
    FileScanStatus,
    FileUploadIntent,
    StoredFile,
    UploadIntentStatus,
)
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


def _fingerprint(payload: FileUploadCreate) -> str:
    document = payload.model_dump(mode="json")
    return hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


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
    organization_id = await _advertiser_scope(session, actor_user_id=actor_user_id, write=True)
    fingerprint = _fingerprint(payload)
    existing = await session.scalar(
        select(FileUploadIntent).where(
            FileUploadIntent.organization_id == organization_id,
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
            organization_id=organization_id,
            uploader_user_id=actor_user_id,
            client_request_id=payload.client_request_id,
            request_fingerprint=fingerprint,
            purpose=payload.purpose.value,
            original_filename=payload.filename,
            declared_content_type=payload.content_type,
            declared_size_bytes=payload.size_bytes,
            declared_sha256=payload.sha256,
            object_key=f"unconfirmed/{organization_id}/{intent_id}",
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
                    FileUploadIntent.organization_id == organization_id,
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
                    "organization_id": str(organization_id),
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
    intent = await session.scalar(
        select(FileUploadIntent)
        .where(
            FileUploadIntent.id == upload_id,
            FileUploadIntent.organization_id == organization_id,
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
    destination_key = f"managed/{organization_id}/{intent.id}"
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
        organization_id=organization_id,
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
            "organization_id": str(organization_id),
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
        try:
            await storage.delete(intent.object_key)
            await storage.delete(f"managed/{intent.organization_id}/{intent.id}")
        except StorageUnavailable:
            raise _storage_unavailable() from None
        intent.status = UploadIntentStatus.EXPIRED
        await create_audit_event(
            session,
            actor_user_id=None,
            action="stored_file.upload_expired",
            entity_type="file_upload_intent",
            entity_id=str(intent.id),
            metadata={"organization_id": str(intent.organization_id)},
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
            "organization_id": str(stored_file.organization_id),
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
            "organization_id": str(stored_file.organization_id),
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
    if access_purpose not in {"creative_review", "security_review", "incident_response"}:
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
    return await _issue_download(
        session,
        stored_file=stored_file,
        actor_user_id=actor_user_id,
        access_purpose=access_purpose,
        reason=reason,
        storage=storage,
        settings=settings,
    )
