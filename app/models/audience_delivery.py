from datetime import datetime
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
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AudienceDelivery(Base):
    __tablename__ = "audience_deliveries"
    __table_args__ = (
        CheckConstraint(
            "operation IN ('csv_export', 'ad_platform_activation')",
            name="ck_audience_deliveries_operation",
        ),
        CheckConstraint(
            "status = 'completed'", name="ck_audience_deliveries_status"
        ),
        CheckConstraint(
            "length(request_fingerprint) = 64 AND length(payload_sha256) = 64 "
            "AND length(result_sha256) = 64",
            name="ck_audience_deliveries_fingerprints",
        ),
        UniqueConstraint(
            "actor_user_id",
            "operation",
            "idempotency_key",
            name="uq_audience_deliveries_actor_operation_key",
        ),
        Index(
            "ix_audience_deliveries_scope",
            "organization_id",
            "campaign_id",
            "segment_id",
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
    segment_id: Mapped[UUID] = mapped_column(
        ForeignKey("exposure_segments.id", ondelete="RESTRICT"), nullable=False
    )
    actor_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    operation: Mapped[str] = mapped_column(String(32), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(
        JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False
    )
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    result: Mapped[dict] = mapped_column(
        JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False
    )
    result_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    adapter_name: Mapped[str] = mapped_column(String(64), nullable=False)
    synthetic: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(16), default="completed", server_default="completed", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


@event.listens_for(AudienceDelivery, "before_update")
@event.listens_for(AudienceDelivery, "before_delete")
def reject_audience_delivery_mutation(
    _mapper, _connection, _target: AudienceDelivery
) -> None:
    raise ValueError("audience delivery receipts are immutable")
