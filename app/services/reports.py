from collections import defaultdict
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.campaign import Campaign, CampaignCreative
from app.models.campaign_assignment import CampaignAssignment
from app.models.campaign_zone import CampaignZone
from app.models.impression import ImpressionEstimate, ImpressionEstimateStatus
from app.models.payout import EarningsLedgerEntry, PayoutCalculation, PayoutCalculationStatus
from app.models.trip import TripSession
from app.models.trip_analytics import FraudFlag, FraudFlagSeverity, FraudFlagStatus, TripAnalytics
from app.models.vehicle import Vehicle
from app.schemas.reports import (
    ASSIGNMENT_STATUSES,
    CAMPAIGN_STATUSES,
    CREATIVE_STATUSES,
    FRAUD_SEVERITIES,
    FRAUD_STATUSES,
    TRIP_STATUSES,
    ZONE_TYPES,
    AdvertiserDashboardSummary,
    AssignmentStatusCounts,
    CampaignCostCurrencySummary,
    CampaignCostSummary,
    CampaignReadSummary,
    CampaignReportResponse,
    CampaignStatusCounts,
    CampaignSummary,
    CampaignTripsResponse,
    CampaignTripSummary,
    CreativeStatusCounts,
    DailyMetricItem,
    DailyMetricsResponse,
    DashboardCostCurrencySummary,
    DashboardCostSummary,
    FraudFlagCounts,
    ImpressionSummary,
    QualitySummary,
    RouteAnalyticsSummary,
    TripAnalyticsSummary,
    TripCostSummary,
    TripFraudFlagCounts,
    TripImpressionSummary,
    TripStatusCounts,
    ZoneTypeCounts,
)
from app.services.campaigns import get_advertiser_campaign, get_required_advertiser_context

ZERO_2 = Decimal("0.00")
ZERO_4 = Decimal("0.0000")
DECIMAL_2 = Decimal("0.01")
DECIMAL_4 = Decimal("0.0001")


def decimal_2(value: object) -> Decimal:
    return Decimal(str(value or 0)).quantize(DECIMAL_2)


def decimal_4(value: object) -> Decimal:
    return Decimal(str(value or 0)).quantize(DECIMAL_4)


def utc_day(value: datetime) -> date:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).date()


def apply_range(filters: list, column, start_at: datetime | None, end_at: datetime | None) -> None:
    if start_at is not None:
        filters.append(column >= start_at)
    if end_at is not None:
        filters.append(column <= end_at)


def campaign_response(campaign: Campaign) -> CampaignReadSummary:
    return CampaignReadSummary(
        id=campaign.id,
        name=campaign.name,
        status=campaign.status,
        start_at=campaign.start_at,
        end_at=campaign.end_at,
        budget_amount=campaign.budget_amount,
        daily_budget_amount=campaign.daily_budget_amount,
        currency=campaign.currency,
    )


def status_counts(rows: list[tuple[str, int]], statuses: list[str]) -> dict[str, int]:
    counts = {status: 0 for status in statuses}
    total = 0
    for status_value, count in rows:
        value = int(count or 0)
        total += value
        counts[str(status_value)] = value
    counts["total"] = total
    return counts


async def campaign_status_counts(
    session: AsyncSession,
    organization_id: UUID,
) -> CampaignStatusCounts:
    result = await session.execute(
        select(Campaign.status, func.count(Campaign.id))
        .where(Campaign.organization_id == organization_id)
        .group_by(Campaign.status)
    )
    return CampaignStatusCounts(**status_counts(result.all(), CAMPAIGN_STATUSES))


async def creative_status_counts(session: AsyncSession, campaign_id: UUID) -> CreativeStatusCounts:
    result = await session.execute(
        select(CampaignCreative.status, func.count(CampaignCreative.id))
        .where(CampaignCreative.campaign_id == campaign_id)
        .group_by(CampaignCreative.status)
    )
    return CreativeStatusCounts(**status_counts(result.all(), CREATIVE_STATUSES))


