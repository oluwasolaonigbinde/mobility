from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, Index, String, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DisclosureQueryDecision(Base):
    __tablename__ = "disclosure_query_decisions"
    __table_args__ = (
        CheckConstraint(
            "decision IN ('served', 'suppressed')",
            name="ck_disclosure_query_decisions_decision",
        ),
        UniqueConstraint(
            "principal_hash",
            "scope_hash",
            "query_hash",
            "result_hash",
            name="uq_disclosure_query_decisions_retry",
        ),
        Index(
            "ix_disclosure_query_decisions_scope_history",
            "principal_hash",
            "scope_hash",
            "expires_at",
            "created_at",
        ),
        Index(
            "ix_disclosure_query_decisions_overlap",
            "tenant_id",
            "campaign_id",
            "expires_at",
            "window_start",
            "window_end",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    principal_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    scope_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    query_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    result_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    tenant_id: Mapped[UUID | None] = mapped_column(nullable=True)
    campaign_id: Mapped[UUID | None] = mapped_column(nullable=True)
    output_class: Mapped[str] = mapped_column(String(64), nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str] = mapped_column(String(64), nullable=False)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
