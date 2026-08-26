from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
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
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ExposureScore(Base):
    __tablename__ = "exposure_scores"
    __table_args__ = (
        CheckConstraint(
            "length(formula_fingerprint) = 64 "
            "AND length(input_fingerprint) = 64 "
            "AND length(result_fingerprint) = 64 "
            "AND length(measurement_input_sha256) = 64 "
            "AND length(measurement_result_sha256) = 64 "
            "AND length(measurement_proof_sha256) = 64",
            name="ck_exposure_scores_fingerprints",
        ),
        UniqueConstraint(
            "measurement_run_id",
            "formula_version",
            name="uq_exposure_scores_run_formula",
        ),
        Index(
            "ix_exposure_scores_campaign_history",
            "organization_id",
            "campaign_id",
            "created_at",
        ),
        Index("ix_exposure_scores_reissue", "reissue_of_score_id"),
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
    issued_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    formula_version: Mapped[str] = mapped_column(String(32), nullable=False)
    formula_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False
    )
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    result_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False
    )
    result_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    measurement_input_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    measurement_result_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    measurement_proof_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    reissue_of_score_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("exposure_scores.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


@event.listens_for(ExposureScore, "before_update")
@event.listens_for(ExposureScore, "before_delete")
def reject_exposure_score_mutation(_mapper, _connection, _target: ExposureScore) -> None:
    raise ValueError("exposure scores are immutable")
