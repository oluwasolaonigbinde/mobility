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
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FilePurpose(StrEnum):
    CREATIVE = "creative"


class UploadIntentStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    EXPIRED = "expired"


class FileScanStatus(StrEnum):
    PENDING = "pending"
    CLEAN = "clean"
    INFECTED = "infected"
    ERROR = "error"


class FileUploadIntent(Base):
    __tablename__ = "file_upload_intents"
    __table_args__ = (
        CheckConstraint("purpose IN ('creative')", name="ck_file_upload_intents_purpose"),
        CheckConstraint(
            "status IN ('pending', 'confirmed', 'expired')",
            name="ck_file_upload_intents_status",
        ),
        CheckConstraint(
            "declared_size_bytes > 0", name="ck_file_upload_intents_size_positive"
        ),
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
        Index("ix_file_upload_intents_status_expires", "status", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("advertiser_organizations.id", ondelete="RESTRICT"), nullable=False
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
        CheckConstraint("purpose IN ('creative')", name="ck_stored_files_purpose"),
        CheckConstraint(
            "scan_status IN ('pending', 'clean', 'infected', 'error')",
            name="ck_stored_files_scan_status",
        ),
        CheckConstraint("size_bytes > 0", name="ck_stored_files_size_positive"),
        CheckConstraint("length(checksum_sha256) = 64", name="ck_stored_files_sha256_length"),
        UniqueConstraint("upload_intent_id", name="uq_stored_files_upload_intent"),
        UniqueConstraint("storage_key", name="uq_stored_files_storage_key"),
        Index("ix_stored_files_organization_created", "organization_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    upload_intent_id: Mapped[UUID] = mapped_column(
        ForeignKey("file_upload_intents.id", ondelete="RESTRICT"), nullable=False
    )
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("advertiser_organizations.id", ondelete="RESTRICT"), nullable=False
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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
