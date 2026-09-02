import re
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_COVERAGE_CELL = re.compile(r"^grid-([1-9][0-9]*)m:-?[0-9]+:-?[0-9]+$")
MIN_AUDIENCE_RESOLUTION_M = 50


class AuthoritativeExposureCell(BaseModel):
    model_config = ConfigDict(extra="forbid")

    coverage_cell: str = Field(pattern=r"^grid-[1-9][0-9]*m:-?[0-9]+:-?[0-9]+$", max_length=64)
    window_start_at: datetime
    window_end_at: datetime
    context: Literal["vehicle_transit"]
    distinct_vehicle_count: int = Field(ge=0)
    trip_count: int = Field(ge=0)
    distinct_day_count: int = Field(ge=0)
    max_contributor_share: Decimal = Field(ge=0, le=1, max_digits=8, decimal_places=7)
    modelled_potential_contacts: Decimal = Field(ge=0, max_digits=20, decimal_places=4)
    formula_version: Literal["audience_exposure_v1"]
    synthetic: bool

    @field_validator("coverage_cell")
    @classmethod
    def validate_resolution(cls, value: str) -> str:
        match = _COVERAGE_CELL.fullmatch(value)
        if match is None or int(match.group(1)) < MIN_AUDIENCE_RESOLUTION_M:
            raise ValueError("Audience cells must use a resolution of at least 50 metres")
        return value

    @model_validator(mode="after")
    def validate_window(self) -> "AuthoritativeExposureCell":
        if (
            self.window_start_at.tzinfo is None
            or self.window_start_at.utcoffset() is None
            or self.window_end_at.tzinfo is None
            or self.window_end_at.utcoffset() is None
        ):
            raise ValueError("Exposure cell windows must be timezone-aware")
        if self.window_start_at >= self.window_end_at:
            raise ValueError("window_start_at must be before window_end_at")
        start_at = self.window_start_at.astimezone(UTC)
        end_at = self.window_end_at.astimezone(UTC)
        if (
            start_at.minute
            or start_at.second
            or start_at.microsecond
            or end_at.minute
            or end_at.second
            or end_at.microsecond
            or (end_at - start_at).total_seconds() % 3_600
        ):
            raise ValueError("Audience windows must be aligned whole UTC hours")
        if self.trip_count < self.distinct_vehicle_count:
            raise ValueError("trip_count cannot be below distinct_vehicle_count")
        if self.distinct_day_count > ((end_at.date() - start_at.date()).days + 1):
            raise ValueError("distinct_day_count cannot exceed the canonical window")
        return self
