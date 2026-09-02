from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, field_serializer

from app.models.campaign import CampaignStatus, CreativeStatus
from app.models.campaign_assignment import CampaignAssignmentStatus
from app.models.campaign_zone import CampaignZoneType
from app.models.trip import TripSessionStatus
from app.models.trip_analytics import FraudFlagSeverity, FraudFlagStatus
from app.schemas.exposure_scores import AdvertiserExposureScoreRead
from app.schemas.measurement import MeasurementResultRead, MeasurementRunSummary
from app.schemas.zone_insights import HighExposureZoneInsightsRead


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


class CampaignStatusCounts(BaseModel):
    total: int = 0
    draft: int = 0
    pending_review: int = 0
    approved: int = 0
    rejected: int = 0
    scheduled: int = 0
    active: int = 0
    paused: int = 0
    completed: int = 0
    cancelled: int = 0


class AssignmentStatusCounts(BaseModel):
    total: int = 0
    offered: int = 0
    accepted: int = 0
    active: int = 0
    deactivated: int = 0
    cancelled: int = 0
    completed: int = 0


class TripStatusCounts(BaseModel):
    total: int = 0
    ended: int = 0
    active: int = 0


class ImpressionSummary(DecimalStringMixin):
    estimated_impressions: Decimal
    estimated_trip_count: int
    insufficient_data_trip_count: int
    excluded_trip_count: int
    average_confidence_score: Decimal


class DashboardCostCurrencySummary(DecimalStringMixin):
    currency: str
    final_payout_total: Decimal
    gross_payout_total: Decimal
    ledger_entry_count: int


class CampaignCostCurrencySummary(DashboardCostCurrencySummary):
    calculated_trip_count: int
    blocked_trip_count: int
    insufficient_data_trip_count: int


class DashboardCostSummary(BaseModel):
    totals_by_currency: list[DashboardCostCurrencySummary]


class CampaignCostSummary(BaseModel):
    totals_by_currency: list[CampaignCostCurrencySummary]


class FraudFlagCounts(BaseModel):
    open: int = 0
    acknowledged: int = 0
    confirmed: int = 0
    dismissed: int = 0
    low: int = 0
    medium: int = 0
    high: int = 0


class QualitySummary(DecimalStringMixin):
    average_quality_score: Decimal
    fraud_flags: FraudFlagCounts


class AdvertiserDashboardSummary(BaseModel):
    organization_id: UUID
    currency: str
    start_at: datetime | None
    end_at: datetime | None
    campaigns: CampaignStatusCounts
    assignments: AssignmentStatusCounts
    trips: TripStatusCounts
    impressions: ImpressionSummary
    costs: DashboardCostSummary
    quality: QualitySummary


class CampaignReadSummary(DecimalStringMixin):
    id: UUID
    name: str
    status: CampaignStatus
    start_at: datetime | None
    end_at: datetime | None
    budget_amount: Decimal | None
    daily_budget_amount: Decimal | None
    currency: str


class CreativeStatusCounts(BaseModel):
    total: int = 0
    ready: int = 0
    draft: int = 0
    archived: int = 0


class ZoneTypeCounts(BaseModel):
    total: int = 0
    target: int = 0
    bonus: int = 0
    exclusion: int = 0


class RouteAnalyticsSummary(DecimalStringMixin):
    analyzed_trip_count: int
    total_distance_m: Decimal
    target_zone_distance_m: Decimal
    bonus_zone_distance_m: Decimal
    exclusion_zone_distance_m: Decimal
    average_quality_score: Decimal


class CampaignSummary(BaseModel):
    campaign: CampaignReadSummary
    start_at: datetime | None
    end_at: datetime | None
    creatives: CreativeStatusCounts
    zones: ZoneTypeCounts
    assignments: AssignmentStatusCounts
    trips: TripStatusCounts
    route_analytics: RouteAnalyticsSummary
    impressions: ImpressionSummary
    costs: CampaignCostSummary
    fraud_flags: FraudFlagCounts


class DailyMetricItem(DecimalStringMixin):
    date: date
    trip_count: int
    analyzed_trip_count: int
    distance_m: Decimal
    estimated_impressions: Decimal
    average_confidence_score: Decimal
    final_payout_total: Decimal
    gross_payout_total: Decimal
    open_fraud_flag_count: int
    average_quality_score: Decimal


class DailyMetricsResponse(BaseModel):
    campaign_id: UUID
    start_at: datetime | None
    end_at: datetime | None
    items: list[DailyMetricItem]
    total: int
    limit: int
    offset: int


class CampaignTripsResponse(BaseModel):
    campaign_id: UUID
    trips: TripStatusCounts
    route_analytics: RouteAnalyticsSummary
    impressions: ImpressionSummary
    costs: CampaignCostSummary
    fraud_flags: FraudFlagCounts


class CampaignReportResponse(BaseModel):
    campaign_id: UUID
    start_at: datetime | None
    end_at: datetime | None
    summary: CampaignReadSummary
    daily_metrics: list[DailyMetricItem]
    creative_summary: CreativeStatusCounts
    zone_summary: ZoneTypeCounts
    assignment_summary: AssignmentStatusCounts
    trip_summary: TripStatusCounts
    impression_summary: ImpressionSummary
    cost_summary: CampaignCostSummary
    fraud_summary: FraudFlagCounts
    measurement_run: MeasurementRunSummary | None = None
    measurement_result: MeasurementResultRead | None = None
    exposure_score: AdvertiserExposureScoreRead | None = None
    high_exposure_zone_insights: HighExposureZoneInsightsRead | None = None


CAMPAIGN_STATUSES = [status.value for status in CampaignStatus]
CREATIVE_STATUSES = [status.value for status in CreativeStatus]
ZONE_TYPES = [zone_type.value for zone_type in CampaignZoneType]
ASSIGNMENT_STATUSES = [status.value for status in CampaignAssignmentStatus]
TRIP_STATUSES = [status.value for status in TripSessionStatus]
FRAUD_STATUSES = [status.value for status in FraudFlagStatus]
FRAUD_SEVERITIES = [severity.value for severity in FraudFlagSeverity]
