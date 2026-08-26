from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EvidenceVerificationType(StrEnum):
    HIGH_EARNER_RENEWAL = "high_earner_renewal"
    CONCURRENT_SESSION = "concurrent_session"
    PHYSICAL_SPOT_CHECK = "physical_spot_check"


class EvidenceVerificationStatus(StrEnum):
    PENDING = "pending"
    SATISFIED = "satisfied"
    MISSED = "missed"
    PASSED = "passed"
    FAILED = "failed"


class EvidenceVerification(Base):
    """Assignment-bound verification work and its durable disposition.

    This records evidence-review decisions. It deliberately does not assert
    that phone location proves a branded vehicle moved.
    """

    __tablename__ = "evidence_verifications"
    __table_args__ = (
        CheckConstraint(
            "verification_type IN ('high_earner_renewal', 'concurrent_session', "
            "'physical_spot_check')",
            name="ck_evidence_verifications_type",
        ),
        CheckConstraint(
            "status IN ('pending', 'satisfied', 'missed', 'passed', 'failed')",
            name="ck_evidence_verifications_status",
        ),
        CheckConstraint(
            "(status = 'pending' AND resolved_at IS NULL AND resolved_by_user_id IS NULL "
            "AND display_proof_id IS NULL AND fraud_flag_id IS NULL) OR "
            "(status = 'satisfied' AND resolved_at IS NOT NULL "
            "AND display_proof_id IS NOT NULL AND fraud_flag_id IS NULL) OR "
            "(status = 'missed' AND resolved_at IS NOT NULL "
            "AND display_proof_id IS NULL AND fraud_flag_id IS NOT NULL) OR "
            "(status = 'passed' AND resolved_at IS NOT NULL "
            "AND resolved_by_user_id IS NOT NULL AND display_proof_id IS NULL "
            "AND fraud_flag_id IS NULL) OR "
            "(status = 'failed' AND resolved_at IS NOT NULL "
            "AND display_proof_id IS NULL AND fraud_flag_id IS NOT NULL)",
            name="ck_evidence_verifications_resolution",
        ),
        CheckConstraint(
            "(verification_type = 'high_earner_renewal' AND due_at IS NOT NULL) OR "
            "(verification_type <> 'high_earner_renewal' AND due_at IS NULL)",
            name="ck_evidence_verifications_due_at",
        ),
        CheckConstraint(
            "(verification_type = 'physical_spot_check' AND issued_by_user_id IS NOT NULL "
            "AND client_request_id IS NOT NULL AND request_fingerprint IS NOT NULL) OR "
            "(verification_type <> 'physical_spot_check' AND client_request_id IS NULL "
            "AND request_fingerprint IS NULL)",
            name="ck_evidence_verifications_request_authority",
        ),
        Index("ix_evidence_verifications_assignment_status", "assignment_id", "status"),
        Index("ix_evidence_verifications_driver_status", "driver_profile_id", "status"),
        Index("ix_evidence_verifications_type_status", "verification_type", "status"),
        Index(
            "uq_evidence_verifications_automatic_source",
            "verification_type",
            "source_trip_session_id",
            unique=True,
            sqlite_where=text("verification_type <> 'physical_spot_check'"),
            postgresql_where=text("verification_type <> 'physical_spot_check'"),
        ),
        Index(
            "uq_evidence_verifications_admin_request",
            "issued_by_user_id",
            "client_request_id",
            unique=True,
            sqlite_where=text("client_request_id IS NOT NULL"),
            postgresql_where=text("client_request_id IS NOT NULL"),
        ),
        Index("ix_evidence_verifications_fraud_flag", "fraud_flag_id"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, default=uuid4, server_default=text("gen_random_uuid()")
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
    source_trip_session_id: Mapped[UUID] = mapped_column(
        ForeignKey("trip_sessions.id", ondelete="RESTRICT"), nullable=False
    )
    verification_type: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    issued_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    resolved_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    client_request_id: Mapped[UUID | None] = mapped_column()
    request_fingerprint: Mapped[str | None] = mapped_column(String(64))
    result_fingerprint: Mapped[str | None] = mapped_column(String(64))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    display_proof_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("display_proofs.id", ondelete="RESTRICT")
    )
    fraud_flag_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("fraud_flags.id", ondelete="RESTRICT")
    )
    result_note: Mapped[str | None] = mapped_column(Text)
    verification_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, default=dict, server_default=text("'{}'"), nullable=False
    )
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
