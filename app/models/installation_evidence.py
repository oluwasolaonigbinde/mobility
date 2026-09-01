from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, JSONEmptyObjectServerDefault


class InstallationEvidenceStatus(StrEnum):
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class InstallationEvidenceSubmission(Base):
    __tablename__ = "installation_evidence_submissions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending_review', 'approved', 'rejected', 'expired')",
            name="ck_installation_evidence_status",
        ),
        CheckConstraint("revision > 0", name="ck_installation_evidence_revision_positive"),
        CheckConstraint(
            "(status = 'pending_review' AND reviewed_by_user_id IS NULL "
            "AND reviewed_at IS NULL AND rejection_reason IS NULL "
            "AND approved_until IS NULL) OR "
            "(status = 'approved' AND reviewed_by_user_id IS NOT NULL "
            "AND reviewed_at IS NOT NULL AND rejection_reason IS NULL "
            "AND approved_until IS NOT NULL) OR "
            "(status = 'rejected' AND reviewed_by_user_id IS NOT NULL "
            "AND reviewed_at IS NOT NULL AND rejection_reason IS NOT NULL "
            "AND length(trim(rejection_reason)) > 0 AND approved_until IS NULL) OR "
            "(status = 'expired' AND reviewed_by_user_id IS NOT NULL "
            "AND reviewed_at IS NOT NULL AND rejection_reason IS NULL "
            "AND approved_until IS NOT NULL)",
            name="ck_installation_evidence_review_coherence",
        ),
        UniqueConstraint(
            "assignment_id",
            "revision",
            name="uq_installation_evidence_assignment_revision",
        ),
        UniqueConstraint(
            "assignment_id",
            "submitted_by_user_id",
            "client_request_id",
            name="uq_installation_evidence_request",
        ),
        Index(
            "uq_installation_evidence_assignment_pending",
            "assignment_id",
            unique=True,
            sqlite_where=text("status = 'pending_review'"),
            postgresql_where=text("status = 'pending_review'"),
        ),
        Index(
            "ix_installation_evidence_assignment_status",
            "assignment_id",
            "status",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    assignment_id: Mapped[UUID] = mapped_column(
        ForeignKey("campaign_assignments.id", ondelete="RESTRICT"), nullable=False
    )
    campaign_id: Mapped[UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="RESTRICT"), nullable=False
    )
    driver_profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("driver_profiles.id", ondelete="RESTRICT"), nullable=False
    )
    vehicle_id: Mapped[UUID] = mapped_column(
        ForeignKey("vehicles.id", ondelete="RESTRICT"), nullable=False
    )
    submitted_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    reviewed_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    client_request_id: Mapped[UUID] = mapped_column(nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    device_id: Mapped[UUID] = mapped_column(nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    required_views: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    evidence_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON,
        default=dict,
        server_default=JSONEmptyObjectServerDefault(),
        nullable=False,
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class InstallationEvidencePhoto(Base):
    __tablename__ = "installation_evidence_photos"
    __table_args__ = (
        UniqueConstraint("submission_id", "view_code", name="uq_installation_evidence_photo_view"),
        UniqueConstraint("stored_file_id", name="uq_installation_evidence_photo_file"),
        Index("ix_installation_evidence_photos_submission", "submission_id"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    submission_id: Mapped[UUID] = mapped_column(
        ForeignKey("installation_evidence_submissions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    view_code: Mapped[str] = mapped_column(String(64), nullable=False)
    stored_file_id: Mapped[UUID] = mapped_column(
        ForeignKey("stored_files.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DisplayProofChallenge(Base):
    __tablename__ = "display_proof_challenges"
    __table_args__ = (
        CheckConstraint("expires_at > created_at", name="ck_display_proof_challenge_expiry"),
        UniqueConstraint("nonce_sha256", name="uq_display_proof_challenge_nonce"),
        Index("ix_display_proof_challenge_assignment", "assignment_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    assignment_id: Mapped[UUID] = mapped_column(
        ForeignKey("campaign_assignments.id", ondelete="RESTRICT"), nullable=False
    )
    evidence_submission_id: Mapped[UUID] = mapped_column(
        ForeignKey("installation_evidence_submissions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    driver_profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("driver_profiles.id", ondelete="RESTRICT"), nullable=False
    )
    vehicle_id: Mapped[UUID] = mapped_column(
        ForeignKey("vehicles.id", ondelete="RESTRICT"), nullable=False
    )
    device_id: Mapped[UUID] = mapped_column(nullable=False)
    nonce_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DisplayProof(Base):
    __tablename__ = "display_proofs"
    __table_args__ = (
        CheckConstraint("valid_until > verified_at", name="ck_display_proof_validity"),
        UniqueConstraint("challenge_id", name="uq_display_proofs_challenge"),
        UniqueConstraint("stored_file_id", name="uq_display_proofs_file"),
        Index("ix_display_proofs_assignment_verified", "assignment_id", "verified_at"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    challenge_id: Mapped[UUID] = mapped_column(
        ForeignKey("display_proof_challenges.id", ondelete="RESTRICT"), nullable=False
    )
    assignment_id: Mapped[UUID] = mapped_column(
        ForeignKey("campaign_assignments.id", ondelete="RESTRICT"), nullable=False
    )
    evidence_submission_id: Mapped[UUID] = mapped_column(
        ForeignKey("installation_evidence_submissions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    driver_profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("driver_profiles.id", ondelete="RESTRICT"), nullable=False
    )
    vehicle_id: Mapped[UUID] = mapped_column(
        ForeignKey("vehicles.id", ondelete="RESTRICT"), nullable=False
    )
    device_id: Mapped[UUID] = mapped_column(nullable=False)
    stored_file_id: Mapped[UUID] = mapped_column(
        ForeignKey("stored_files.id", ondelete="RESTRICT"), nullable=False
    )
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    proof_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON,
        default=dict,
        server_default=JSONEmptyObjectServerDefault(),
        nullable=False,
    )
