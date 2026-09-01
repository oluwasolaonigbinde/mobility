from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class KycSubmissionStatus(StrEnum):
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class KycReviewReason(StrEnum):
    COMPLETE_CURRENT_EVIDENCE = "complete_current_evidence"
    MISSING_EVIDENCE = "missing_evidence"
    REJECTED_EVIDENCE = "rejected_evidence"
    EXPIRED_EVIDENCE = "expired_evidence"
    UNSAFE_EVIDENCE = "unsafe_evidence"
    IDENTITY_MISMATCH = "identity_mismatch"
    BANK_ACCOUNT_MISMATCH = "bank_account_mismatch"
    UNREADABLE_EVIDENCE = "unreadable_evidence"


class DriverKycDocumentType(StrEnum):
    DRIVER_LICENSE = "driver_license"
    DRIVER_PHOTO = "driver_photo"
    SIGNED_AGREEMENT = "signed_agreement"


class VehicleEvidenceDocumentType(StrEnum):
    REGISTRATION = "registration"
    INSURANCE = "insurance"
    VEHICLE_PHOTO = "vehicle_photo"


class VehicleReviewReason(StrEnum):
    COMPLETE_CURRENT_EVIDENCE = "complete_current_evidence"
    MISSING_EVIDENCE = "missing_evidence"
    UNSAFE_EVIDENCE = "unsafe_evidence"
    EXPIRED_EVIDENCE = "expired_evidence"
    OWNER_MISMATCH = "owner_mismatch"
    VEHICLE_IDENTITY_MISMATCH = "vehicle_identity_mismatch"
    NOT_ROADWORTHY = "not_roadworthy"
    NOT_PILOT_ELIGIBLE = "not_pilot_eligible"
    UNREADABLE_EVIDENCE = "unreadable_evidence"


