from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.models.campaign import Campaign, CampaignCreative
from app.models.campaign_assignment import CampaignAssignment
from app.models.campaign_zone import CampaignZone
from app.models.impression import ImpressionEstimate, ImpressionEstimateStatus
from app.models.payout import EarningsLedgerEntry, PayoutCalculation, PayoutCalculationStatus
from app.models.trip import TripSession, TripSessionStatus
from app.models.trip_analytics import FraudFlag, TripAnalytics
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
    CampaignStatusCounts,
    CampaignSummary,
    CampaignTripsResponse,
    CreativeStatusCounts,
    DailyMetricItem,
    DailyMetricsResponse,
    DashboardCostCurrencySummary,
    DashboardCostSummary,
    FraudFlagCounts,
    ImpressionSummary,
    QualitySummary,
    RouteAnalyticsSummary,
    TripStatusCounts,
    ZoneTypeCounts,
)
from app.services.campaign_lifecycle import assignment_status_expression, campaign_status_expression
from app.services.campaigns import get_advertiser_campaign, get_required_advertiser_context
from app.services.disclosure import (
    lock_trip_disclosure_snapshot,
    record_governed_trip_output,
    require_governed_advertiser_output,
)
from app.services.impressions import current_authoritative_estimates
from app.services.payouts.ledger import latest_payout_calculation_ids
from app.services.report_cohorts import ReportCohort, select_report_cohort

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
    status_column = campaign_status_expression()
    result = await session.execute(
        select(status_column, func.count(Campaign.id))
        .where(Campaign.organization_id == organization_id)
        .group_by(status_column)
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
    status_column = assignment_status_expression()
    result = await session.execute(
        select(status_column, func.count(CampaignAssignment.id))
        .join(Campaign, Campaign.id == CampaignAssignment.campaign_id)
        .where(Campaign.organization_id == organization_id)
        .group_by(status_column)
    )
    return AssignmentStatusCounts(**status_counts(result.all(), ASSIGNMENT_STATUSES))


async def assignment_counts_for_campaign(
    session: AsyncSession,
    campaign_id: UUID,
) -> AssignmentStatusCounts:
    status_column = assignment_status_expression()
    result = await session.execute(
        select(status_column, func.count(CampaignAssignment.id))
        .where(CampaignAssignment.campaign_id == campaign_id)
        .group_by(status_column)
    )
    return AssignmentStatusCounts(**status_counts(result.all(), ASSIGNMENT_STATUSES))


def fold_sealed_into_ended(rows: list[tuple[str, int]]) -> list[tuple[str, int]]:
    """Advertiser/admin reporting counts `sealed` trips as `ended`.

    The seal lifecycle (RM3) is an internal money-integrity state; to report
    consumers a finished trip is a finished trip.
    """
    folded: dict[str, int] = {}
    for status_value, count in rows:
        key = (
            TripSessionStatus.ENDED.value
            if str(status_value) == TripSessionStatus.SEALED.value
            else str(status_value)
        )
        folded[key] = folded.get(key, 0) + int(count or 0)
    return list(folded.items())


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
    return TripStatusCounts(**status_counts(fold_sealed_into_ended(result.all()), TRIP_STATUSES))


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
    return TripStatusCounts(**status_counts(fold_sealed_into_ended(result.all()), TRIP_STATUSES))


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
        ImpressionEstimate.is_authoritative.is_(True),
    ]
    apply_range(filters, ImpressionEstimate.estimated_at, start_at, end_at)
    return await impression_summary_query(session, filters, join_campaign=True, settings=settings)


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
        ImpressionEstimate.is_authoritative.is_(True),
    ]
    apply_range(filters, ImpressionEstimate.estimated_at, start_at, end_at)
    return await impression_summary_query(session, filters, join_campaign=False, settings=settings)


