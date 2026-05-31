from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.vehicle import VehicleStatus, VehicleType
from app.schemas.drivers import normalize_optional_text


def normalize_required_text(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError("Value must not be blank")
    return stripped


def normalize_plate_country_code(value: str) -> str:
    normalized = normalize_required_text(value).upper()
    if len(normalized) != 2:
        raise ValueError("Plate country code must be two characters")
    return normalized


def validate_vehicle_year(value: int | None) -> int | None:
    if value is None:
        return None
    max_year = date.today().year + 1
    if value < 1980 or value > max_year:
        raise ValueError(f"Vehicle year must be between 1980 and {max_year}")
    return value


class VehicleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plate_number: str = Field(min_length=1, max_length=32)
    plate_country_code: str = Field(min_length=2, max_length=2)
    vehicle_type: VehicleType
    make: str | None = Field(default=None, max_length=128)
    model: str | None = Field(default=None, max_length=128)
    year: int | None = None
    color: str | None = Field(default=None, max_length=64)
    status: VehicleStatus = VehicleStatus.PENDING
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("plate_number")
    @classmethod
    def trim_plate_number(cls, value: str) -> str:
        return normalize_required_text(value)

    @field_validator("plate_country_code")
    @classmethod
    def uppercase_plate_country_code(cls, value: str) -> str:
        return normalize_plate_country_code(value)

    @field_validator("make", "model", "color")
    @classmethod
    def trim_optional_text(cls, value: str | None) -> str | None:
        return normalize_optional_text(value)

    @field_validator("year")
    @classmethod
    def year_is_reasonable(cls, value: int | None) -> int | None:
        return validate_vehicle_year(value)


class VehicleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plate_number: str | None = Field(default=None, min_length=1, max_length=32)
    plate_country_code: str | None = Field(default=None, min_length=2, max_length=2)
    vehicle_type: VehicleType | None = None
    make: str | None = Field(default=None, max_length=128)
    model: str | None = Field(default=None, max_length=128)
    year: int | None = None
    color: str | None = Field(default=None, max_length=64)
    status: VehicleStatus | None = None
    metadata: dict[str, Any] | None = None

    @field_validator("plate_number")
    @classmethod
    def trim_plate_number(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return normalize_required_text(value)

    @field_validator("plate_country_code")
    @classmethod
    def uppercase_plate_country_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return normalize_plate_country_code(value)

    @field_validator("make", "model", "color")
    @classmethod
    def trim_optional_text(cls, value: str | None) -> str | None:
        return normalize_optional_text(value)

    @field_validator("year")
    @classmethod
    def year_is_reasonable(cls, value: int | None) -> int | None:
        return validate_vehicle_year(value)


class VehicleRead(BaseModel):
    id: UUID
    driver_profile_id: UUID
    plate_number: str
    plate_number_normalized: str
    plate_country_code: str
    vehicle_type: VehicleType
    make: str | None
    model: str | None
    year: int | None
    color: str | None
    status: VehicleStatus
    created_at: datetime
    updated_at: datetime


class VehicleListResponse(BaseModel):
    items: list[VehicleRead]
    total: int
    limit: int
    offset: int


class VehicleDriverSummary(BaseModel):
    id: UUID
    user_id: UUID
    email: str
    full_name: str
    phone: str | None


class AdminVehicleRead(VehicleRead):
    metadata: dict[str, Any] = Field(default_factory=dict)
    driver_profile: VehicleDriverSummary


class AdminVehicleListResponse(BaseModel):
    items: list[AdminVehicleRead]
    total: int
    limit: int
    offset: int
