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
    event,
    func,
    inspect,
    text,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DataSubjectRequestType(StrEnum):
    ACCESS = "access"
    RECTIFICATION = "rectification"
    ERASURE = "erasure"


class DataSubjectRequestStatus(StrEnum):
    OPEN = "open"
    IDENTITY_VERIFIED = "identity_verified"
    COMPLETED = "completed"


class DataSubjectLocation(StrEnum):
    DATABASE = "database"
    OBJECT_STORAGE = "object_storage"
    DEVICE_QUEUE = "device_queue"
    OPERATIONAL_LOGS = "operational_logs"
    BACKUPS = "backups"
    PROCESSORS = "processors"


class DataSubjectDisposition(StrEnum):
    PROVIDED = "provided"
    RECTIFIED = "rectified"
    ERASED = "erased"
    NOT_FOUND = "not_found"
    RETAINED_EXCEPTION = "retained_exception"


class DataSubjectRequest(Base):
    __tablename__ = "data_subject_requests"
    __table_args__ = (
        CheckConstraint(
            "request_type IN ('access', 'rectification', 'erasure')",
            name="ck_data_subject_requests_type",
        ),
        CheckConstraint(
            "status IN ('open', 'identity_verified', 'completed')",
            name="ck_data_subject_requests_status",
        ),
        CheckConstraint(
            "length(request_fingerprint) = 64",
            name="ck_data_subject_requests_fingerprint",
        ),
        CheckConstraint(
            "(status = 'open' AND identity_verified_at IS NULL "
            "AND identity_verified_by_user_id IS NULL AND completed_at IS NULL "
            "AND completed_by_user_id IS NULL) OR "
            "(status = 'identity_verified' AND identity_verified_at IS NOT NULL "
            "AND identity_verified_by_user_id IS NOT NULL AND completed_at IS NULL "
            "AND completed_by_user_id IS NULL) OR "
            "(status = 'completed' AND identity_verified_at IS NOT NULL "
            "AND identity_verified_by_user_id IS NOT NULL AND completed_at IS NOT NULL "
            "AND completed_by_user_id IS NOT NULL)",
            name="ck_data_subject_requests_lifecycle",
        ),
        UniqueConstraint(
            "opened_by_user_id",
            "client_request_id",
            name="uq_data_subject_requests_actor_request",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, default=uuid4, server_default=text("gen_random_uuid()")
    )
    subject_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    request_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=DataSubjectRequestStatus.OPEN.value,
        server_default=text("'open'"),
    )
    opened_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    client_request_id: Mapped[UUID] = mapped_column(nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    identity_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    identity_verified_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DataSubjectLocationAssessment(Base):
    __tablename__ = "data_subject_location_assessments"
    __table_args__ = (
        CheckConstraint(
            "location IN ('database', 'object_storage', 'device_queue', "
            "'operational_logs', 'backups', 'processors')",
            name="ck_data_subject_location_assessments_location",
        ),
        CheckConstraint(
            "disposition IN ('provided', 'rectified', 'erased', 'not_found', "
            "'retained_exception')",
            name="ck_data_subject_location_assessments_disposition",
        ),
        CheckConstraint("record_count >= 0", name="ck_data_subject_assessments_count"),
        CheckConstraint(
            "length(request_fingerprint) = 64",
            name="ck_data_subject_assessments_fingerprint",
        ),
        CheckConstraint(
            "length(trim(evidence_reference)) > 0",
            name="ck_data_subject_assessments_evidence",
        ),
        CheckConstraint(
            "(disposition = 'retained_exception' AND exception_reference IS NOT NULL "
            "AND length(trim(exception_reference)) > 0) OR "
            "(disposition <> 'retained_exception' AND exception_reference IS NULL)",
            name="ck_data_subject_assessments_exception",
        ),
        UniqueConstraint(
            "request_id", "location", name="uq_data_subject_assessments_request_location"
        ),
        UniqueConstraint(
            "assessed_by_user_id",
            "client_request_id",
            name="uq_data_subject_assessments_actor_request",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, default=uuid4, server_default=text("gen_random_uuid()")
    )
    request_id: Mapped[UUID] = mapped_column(
        ForeignKey("data_subject_requests.id", ondelete="RESTRICT"), nullable=False
    )
    location: Mapped[str] = mapped_column(String(32), nullable=False)
    disposition: Mapped[str] = mapped_column(String(32), nullable=False)
    record_count: Mapped[int] = mapped_column(Integer, nullable=False)
    data_class_counts: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False
    )
    evidence_reference: Mapped[str] = mapped_column(String(255), nullable=False)
    exception_reference: Mapped[str | None] = mapped_column(String(255))
    assessed_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    client_request_id: Mapped[UUID] = mapped_column(nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


_IMMUTABLE_REQUEST_FIELDS = {
    "id",
    "subject_user_id",
    "request_type",
    "opened_by_user_id",
    "client_request_id",
    "request_fingerprint",
    "requested_at",
    "created_at",
}


@event.listens_for(DataSubjectRequest, "before_update")
def validate_dsr_request_transition(_mapper, _connection, target) -> None:
    state = inspect(target)
    if any(state.attrs[field].history.has_changes() for field in _IMMUTABLE_REQUEST_FIELDS):
        raise ValueError("data subject request identity is immutable")

    status_history = state.attrs.status.history
    previous = status_history.deleted[0] if status_history.deleted else None
    lifecycle_changes = {
        field
        for field in {
            "identity_verified_at",
            "identity_verified_by_user_id",
            "completed_at",
            "completed_by_user_id",
        }
        if state.attrs[field].history.has_changes()
    }
    if not status_history.has_changes():
        if lifecycle_changes:
            raise ValueError("data subject request lifecycle evidence is immutable")
        return
    allowed = {
        (DataSubjectRequestStatus.OPEN.value, DataSubjectRequestStatus.IDENTITY_VERIFIED.value),
        (
            DataSubjectRequestStatus.IDENTITY_VERIFIED.value,
            DataSubjectRequestStatus.COMPLETED.value,
        ),
    }
    if (previous, target.status) not in allowed:
        raise ValueError("invalid data subject request status transition")
    if target.status == DataSubjectRequestStatus.IDENTITY_VERIFIED.value:
        if lifecycle_changes != {"identity_verified_at", "identity_verified_by_user_id"}:
            raise ValueError("identity verification evidence must move atomically")
    elif lifecycle_changes != {"completed_at", "completed_by_user_id"}:
        raise ValueError("completion evidence must move atomically")


@event.listens_for(DataSubjectRequest, "before_delete")
def reject_dsr_request_delete(_mapper, _connection, _target) -> None:
    raise ValueError("data subject requests are append-only evidence")


@event.listens_for(DataSubjectLocationAssessment, "before_update")
def reject_dsr_assessment_update(_mapper, _connection, _target) -> None:
    raise ValueError("data subject location assessments are immutable")


@event.listens_for(DataSubjectLocationAssessment, "before_delete")
def reject_dsr_assessment_delete(_mapper, _connection, _target) -> None:
    raise ValueError("data subject location assessments are append-only")
