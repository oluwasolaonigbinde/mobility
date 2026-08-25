from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class RetargetingSourceLinkCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: UUID
    campaign_id: UUID
    zone_id: UUID
    start_at: datetime
    end_at: datetime

    @field_validator("start_at", "end_at")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            raise ValueError("Link times must include timezone information")
        return value

    @model_validator(mode="after")
    def ordered(self) -> "RetargetingSourceLinkCreate":
        if self.start_at >= self.end_at:
            raise ValueError("start_at must be before end_at")
        return self


class RetargetingSourceLinkSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization_id: UUID
    source_id: UUID
    campaign_id: UUID
    zone_id: UUID
    start_at: datetime
    end_at: datetime
    source_fingerprint: str = Field(min_length=64, max_length=64)
    campaign_fingerprint: str = Field(min_length=64, max_length=64)
    zone_fingerprint: str = Field(min_length=64, max_length=64)

    @field_validator("start_at", "end_at")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            raise ValueError("Snapshot times must include timezone information")
        return value


class RetargetingSourceLinkRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    organization_id: UUID
    source_id: UUID
    campaign_id: UUID
    zone_id: UUID
    start_at: datetime
    end_at: datetime
    status: Literal["active", "removed"]
    stale: bool
    snapshot: RetargetingSourceLinkSnapshot
    snapshot_sha256: str
    created_at: datetime
    removed_at: datetime | None


class RetargetingSourceLinkListRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[RetargetingSourceLinkRead]
    total: int


class RetargetingSourceLinkEventRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    sequence_number: int
    event_type: Literal["created", "removed"]
    snapshot: RetargetingSourceLinkSnapshot
    snapshot_sha256: str
    created_at: datetime


class RetargetingSourceLinkHistoryRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    link: RetargetingSourceLinkRead
    events: list[RetargetingSourceLinkEventRead]
