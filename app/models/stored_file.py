from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    event,
    func,
    inspect,
    select,
    text,
)
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.db.base import Base


class FilePurpose(StrEnum):
    CREATIVE = "creative"
    DRIVER_KYC = "driver_kyc"
    VEHICLE_EVIDENCE = "vehicle_evidence"
    INSTALLATION_EVIDENCE = "installation_evidence"
    REPORT_EXPORT = "report_export"


class UploadIntentStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    EXPIRED = "expired"


class FileScanStatus(StrEnum):
    PENDING = "pending"
    CLEAN = "clean"
    INFECTED = "infected"
    REJECTED = "rejected"
    ERROR = "error"


class StoredObjectDeletionState(StrEnum):
    PENDING = "pending"
    PROVIDER_DELETED = "provider_deleted"
    COMPLETED = "completed"


class FileUploadIntent(Base):
    __tablename__ = "file_upload_intents"
    __table_args__ = (
        CheckConstraint(
            "purpose IN ('creative', 'driver_kyc', 'vehicle_evidence', 'installation_evidence')",
            name="ck_file_upload_intents_purpose",
        ),
        CheckConstraint(
            "(purpose = 'creative' AND organization_id IS NOT NULL "
            "AND subject_user_id IS NULL) OR "
            "(purpose IN ('driver_kyc', 'vehicle_evidence', 'installation_evidence') "
            "AND organization_id IS NULL AND subject_user_id IS NOT NULL)",
            name="ck_file_upload_intents_scope",
        ),
        CheckConstraint(
            "status IN ('pending', 'confirmed', 'expired')",
            name="ck_file_upload_intents_status",
        ),
        CheckConstraint("declared_size_bytes > 0", name="ck_file_upload_intents_size_positive"),
        CheckConstraint(
            "length(declared_sha256) = 64", name="ck_file_upload_intents_sha256_length"
        ),
        UniqueConstraint("object_key", name="uq_file_upload_intents_object_key"),
        UniqueConstraint(
            "organization_id",
            "uploader_user_id",
            "client_request_id",
            name="uq_file_upload_intents_scope_request",
        ),
        UniqueConstraint(
            "subject_user_id",
            "uploader_user_id",
            "client_request_id",
            name="uq_file_upload_intents_subject_request",
        ),
        Index("ix_file_upload_intents_status_expires", "status", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    organization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("advertiser_organizations.id", ondelete="RESTRICT")
    )
    subject_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    uploader_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    client_request_id: Mapped[UUID] = mapped_column(nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    purpose: Mapped[str] = mapped_column(String(32), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    declared_content_type: Mapped[str] = mapped_column(String(255), nullable=False)
    declared_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    declared_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    object_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default=UploadIntentStatus.PENDING, server_default="pending", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class StoredFile(Base):
    __tablename__ = "stored_files"
    __table_args__ = (
        CheckConstraint(
            "purpose IN ('creative', 'driver_kyc', 'vehicle_evidence', "
            "'installation_evidence', 'report_export')",
            name="ck_stored_files_purpose",
        ),
        CheckConstraint(
            "(purpose IN ('creative', 'report_export') AND organization_id IS NOT NULL "
            "AND subject_user_id IS NULL) OR "
            "(purpose IN ('driver_kyc', 'vehicle_evidence', 'installation_evidence') "
            "AND organization_id IS NULL AND subject_user_id IS NOT NULL)",
            name="ck_stored_files_scope",
        ),
        CheckConstraint(
            "scan_status IN ('pending', 'clean', 'infected', 'rejected', 'error')",
            name="ck_stored_files_scan_status",
        ),
        CheckConstraint("size_bytes > 0", name="ck_stored_files_size_positive"),
        CheckConstraint("length(checksum_sha256) = 64", name="ck_stored_files_sha256_length"),
        CheckConstraint(
            "(purpose = 'report_export' AND upload_intent_id IS NULL) OR "
            "(purpose <> 'report_export' AND upload_intent_id IS NOT NULL)",
            name="ck_stored_files_generated_source",
        ),
        UniqueConstraint("upload_intent_id", name="uq_stored_files_upload_intent"),
        UniqueConstraint("storage_key", name="uq_stored_files_storage_key"),
        Index("ix_stored_files_organization_created", "organization_id", "created_at"),
        Index("ix_stored_files_subject_created", "subject_user_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    upload_intent_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("file_upload_intents.id", ondelete="RESTRICT")
    )
    organization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("advertiser_organizations.id", ondelete="RESTRICT")
    )
    subject_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    uploader_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    purpose: Mapped[str] = mapped_column(String(32), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    content_type: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    scan_status: Mapped[str] = mapped_column(
        String(32), default=FileScanStatus.PENDING, server_default="pending", nullable=False
    )
    actual_content_type: Mapped[str | None] = mapped_column(String(255))
    scan_attempts: Mapped[int] = mapped_column(default=0, server_default="0", nullable=False)
    scan_error_code: Mapped[str | None] = mapped_column(String(64))
    malware_signature: Mapped[str | None] = mapped_column(String(255))
    next_scan_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class StoredObjectDeletion(Base):
    __tablename__ = "stored_object_deletions"
    __table_args__ = (
        CheckConstraint(
            "state IN ('pending', 'provider_deleted', 'completed')",
            name="ck_stored_object_deletions_state",
        ),
        CheckConstraint(
            "length(storage_key_sha256) = 64",
            name="ck_stored_object_deletions_key_hash",
        ),
        CheckConstraint(
            "length(object_checksum_sha256) = 64",
            name="ck_stored_object_deletions_object_checksum",
        ),
        CheckConstraint(
            "length(request_fingerprint) = 64",
            name="ck_stored_object_deletions_fingerprint",
        ),
        CheckConstraint(
            "(organization_id IS NOT NULL) <> (subject_user_id IS NOT NULL)",
            name="ck_stored_object_deletions_scope",
        ),
        CheckConstraint(
            "(state = 'pending' AND provider_deleted_at IS NULL AND completed_at IS NULL) OR "
            "(state = 'provider_deleted' AND provider_deleted_at IS NOT NULL "
            "AND completed_at IS NULL) OR "
            "(state = 'completed' AND provider_deleted_at IS NOT NULL "
            "AND completed_at IS NOT NULL)",
            name="ck_stored_object_deletions_timeline",
        ),
        UniqueConstraint(
            "request_fingerprint",
            name="uq_stored_object_deletions_request_fingerprint",
        ),
        Index("ix_stored_object_deletions_state_created", "state", "created_at"),
        Index("ix_stored_object_deletions_owner", "owner_type", "owner_id"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    stored_file_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("stored_files.id", ondelete="SET NULL"), index=True
    )
    upload_intent_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("file_upload_intents.id", ondelete="SET NULL"), index=True
    )
    organization_id: Mapped[UUID | None] = mapped_column(index=True)
    subject_user_id: Mapped[UUID | None] = mapped_column(index=True)
    owner_type: Mapped[str] = mapped_column(String(64), nullable=False)
    owner_id: Mapped[UUID] = mapped_column(nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    storage_key_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    object_checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(String(64), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(
        String(32),
        default=StoredObjectDeletionState.PENDING.value,
        server_default=text("'pending'"),
        nullable=False,
    )
    attempts: Mapped[int] = mapped_column(default=0, server_default=text("0"), nullable=False)
    last_error_code: Mapped[str | None] = mapped_column(String(64))
    provider_deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


_DELETION_RECEIPT_IDENTITY_FIELDS = frozenset(
    {
        "organization_id",
        "subject_user_id",
        "owner_type",
        "owner_id",
        "storage_key",
        "storage_key_sha256",
        "object_checksum_sha256",
        "reason",
        "request_fingerprint",
        "created_at",
    }
)


@event.listens_for(StoredObjectDeletion, "before_update")
def validate_stored_object_deletion_transition(_mapper, _connection, target) -> None:
    state = inspect(target)
    if any(state.attrs[field].history.has_changes() for field in _DELETION_RECEIPT_IDENTITY_FIELDS):
        raise ValueError("stored-object deletion identity is immutable")
    provider_time_changed = state.attrs.provider_deleted_at.history.has_changes()
    completed_time_changed = state.attrs.completed_at.history.has_changes()
    history = state.attrs.state.history
    if not history.has_changes():
        if provider_time_changed or completed_time_changed:
            raise ValueError("stored-object deletion receipt timestamps are write-once")
        return
    before = history.deleted[0] if history.deleted else None
    after = history.added[0] if history.added else None
    if (before, after) not in {
        (
            StoredObjectDeletionState.PENDING.value,
            StoredObjectDeletionState.PROVIDER_DELETED.value,
        ),
        (
            StoredObjectDeletionState.PROVIDER_DELETED.value,
            StoredObjectDeletionState.COMPLETED.value,
        ),
    }:
        raise ValueError("stored-object deletion state transition is invalid")
    if before == StoredObjectDeletionState.PENDING.value:
        if not provider_time_changed or completed_time_changed:
            raise ValueError("stored-object deletion receipt timestamps are write-once")
    elif not completed_time_changed or provider_time_changed:
        raise ValueError("stored-object deletion receipt timestamps are write-once")


@event.listens_for(StoredObjectDeletion, "before_delete")
def reject_stored_object_deletion_delete(_mapper, _connection, _target) -> None:
    raise ValueError("stored-object deletion receipts are append-only")


_STORED_FILE_REFERENCE_MODELS = frozenset(
    {
        "CampaignCreative",
        "DriverKycDocument",
        "VehicleEvidenceDocument",
        "InstallationEvidencePhoto",
        "DisplayProof",
        "ReportArtifact",
    }
)


@event.listens_for(Session, "before_flush")
def reject_reference_to_deleting_stored_object(session, _flush_context, _instances) -> None:
    candidates = [
        item
        for item in session.new.union(session.dirty)
        if type(item).__name__ in _STORED_FILE_REFERENCE_MODELS
        and getattr(item, "stored_file_id", None) is not None
        and (
            item in session.new
            or inspect(item).attrs.stored_file_id.history.has_changes()
        )
    ]
    for item in candidates:
        session.execute(
            select(StoredFile.id)
            .where(StoredFile.id == item.stored_file_id)
            .with_for_update()
        ).first()
        active = session.execute(
            select(StoredObjectDeletion.id)
            .where(
                StoredObjectDeletion.stored_file_id == item.stored_file_id,
                StoredObjectDeletion.state != StoredObjectDeletionState.COMPLETED.value,
            )
            .limit(1)
        ).first()
        if active is not None:
            raise ValueError("stored object has an active deletion intent")


def _is_linked_report_artifact(connection, stored_file_id: UUID) -> bool:
    report_artifacts = Base.metadata.tables.get("report_artifacts")
    if report_artifacts is None:
        return False
    return (
        connection.execute(
            select(report_artifacts.c.id)
            .where(report_artifacts.c.stored_file_id == stored_file_id)
            .limit(1)
        ).first()
        is not None
    )


@event.listens_for(StoredFile, "before_update")
@event.listens_for(StoredFile, "before_delete")
def reject_report_artifact_file_mutation(_mapper, connection, target: StoredFile) -> None:
    if target.id is not None and _is_linked_report_artifact(connection, target.id):
        raise ValueError("report artifact stored file is immutable")
