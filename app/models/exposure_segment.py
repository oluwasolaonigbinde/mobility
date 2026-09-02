from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    event,
    func,
    text,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ExposureSegment(Base):
    __tablename__ = "exposure_segments"
    __table_args__ = (
        CheckConstraint("version > 0", name="ck_exposure_segments_version"),
        CheckConstraint(
            "releasable_cell_count >= 0 AND suppressed_cell_count >= 0",
            name="ck_exposure_segments_cell_counts",
        ),
        CheckConstraint(
            "length(facts_fingerprint) = 64 "
            "AND length(snapshot_sha256) = 64 "
            "AND length(source_link_snapshot_sha256) = 64 "
            "AND length(measurement_input_sha256) = 64 "
            "AND length(measurement_result_sha256) = 64 "
            "AND length(measurement_proof_sha256) = 64",
            name="ck_exposure_segments_fingerprints",
        ),
        CheckConstraint(
            "(aggregate_formula_version IS NULL "
            "AND aggregate_authority_sha256 IS NULL "
            "AND disclosure_policy_sha256 IS NULL) OR "
            "(aggregate_formula_version IS NOT NULL "
            "AND aggregate_authority_sha256 IS NOT NULL "
            "AND disclosure_policy_sha256 IS NOT NULL "
            "AND length(trim(aggregate_formula_version)) > 0 "
            "AND length(aggregate_authority_sha256) = 64 "
            "AND length(disclosure_policy_sha256) = 64)",
            name="ck_exposure_segments_governance",
        ),
        UniqueConstraint(
            "source_link_id", "version", name="uq_exposure_segments_link_version"
        ),
        UniqueConstraint(
            "source_link_id",
            "facts_fingerprint",
            name="uq_exposure_segments_link_facts",
        ),
        Index(
            "ix_exposure_segments_scope",
            "organization_id",
            "campaign_id",
            "zone_id",
            "created_at",
        ),
        Index("ix_exposure_segments_reissue", "reissue_of_segment_id"),
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
    zone_id: Mapped[UUID] = mapped_column(
        ForeignKey("campaign_zones.id", ondelete="RESTRICT"), nullable=False
    )
    source_id: Mapped[UUID] = mapped_column(
        ForeignKey("retargeting_sources.id", ondelete="RESTRICT"), nullable=False
    )
    source_link_id: Mapped[UUID] = mapped_column(
        ForeignKey("retargeting_source_links.id", ondelete="RESTRICT"), nullable=False
    )
    measurement_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("measurement_runs.id", ondelete="RESTRICT"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    facts_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    source_link_snapshot_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    measurement_input_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    measurement_result_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    measurement_proof_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_formula_version: Mapped[str | None] = mapped_column(String(64))
    aggregate_authority_sha256: Mapped[str | None] = mapped_column(String(64))
    disclosure_policy_sha256: Mapped[str | None] = mapped_column(String(64))
    synthetic: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    snapshot: Mapped[dict] = mapped_column(
        JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False
    )
    snapshot_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    releasable_cell_count: Mapped[int] = mapped_column(Integer, nullable=False)
    suppressed_cell_count: Mapped[int] = mapped_column(Integer, nullable=False)
    reissue_of_segment_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("exposure_segments.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ExposureSegmentCell(Base):
    __tablename__ = "exposure_segment_cells"
    __table_args__ = (
        CheckConstraint(
            "distinct_vehicle_count >= 0 AND trip_count >= 0 "
            "AND modelled_potential_contacts >= 0",
            name="ck_exposure_segment_cells_counts",
        ),
        CheckConstraint(
            "window_start_at < window_end_at", name="ck_exposure_segment_cells_window"
        ),
        CheckConstraint(
            "(resolution_m IS NULL AND distinct_day_count IS NULL "
            "AND max_contributor_share IS NULL) OR "
            "(resolution_m IS NOT NULL AND distinct_day_count IS NOT NULL "
            "AND max_contributor_share IS NOT NULL "
            "AND resolution_m >= 50 AND distinct_day_count >= 0 "
            "AND max_contributor_share >= 0 AND max_contributor_share <= 1)",
            name="ck_exposure_segment_cells_governance",
        ),
        CheckConstraint(
            "context = 'vehicle_transit'", name="ck_exposure_segment_cells_context"
        ),
        UniqueConstraint(
            "segment_id",
            "coverage_cell",
            "window_start_at",
            "window_end_at",
            "context",
            name="uq_exposure_segment_cells_identity",
        ),
        Index("ix_exposure_segment_cells_segment", "segment_id", "coverage_cell"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, default=uuid4, server_default=text("gen_random_uuid()")
    )
    segment_id: Mapped[UUID] = mapped_column(
        ForeignKey("exposure_segments.id", ondelete="RESTRICT"), nullable=False
    )
    coverage_cell: Mapped[str] = mapped_column(String(64), nullable=False)
    window_start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    context: Mapped[str] = mapped_column(String(32), nullable=False)
    resolution_m: Mapped[int | None] = mapped_column(Integer)
    distinct_vehicle_count: Mapped[int] = mapped_column(Integer, nullable=False)
    trip_count: Mapped[int] = mapped_column(Integer, nullable=False)
    distinct_day_count: Mapped[int | None] = mapped_column(Integer)
    max_contributor_share: Mapped[Decimal | None] = mapped_column(Numeric(8, 7))
    modelled_potential_contacts: Mapped[Decimal] = mapped_column(
        Numeric(20, 4), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


@event.listens_for(ExposureSegment, "before_update")
@event.listens_for(ExposureSegment, "before_delete")
def reject_exposure_segment_mutation(_mapper, _connection, _target: ExposureSegment) -> None:
    raise ValueError("exposure segments are immutable")


@event.listens_for(ExposureSegmentCell, "before_update")
@event.listens_for(ExposureSegmentCell, "before_delete")
def reject_exposure_cell_mutation(_mapper, _connection, _target: ExposureSegmentCell) -> None:
    raise ValueError("exposure segment cells are immutable")
