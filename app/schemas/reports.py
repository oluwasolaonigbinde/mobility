from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_serializer

from app.models.campaign_assignment import CampaignAssignmentStatus


class DecimalStringMixin(BaseModel):
    @field_serializer(
        "budget_amount",
        "daily_budget_amount",
        "estimated_impressions",
        "average_confidence_score",
        "average_quality_score",
        "final_payout_total",
        "gross_payout_total",
        "total_distance_m",
        "target_zone_distance_m",
        "bonus_zone_distance_m",
        "exclusion_zone_distance_m",
        "distance_m",
        "final_payout",
        "gross_payout",
        "quality_score",
        "confidence_score",
        check_fields=False,
    )
    def serialize_decimal(self, value: Decimal | None) -> str | None:
        if value is None:
            return None
        return str(value)


class DailyMetricItem(DecimalStringMixin):
    date: date
    distance_m: Decimal | None
    vehicle_count: int | None
    trip_count: int | None
    driving_seconds: int | None
    estimated_impressions: Decimal | None
    status: Literal["released", "not_ready", "not_enough_cars"]


class DailyMetricsResponse(BaseModel):
    campaign_id: UUID
    start_at: datetime | None
    end_at: datetime | None
    timezone: str = "Africa/Lagos"
    items: list[DailyMetricItem]
    total: int
    limit: int
    offset: int


class CampaignPerformanceArea(BaseModel):
    area_id: UUID
    name: str
    trip_count: int = Field(ge=0)
    modelled_potential_contacts: str | None


class CampaignPerformanceRead(BaseModel):
    campaign_id: UUID
    areas: list[CampaignPerformanceArea]
    completeness: str
    uncertainty: str


ASSIGNMENT_STATUSES = [status.value for status in CampaignAssignmentStatus] + ["finished"]
