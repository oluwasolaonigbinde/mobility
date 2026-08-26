from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ExposureCellInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    coverage_cell: str = Field(pattern=r"^grid-[1-9][0-9]*m:-?[0-9]+:-?[0-9]+$", max_length=64)
    window_start_at: datetime
    window_end_at: datetime
    context: Literal["vehicle_transit"]
    distinct_vehicle_count: int = Field(ge=0)
    trip_count: int = Field(ge=0)
    modelled_potential_contacts: Decimal = Field(ge=0, max_digits=20, decimal_places=4)

    @model_validator(mode="after")
    def validate_window(self) -> "ExposureCellInput":
        if (
            self.window_start_at.tzinfo is None
            or self.window_start_at.utcoffset() is None
            or self.window_end_at.tzinfo is None
            or self.window_end_at.utcoffset() is None
        ):
            raise ValueError("Exposure cell windows must be timezone-aware")
        if self.window_start_at >= self.window_end_at:
            raise ValueError("window_start_at must be before window_end_at")
        if self.trip_count < self.distinct_vehicle_count:
            raise ValueError("trip_count cannot be below distinct_vehicle_count")
        return self