class DriverKycSubmission(Base):
    __tablename__ = "driver_kyc_submissions"
    __table_args__ = (
        CheckConstraint("version > 0", name="ck_driver_kyc_submissions_version"),
        CheckConstraint(
            "status IN ('pending_review', 'approved', 'rejected', 'expired')",
            name="ck_driver_kyc_submissions_status",
        ),
        CheckConstraint(
            "encryption_algorithm = 'AES-256-GCM'",
            name="ck_driver_kyc_submissions_algorithm",
        ),
        CheckConstraint(
            "encryption_key_version > 0",
            name="ck_driver_kyc_submissions_key_version",
        ),
        CheckConstraint(
            "length(nin_last_four) = 4",
            name="ck_driver_kyc_submissions_nin_last_four",
        ),
        UniqueConstraint(
            "driver_profile_id", "version", name="uq_driver_kyc_submissions_profile_version"
        ),
        UniqueConstraint(
            "driver_profile_id",
            "client_request_id",
            name="uq_driver_kyc_submissions_profile_request",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, default=uuid4, server_default=text("gen_random_uuid()")
    )
    driver_profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("driver_profiles.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    nin_record_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    client_request_id: Mapped[UUID] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    encrypted_nin: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    encryption_algorithm: Mapped[str] = mapped_column(String(32), nullable=False)
    encryption_key_version: Mapped[int] = mapped_column(Integer, nullable=False)
    nin_last_four: Mapped[str] = mapped_column(String(4), nullable=False)
    bank_account_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("payee_bank_account_versions.id", ondelete="RESTRICT"), nullable=False
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DriverKycDocument(Base):
    __tablename__ = "driver_kyc_documents"
    __table_args__ = (
        CheckConstraint(
            "document_type IN ('driver_license', 'driver_photo', 'signed_agreement')",
            name="ck_driver_kyc_documents_type",
        ),
        UniqueConstraint(
            "submission_id", "document_type", name="uq_driver_kyc_documents_submission_type"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, default=uuid4, server_default=text("gen_random_uuid()")
    )
    submission_id: Mapped[UUID] = mapped_column(
        ForeignKey("driver_kyc_submissions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    stored_file_id: Mapped[UUID] = mapped_column(
        ForeignKey("stored_files.id", ondelete="RESTRICT"), nullable=False
    )
    document_type: Mapped[str] = mapped_column(String(32), nullable=False)


class DriverKycReviewDecision(Base):
    """Immutable authorized decision over one exact person/payee submission."""

    __tablename__ = "driver_kyc_review_decisions"
    __table_args__ = (
        CheckConstraint(
            "decision IN ('approved', 'rejected', 'expired')",
            name="ck_driver_kyc_review_decisions_decision",
        ),
        CheckConstraint(
            "reason_code IN ('complete_current_evidence', 'missing_evidence', "
            "'rejected_evidence', 'expired_evidence', 'unsafe_evidence', "
            "'identity_mismatch', 'bank_account_mismatch', 'unreadable_evidence')",
            name="ck_driver_kyc_review_decisions_reason",
        ),
        CheckConstraint(
            "length(request_fingerprint) = 64",
            name="ck_driver_kyc_review_decisions_fingerprint",
        ),
        CheckConstraint(
            "(decision = 'approved' AND reason_code = 'complete_current_evidence' "
            "AND identity_match_confirmed AND bank_account_match_confirmed "
            "AND documents_readable_confirmed) OR "
            "(decision IN ('rejected', 'expired') "
            "AND reason_code <> 'complete_current_evidence')",
            name="ck_driver_kyc_review_decisions_facts",
        ),
        UniqueConstraint("submission_id", name="uq_driver_kyc_review_decisions_submission"),
        UniqueConstraint("client_request_id", name="uq_driver_kyc_review_decisions_client_request"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, default=uuid4, server_default=text("gen_random_uuid()")
    )
    submission_id: Mapped[UUID] = mapped_column(
        ForeignKey("driver_kyc_submissions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    client_request_id: Mapped[UUID] = mapped_column(nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(64), nullable=False)
    identity_match_confirmed: Mapped[bool] = mapped_column(nullable=False)
    bank_account_match_confirmed: Mapped[bool] = mapped_column(nullable=False)
    documents_readable_confirmed: Mapped[bool] = mapped_column(nullable=False)
    decided_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class VehicleEvidenceSubmission(Base):
    __tablename__ = "vehicle_evidence_submissions"
    __table_args__ = (
        CheckConstraint("version > 0", name="ck_vehicle_evidence_submissions_version"),
        CheckConstraint(
            "status IN ('pending_review', 'approved', 'rejected', 'expired')",
            name="ck_vehicle_evidence_submissions_status",
        ),
        UniqueConstraint(
            "vehicle_id", "version", name="uq_vehicle_evidence_submissions_vehicle_version"
        ),
        UniqueConstraint(
            "vehicle_id",
            "client_request_id",
            name="uq_vehicle_evidence_submissions_vehicle_request",
        ),
        UniqueConstraint(
            "created_by_user_id",
            "client_request_id",
            name="uq_vehicle_evidence_submissions_owner_request",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, default=uuid4, server_default=text("gen_random_uuid()")
    )
    vehicle_id: Mapped[UUID] = mapped_column(
        ForeignKey("vehicles.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    client_request_id: Mapped[UUID] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    snapshot_trusted: Mapped[bool] = mapped_column(
        nullable=False, default=True, server_default=text("false")
    )
    plate_number_snapshot: Mapped[str] = mapped_column(String(32), nullable=False)
    plate_number_normalized_snapshot: Mapped[str] = mapped_column(String(32), nullable=False)
    plate_country_code_snapshot: Mapped[str] = mapped_column(String(2), nullable=False)
    vehicle_type_snapshot: Mapped[str] = mapped_column(String(32), nullable=False)
    make_snapshot: Mapped[str | None] = mapped_column(String(128))
    model_snapshot: Mapped[str | None] = mapped_column(String(128))
    year_snapshot: Mapped[int | None] = mapped_column(Integer)
    color_snapshot: Mapped[str | None] = mapped_column(String(64))
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class VehicleEvidenceDocument(Base):
    __tablename__ = "vehicle_evidence_documents"
    __table_args__ = (
        CheckConstraint(
            "document_type IN ('registration', 'insurance', 'vehicle_photo')",
            name="ck_vehicle_evidence_documents_type",
        ),
        UniqueConstraint(
            "submission_id",
            "document_type",
            name="uq_vehicle_evidence_documents_submission_type",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, default=uuid4, server_default=text("gen_random_uuid()")
    )
    submission_id: Mapped[UUID] = mapped_column(
        ForeignKey("vehicle_evidence_submissions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    stored_file_id: Mapped[UUID] = mapped_column(
        ForeignKey("stored_files.id", ondelete="RESTRICT"), nullable=False
    )
    document_type: Mapped[str] = mapped_column(String(32), nullable=False)


class VehicleEvidenceReviewDecision(Base):
    """Append-only authorized decision sequence over one exact vehicle revision."""

    __tablename__ = "vehicle_evidence_review_decisions"
    __table_args__ = (
        CheckConstraint("sequence > 0", name="ck_vehicle_review_decisions_sequence"),
        CheckConstraint(
            "decision IN ('approved', 'rejected', 'expired')",
            name="ck_vehicle_review_decisions_decision",
        ),
        CheckConstraint(
            "reason_code IN ('complete_current_evidence', 'missing_evidence', "
            "'unsafe_evidence', 'expired_evidence', 'owner_mismatch', 'vehicle_identity_mismatch', "
            "'not_roadworthy', 'not_pilot_eligible', 'unreadable_evidence')",
            name="ck_vehicle_review_decisions_reason",
        ),
        CheckConstraint(
            "length(request_fingerprint) = 64",
            name="ck_vehicle_review_decisions_fingerprint",
        ),
        CheckConstraint(
            "(decision = 'approved' AND reason_code = 'complete_current_evidence' "
            "AND owner_match_confirmed AND vehicle_identity_confirmed "
            "AND roadworthy_confirmed AND pilot_car_confirmed "
            "AND documents_readable_confirmed AND valid_until IS NOT NULL) OR "
            "(decision IN ('rejected', 'expired') "
            "AND reason_code <> 'complete_current_evidence')",
            name="ck_vehicle_review_decisions_facts",
        ),
        CheckConstraint(
            "decision = 'expired' OR decided_by_user_id IS NOT NULL",
            name="ck_vehicle_review_decisions_admin_actor",
        ),
        UniqueConstraint(
            "submission_id", "sequence", name="uq_vehicle_review_decisions_submission_sequence"
        ),
        UniqueConstraint("client_request_id", name="uq_vehicle_review_decisions_client_request"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, default=uuid4, server_default=text("gen_random_uuid()")
    )
    submission_id: Mapped[UUID] = mapped_column(
        ForeignKey("vehicle_evidence_submissions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    client_request_id: Mapped[UUID] = mapped_column(nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(64), nullable=False)
    owner_match_confirmed: Mapped[bool] = mapped_column(nullable=False)
    vehicle_identity_confirmed: Mapped[bool] = mapped_column(nullable=False)
    roadworthy_confirmed: Mapped[bool] = mapped_column(nullable=False)
    pilot_car_confirmed: Mapped[bool] = mapped_column(nullable=False)
    documents_readable_confirmed: Mapped[bool] = mapped_column(nullable=False)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
