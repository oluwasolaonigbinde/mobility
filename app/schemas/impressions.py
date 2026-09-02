from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from app.models.impression import (
    ImpressionEstimateStatus,
    TrafficDensityProfileStatus,
    TrafficDensityProfileType,
)
from app.schemas.drivers import normalize_optional_text
from app.schemas.vehicles import normalize_required_text


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


class TrafficDensityProfileBase(BaseModel):
    name: str = Field(min_length=1)
    description: str | None = None
    profile_type: TrafficDensityProfileType = TrafficDensityProfileType.DEFAULT
    traffic_density_per_km: Decimal = Field(ge=Decimal("0"))
    dwell_impressions_per_minute: Decimal = Field(ge=Decimal("0"))
    road_category_weight: Decimal = Field(default=Decimal("1.0"), ge=Decimal("0"))
    morning_weight: Decimal = Field(default=Decimal("1.0"), ge=Decimal("0"))
    midday_weight: Decimal = Field(default=Decimal("1.0"), ge=Decimal("0"))
    evening_weight: Decimal = Field(default=Decimal("1.0"), ge=Decimal("0"))
    night_weight: Decimal = Field(default=Decimal("0.7"), ge=Decimal("0"))
    target_zone_weight: Decimal = Field(default=Decimal("1.0"), ge=Decimal("0"))
    bonus_zone_weight: Decimal = Field(default=Decimal("1.25"), ge=Decimal("0"))
    exclusion_zone_weight: Decimal = Field(default=Decimal("0.0"), ge=Decimal("0"))
    is_default: bool = False
    status: TrafficDensityProfileStatus = TrafficDensityProfileStatus.ACTIVE
    metadata: dict[str, Any] = Field(default_factory=dict)
    effective_from: datetime | None = None

    @field_validator("name")
    @classmethod
    def trim_name(cls, value: str) -> str:
        return normalize_required_text(value)

    @field_validator("description")
    @classmethod
    def trim_description(cls, value: str | None) -> str | None:
        return normalize_optional_text(value)

    @field_validator("effective_from")
    @classmethod
    def require_effective_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("effective_from must include a timezone offset")
        return value


class TrafficDensityProfileCreate(TrafficDensityProfileBase):
    model_config = ConfigDict(extra="forbid")


class TrafficDensityProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1)
    description: str | None = None
    profile_type: TrafficDensityProfileType | None = None
    traffic_density_per_km: Decimal | None = Field(default=None, ge=Decimal("0"))
    dwell_impressions_per_minute: Decimal | None = Field(default=None, ge=Decimal("0"))
    road_category_weight: Decimal | None = Field(default=None, ge=Decimal("0"))
    morning_weight: Decimal | None = Field(default=None, ge=Decimal("0"))
    midday_weight: Decimal | None = Field(default=None, ge=Decimal("0"))
    evening_weight: Decimal | None = Field(default=None, ge=Decimal("0"))
    night_weight: Decimal | None = Field(default=None, ge=Decimal("0"))
    target_zone_weight: Decimal | None = Field(default=None, ge=Decimal("0"))
    bonus_zone_weight: Decimal | None = Field(default=None, ge=Decimal("0"))
    exclusion_zone_weight: Decimal | None = Field(default=None, ge=Decimal("0"))
    is_default: bool | None = None
    status: TrafficDensityProfileStatus | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    effective_from: datetime | None = None
    expected_revision: int | None = Field(default=None, ge=1)
    expected_value_fingerprint: str | None = Field(
        default=None,
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )

    @field_validator("name")
    @classmethod
    def trim_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return normalize_required_text(value)

    @field_validator("description")
    @classmethod
    def trim_description(cls, value: str | None) -> str | None:
        return normalize_optional_text(value)

    @field_validator("effective_from")
    @classmethod
    def require_effective_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("effective_from must include a timezone offset")
        return value


class TrafficDensityProfileRead(DecimalStringMixin):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    lineage_id: UUID
    revision: int
    effective_from: datetime
    supersedes_id: UUID | None
    value_fingerprint: str
    name: str
    description: str | None
    profile_type: TrafficDensityProfileType
    traffic_density_per_km: Decimal
    dwell_impressions_per_minute: Decimal
    road_category_weight: Decimal
    morning_weight: Decimal
    midday_weight: Decimal
    evening_weight: Decimal
    night_weight: Decimal
    target_zone_weight: Decimal
    bonus_zone_weight: Decimal
    exclusion_zone_weight: Decimal
    is_default: bool
    status: TrafficDensityProfileStatus
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class TrafficDensityProfileListResponse(BaseModel):
    items: list[TrafficDensityProfileRead]
    total: int
    limit: int
    offset: int


class EstimateImpressionsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    traffic_density_profile_id: UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ImpressionEstimateRead(DecimalStringMixin):
    id: UUID
    trip_session_id: UUID
    trip_analytics_id: UUID
    assignment_id: UUID
    campaign_id: UUID
    driver_profile_id: UUID
    vehicle_id: UUID
    traffic_density_profile_id: UUID
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
