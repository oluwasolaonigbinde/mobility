from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Index, Integer, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DataPurgeEvent(StrEnum):
    PURGE_STARTED = "purge_started"
    DETACH_FINALIZED = "detach_finalized"
    DROPPED = "dropped"
    BATCHES_PURGED = "batches_purged"
    QUARANTINED_BATCHES_PURGED = "quarantined_batches_purged"


class DataPurgeAudit(Base):
    """Append-only purge-evidence rows (NDPA/NDPR compliance artifact).

    One row per lifecycle event, never updated: the newest event per
    partition is the truth. A partial unique index allows exactly one
    'dropped' row per partition — evidence of destruction can never
    duplicate, while repeated attempts legitimately append repeated
    'purge_started' rows distinguished by job_run_id.
    """

    __tablename__ = "data_purge_audit"
    __table_args__ = (
        CheckConstraint(
            "event IN ('purge_started', 'detach_finalized', 'dropped', 'batches_purged', "
            "'quarantined_batches_purged')",
            name="ck_data_purge_audit_event",
        ),
        CheckConstraint(
            "partition_name IS NOT NULL"
            " OR event IN ('batches_purged', 'quarantined_batches_purged')",
            name="ck_data_purge_audit_partition_name_required",
        ),
        Index(
            "uq_data_purge_audit_dropped",
            "partition_name",
            unique=True,
            sqlite_where=text("event = 'dropped'"),
            postgresql_where=text("event = 'dropped'"),
        ),
        Index("ix_data_purge_audit_partition_created_at", "partition_name", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    partition_name: Mapped[str | None] = mapped_column(Text)
    range_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    range_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    event: Mapped[str] = mapped_column(Text, nullable=False)
    row_count: Mapped[int | None] = mapped_column(BigInteger)
    retention_months: Mapped[int] = mapped_column(Integer, nullable=False)
    initiated_by: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'system'"))
    job_run_id: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
