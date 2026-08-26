from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.data_subject_request import (
    DataSubjectDisposition,
    DataSubjectLocation,
    DataSubjectRequestStatus,
    DataSubjectRequestType,
)


class DataSubjectRequestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject_user_id: UUID
    request_type: DataSubjectRequestType
    client_request_id: UUID
    requested_at: datetime

    @field_validator("requested_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("requested_at must include a timezone")
        return value


class DataSubjectLocationAssessmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    disposition: DataSubjectDisposition
    evidence_reference: str = Field(min_length=1, max_length=255)
    exception_reference: str | None = Field(default=None, min_length=1, max_length=255)
    external_record_count: int | None = Field(default=None, ge=0)
    client_request_id: UUID


class DataSubjectLocationAssessmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    location: DataSubjectLocation
    disposition: DataSubjectDisposition
    record_count: int
    data_class_counts: dict[str, int]
    evidence_reference: str
    exception_reference: str | None
    assessed_by_user_id: UUID
    created_at: datetime


class DataSubjectRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    subject_user_id: UUID
    request_type: DataSubjectRequestType
    status: DataSubjectRequestStatus
    opened_by_user_id: UUID
    requested_at: datetime
    identity_verified_at: datetime | None
    identity_verified_by_user_id: UUID | None
    completed_at: datetime | None
    completed_by_user_id: UUID | None
    created_at: datetime


class DataSubjectInventoryRead(BaseModel):
    database: dict[str, int]
    object_storage: dict[str, int]
    manual_locations: list[DataSubjectLocation]
