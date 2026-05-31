from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.trip import TripSessionStatus
from app.schemas.campaigns import ensure_timezone_aware
from app.schemas.drivers import normalize_optional_text
from app.schemas.vehicles import normalize_required_text


class TripStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assignment_id: UUID
    metadata: dict[str, Any] = Field(default_factory=dict)


class TripEndRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    end_reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("end_reason")
    @classmethod
    def trim_end_reason(cls, value: str | None) -> str | None:
        return normalize_optional_text(value)


class LocationPingCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recorded_at: datetime
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    accuracy_m: float | None = Field(default=None, ge=0)
    speed_mps: float | None = Field(default=None, ge=0)
    heading_degrees: float | None = Field(default=None, ge=0, lt=360)
    altitude_m: float | None = Field(default=None, ge=-500, le=10000)
    sequence_number: int | None = Field(default=None, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("recorded_at")
    @classmethod
    def recorded_at_must_be_aware(cls, value: datetime) -> datetime:
        return ensure_timezone_aware(value)


class LocationPingBatchCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idempotency_key: str = Field(min_length=1)
    pings: list[LocationPingCreate] = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("idempotency_key")
    @classmethod
    def trim_idempotency_key(cls, value: str) -> str:
        return normalize_required_text(value)


class TripRead(BaseModel):
    id: UUID
    assignment_id: UUID
    campaign_id: UUID
    driver_profile_id: UUID
    vehicle_id: UUID
    status: TripSessionStatus
    started_at: datetime
    ended_at: datetime | None
    end_reason: str | None = None
    ping_count: int
    first_ping_at: datetime | None
    last_ping_at: datetime | None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class CurrentTripResponse(BaseModel):
    trip: TripRead | None


class LocationPingBatchResponse(BaseModel):
    batch_id: UUID
    trip_id: UUID
    accepted_count: int
    duplicate: bool
