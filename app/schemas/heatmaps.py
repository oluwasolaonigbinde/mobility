from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, field_serializer


class HeatmapMetric(StrEnum):
    PING_COUNT = "ping_count"
    TRIP_COUNT = "trip_count"
    DISTANCE_M = "distance_m"
    ESTIMATED_IMPRESSIONS = "estimated_impressions"


class HeatmapMetadata(BaseModel):
    metric: HeatmapMetric
    bbox: list[float]
    resolution_m: int
    start_at: datetime | None
    end_at: datetime | None
    generated_at: datetime
    aggregation_version: str = "heatmap_v1"
    aggregation_method: str = "postgis_grid_ping_weighted"
    distance_allocation: str = "trip_distance_allocated_by_ping_share"
    impression_allocation: str = "trip_impressions_allocated_by_ping_share"
    campaign_id: UUID | None = None
    organization_id: UUID | None = None
    vehicle_type: str | None = None


class HeatmapFeatureProperties(BaseModel):
    cell_id: str
    metric: HeatmapMetric
    weight: Decimal
    ping_count: int
    trip_count: int
    distance_m: Decimal
    estimated_impressions: Decimal
    average_quality_score: Decimal

    @field_serializer(
        "weight",
        "distance_m",
        "estimated_impressions",
        "average_quality_score",
    )
    def serialize_decimal(self, value: Decimal) -> str:
        return str(value)


class HeatmapFeature(BaseModel):
    type: str = "Feature"
    geometry: dict[str, Any]
    properties: HeatmapFeatureProperties


class HeatmapFeatureCollection(BaseModel):
    type: str = "FeatureCollection"
    metadata: HeatmapMetadata
    features: list[HeatmapFeature]