async def zone_type_counts(session: AsyncSession, campaign_id: UUID) -> ZoneTypeCounts:
    result = await session.execute(
        select(CampaignZone.zone_type, func.count(CampaignZone.id))
        .where(CampaignZone.campaign_id == campaign_id)
        .group_by(CampaignZone.zone_type)
    )
    return ZoneTypeCounts(**status_counts(result.all(), ZONE_TYPES))


async def assignment_counts_for_org(
    session: AsyncSession,
    organization_id: UUID,
) -> AssignmentStatusCounts:
    result = await session.execute(
        select(CampaignAssignment.status, func.count(CampaignAssignment.id))
        .join(Campaign, Campaign.id == CampaignAssignment.campaign_id)
        .where(Campaign.organization_id == organization_id)
        .group_by(CampaignAssignment.status)
    )
    return AssignmentStatusCounts(**status_counts(result.all(), ASSIGNMENT_STATUSES))


async def assignment_counts_for_campaign(
    session: AsyncSession,
    campaign_id: UUID,
) -> AssignmentStatusCounts:
    result = await session.execute(
        select(CampaignAssignment.status, func.count(CampaignAssignment.id))
        .where(CampaignAssignment.campaign_id == campaign_id)
        .group_by(CampaignAssignment.status)
    )
    return AssignmentStatusCounts(**status_counts(result.all(), ASSIGNMENT_STATUSES))


async def trip_counts_for_org(
    session: AsyncSession,
    organization_id: UUID,
    *,
    start_at: datetime | None,
    end_at: datetime | None,
) -> TripStatusCounts:
    filters = [Campaign.organization_id == organization_id]
    apply_range(filters, TripSession.started_at, start_at, end_at)
    result = await session.execute(
        select(TripSession.status, func.count(TripSession.id))
        .join(Campaign, Campaign.id == TripSession.campaign_id)
        .where(*filters)
        .group_by(TripSession.status)
    )
    return TripStatusCounts(**status_counts(result.all(), TRIP_STATUSES))


async def trip_counts_for_campaign(
    session: AsyncSession,
    campaign_id: UUID,
    *,
    start_at: datetime | None,
    end_at: datetime | None,
) -> TripStatusCounts:
    filters = [TripSession.campaign_id == campaign_id]
    apply_range(filters, TripSession.started_at, start_at, end_at)
    result = await session.execute(
        select(TripSession.status, func.count(TripSession.id))
        .where(*filters)
        .group_by(TripSession.status)
    )
    return TripStatusCounts(**status_counts(result.all(), TRIP_STATUSES))


async def impression_summary_for_org(
    session: AsyncSession,
    organization_id: UUID,
    *,
    start_at: datetime | None,
    end_at: datetime | None,
    settings: Settings,
) -> ImpressionSummary:
    filters = [
        Campaign.organization_id == organization_id,
        ImpressionEstimate.formula_version == settings.impression_formula_version,
    ]
    apply_range(filters, ImpressionEstimate.estimated_at, start_at, end_at)
    return await impression_summary_query(session, filters, join_campaign=True)


async def impression_summary_for_campaign(
    session: AsyncSession,
    campaign_id: UUID,
    *,
    start_at: datetime | None,
    end_at: datetime | None,
    settings: Settings,
) -> ImpressionSummary:
    filters = [
        ImpressionEstimate.campaign_id == campaign_id,
        ImpressionEstimate.formula_version == settings.impression_formula_version,
    ]
    apply_range(filters, ImpressionEstimate.estimated_at, start_at, end_at)
    return await impression_summary_query(session, filters, join_campaign=False)