async def impression_summary_query(
    session: AsyncSession,
    filters: list,
    *,
    join_campaign: bool,
    settings: Settings,
) -> ImpressionSummary:
    statement = select(ImpressionEstimate).select_from(ImpressionEstimate)
    if join_campaign:
        statement = statement.join(Campaign, Campaign.id == ImpressionEstimate.campaign_id)
    estimates = list((await session.scalars(statement.where(*filters))).all())
    estimates = await current_authoritative_estimates(session, estimates, settings=settings)
    estimated_impressions = sum(
        (Decimal(estimate.estimated_impressions or 0) for estimate in estimates),
        Decimal("0"),
    )
    estimated_count = sum(
        estimate.status == ImpressionEstimateStatus.ESTIMATED.value for estimate in estimates
    )
    insufficient_count = sum(
        estimate.status == ImpressionEstimateStatus.INSUFFICIENT_DATA.value
        for estimate in estimates
    )
    excluded_count = sum(
        estimate.status == ImpressionEstimateStatus.EXCLUDED.value for estimate in estimates
    )
    confidence_total = sum(
        (Decimal(estimate.confidence_score or 0) for estimate in estimates),
        Decimal("0"),
    )
    return ImpressionSummary(
        estimated_impressions=decimal_2(estimated_impressions),
        estimated_trip_count=estimated_count,
        insufficient_data_trip_count=insufficient_count,
        excluded_trip_count=excluded_count,
        average_confidence_score=decimal_4(
            confidence_total / len(estimates) if estimates else Decimal("0")
        ),
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
        PayoutCalculation.id.in_(latest_payout_calculation_ids(organization_id=organization_id)),
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
        PayoutCalculation.id.in_(latest_payout_calculation_ids(campaign_id=campaign_id)),
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
                            PayoutCalculation.status == PayoutCalculationStatus.CALCULATED.value,
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


async def campaign_cost_summary_from_cohort(
    session: AsyncSession,
    cohort: ReportCohort,
    *,
    default_currency: str,
) -> CampaignCostSummary:
    ledger_counts: dict[UUID, int] = {}
    payout_ids = [row.id for row in cohort.payouts]
    if payout_ids:
        ledger_counts = {
            payout_id: int(count or 0)
            for payout_id, count in (
                await session.execute(
                    select(
                        EarningsLedgerEntry.payout_calculation_id,
                        func.count(EarningsLedgerEntry.id),
                    )
                    .where(EarningsLedgerEntry.payout_calculation_id.in_(payout_ids))
                    .group_by(EarningsLedgerEntry.payout_calculation_id)
                )
            ).all()
        }
    totals: dict[str, dict[str, object]] = defaultdict(
        lambda: {
            "final": ZERO_2,
            "gross": ZERO_2,
            "calculated": 0,
            "blocked": 0,
            "insufficient": 0,
            "ledger": 0,
        }
    )
    for payout in cohort.payouts:
        values = totals[payout.currency]
        values["final"] = decimal_2(values["final"]) + decimal_2(cohort.final_cost(payout))
        values["gross"] = decimal_2(values["gross"]) + decimal_2(payout.gross_payout)
        if payout.status == PayoutCalculationStatus.CALCULATED.value:
            values["calculated"] = int(values["calculated"]) + 1
        elif payout.status == PayoutCalculationStatus.BLOCKED.value:
            values["blocked"] = int(values["blocked"]) + 1
        elif payout.status == PayoutCalculationStatus.INSUFFICIENT_DATA.value:
            values["insufficient"] = int(values["insufficient"]) + 1
        values["ledger"] = int(values["ledger"]) + (
            sum(r.trip_session_id == payout.trip_session_id for r in cohort.ledger)
            if cohort.ledger is not None
            else ledger_counts.get(payout.id, 0)
        )
    rows = [
        CampaignCostCurrencySummary(
            currency=currency,
            final_payout_total=decimal_2(values["final"]),
            gross_payout_total=decimal_2(values["gross"]),
            calculated_trip_count=int(values["calculated"]),
            blocked_trip_count=int(values["blocked"]),
            insufficient_data_trip_count=int(values["insufficient"]),
            ledger_entry_count=int(values["ledger"]),
        )
        for currency, values in sorted(totals.items())
    ]
    if not rows:
        rows.append(
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
    return CampaignCostSummary(totals_by_currency=rows)


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
    severity_statement = select(FraudFlag.severity, func.count(FraudFlag.id)).select_from(FraudFlag)
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


def trip_counts_from_cohort(cohort: ReportCohort) -> TripStatusCounts:
    rows: dict[str, int] = defaultdict(int)
    for trip in cohort.trips:
        rows[str(trip.status)] += 1
    return TripStatusCounts(
        **status_counts(fold_sealed_into_ended(list(rows.items())), TRIP_STATUSES)
    )


def route_analytics_from_cohort(cohort: ReportCohort) -> RouteAnalyticsSummary:
    rows = cohort.analytics
    return RouteAnalyticsSummary(
        analyzed_trip_count=len(rows),
        total_distance_m=decimal_2(sum((row.distance_m for row in rows), Decimal(0))),
        target_zone_distance_m=decimal_2(
            sum((row.target_zone_distance_m for row in rows), Decimal(0))
        ),
        bonus_zone_distance_m=decimal_2(
            sum((row.bonus_zone_distance_m for row in rows), Decimal(0))
        ),
        exclusion_zone_distance_m=decimal_2(
            sum((row.exclusion_zone_distance_m for row in rows), Decimal(0))
        ),
        average_quality_score=decimal_4(
            sum((row.quality_score for row in rows), Decimal(0)) / len(rows) if rows else Decimal(0)
        ),
    )


def impression_summary_from_cohort(cohort: ReportCohort) -> ImpressionSummary:
    rows = cohort.impressions
    return ImpressionSummary(
        estimated_impressions=decimal_2(
            sum((row.estimated_impressions for row in rows), Decimal(0))
        ),
        estimated_trip_count=sum(
            row.status == ImpressionEstimateStatus.ESTIMATED.value for row in rows
        ),
        insufficient_data_trip_count=sum(
            row.status == ImpressionEstimateStatus.INSUFFICIENT_DATA.value for row in rows
        ),
        excluded_trip_count=sum(
            row.status == ImpressionEstimateStatus.EXCLUDED.value for row in rows
        ),
        average_confidence_score=decimal_4(
            sum((row.confidence_score for row in rows), Decimal(0)) / len(rows)
            if rows
            else Decimal(0)
        ),
    )


async def fraud_counts_from_cohort(session: AsyncSession, cohort: ReportCohort) -> FraudFlagCounts:
    values = {status_value: 0 for status_value in FRAUD_STATUSES}
    severities = {severity: 0 for severity in FRAUD_SEVERITIES}
    if cohort.trip_ids:
        values.update(
            {
                str(status_value): int(count or 0)
                for status_value, count in (
                    await session.execute(
                        select(FraudFlag.status, func.count(FraudFlag.id))
                        .where(FraudFlag.trip_session_id.in_(cohort.trip_ids))
                        .group_by(FraudFlag.status)
                    )
                ).all()
            }
        )
        severities.update(
            {
                str(severity): int(count or 0)
                for severity, count in (
                    await session.execute(
                        select(FraudFlag.severity, func.count(FraudFlag.id))
                        .where(FraudFlag.trip_session_id.in_(cohort.trip_ids))
                        .group_by(FraudFlag.severity)
                    )
                ).all()
            }
        )
    return FraudFlagCounts(**values, **severities)


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
    organization_id = await require_governed_advertiser_output(
        session,
        settings=settings,
        route_id="advertiser.dashboard.summary",
        user_id=user_id,
    )
    organization, _ = await get_required_advertiser_context(session, user_id)
    await lock_trip_disclosure_snapshot(
        session,
        tenant_id=organization.id,
        campaign_id=None,
    )
    result = AdvertiserDashboardSummary(
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
    await record_governed_trip_output(
        session,
        settings=settings,
        route_id="advertiser.dashboard.summary",
        principal_id=user_id,
        tenant_id=organization_id,
        campaign_id=None,
        start_at=start_at,
        end_at=end_at,
        filters={},
        result=result,
    )
    return result


async def advertiser_campaign_summary(
    session: AsyncSession,
    *,
    user_id: UUID,
    campaign_id: UUID,
    start_at: datetime | None,
    end_at: datetime | None,
    settings: Settings,
    cohort: ReportCohort | None = None,
    record_history: bool = True,
) -> CampaignSummary:
    organization_id = await require_governed_advertiser_output(
        session,
        settings=settings,
        route_id="advertiser.campaign.summary",
        user_id=user_id,
    )
    campaign = await get_advertiser_campaign(session, user_id=user_id, campaign_id=campaign_id)
    await lock_trip_disclosure_snapshot(
        session,
        tenant_id=organization_id,
        campaign_id=campaign.id,
    )
    result = CampaignSummary(
        campaign=campaign_response(campaign),
        start_at=start_at,
        end_at=end_at,
        creatives=await creative_status_counts(session, campaign.id),
        zones=await zone_type_counts(session, campaign.id),
        assignments=await assignment_counts_for_campaign(session, campaign.id),
        trips=(
            trip_counts_from_cohort(cohort)
            if cohort is not None
            else await trip_counts_for_campaign(
                session, campaign.id, start_at=start_at, end_at=end_at
            )
        ),
        route_analytics=(
            route_analytics_from_cohort(cohort)
            if cohort is not None
            else await route_analytics_summary(
                session, campaign.id, start_at=start_at, end_at=end_at
            )
        ),
        impressions=(
            impression_summary_from_cohort(cohort)
            if cohort is not None
            else await impression_summary_for_campaign(
                session,
                campaign.id,
                start_at=start_at,
                end_at=end_at,
                settings=settings,
            )
        ),
        costs=(
            await campaign_cost_summary_from_cohort(
                session, cohort, default_currency=campaign.currency
            )
            if cohort is not None
            else await campaign_cost_summary(
                session,
                campaign.id,
                start_at=start_at,
                end_at=end_at,
                default_currency=campaign.currency,
                settings=settings,
            )
        ),
        fraud_flags=(
            await fraud_counts_from_cohort(session, cohort)
            if cohort is not None
            else await fraud_counts_for_campaign(
                session, campaign.id, start_at=start_at, end_at=end_at
            )
        ),
    )
    if record_history:
        await record_governed_trip_output(
            session,
            settings=settings,
            route_id="advertiser.campaign.summary",
            principal_id=user_id,
            tenant_id=organization_id,
            campaign_id=campaign.id,
            start_at=start_at,
            end_at=end_at,
            filters={},
            result=result,
        )
    return result


LAGOS = ZoneInfo("Africa/Lagos")


def campaign_daily_series(cohort: ReportCohort, *, start_day: date, end_day: date):
    """One Nigeria-day calculation for reports and the owned seven-day read (D118).

    Only verified driving contributes. A suppressed day contains no counts or
    amounts; an empty day has zero measured driving and zero estimated views.
    """
    trips = {trip.id: trip for trip in cohort.trips if trip.ended_at is not None}
    by_day = defaultdict(list)
    source_days = defaultdict(list)
    analytics = {row.trip_session_id: row for row in cohort.analytics}
    for trip in trips.values():
        ended = trip.ended_at
        assert ended is not None  # The terminal-trip map excludes open trips.
        if ended.tzinfo is None:
            ended = ended.replace(tzinfo=UTC)
        source_days[ended.astimezone(LAGOS).date()].append(trip)
    estimates = {r.trip_session_id: r for r in cohort.impressions if r.status == "estimated"}
    for row in cohort.analytics:
        trip = trips.get(row.trip_session_id)
        if (
            trip is not None
            and row.status == "computed"
            and (row.distance_m > 0 or row.moving_seconds > 0)
        ):
            ended = trip.ended_at
            assert ended is not None
            if ended.tzinfo is None:
                ended = ended.replace(tzinfo=UTC)
            by_day[ended.astimezone(LAGOS).date()].append(row)
    items = []
    day = start_day
    while day <= end_day:
        rows = by_day[day]
        cars = {row.vehicle_id for row in rows}
        incomplete = any(
            trip.id not in analytics or analytics[trip.id].status != "computed"
            for trip in source_days[day]
        )
        suppressed = (incomplete and not rows) or 0 < len(cars) < 3
        estimate_rows = [
            estimates[r.trip_session_id] for r in rows if r.trip_session_id in estimates
        ]
        items.append(
            DailyMetricItem(
                date=day,
                vehicle_count=None if suppressed else len(cars),
                trip_count=None if suppressed else len(rows),
                distance_m=None if suppressed else sum((r.distance_m for r in rows), ZERO_2),
                driving_seconds=None if suppressed else sum(r.moving_seconds for r in rows),
                estimated_impressions=(
                    None
                    if suppressed or len(estimate_rows) != len(rows)
                    else sum((r.estimated_impressions for r in estimate_rows), ZERO_2)
                ),
                suppressed=suppressed,
            )
        )
        day += timedelta(days=1)
    return items


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
    cohort: ReportCohort | None = None,
    record_history: bool = True,
) -> DailyMetricsResponse:
    from app.services.disclosure import DisclosureQuery, _canonical_hash, record_disclosure
    from app.services.payout_rule_serialization import database_clock

    organization_id = await require_governed_advertiser_output(
        session,
        settings=settings,
        route_id="advertiser.campaign.daily_metrics",
        user_id=user_id,
    )
    campaign = await get_advertiser_campaign(session, user_id=user_id, campaign_id=campaign_id)
    await lock_trip_disclosure_snapshot(session, tenant_id=organization_id, campaign_id=campaign.id)
    now = await database_clock(session)
    today = now.astimezone(LAGOS).date()
    last_day = (
        min((end_at - timedelta(microseconds=1)).astimezone(LAGOS).date(), today)
        if end_at
        else today
    )
    first_day = start_at.astimezone(LAGOS).date() if start_at else last_day - timedelta(days=6)
    start = start_at or datetime.combine(first_day, time.min, LAGOS)
    end = min(end_at, now) if end_at else now
    if first_day > last_day or start > end:
        raise AppError(
            "REPORT_PERIOD_INVALID", "Choose a reporting period that has started", status_code=422
        )
    total = (last_day - first_day).days + 1
    page_start = first_day + timedelta(days=min(offset, total))
    page_end = min(last_day, page_start + timedelta(days=limit - 1))
    if cohort is None and offset < total and start < end:
        cohort = await select_report_cohort(
            session,
            campaign_id=campaign.id,
            start_at=max(start, datetime.combine(page_start, time.min, LAGOS)),
            end_at=min(end, datetime.combine(page_end + timedelta(days=1), time.min, LAGOS)),
            settings=settings,
            terminal_period=True,
            include_money=False,
        )
    cohort = cohort or ReportCohort((), (), (), (), terminal_period=True)
    series = campaign_daily_series(cohort, start_day=page_start, end_day=page_end)
    result = DailyMetricsResponse(
        campaign_id=campaign.id,
        start_at=start,
        end_at=end,
        items=series,
        total=total,
        limit=limit,
        offset=offset,
    )
    if record_history:
        # Placeholders disclose no contributor facts. Every nonzero measured day
        # was independently checked; an empty day is the client-requested zero.
        safe = all(
            (
                row.suppressed
                and all(
                    value is None
                    for value in (
                        row.vehicle_count,
                        row.trip_count,
                        row.distance_m,
                        row.driving_seconds,
                        row.estimated_impressions,
                    )
                )
            )
            or (
                not row.suppressed
                and row.vehicle_count is not None
                and (row.vehicle_count == 0 or row.vehicle_count >= 3)
            )
            for row in result.items
        )
        await record_disclosure(
            session,
            settings=settings,
            query=DisclosureQuery(
                route_id="advertiser.campaign.daily_metrics",
                principal_id=user_id,
                tenant_id=organization_id,
                campaign_id=campaign.id,
                start_at=start,
                end_at=end,
                filters={"limit": limit, "offset": offset},
            ),
            has_releasable_cells=safe,
            result_hash=_canonical_hash(result.model_dump(mode="json")),
        )
    return result


async def advertiser_campaign_trips(
    session: AsyncSession,
    *,
    user_id: UUID,
    campaign_id: UUID,
    settings: Settings,
) -> CampaignTripsResponse:
    organization_id = await require_governed_advertiser_output(
        session,
        settings=settings,
        route_id="advertiser.campaign.trips",
        user_id=user_id,
    )
    campaign = await get_advertiser_campaign(session, user_id=user_id, campaign_id=campaign_id)
    await lock_trip_disclosure_snapshot(
        session,
        tenant_id=organization_id,
        campaign_id=campaign.id,
    )
    result = CampaignTripsResponse(
        campaign_id=campaign.id,
        trips=await trip_counts_for_campaign(
            session,
            campaign.id,
            start_at=None,
            end_at=None,
        ),
        route_analytics=await route_analytics_summary(
            session,
            campaign.id,
            start_at=None,
            end_at=None,
        ),
        impressions=await impression_summary_for_campaign(
            session,
            campaign.id,
            start_at=None,
            end_at=None,
            settings=settings,
        ),
        costs=await campaign_cost_summary(
            session,
            campaign.id,
            start_at=None,
            end_at=None,
            default_currency=campaign.currency,
            settings=settings,
        ),
        fraud_flags=await fraud_counts_for_campaign(
            session,
            campaign.id,
            start_at=None,
            end_at=None,
        ),
    )
    await record_governed_trip_output(
        session,
        settings=settings,
        route_id="advertiser.campaign.trips",
        principal_id=user_id,
        tenant_id=organization_id,
        campaign_id=campaign.id,
        start_at=None,
        end_at=None,
        filters={},
        result=result,
    )
    return result


async def advertiser_campaign_report(session, *, user_id, campaign_id, start_at, end_at, settings):
    from app.services.campaign_performance import PERFORMANCE_POLICY, live_campaign_performance
    from app.services.disclosure import DisclosureQuery, _canonical_hash, record_disclosure
    from app.services.payout_rule_serialization import database_clock

    organization_id = await require_governed_advertiser_output(
        session, settings=settings, route_id="advertiser.campaign.performance", user_id=user_id
    )
    campaign = await get_advertiser_campaign(session, user_id=user_id, campaign_id=campaign_id)
    await lock_trip_disclosure_snapshot(session, tenant_id=organization_id, campaign_id=campaign_id)
    result = await live_campaign_performance(
        session,
        campaign=campaign,
        settings=settings,
        now=await database_clock(session),
        start_at=start_at,
        end_at=end_at,
    )
    await record_disclosure(
        session,
        query=DisclosureQuery(
            route_id="advertiser.campaign.performance",
            principal_id=user_id,
            tenant_id=organization_id,
            campaign_id=campaign_id,
            start_at=result.start_at,
            end_at=result.end_at,
            filters={"policy": PERFORMANCE_POLICY},
        ),
        settings=settings,
        has_releasable_cells=True,
        result_hash=_canonical_hash(result.model_dump(mode="json")),
    )
    return result
