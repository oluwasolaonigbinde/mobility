from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import and_, delete, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.config import Settings
from app.core.errors import AppError
from app.models.campaign import Campaign
from app.models.campaign_assignment import CampaignAssignment
from app.models.disclosure import DisclosureQueryDecision
from app.models.impression import ImpressionEstimate, ImpressionEstimateStatus
from app.models.organization import AdvertiserOrganization, OrganizationMembership
from app.models.payout import EarningsLedgerEntry, PayoutCalculation
from app.models.trip import TripSession
from app.models.trip_analytics import FraudFlag, TripAnalytics

DISCLOSURE_ROUTE_INVENTORY = frozenset(
    {
        "advertiser.dashboard.summary",
        "advertiser.campaign.summary",
        "advertiser.campaign.daily_metrics",
        "advertiser.campaign.trips",
        "advertiser.campaign.report",
        "advertiser.campaign.impressions_summary",
        "advertiser.campaign.heatmap",
        "admin.heatmap",
        "advertiser.audience.recommendations",
        "admin.audience.recommendations",
        "advertiser.audience.export",
        "admin.audience.activation",
        "advertiser.campaign.zone_insights",
        "admin.campaign.zone_insights",
    }
)

_PLACEHOLDERS = {"", "missing", "todo", "tbd", "placeholder", "n/a", "none"}
_DEFAULT_WINDOW_START = datetime(2000, 1, 1, tzinfo=UTC)
_DEFAULT_WINDOW_END = datetime(2100, 1, 1, tzinfo=UTC)


@dataclass(frozen=True)
class DisclosureQuery:
    route_id: str
    principal_id: UUID
    tenant_id: UUID | None
    campaign_id: UUID | None
    start_at: datetime | None
    end_at: datetime | None
    filters: dict[str, Any]


def _approved_reference(value: str) -> bool:
    normalized = value.strip().lower()
    return normalized not in _PLACEHOLDERS and not normalized.startswith("ext-")


