from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query
from starlette import status

from app.api.v1.dependencies import AdvertiserUserDependency, SessionDependency, SettingsDependency
from app.core.errors import AppError
from app.schemas.campaigns import ensure_timezone_aware
from app.schemas.reports import (
    CampaignPerformanceRead,
    DailyMetricsResponse,
)
from app.services.reports import (
    advertiser_campaign_report,
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
    "/advertiser/campaigns/{campaign_id}/daily-metrics",
    response_model=DailyMetricsResponse,
    summary="List advertiser campaign daily metrics",
    description=(
        "Return Nigeria calendar days (WAT); default to seven days with today not ready. "
        "Empty days are zero; days below three cars are withheld."
    ),
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
    "/advertiser/campaigns/{campaign_id}/report",
    response_model=CampaignPerformanceRead,
    summary="Read campaign results",
    description=(
        "Return trip counts and estimated views summed from qualifying complete area weeks."
    ),
)
async def advertiser_get_campaign_report(
    campaign_id: UUID,
    current_user: AdvertiserUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> CampaignPerformanceRead:
    return await advertiser_campaign_report(
        session,
        user_id=current_user.id,
        campaign_id=campaign_id,
        settings=settings,
    )
