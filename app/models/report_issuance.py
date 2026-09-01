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
    UniqueConstraint,
    event,
    func,
    inspect,
    text,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ReportIssuanceStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class ReportArtifactFormat(StrEnum):
    CSV = "csv"
    PDF = "pdf"


class ReportIssuance(Base):
    __tablename__ = "report_issuances"
    __table_args__ = (
        CheckConstraint("version > 0", name="ck_report_issuances_version_positive"),
        CheckConstraint("worker_attempts >= 0", name="ck_report_issuances_attempts_nonnegative"),
        CheckConstraint(
            "status IN ('queued', 'processing', 'ready', 'failed')",
            name="ck_report_issuances_status",
        ),
        CheckConstraint(
            "roi_decision IN ('OMIT', 'INCLUDE')",
            name="ck_report_issuances_roi_decision",
        ),
        CheckConstraint(
            "length(request_fingerprint) = 64 AND length(snapshot_sha256) = 64 "
            "AND length(authority_fingerprint) = 64 "
            "AND length(input_manifest_sha256) = 64 "
            "AND length(result_manifest_sha256) = 64 "
            "AND length(proof_manifest_sha256) = 64 "
            "AND length(report_snapshot_sha256) = 64",
            name="ck_report_issuances_fingerprints",
        ),
        CheckConstraint(
            "(status = 'processing' AND processing_token IS NOT NULL "
            "AND lease_expires_at IS NOT NULL AND ready_at IS NULL) OR "
            "(status = 'ready' AND processing_token IS NULL "
            "AND lease_expires_at IS NULL AND ready_at IS NOT NULL "
            "AND last_error_code IS NULL) OR "
            "(status = 'failed' AND processing_token IS NULL "
            "AND lease_expires_at IS NULL AND ready_at IS NULL "
            "AND last_error_code IS NOT NULL) OR "
            "(status = 'queued' AND processing_token IS NULL "
            "AND lease_expires_at IS NULL AND ready_at IS NULL)",
            name="ck_report_issuances_status_fields",
        ),
        UniqueConstraint(
            "requested_by_user_id",
            "client_request_id",
            name="uq_report_issuances_actor_request",
        ),
        UniqueConstraint(
            "measurement_run_id",
            "version",
            name="uq_report_issuances_run_version",
        ),
        Index(
            "uq_report_issuances_initial_run",
            "measurement_run_id",
            unique=True,
            postgresql_where=text("reissue_of_id IS NULL"),
            sqlite_where=text("reissue_of_id IS NULL"),
        ),
        Index(
            "ix_report_issuances_due",
            "status",
            "next_attempt_at",
            "lease_expires_at",
            "created_at",
        ),
        Index(
            "ix_report_issuances_scope",
            "organization_id",
            "campaign_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, default=uuid4, server_default=text("gen_random_uuid()")
    )
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("advertiser_organizations.id", ondelete="RESTRICT"), nullable=False
    )
    campaign_id: Mapped[UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="RESTRICT"), nullable=False
    )
    measurement_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("measurement_runs.id", ondelete="RESTRICT"), nullable=False
    )
    requested_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    client_request_id: Mapped[UUID] = mapped_column(nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    reissue_of_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("report_issuances.id", ondelete="RESTRICT")
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False
    )
    snapshot_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    authority_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    input_manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    result_manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    proof_manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    report_snapshot_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    renderer_version: Mapped[str] = mapped_column(String(64), nullable=False)
    method_revision: Mapped[str] = mapped_column(String(255), nullable=False)
    roi_decision: Mapped[str] = mapped_column(String(16), nullable=False)
    synthetic: Mapped[bool] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), default=ReportIssuanceStatus.QUEUED, server_default="queued", nullable=False
    )
    worker_attempts: Mapped[int] = mapped_column(default=0, server_default="0", nullable=False)
    processing_token: Mapped[UUID | None] = mapped_column()
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(64))
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ReportArtifact(Base):
    __tablename__ = "report_artifacts"
    __table_args__ = (
        CheckConstraint("format IN ('csv', 'pdf')", name="ck_report_artifacts_format"),
        CheckConstraint("size_bytes > 0", name="ck_report_artifacts_size_positive"),
        CheckConstraint("length(checksum_sha256) = 64", name="ck_report_artifacts_sha256"),
        UniqueConstraint(
            "report_issuance_id", "format", name="uq_report_artifacts_issuance_format"
        ),
        UniqueConstraint("stored_file_id", name="uq_report_artifacts_stored_file"),
        Index("ix_report_artifacts_issuance", "report_issuance_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, default=uuid4, server_default=text("gen_random_uuid()")
    )
    report_issuance_id: Mapped[UUID] = mapped_column(
        ForeignKey("report_issuances.id", ondelete="RESTRICT"), nullable=False
    )
    stored_file_id: Mapped[UUID] = mapped_column(
        ForeignKey("stored_files.id", ondelete="RESTRICT"), nullable=False
    )
    format: Mapped[str] = mapped_column(String(8), nullable=False)
    content_type: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    renderer_version: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


_ISSUANCE_MUTABLE_FIELDS = frozenset(
    {
        "status",
        "worker_attempts",
        "processing_token",
        "lease_expires_at",
        "next_attempt_at",
        "last_error_code",
        "ready_at",
        "updated_at",
    }
)


@event.listens_for(ReportIssuance, "before_update")
def reject_report_issuance_authority_mutation(_mapper, _connection, target: ReportIssuance) -> None:
    changed = {
        attribute.key for attribute in inspect(target).attrs if attribute.history.has_changes()
    }
    if changed - _ISSUANCE_MUTABLE_FIELDS:
        raise ValueError("report issuance frozen authority is immutable")


@event.listens_for(ReportIssuance, "before_delete")
def reject_report_issuance_delete(_mapper, _connection, _target: ReportIssuance) -> None:
    raise ValueError("report issuances are append-only")


@event.listens_for(ReportArtifact, "before_update")
@event.listens_for(ReportArtifact, "before_delete")
def reject_report_artifact_mutation(_mapper, _connection, _target: ReportArtifact) -> None:
    raise ValueError("report artifacts are immutable")