async def impression_summary_query(
    session: AsyncSession,
    filters: list,
    *,
    join_campaign: bool,
) -> ImpressionSummary:
    statement = select(
        func.coalesce(func.sum(ImpressionEstimate.estimated_impressions), 0),
        func.coalesce(
            func.sum(
                case(
                    (ImpressionEstimate.status == ImpressionEstimateStatus.ESTIMATED.value, 1),
                    else_=0,
                )
            ),
            0,
        ),
        func.coalesce(
            func.sum(
                case(
                    (
                        ImpressionEstimate.status
                        == ImpressionEstimateStatus.INSUFFICIENT_DATA.value,
                        1,
                    ),
                    else_=0,
                )
            ),
            0,
        ),
        func.coalesce(
            func.sum(
                case(
                    (ImpressionEstimate.status == ImpressionEstimateStatus.EXCLUDED.value, 1),
                    else_=0,
                )
            ),
            0,
        ),
        func.coalesce(func.avg(ImpressionEstimate.confidence_score), 0),
    ).select_from(ImpressionEstimate)
    if join_campaign:
        statement = statement.join(Campaign, Campaign.id == ImpressionEstimate.campaign_id)
    row = (await session.execute(statement.where(*filters))).one()
    return ImpressionSummary(
        estimated_impressions=decimal_2(row[0]),
        estimated_trip_count=int(row[1] or 0),
        insufficient_data_trip_count=int(row[2] or 0),
        excluded_trip_count=int(row[3] or 0),
        average_confidence_score=decimal_4(row[4]),
    )


async def dashboard_cost_summary(
    session: AsyncSession,
    organization_id: UUID,
    *,
    start_at: datetime | None,
    end_at: datetime | None,
    default_currency: str,
    settings: Settings,
) -> DashboardCostSummary:
    filters = [
        Campaign.organization_id == organization_id,
        PayoutCalculation.formula_version == settings.payout_formula_version,
    ]
    apply_range(filters, PayoutCalculation.calculated_at, start_at, end_at)
    result = await session.execute(
        select(
            PayoutCalculation.currency,
            func.coalesce(func.sum(PayoutCalculation.final_payout), 0),
            func.coalesce(func.sum(PayoutCalculation.gross_payout), 0),
            func.count(EarningsLedgerEntry.id),
        )
        .select_from(PayoutCalculation)
        .join(Campaign, Campaign.id == PayoutCalculation.campaign_id)
        .outerjoin(
            EarningsLedgerEntry,
            EarningsLedgerEntry.payout_calculation_id == PayoutCalculation.id,
        )
        .where(*filters)
        .group_by(PayoutCalculation.currency)
    )
    totals = [
        DashboardCostCurrencySummary(
            currency=row[0],
            final_payout_total=decimal_2(row[1]),
            gross_payout_total=decimal_2(row[2]),
            ledger_entry_count=int(row[3] or 0),
        )
        for row in result.all()
    ]
    if not totals:
        totals.append(
            DashboardCostCurrencySummary(
                currency=default_currency,
                final_payout_total=ZERO_2,
                gross_payout_total=ZERO_2,
                ledger_entry_count=0,
            )
        )
    return DashboardCostSummary(totals_by_currency=totals)


