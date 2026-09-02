from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query
from starlette import status

from app.api.v1.dependencies import AdvertiserUserDependency, SessionDependency, SettingsDependency
from app.core.errors import AppError
from app.schemas.campaigns import ensure_timezone_aware
from app.schemas.reports import (
    AdvertiserDashboardSummary,
    CampaignReportResponse,
    CampaignSummary,
    CampaignTripsResponse,
    DailyMetricsResponse,
)
from app.services.reports import (
    advertiser_campaign_report,
    advertiser_campaign_summary,
    advertiser_campaign_trips,
    advertiser_dashboard_summary,
    daily_metrics_for_campaign,
)

router = APIRouter(tags=["Advertiser Reports"])


def ensure_report_datetime(value: datetime | None, field_name: str) -> datetime | None:
    try:
        return ensure_timezone_aware(value)
    except ValueError as exc:
        raise AppError(
            "VALIDATION_ERROR",
            "Request validation failed",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            details={"errors": [{"loc": ["query", field_name], "msg": str(exc)}]},
        ) from exc


def ensure_report_date_range(
    start_at: datetime | None,
    end_at: datetime | None,
) -> tuple[datetime | None, datetime | None]:
    start_at = ensure_report_datetime(start_at, "start_at")
    end_at = ensure_report_datetime(end_at, "end_at")
    if start_at is not None and end_at is not None and start_at > end_at:
        raise AppError(
            "INVALID_DATE_RANGE",
            "start_at must be before or equal to end_at",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return start_at, end_at


@router.get(
    "/advertiser/dashboard/summary",
    response_model=AdvertiserDashboardSummary,
    summary="Read advertiser dashboard summary",
    description=(
        "Aggregate stored campaign, trip, impression, payout, and fraud data for the "
        "current advertiser organization. The demo seed returns non-empty data here."
    ),
)
async def advertiser_get_dashboard_summary(
    current_user: AdvertiserUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
) -> AdvertiserDashboardSummary:
    start_at, end_at = ensure_report_date_range(start_at, end_at)
    return await advertiser_dashboard_summary(
        session,
        user_id=current_user.id,
        start_at=start_at,
        end_at=end_at,
        settings=settings,
    )


@router.get(
    "/advertiser/campaigns/{campaign_id}/summary",
    response_model=CampaignSummary,
    summary="Read advertiser campaign reporting summary",
    description="Return frontend-ready totals for one advertiser-owned campaign.",
)
async def advertiser_get_campaign_summary(
    campaign_id: UUID,
    current_user: AdvertiserUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
) -> CampaignSummary:
    start_at, end_at = ensure_report_date_range(start_at, end_at)
    return await advertiser_campaign_summary(
        session,
        user_id=current_user.id,
        campaign_id=campaign_id,
        start_at=start_at,
        end_at=end_at,
        settings=settings,
    )


@router.get(
    "/advertiser/campaigns/{campaign_id}/daily-metrics",
    response_model=DailyMetricsResponse,
    summary="List advertiser campaign daily metrics",
    description="Return UTC daily reporting rows from stored demo or production data.",
)
async def advertiser_get_campaign_daily_metrics(
    campaign_id: UUID,
    current_user: AdvertiserUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=366)] = 90,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DailyMetricsResponse:
    start_at, end_at = ensure_report_date_range(start_at, end_at)
    return await daily_metrics_for_campaign(
        session,
        user_id=current_user.id,
        campaign_id=campaign_id,
        start_at=start_at,
        end_at=end_at,
        limit=limit,
        offset=offset,
        settings=settings,
    )


@router.get(
    "/advertiser/campaigns/{campaign_id}/trips",
    response_model=CampaignTripsResponse,
    summary="Read advertiser campaign trip aggregate",
    description=(
        "Return one privacy-governed whole-campaign aggregate without trip rows, identifiers, "
        "or event timestamps."
    ),
)
async def advertiser_get_campaign_trip_aggregate(
    campaign_id: UUID,
    current_user: AdvertiserUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> CampaignTripsResponse:
    return await advertiser_campaign_trips(
        session,
        user_id=current_user.id,
        campaign_id=campaign_id,
        settings=settings,
    )


@router.get(
    "/advertiser/campaigns/{campaign_id}/report",
    response_model=CampaignReportResponse,
    summary="Read bundled advertiser campaign report",
    description="Return compact dashboard, daily, creative, zone, assignment, and cost sections.",
)
async def advertiser_get_campaign_report(
    campaign_id: UUID,
    current_user: AdvertiserUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
) -> CampaignReportResponse:
    start_at, end_at = ensure_report_date_range(start_at, end_at)
    return await advertiser_campaign_report(
        session,
        user_id=current_user.id,
        campaign_id=campaign_id,
        start_at=start_at,
        end_at=end_at,
        settings=settings,
    )
