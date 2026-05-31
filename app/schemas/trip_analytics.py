from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from app.models.trip_analytics import (
    FraudFlagSeverity,
    FraudFlagStatus,
    FraudFlagType,
    TripAnalyticsStatus,
)


class DecimalStringMixin(BaseModel):
    @field_serializer(
        "distance_m",
        "avg_speed_mps",
        "max_observed_speed_mps",
        "avg_accuracy_m",
        "target_zone_distance_m",
        "bonus_zone_distance_m",
        "exclusion_zone_distance_m",
        "quality_score",
        check_fields=False,
    )
    def serialize_decimal(self, value: Decimal | None) -> str | None:
        if value is None:
            return None
        return str(value)


class AnalyticsRecomputeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metadata: dict[str, Any] = Field(default_factory=dict)


class FraudFlagRead(BaseModel):
    id: UUID
    trip_session_id: UUID
    trip_analytics_id: UUID | None
    assignment_id: UUID
    campaign_id: UUID
    driver_profile_id: UUID
    vehicle_id: UUID
    flag_type: FraudFlagType
    severity: FraudFlagSeverity
    status: FraudFlagStatus
    description: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    detected_at: datetime
    created_at: datetime
    updated_at: datetime


class TripAnalyticsRead(DecimalStringMixin):
    id: UUID
    trip_session_id: UUID
    assignment_id: UUID
    campaign_id: UUID
    driver_profile_id: UUID
    vehicle_id: UUID
    formula_version: str
    status: TripAnalyticsStatus
    ping_count: int
    valid_ping_count: int
    invalid_ping_count: int
    started_at: datetime | None
    ended_at: datetime | None
    first_ping_at: datetime | None
    last_ping_at: datetime | None
    duration_seconds: int
    active_tracking_seconds: int
    moving_seconds: int
    stationary_seconds: int
    distance_m: Decimal
    avg_speed_mps: Decimal | None
    max_observed_speed_mps: Decimal | None
    avg_accuracy_m: Decimal | None
    poor_accuracy_ping_count: int
    target_zone_distance_m: Decimal
    bonus_zone_distance_m: Decimal
    exclusion_zone_distance_m: Decimal
    target_zone_seconds: int
    bonus_zone_seconds: int
    exclusion_zone_seconds: int
    quality_score: Decimal
    computed_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    fraud_flags: list[FraudFlagRead] = Field(default_factory=list)


class FraudFlagListResponse(BaseModel):
    items: list[FraudFlagRead]
    total: int
    limit: int
    offset: int


class DriverTripAnalyticsSummary(DecimalStringMixin):
    trip_id: UUID
    analytics_status: TripAnalyticsStatus
    distance_m: Decimal
    duration_seconds: int
    moving_seconds: int
    stationary_seconds: int
    quality_score: Decimal
    has_flags: bool
    flag_counts: dict[str, int]