async def campaign_cost_summary(
    session: AsyncSession,
    campaign_id: UUID,
    *,
    start_at: datetime | None,
    end_at: datetime | None,
    default_currency: str,
    settings: Settings,
) -> CampaignCostSummary:
    filters = [
        PayoutCalculation.campaign_id == campaign_id,
        PayoutCalculation.formula_version == settings.payout_formula_version,
    ]
    apply_range(filters, PayoutCalculation.calculated_at, start_at, end_at)
    result = await session.execute(
        select(
            PayoutCalculation.currency,
            func.coalesce(func.sum(PayoutCalculation.final_payout), 0),
            func.coalesce(func.sum(PayoutCalculation.gross_payout), 0),
            func.coalesce(
                func.sum(
                    case(
                        (
                            PayoutCalculation.status
                            == PayoutCalculationStatus.CALCULATED.value,
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
            func.coalesce(
                func.sum(
                    case(
                        (PayoutCalculation.status == PayoutCalculationStatus.BLOCKED.value, 1),
                        else_=0,
                    )
                ),
                0,
            ),
            func.coalesce(
                func.sum(
                    case(
                        (
                            PayoutCalculation.status
                            == PayoutCalculationStatus.INSUFFICIENT_DATA.value,
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
            func.count(EarningsLedgerEntry.id),
        )
        .select_from(PayoutCalculation)
        .outerjoin(
            EarningsLedgerEntry,
            EarningsLedgerEntry.payout_calculation_id == PayoutCalculation.id,
        )
        .where(*filters)
        .group_by(PayoutCalculation.currency)
    )
    totals = [
        CampaignCostCurrencySummary(
            currency=row[0],
            final_payout_total=decimal_2(row[1]),
            gross_payout_total=decimal_2(row[2]),
            calculated_trip_count=int(row[3] or 0),
            blocked_trip_count=int(row[4] or 0),
            insufficient_data_trip_count=int(row[5] or 0),
            ledger_entry_count=int(row[6] or 0),
        )
        for row in result.all()
    ]
    if not totals:
        totals.append(
            CampaignCostCurrencySummary(
                currency=default_currency,
                final_payout_total=ZERO_2,
                gross_payout_total=ZERO_2,
                calculated_trip_count=0,
                blocked_trip_count=0,
                insufficient_data_trip_count=0,
                ledger_entry_count=0,
            )
        )
    return CampaignCostSummary(totals_by_currency=totals)


async def fraud_counts_for_org(
    session: AsyncSession,
    organization_id: UUID,
    *,
    start_at: datetime | None,
    end_at: datetime | None,
) -> FraudFlagCounts:
    filters = [Campaign.organization_id == organization_id]
    apply_range(filters, FraudFlag.detected_at, start_at, end_at)
    return await fraud_counts_query(session, filters, join_campaign=True)


async def fraud_counts_for_campaign(
    session: AsyncSession,
    campaign_id: UUID,
    *,
    start_at: datetime | None,
    end_at: datetime | None,
) -> FraudFlagCounts:
    filters = [FraudFlag.campaign_id == campaign_id]
    apply_range(filters, FraudFlag.detected_at, start_at, end_at)
    return await fraud_counts_query(session, filters, join_campaign=False)


async def fraud_counts_query(
    session: AsyncSession,
    filters: list,
    *,
    join_campaign: bool,
) -> FraudFlagCounts:
    status_statement = select(FraudFlag.status, func.count(FraudFlag.id)).select_from(FraudFlag)
    severity_statement = select(FraudFlag.severity, func.count(FraudFlag.id)).select_from(
        FraudFlag
    )
    if join_campaign:
        status_statement = status_statement.join(Campaign, Campaign.id == FraudFlag.campaign_id)
        severity_statement = severity_statement.join(Campaign, Campaign.id == FraudFlag.campaign_id)
    status_result = await session.execute(
        status_statement.where(*filters).group_by(FraudFlag.status)
    )
    severity_result = await session.execute(
        severity_statement.where(*filters).group_by(FraudFlag.severity)
    )
    status_values = {status_value: 0 for status_value in FRAUD_STATUSES}
    severity_values = {severity: 0 for severity in FRAUD_SEVERITIES}
    status_values.update(
        {str(status_value): int(count or 0) for status_value, count in status_result.all()}
    )
    severity_values.update(
        {str(severity): int(count or 0) for severity, count in severity_result.all()}
    )
    return FraudFlagCounts(**status_values, **severity_values)


async def route_analytics_summary(
    session: AsyncSession,
    campaign_id: UUID,
    *,
    start_at: datetime | None,
    end_at: datetime | None,
) -> RouteAnalyticsSummary:
    filters = [TripAnalytics.campaign_id == campaign_id]
    apply_range(filters, TripSession.started_at, start_at, end_at)
    row = (
        await session.execute(
            select(
                func.count(TripAnalytics.id),
                func.coalesce(func.sum(TripAnalytics.distance_m), 0),
                func.coalesce(func.sum(TripAnalytics.target_zone_distance_m), 0),
                func.coalesce(func.sum(TripAnalytics.bonus_zone_distance_m), 0),
                func.coalesce(func.sum(TripAnalytics.exclusion_zone_distance_m), 0),
                func.coalesce(func.avg(TripAnalytics.quality_score), 0),
            )
            .select_from(TripAnalytics)
            .join(TripSession, TripSession.id == TripAnalytics.trip_session_id)
            .where(*filters)
        )
    ).one()
    return RouteAnalyticsSummary(
        analyzed_trip_count=int(row[0] or 0),
        total_distance_m=decimal_2(row[1]),
        target_zone_distance_m=decimal_2(row[2]),
        bonus_zone_distance_m=decimal_2(row[3]),
        exclusion_zone_distance_m=decimal_2(row[4]),
        average_quality_score=decimal_4(row[5]),
    )


async def quality_summary_for_org(
    session: AsyncSession,
    organization_id: UUID,
    *,
    start_at: datetime | None,
    end_at: datetime | None,
) -> QualitySummary:
    filters = [Campaign.organization_id == organization_id]
    apply_range(filters, TripSession.started_at, start_at, end_at)
    row = (
        await session.execute(
            select(func.coalesce(func.avg(TripAnalytics.quality_score), 0))
            .select_from(TripAnalytics)
            .join(Campaign, Campaign.id == TripAnalytics.campaign_id)
            .join(TripSession, TripSession.id == TripAnalytics.trip_session_id)
            .where(*filters)
        )
    ).one()
    return QualitySummary(
        average_quality_score=decimal_4(row[0]),
        fraud_flags=await fraud_counts_for_org(
            session,
            organization_id,
            start_at=start_at,
            end_at=end_at,
        ),
    )


async def advertiser_dashboard_summary(
    session: AsyncSession,
    *,
    user_id: UUID,
    start_at: datetime | None,
    end_at: datetime | None,
    settings: Settings,
) -> AdvertiserDashboardSummary:
    organization, _ = await get_required_advertiser_context(session, user_id)
    return AdvertiserDashboardSummary(
        organization_id=organization.id,
        currency=organization.currency,
        start_at=start_at,
        end_at=end_at,
        campaigns=await campaign_status_counts(session, organization.id),
        assignments=await assignment_counts_for_org(session, organization.id),
        trips=await trip_counts_for_org(
            session,
            organization.id,
            start_at=start_at,
            end_at=end_at,
        ),
        impressions=await impression_summary_for_org(
            session,
            organization.id,
            start_at=start_at,
            end_at=end_at,
            settings=settings,
        ),
        costs=await dashboard_cost_summary(
            session,
            organization.id,
            start_at=start_at,
            end_at=end_at,
            default_currency=organization.currency,
            settings=settings,
        ),
        quality=await quality_summary_for_org(
            session,
            organization.id,
            start_at=start_at,
            end_at=end_at,
        ),
    )


async def advertiser_campaign_summary(
    session: AsyncSession,
    *,
    user_id: UUID,
    campaign_id: UUID,
    start_at: datetime | None,
    end_at: datetime | None,
    settings: Settings,
) -> CampaignSummary:
    campaign = await get_advertiser_campaign(session, user_id=user_id, campaign_id=campaign_id)
    return CampaignSummary(
        campaign=campaign_response(campaign),
        start_at=start_at,
        end_at=end_at,
        creatives=await creative_status_counts(session, campaign.id),
        zones=await zone_type_counts(session, campaign.id),
        assignments=await assignment_counts_for_campaign(session, campaign.id),
        trips=await trip_counts_for_campaign(
            session,
            campaign.id,
            start_at=start_at,
            end_at=end_at,
        ),
        route_analytics=await route_analytics_summary(
            session,
            campaign.id,
            start_at=start_at,
            end_at=end_at,
        ),
        impressions=await impression_summary_for_campaign(
            session,
            campaign.id,
            start_at=start_at,
            end_at=end_at,
            settings=settings,
        ),
        costs=await campaign_cost_summary(
            session,
            campaign.id,
            start_at=start_at,
            end_at=end_at,
            default_currency=campaign.currency,
            settings=settings,
        ),
        fraud_flags=await fraud_counts_for_campaign(
            session,
            campaign.id,
            start_at=start_at,
            end_at=end_at,
        ),
    )


async def daily_metrics_for_campaign(
    session: AsyncSession,
    *,
    user_id: UUID,
    campaign_id: UUID,
    start_at: datetime | None,
    end_at: datetime | None,
    limit: int,
    offset: int,
    settings: Settings,
) -> DailyMetricsResponse:
    campaign = await get_advertiser_campaign(session, user_id=user_id, campaign_id=campaign_id)
    by_day: dict[date, dict[str, object]] = defaultdict(
        lambda: {
            "trip_count": 0,
            "analyzed_trip_count": 0,
            "distance_m": ZERO_2,
            "estimated_impressions": ZERO_2,
            "confidence_total": ZERO_4,
            "confidence_count": 0,
            "final_payout_total": ZERO_2,
            "gross_payout_total": ZERO_2,
            "open_fraud_flag_count": 0,
            "quality_total": ZERO_4,
            "quality_count": 0,
        }
    )

    trip_filters = [TripSession.campaign_id == campaign.id]
    apply_range(trip_filters, TripSession.started_at, start_at, end_at)
    trip_rows = (
        await session.execute(select(TripSession.id, TripSession.started_at).where(*trip_filters))
    ).all()
    trip_days = {trip_id: utc_day(started_at) for trip_id, started_at in trip_rows}
    for day in trip_days.values():
        by_day[day]["trip_count"] = int(by_day[day]["trip_count"]) + 1

    if trip_days:
        trip_ids = list(trip_days)
        analytics_rows = (
            await session.execute(
                select(
                    TripAnalytics.trip_session_id,
                    TripAnalytics.distance_m,
                    TripAnalytics.quality_score,
                ).where(TripAnalytics.trip_session_id.in_(trip_ids))
            )
        ).all()
        for trip_id, distance_m, quality_score in analytics_rows:
            day = trip_days[trip_id]
            by_day[day]["analyzed_trip_count"] = int(by_day[day]["analyzed_trip_count"]) + 1
            by_day[day]["distance_m"] = decimal_2(by_day[day]["distance_m"]) + decimal_2(
                distance_m
            )
            by_day[day]["quality_total"] = decimal_4(by_day[day]["quality_total"]) + decimal_4(
                quality_score
            )
            by_day[day]["quality_count"] = int(by_day[day]["quality_count"]) + 1

        estimate_rows = (
            await session.execute(
                select(
                    ImpressionEstimate.trip_session_id,
                    ImpressionEstimate.estimated_impressions,
                    ImpressionEstimate.confidence_score,
                ).where(
                    ImpressionEstimate.trip_session_id.in_(trip_ids),
                    ImpressionEstimate.formula_version == settings.impression_formula_version,
                )
            )
        ).all()
        for trip_id, estimated_impressions, confidence_score in estimate_rows:
            day = trip_days[trip_id]
            by_day[day]["estimated_impressions"] = decimal_2(
                by_day[day]["estimated_impressions"]
            ) + decimal_2(estimated_impressions)
            by_day[day]["confidence_total"] = decimal_4(
                by_day[day]["confidence_total"]
            ) + decimal_4(confidence_score)
            by_day[day]["confidence_count"] = int(by_day[day]["confidence_count"]) + 1

        payout_rows = (
            await session.execute(
                select(
                    PayoutCalculation.trip_session_id,
                    PayoutCalculation.final_payout,
                    PayoutCalculation.gross_payout,
                ).where(
                    PayoutCalculation.trip_session_id.in_(trip_ids),
                    PayoutCalculation.formula_version == settings.payout_formula_version,
                )
            )
        ).all()
        for trip_id, final_payout, gross_payout in payout_rows:
            day = trip_days[trip_id]
            by_day[day]["final_payout_total"] = decimal_2(
                by_day[day]["final_payout_total"]
            ) + decimal_2(final_payout)
            by_day[day]["gross_payout_total"] = decimal_2(
                by_day[day]["gross_payout_total"]
            ) + decimal_2(gross_payout)

        fraud_rows = (
            await session.execute(
                select(FraudFlag.trip_session_id, func.count(FraudFlag.id))
                .where(
                    FraudFlag.trip_session_id.in_(trip_ids),
                    FraudFlag.status == FraudFlagStatus.OPEN.value,
                )
                .group_by(FraudFlag.trip_session_id)
            )
        ).all()
        for trip_id, count in fraud_rows:
            day = trip_days[trip_id]
            by_day[day]["open_fraud_flag_count"] = int(
                by_day[day]["open_fraud_flag_count"]
            ) + int(count or 0)

    sorted_days = sorted(by_day, reverse=True)
    items = [daily_item(day, by_day[day]) for day in sorted_days[offset : offset + limit]]
    return DailyMetricsResponse(
        campaign_id=campaign.id,
        start_at=start_at,
        end_at=end_at,
        items=items,
        total=len(sorted_days),
        limit=limit,
        offset=offset,
    )


def daily_item(day: date, values: dict[str, object]) -> DailyMetricItem:
    confidence_count = int(values["confidence_count"])
    quality_count = int(values["quality_count"])
    return DailyMetricItem(
        date=day,
        trip_count=int(values["trip_count"]),
        analyzed_trip_count=int(values["analyzed_trip_count"]),
        distance_m=decimal_2(values["distance_m"]),
        estimated_impressions=decimal_2(values["estimated_impressions"]),
        average_confidence_score=(
            decimal_4(decimal_4(values["confidence_total"]) / confidence_count)
            if confidence_count
            else ZERO_4
        ),
        final_payout_total=decimal_2(values["final_payout_total"]),
        gross_payout_total=decimal_2(values["gross_payout_total"]),
        open_fraud_flag_count=int(values["open_fraud_flag_count"]),
        average_quality_score=(
            decimal_4(decimal_4(values["quality_total"]) / quality_count)
            if quality_count
            else ZERO_4
        ),
    )


async def advertiser_campaign_trips(
    session: AsyncSession,
    *,
    user_id: UUID,
    campaign_id: UUID,
    start_at: datetime | None,
    end_at: datetime | None,
    limit: int,
    offset: int,
    trip_status: str | None,
    has_fraud_flags: bool | None,
    analytics_status: str | None,
    impression_status: str | None,
    payout_status: str | None,
    settings: Settings,
) -> CampaignTripsResponse:
    campaign = await get_advertiser_campaign(session, user_id=user_id, campaign_id=campaign_id)
    filters = [TripSession.campaign_id == campaign.id]
    apply_range(filters, TripSession.started_at, start_at, end_at)
    if trip_status is not None:
        filters.append(TripSession.status == trip_status)
    if analytics_status is not None:
        filters.append(
            TripSession.id.in_(
                select(TripAnalytics.trip_session_id).where(
                    TripAnalytics.status == analytics_status
                )
            )
        )
    if impression_status is not None:
        filters.append(
            TripSession.id.in_(
                select(ImpressionEstimate.trip_session_id).where(
                    ImpressionEstimate.status == impression_status,
                    ImpressionEstimate.formula_version == settings.impression_formula_version,
                )
            )
        )
    if payout_status is not None:
        filters.append(
            TripSession.id.in_(
                select(PayoutCalculation.trip_session_id).where(
                    PayoutCalculation.status == payout_status,
                    PayoutCalculation.formula_version == settings.payout_formula_version,
                )
            )
        )
    if has_fraud_flags is not None:
        flagged_trip_ids = select(FraudFlag.trip_session_id).where(
            FraudFlag.campaign_id == campaign.id
        )
        filters.append(
            TripSession.id.in_(flagged_trip_ids)
            if has_fraud_flags
            else TripSession.id.not_in(flagged_trip_ids)
        )

    total = await session.scalar(select(func.count()).select_from(TripSession).where(*filters))
    result = await session.execute(
        select(TripSession, Vehicle.vehicle_type)
        .join(Vehicle, Vehicle.id == TripSession.vehicle_id)
        .where(*filters)
        .order_by(TripSession.started_at.desc(), TripSession.id)
        .limit(limit)
        .offset(offset)
    )
    rows = result.all()
    trips = [row[0] for row in rows]
    trip_ids = [trip.id for trip in trips]
    analytics_by_trip = {}
    estimates_by_trip = {}
    payouts_by_trip = {}
    fraud_by_trip = defaultdict(TripFraudFlagCounts)
    if trip_ids:
        analytics_by_trip = {
            analytics.trip_session_id: analytics
            for analytics in (
                await session.execute(
                    select(TripAnalytics).where(TripAnalytics.trip_session_id.in_(trip_ids))
                )
            )
            .scalars()
            .all()
        }
        for estimate in (
            await session.execute(
                select(ImpressionEstimate)
                .where(
                    ImpressionEstimate.trip_session_id.in_(trip_ids),
                    ImpressionEstimate.formula_version == settings.impression_formula_version,
                )
                .order_by(ImpressionEstimate.estimated_at.desc(), ImpressionEstimate.id)
            )
        ).scalars():
            estimates_by_trip.setdefault(estimate.trip_session_id, estimate)
        for payout in (
            await session.execute(
                select(PayoutCalculation)
                .where(
                    PayoutCalculation.trip_session_id.in_(trip_ids),
                    PayoutCalculation.formula_version == settings.payout_formula_version,
                )
                .order_by(PayoutCalculation.calculated_at.desc(), PayoutCalculation.id)
            )
        ).scalars():
            payouts_by_trip.setdefault(payout.trip_session_id, payout)
        fraud_rows = await session.execute(
            select(FraudFlag.trip_session_id, FraudFlag.status, FraudFlag.severity).where(
                FraudFlag.trip_session_id.in_(trip_ids)
            )
        )
        for trip_id, flag_status, severity in fraud_rows.all():
            counts = fraud_by_trip[trip_id]
            if flag_status == FraudFlagStatus.OPEN.value:
                counts.open_count += 1
                if severity == FraudFlagSeverity.HIGH.value:
                    counts.high_count += 1
                elif severity == FraudFlagSeverity.MEDIUM.value:
                    counts.medium_count += 1
                elif severity == FraudFlagSeverity.LOW.value:
                    counts.low_count += 1

    items = []
    for trip, vehicle_type in rows:
        analytics = analytics_by_trip.get(trip.id)
        estimate = estimates_by_trip.get(trip.id)
        payout = payouts_by_trip.get(trip.id)
        items.append(
            CampaignTripSummary(
                trip_id=trip.id,
                assignment_id=trip.assignment_id,
                vehicle_type=vehicle_type,
                trip_status=trip.status,
                started_at=trip.started_at,
                ended_at=trip.ended_at,
                analytics=(
                    TripAnalyticsSummary(
                        status=analytics.status,
                        distance_m=analytics.distance_m,
                        moving_seconds=analytics.moving_seconds,
                        stationary_seconds=analytics.stationary_seconds,
                        quality_score=analytics.quality_score,
                    )
                    if analytics is not None
                    else None
                ),
                impressions=(
                    TripImpressionSummary(
                        status=estimate.status,
                        estimated_impressions=estimate.estimated_impressions,
                        confidence_score=estimate.confidence_score,
                    )
                    if estimate is not None
                    else None
                ),
                cost=(
                    TripCostSummary(
                        status=payout.status,
                        currency=payout.currency,
                        final_payout=payout.final_payout,
                        gross_payout=payout.gross_payout,
                    )
                    if payout is not None
                    else None
                ),
                fraud_flags=fraud_by_trip[trip.id],
            )
        )

    return CampaignTripsResponse(
        campaign_id=campaign.id,
        items=items,
        total=int(total or 0),
        limit=limit,
        offset=offset,
    )


async def advertiser_campaign_report(
    session: AsyncSession,
    *,
    user_id: UUID,
    campaign_id: UUID,
    start_at: datetime | None,
    end_at: datetime | None,
    settings: Settings,
) -> CampaignReportResponse:
    summary = await advertiser_campaign_summary(
        session,
        user_id=user_id,
        campaign_id=campaign_id,
        start_at=start_at,
        end_at=end_at,
        settings=settings,
    )
    daily_metrics = await daily_metrics_for_campaign(
        session,
        user_id=user_id,
        campaign_id=campaign_id,
        start_at=start_at,
        end_at=end_at,
        limit=366,
        offset=0,
        settings=settings,
    )
    return CampaignReportResponse(
        campaign_id=summary.campaign.id,
        start_at=start_at,
        end_at=end_at,
        summary=summary.campaign,
        daily_metrics=daily_metrics.items,
        creative_summary=summary.creatives,
        zone_summary=summary.zones,
        assignment_summary=summary.assignments,
        trip_summary=summary.trips,
        impression_summary=summary.impressions,
        cost_summary=summary.costs,
        fraud_summary=summary.fraud_flags,
    )