def ensure_disclosure_live_gate(settings: Settings, *, requires_measurement_run: bool) -> None:
    if settings.privacy_disclosure_synthetic_test_mode:
        return
    references = (
        settings.privacy_legal_approval_reference,
        settings.privacy_disclosure_config_reference,
        settings.privacy_query_history_retention_reference,
    )
    if not settings.privacy_disclosure_live_authorized or not all(
        _approved_reference(reference) for reference in references
    ):
        raise AppError(
            "PRIVACY_LIVE_USE_BLOCKED",
            "Advertiser analytics are unavailable until privacy approval and disclosure "
            "controls are complete",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    if requires_measurement_run:
        raise AppError(
            "SAFE_MEASUREMENT_RUN_REQUIRED",
            "This output remains unavailable until immutable measurement runs are implemented",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )


async def require_governed_advertiser_output(
    session: AsyncSession,
    *,
    settings: Settings,
    route_id: str,
    user_id: UUID,
    requires_measurement_run: bool = True,
) -> UUID:
    if route_id not in DISCLOSURE_ROUTE_INVENTORY:
        raise RuntimeError(f"Unregistered disclosure route: {route_id}")
    ensure_disclosure_live_gate(
        settings,
        requires_measurement_run=requires_measurement_run,
    )
    row = (
        await session.execute(
            select(AdvertiserOrganization.id)
            .join(
                OrganizationMembership,
                OrganizationMembership.organization_id == AdvertiserOrganization.id,
            )
            .where(
                OrganizationMembership.user_id == user_id,
                OrganizationMembership.status == "active",
                AdvertiserOrganization.status == "active",
            )
            .order_by(
                OrganizationMembership.created_at.desc(),
                OrganizationMembership.id.desc(),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        raise AppError(
            "ADVERTISER_ORGANIZATION_NOT_FOUND",
            "Advertiser organization was not found for the current user",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return row


async def lock_trip_disclosure_snapshot(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    campaign_id: UUID | None,
) -> None:
    """Freeze report contributors before response construction under PostgreSQL."""
    if session.get_bind().dialect.name != "postgresql":
        return
    await session.scalar(
        select(AdvertiserOrganization.id)
        .where(AdvertiserOrganization.id == tenant_id)
        .with_for_update()
    )
    campaign_filters = [Campaign.organization_id == tenant_id]
    if campaign_id is not None:
        campaign_filters.append(Campaign.id == campaign_id)
    campaign_ids = list(
        await session.scalars(
            select(Campaign.id)
            .where(*campaign_filters)
            .order_by(Campaign.id)
            .with_for_update()
        )
    )
    if not campaign_ids:
        return
    list(
        await session.scalars(
            select(CampaignAssignment.id)
            .where(CampaignAssignment.campaign_id.in_(campaign_ids))
            .order_by(CampaignAssignment.id)
            .with_for_update()
        )
    )
    trip_ids = list(
        await session.scalars(
            select(TripSession.id)
            .where(TripSession.campaign_id.in_(campaign_ids))
            .order_by(TripSession.id)
            .with_for_update()
        )
    )
    if not trip_ids:
        return
    for model in (
        TripAnalytics,
        ImpressionEstimate,
        PayoutCalculation,
        FraudFlag,
        EarningsLedgerEntry,
    ):
        await session.scalars(
            select(model.id)
            .where(model.trip_session_id.in_(trip_ids))
            .order_by(model.id)
            .with_for_update()
        )


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def _principal_hash(principal_id: UUID) -> str:
    return hashlib.sha256(f"disclosure-principal-v1:{principal_id}".encode()).hexdigest()


def _window(query: DisclosureQuery) -> tuple[datetime, datetime]:
    return query.start_at or _DEFAULT_WINDOW_START, query.end_at or _DEFAULT_WINDOW_END


def _utc_date(value: datetime):
    aware = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return aware.astimezone(UTC).date()


async def _lock_disclosure_history(session: AsyncSession) -> None:
    if session.get_bind().dialect.name != "postgresql":
        return
    lock_digest = hashlib.sha256(b"disclosure-history-v2").digest()[:8]
    lock_key = int.from_bytes(lock_digest, "big", signed=True)
    await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key})


def disclosure_suppressed(reason: str) -> AppError:
    return AppError(
        "DISCLOSURE_SUPPRESSED",
        "The requested aggregate is unavailable under the privacy disclosure floor",
        status_code=status.HTTP_409_CONFLICT,
        details={"reason": reason},
    )


def exposure_cell_meets_disclosure_floor(
    *,
    distinct_vehicle_count: int,
    trip_count: int,
    distinct_day_count: int,
    max_contributor_share: float,
    resolution_m: int,
    settings: Settings,
) -> bool:
    """Apply the complete audience disclosure policy before persistence or release."""
    return (
        distinct_vehicle_count >= settings.privacy_min_vehicles_per_cell
        and trip_count >= settings.privacy_min_trips_per_cell
        and distinct_day_count >= settings.privacy_min_days_per_cell
        and max_contributor_share <= settings.privacy_max_contributor_share
        and resolution_m >= settings.privacy_min_resolution_m
    )


def audience_disclosure_policy(settings: Settings) -> dict[str, int | float | str]:
    return {
        "schema_version": "audience-disclosure-policy-v1",
        "minimum_distinct_vehicles": settings.privacy_min_vehicles_per_cell,
        "minimum_distinct_trips": settings.privacy_min_trips_per_cell,
        "minimum_distinct_days": settings.privacy_min_days_per_cell,
        "maximum_contributor_share": settings.privacy_max_contributor_share,
        "minimum_resolution_m": settings.privacy_min_resolution_m,
        "window_alignment": "whole_utc_hours",
    }


def _maximum_contributor_share(
    contributions: dict[str, Counter[UUID]],
) -> float:
    shares = []
    for by_vehicle in contributions.values():
        total = sum(by_vehicle.values(), Decimal("0"))
        if total > 0:
            shares.append(max(by_vehicle.values()) / total)
    return float(max(shares, default=Decimal("1")))


def _add_contribution(
    contributions: dict[str, Counter[UUID]],
    metric: str,
    vehicle_id: UUID,
    value: int | float | Decimal | None,
) -> None:
    amount = Decimal(str(value or 0))
    if amount > 0:
        contributions.setdefault(metric, Counter())[vehicle_id] += amount


def frozen_manifest_meets_disclosure_floor(
    manifest: dict[str, Any], *, settings: Settings
) -> bool:
    authority = manifest.get("disclosure_authority")
    if isinstance(authority, dict):
        frozen_contributions: dict[str, Counter[UUID]] = {}
        try:
            for metric, values in authority["contributions"].items():
                frozen_contributions[metric] = Counter(
                    {UUID(vehicle_id): Decimal(str(value)) for vehicle_id, value in values.items()}
                )
        except (AttributeError, KeyError, TypeError, ValueError):
            return False
        return (
            authority.get("schema_version") == "frozen-report-disclosure-v1"
            and authority.get("route_id") == "advertiser.campaign.report"
            and authority.get("passed") is True
            and authority.get("vehicle_count") >= settings.privacy_min_vehicles_per_cell
            and authority.get("trip_count") >= settings.privacy_min_trips_per_cell
            and authority.get("day_count") >= settings.privacy_min_days_per_cell
            and all(
                len(values) >= settings.privacy_min_vehicles_per_cell
                and sum(values.values(), Decimal("0"))
                >= settings.privacy_min_trips_per_cell
                for metric, values in frozen_contributions.items()
                if metric.startswith("daily:trip_count:")
            )
            and _maximum_contributor_share(frozen_contributions)
            <= settings.privacy_max_contributor_share
        )
    sources = manifest.get("sources", {})
    analytics = [
        row for row in sources.get("trip_analytics", []) if row.get("status") == "computed"
    ]
    estimates = [
        row for row in sources.get("impression_estimates", []) if row.get("status") == "estimated"
    ]
    calculations = [
        row for row in sources.get("payout_calculations", []) if row.get("status") == "calculated"
    ]
    required_analytics = {
        "trip_session_id",
        "vehicle_id",
        "started_at",
        "distance_m",
        "target_zone_distance_m",
        "bonus_zone_distance_m",
        "exclusion_zone_distance_m",
        "active_tracking_seconds",
        "quality_score",
    }
    if not analytics or any(not required_analytics <= row.keys() for row in analytics):
        return False
    vehicle_by_trip = {
        str(row["trip_session_id"]): UUID(str(row["vehicle_id"])) for row in analytics
    }
    contributions: dict[str, Counter[UUID]] = {}
    trip_ids = set(vehicle_by_trip)
    days = set()
    for row in analytics:
        vehicle_id = UUID(str(row["vehicle_id"]))
        days.add(_utc_date(datetime.fromisoformat(str(row["started_at"]))))
        _add_contribution(contributions, "analytics:trip_count", vehicle_id, 1)
        for metric in (
            "distance_m",
            "target_zone_distance_m",
            "bonus_zone_distance_m",
            "exclusion_zone_distance_m",
            "active_tracking_seconds",
            "quality_score",
        ):
            _add_contribution(contributions, f"analytics:{metric}", vehicle_id, row[metric])
    for row in estimates:
        vehicle_id = vehicle_by_trip.get(str(row.get("trip_session_id")))
        if vehicle_id is None:
            return False
        _add_contribution(contributions, f"impressions:status:{row['status']}", vehicle_id, 1)
        _add_contribution(
            contributions,
            "impressions:estimated_impressions",
            vehicle_id,
            row.get("estimated_impressions"),
        )
        _add_contribution(
            contributions,
            "impressions:confidence_score",
            vehicle_id,
            row.get("confidence_score"),
        )
    for row in calculations:
        vehicle_id = vehicle_by_trip.get(str(row.get("trip_session_id")))
        if vehicle_id is None:
            return False
        for metric in ("gross_payout", "final_payout"):
            _add_contribution(
                contributions,
                f"cost:{row['currency']}:{metric}",
                vehicle_id,
                row.get(metric),
            )
    return (
        len(set(vehicle_by_trip.values())) >= settings.privacy_min_vehicles_per_cell
        and len(trip_ids) >= settings.privacy_min_trips_per_cell
        and len(days) >= settings.privacy_min_days_per_cell
        and _maximum_contributor_share(contributions)
        <= settings.privacy_max_contributor_share
    )


async def trip_cohort_meets_disclosure_floor(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    campaign_id: UUID | None,
    start_at: datetime | None,
    end_at: datetime | None,
    route_id: str,
    settings: Settings,
    return_manifest: bool = False,
) -> bool | dict[str, Any]:
    filters = [Campaign.organization_id == tenant_id]
    if campaign_id is not None:
        filters.append(TripSession.campaign_id == campaign_id)
    if start_at is not None:
        filters.append(TripSession.started_at >= start_at)
    if end_at is not None:
        filters.append(TripSession.started_at <= end_at)
    rows = (
        await session.execute(
            select(
                TripSession.id,
                TripSession.vehicle_id,
                TripSession.started_at,
                TripSession.status,
            )
            .join(Campaign, Campaign.id == TripSession.campaign_id)
            .where(*filters)
        )
    ).all()
    if not rows:
        if return_manifest:
            return {
                "passed": False,
                "vehicle_count": 0,
                "trip_count": 0,
                "day_count": 0,
                "contributions": {},
            }
        return False
    trip_ids = {row.id for row in rows}
    vehicles = Counter(row.vehicle_id for row in rows)
    trip_rows = {row.id: row for row in rows}
    daily_metrics = route_id == "advertiser.campaign.daily_metrics"
    contributions: dict[str, Counter[UUID]] = {}
    if route_id in {
        "advertiser.dashboard.summary",
        "advertiser.campaign.summary",
        "advertiser.campaign.report",
    }:
        assignment_statement = select(CampaignAssignment).join(
            Campaign, Campaign.id == CampaignAssignment.campaign_id
        )
        assignment_filters = [Campaign.organization_id == tenant_id]
        if campaign_id is not None:
            assignment_filters.append(CampaignAssignment.campaign_id == campaign_id)
        assignments = list(
            await session.scalars(assignment_statement.where(*assignment_filters))
        )
        for assignment in assignments:
            _add_contribution(
                contributions,
                f"assignment:status:{assignment.status}",
                assignment.vehicle_id,
                1,
            )
    if route_id != "advertiser.campaign.impressions_summary":
        for row in rows:
            day = _utc_date(row.started_at)
            metric = f"trip_count:{day}" if daily_metrics else f"trip_status:{row.status}"
            _add_contribution(contributions, metric, row.vehicle_id, 1)

    include_all_metrics = route_id != "advertiser.campaign.impressions_summary"
    if include_all_metrics:
        analytics = list(
            await session.scalars(
                select(TripAnalytics).where(
                    TripAnalytics.trip_session_id.in_(trip_ids),
                )
            )
        )
        for row in analytics:
            for metric in (
                "distance_m",
                "target_zone_distance_m",
                "bonus_zone_distance_m",
                "exclusion_zone_distance_m",
                "quality_score",
            ):
                group = (
                    f":{_utc_date(trip_rows[row.trip_session_id].started_at)}"
                    if daily_metrics
                    else ""
                )
                _add_contribution(
                    contributions,
                    f"analytics:{metric}{group}",
                    row.vehicle_id,
                    getattr(row, metric),
                )
            group = (
                f":{_utc_date(trip_rows[row.trip_session_id].started_at)}" if daily_metrics else ""
            )
            _add_contribution(contributions, f"analytics:count{group}", row.vehicle_id, 1)

    estimate_filters = [
        ImpressionEstimate.formula_version == settings.impression_formula_version,
        ImpressionEstimate.is_authoritative.is_(True),
    ]
    estimate_statement = select(ImpressionEstimate)
    if daily_metrics:
        estimate_filters.append(ImpressionEstimate.trip_session_id.in_(trip_ids))
    else:
        if campaign_id is not None:
            estimate_filters.append(ImpressionEstimate.campaign_id == campaign_id)
        else:
            estimate_statement = estimate_statement.join(
                Campaign, Campaign.id == ImpressionEstimate.campaign_id
            )
            estimate_filters.append(Campaign.organization_id == tenant_id)
        if start_at is not None:
            estimate_filters.append(ImpressionEstimate.estimated_at >= start_at)
        if end_at is not None:
            estimate_filters.append(ImpressionEstimate.estimated_at <= end_at)
    estimates = list(await session.scalars(estimate_statement.where(*estimate_filters)))
    from app.services.impressions import current_authoritative_estimates

    estimates = await current_authoritative_estimates(session, estimates, settings=settings)
    for row in estimates:
        group = f":{_utc_date(trip_rows[row.trip_session_id].started_at)}" if daily_metrics else ""
        _add_contribution(
            contributions,
            f"impressions:trip_count{group}",
            row.vehicle_id,
            1,
        )
        _add_contribution(
            contributions,
            f"impressions:status:{row.status}{group}",
            row.vehicle_id,
            1,
        )
        _add_contribution(
            contributions,
            f"impressions:estimated_impressions{group}",
            row.vehicle_id,
            row.estimated_impressions
            if row.status == ImpressionEstimateStatus.ESTIMATED.value
            else 0,
        )
        _add_contribution(
            contributions,
            f"impressions:confidence_score{group}",
            row.vehicle_id,
            row.confidence_score,
        )

    if include_all_metrics:
        from app.services.payouts import latest_payout_calculation_ids

        calculation_filters = []
        if daily_metrics:
            calculation_filters.append(PayoutCalculation.trip_session_id.in_(trip_ids))
            latest_calculation_ids = latest_payout_calculation_ids(trip_ids=trip_ids)
        elif campaign_id is not None:
            calculation_filters.append(PayoutCalculation.campaign_id == campaign_id)
            latest_calculation_ids = latest_payout_calculation_ids(campaign_id=campaign_id)
        else:
            calculation_filters.append(Campaign.organization_id == tenant_id)
            latest_calculation_ids = latest_payout_calculation_ids(organization_id=tenant_id)
        if not daily_metrics and start_at is not None:
            calculation_filters.append(PayoutCalculation.calculated_at >= start_at)
        if not daily_metrics and end_at is not None:
            calculation_filters.append(PayoutCalculation.calculated_at <= end_at)
        calculation_statement = select(PayoutCalculation)
        if campaign_id is None and not daily_metrics:
            calculation_statement = calculation_statement.join(
                Campaign, Campaign.id == PayoutCalculation.campaign_id
            )
        calculations = list(
            await session.scalars(
                calculation_statement.where(
                    *calculation_filters,
                    PayoutCalculation.id.in_(latest_calculation_ids),
                )
            )
        )
        for row in calculations:
            group = (
                f":{_utc_date(trip_rows[row.trip_session_id].started_at)}" if daily_metrics else ""
            )
            for metric in ("gross_payout", "final_payout"):
                _add_contribution(
                    contributions,
                    f"cost:{row.currency}:{metric}{group}",
                    row.vehicle_id,
                    getattr(row, metric),
                )
            if route_id != "advertiser.dashboard.summary" and not daily_metrics:
                _add_contribution(
                    contributions,
                    f"cost:{row.currency}:status:{row.status}",
                    row.vehicle_id,
                    1,
                )
        calculation_ids = {row.id: row for row in calculations}
        ledger_rows = list(
            await session.scalars(
                select(EarningsLedgerEntry).where(
                    EarningsLedgerEntry.payout_calculation_id.in_(calculation_ids)
                )
            )
        )
        for ledger in ledger_rows:
            calculation = calculation_ids[ledger.payout_calculation_id]
            group = (
                f":{_utc_date(trip_rows[calculation.trip_session_id].started_at)}"
                if daily_metrics
                else ""
            )
            _add_contribution(
                contributions,
                f"cost:{calculation.currency}:ledger_count{group}",
                calculation.vehicle_id,
                1,
            )
        fraud_filters = (
            [FraudFlag.trip_session_id.in_(trip_ids)] if daily_metrics else []
        )
        fraud_statement = select(FraudFlag)
        if daily_metrics:
            pass
        elif campaign_id is not None:
            fraud_filters.append(FraudFlag.campaign_id == campaign_id)
        else:
            fraud_statement = fraud_statement.join(
                Campaign, Campaign.id == FraudFlag.campaign_id
            )
            fraud_filters.append(Campaign.organization_id == tenant_id)
        if not daily_metrics:
            if start_at is not None:
                fraud_filters.append(FraudFlag.detected_at >= start_at)
            if end_at is not None:
                fraud_filters.append(FraudFlag.detected_at <= end_at)
        flags = list(await session.scalars(fraud_statement.where(*fraud_filters)))
        for row in flags:
            if daily_metrics:
                if row.status == "open":
                    day = _utc_date(trip_rows[row.trip_session_id].started_at)
                    _add_contribution(
                        contributions,
                        f"fraud:open:{day}",
                        row.vehicle_id,
                        1,
                    )
            else:
                _add_contribution(
                    contributions,
                    f"fraud:status:{row.status}",
                    row.vehicle_id,
                    1,
                )
                _add_contribution(
                    contributions,
                    f"fraud:severity:{row.severity}",
                    row.vehicle_id,
                    1,
                )
    days = {
        (value if value.tzinfo is not None else value.replace(tzinfo=UTC)).astimezone(UTC).date()
        for _, _, value, _ in rows
    }
    max_contributor_share = _maximum_contributor_share(contributions)
    if daily_metrics:
        daily_trip_vehicles: dict[str, Counter[UUID]] = {}
        for row in rows:
            _add_contribution(
                daily_trip_vehicles,
                str(_utc_date(row.started_at)),
                row.vehicle_id,
                1,
            )
        if any(
            len(day_vehicles) < settings.privacy_min_vehicles_per_cell
            or sum(day_vehicles.values()) < settings.privacy_min_trips_per_cell
            for day_vehicles in daily_trip_vehicles.values()
        ):
            if not return_manifest:
                return False
            return {
                "passed": False,
                "vehicle_count": len(vehicles),
                "trip_count": len(trip_ids),
                "day_count": len(days),
                "contributions": {
                    metric: {
                        str(vehicle_id): str(value) for vehicle_id, value in values.items()
                    }
                    for metric, values in sorted(contributions.items())
                },
            }
    passed = (
        len(vehicles) >= settings.privacy_min_vehicles_per_cell
        and len(trip_ids) >= settings.privacy_min_trips_per_cell
        and len(days) >= settings.privacy_min_days_per_cell
        and max_contributor_share <= settings.privacy_max_contributor_share
    )
    if not return_manifest:
        return passed
    return {
        "passed": passed,
        "vehicle_count": len(vehicles),
        "trip_count": len(trip_ids),
        "day_count": len(days),
        "contributions": {
            metric: {str(vehicle_id): str(value) for vehicle_id, value in values.items()}
            for metric, values in sorted(contributions.items())
        },
    }


async def record_governed_trip_output(
    session: AsyncSession,
    *,
    settings: Settings,
    route_id: str,
    principal_id: UUID,
    tenant_id: UUID,
    campaign_id: UUID | None,
    start_at: datetime | None,
    end_at: datetime | None,
    filters: dict[str, Any],
    result: Any,
    contribution_manifest: dict[str, Any] | None = None,
) -> None:
    serialized = result.model_dump(mode="json") if hasattr(result, "model_dump") else result
    has_releasable_cells = settings.privacy_disclosure_synthetic_test_mode or (
        frozen_manifest_meets_disclosure_floor(contribution_manifest, settings=settings)
        if contribution_manifest is not None
        else await trip_cohort_meets_disclosure_floor(
            session,
            tenant_id=tenant_id,
            campaign_id=campaign_id,
            start_at=start_at,
            end_at=end_at,
            route_id=route_id,
            settings=settings,
        )
    )
    await record_disclosure(
        session,
        query=DisclosureQuery(
            route_id=route_id,
            principal_id=principal_id,
            tenant_id=tenant_id,
            campaign_id=campaign_id,
            start_at=start_at,
            end_at=end_at,
            filters=filters,
        ),
        settings=settings,
        has_releasable_cells=has_releasable_cells,
        result_hash=_canonical_hash(serialized),
    )


async def record_disclosure(
    session: AsyncSession,
    *,
    query: DisclosureQuery,
    settings: Settings,
    has_releasable_cells: bool,
    result_hash: str,
    commit_served: bool = True,
) -> None:
    if query.route_id not in DISCLOSURE_ROUTE_INVENTORY:
        raise RuntimeError(f"Unregistered disclosure route: {query.route_id}")
    ensure_disclosure_live_gate(settings, requires_measurement_run=False)
    if settings.privacy_disclosure_synthetic_test_mode:
        return
    principal_hash = _principal_hash(query.principal_id)
    scope_hash = _canonical_hash(
        {
            "tenant_id": query.tenant_id,
            "campaign_id": query.campaign_id,
            "family": "governed_aggregate_v2",
        }
    )
    window_start, window_end = _window(query)
    query_hash = _canonical_hash(
        {
            "route_id": query.route_id,
            "scope_hash": scope_hash,
            "window_start": window_start,
            "window_end": window_end,
            "filters": query.filters,
        }
    )
    await _lock_disclosure_history(session)
    now = datetime.now(UTC)
    await session.execute(
        delete(DisclosureQueryDecision).where(DisclosureQueryDecision.expires_at <= now)
    )
    exact = await session.scalar(
        select(DisclosureQueryDecision).where(
            DisclosureQueryDecision.principal_hash == principal_hash,
            DisclosureQueryDecision.scope_hash == scope_hash,
            DisclosureQueryDecision.query_hash == query_hash,
            DisclosureQueryDecision.result_hash == result_hash,
            DisclosureQueryDecision.output_class == query.route_id,
        )
    )
    if exact is not None:
        if exact.decision == "suppressed":
            raise disclosure_suppressed(exact.reason)
        return

    if query.tenant_id is None:
        overlap_scope = True
    elif query.campaign_id is None:
        overlap_scope = or_(
            DisclosureQueryDecision.tenant_id.is_(None),
            DisclosureQueryDecision.tenant_id == query.tenant_id,
        )
    else:
        overlap_scope = or_(
            DisclosureQueryDecision.tenant_id.is_(None),
            and_(
                DisclosureQueryDecision.tenant_id == query.tenant_id,
                or_(
                    DisclosureQueryDecision.campaign_id.is_(None),
                    DisclosureQueryDecision.campaign_id == query.campaign_id,
                ),
            ),
        )
    prior = await session.scalar(
        select(DisclosureQueryDecision.id)
        .where(
            overlap_scope,
            DisclosureQueryDecision.expires_at > now,
            DisclosureQueryDecision.window_start <= window_end,
            DisclosureQueryDecision.window_end >= window_start,
        )
        .limit(1)
    )
    decision = "served"
    reason = "privacy_floor_passed"
    if prior is not None:
        decision = "suppressed"
        reason = "overlapping_query_differencing"
    elif not has_releasable_cells:
        decision = "suppressed"
        reason = "minimum_counts_or_contributor_cap"
    session.add(
        DisclosureQueryDecision(
            principal_hash=principal_hash,
            scope_hash=scope_hash,
            query_hash=query_hash,
            result_hash=result_hash,
            tenant_id=query.tenant_id,
            campaign_id=query.campaign_id,
            output_class=query.route_id,
            decision=decision,
            reason=reason,
            window_start=window_start,
            window_end=window_end,
            expires_at=now + timedelta(days=settings.privacy_query_history_retention_days),
        )
    )
    if decision == "suppressed" or commit_served:
        await session.commit()
    else:
        await session.flush()
    if decision == "suppressed":
        raise disclosure_suppressed(reason)


async def record_heatmap_disclosure(
    session: AsyncSession,
    *,
    query: DisclosureQuery,
    settings: Settings,
    has_releasable_cells: bool,
    result_hash: str,
) -> None:
    if query.route_id not in {"advertiser.campaign.heatmap", "admin.heatmap"}:
        raise RuntimeError("Heatmap disclosure history received a non-heatmap route")
    await record_disclosure(
        session,
        query=query,
        settings=settings,
        has_releasable_cells=has_releasable_cells,
        result_hash=result_hash,
    )
