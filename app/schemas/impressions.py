from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from app.models.impression import (
    ImpressionEstimateStatus,
)


class DecimalStringMixin(BaseModel):
    @field_serializer(
        "traffic_density_per_km",
        "dwell_impressions_per_minute",
        "road_category_weight",
        "morning_weight",
        "midday_weight",
        "evening_weight",
        "night_weight",
        "target_zone_weight",
        "bonus_zone_weight",
        "exclusion_zone_weight",
        "estimated_impressions",
        "base_distance_impressions",
        "dwell_impressions",
        "target_zone_impressions",
        "bonus_zone_impressions",
        "exclusion_zone_adjustment",
        "quality_multiplier",
        "fraud_adjustment_multiplier",
        "confidence_score",
        "average_confidence_score",
        check_fields=False,
    )
    def serialize_decimal(self, value: Decimal | None) -> str | None:
        if value is None:
            return None
        return str(value)


class EstimateImpressionsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metadata: dict[str, Any] = Field(default_factory=dict)


class ImpressionEstimateRead(DecimalStringMixin):
    id: UUID
    trip_session_id: UUID
    trip_analytics_id: UUID
    assignment_id: UUID
    campaign_id: UUID
    driver_profile_id: UUID
    vehicle_id: UUID
    formula_version: str
    is_authoritative: bool
    status: ImpressionEstimateStatus
    estimated_impressions: Decimal
    base_distance_impressions: Decimal
    dwell_impressions: Decimal
    target_zone_impressions: Decimal
    bonus_zone_impressions: Decimal
    exclusion_zone_adjustment: Decimal
    quality_multiplier: Decimal
    fraud_adjustment_multiplier: Decimal
    confidence_score: Decimal
    started_at: datetime | None
    ended_at: datetime | None
    estimated_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class ImpressionEstimateListResponse(BaseModel):
    items: list[ImpressionEstimateRead]
    total: int
    limit: int
    offset: int


class CampaignImpressionSummary(DecimalStringMixin):
    campaign_id: UUID
    formula_version: str
    estimated_impressions: Decimal
    trip_count: int
    estimated_trip_count: int
    insufficient_data_trip_count: int
    excluded_trip_count: int
    average_confidence_score: Decimal
    start_at: datetime | None
    end_at: datetime | None
