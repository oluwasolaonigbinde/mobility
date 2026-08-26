from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    event,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MeasurementRunMode(StrEnum):
    PERFORMANCE_ONLY = "performance_only"
    ROI_ENABLED = "roi_enabled"


class MeasurementRun(Base):
    __tablename__ = "measurement_runs"
    __table_args__ = (
        CheckConstraint(
            "mode IN ('performance_only', 'roi_enabled')",
            name="ck_measurement_runs_mode",
        ),
        CheckConstraint(
            "period_start_at < period_end_at",
            name="ck_measurement_runs_period",
        ),
        CheckConstraint(
            "(mode = 'performance_only' AND roi_method_revision IS NULL) OR "
            "(mode = 'roi_enabled' AND roi_method_revision IS NOT NULL "
            "AND length(trim(roi_method_revision)) > 0)",
            name="ck_measurement_runs_roi_method",
        ),
        CheckConstraint(
            "length(input_manifest_sha256) = 64 "
            "AND length(result_manifest_sha256) = 64 "
            "AND length(proof_manifest_sha256) = 64 "
            "AND length(report_snapshot_sha256) = 64 "
            "AND length(request_fingerprint) = 64",
            name="ck_measurement_runs_fingerprints",
        ),
        UniqueConstraint(
            "created_by_user_id",
            "client_request_id",
            name="uq_measurement_runs_actor_request",
        ),
        Index(
            "ix_measurement_runs_campaign_period",
            "campaign_id",
            "period_start_at",
            "period_end_at",
            "created_at",
        ),
        Index("ix_measurement_runs_organization", "organization_id", "created_at"),
        Index("ix_measurement_runs_reissue", "reissue_of_run_id"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("advertiser_organizations.id", ondelete="RESTRICT"), nullable=False
    )
    campaign_id: Mapped[UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="RESTRICT"), nullable=False
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    client_request_id: Mapped[UUID] = mapped_column(nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    test_only: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    formula_version: Mapped[str] = mapped_column(String(64), nullable=False)
    method_revision: Mapped[str] = mapped_column(String(255), nullable=False)
    roi_method_revision: Mapped[str | None] = mapped_column(String(255))
    period_start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    input_manifest: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    input_manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    result_manifest: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    result_manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    proof_manifest: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    proof_manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    report_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    report_snapshot_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    reissue_of_run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("measurement_runs.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class MeasurementRunProofBinding(Base):
    __tablename__ = "measurement_run_proof_bindings"
    __table_args__ = (
        CheckConstraint(
            "length(activation_snapshot_sha256) = 64 AND length(binding_fingerprint) = 64",
            name="ck_measurement_run_proof_binding_fingerprints",
        ),
        UniqueConstraint(
            "measurement_run_id",
            "assignment_id",
            name="uq_measurement_run_proof_assignment",
        ),
        Index("ix_measurement_run_proof_activation", "activation_event_id"),
        Index("ix_measurement_run_proof_creative", "creative_id"),
        Index("ix_measurement_run_proof_evidence", "installation_evidence_submission_id"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    measurement_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("measurement_runs.id", ondelete="RESTRICT"), nullable=False
    )
    assignment_id: Mapped[UUID] = mapped_column(
        ForeignKey("campaign_assignments.id", ondelete="RESTRICT"), nullable=False
    )
    activation_event_id: Mapped[UUID] = mapped_column(
        ForeignKey("campaign_activation_events.id", ondelete="RESTRICT"), nullable=False
    )
    creative_id: Mapped[UUID] = mapped_column(
        ForeignKey("campaign_creatives.id", ondelete="RESTRICT"), nullable=False
    )
    installation_evidence_submission_id: Mapped[UUID] = mapped_column(
        ForeignKey("installation_evidence_submissions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    activation_snapshot_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    binding_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


@event.listens_for(MeasurementRun, "before_update")
@event.listens_for(MeasurementRun, "before_delete")
def reject_measurement_run_mutation(_mapper, _connection, _target: MeasurementRun) -> None:
    raise ValueError("measurement runs are immutable")


@event.listens_for(MeasurementRunProofBinding, "before_update")
@event.listens_for(MeasurementRunProofBinding, "before_delete")
def reject_measurement_proof_mutation(
    _mapper, _connection, _target: MeasurementRunProofBinding
) -> None:
    raise ValueError("measurement run proof bindings are immutable")
