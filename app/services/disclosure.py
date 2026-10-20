from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

if TYPE_CHECKING:
    from app.services.report_cohorts import ReportCohort

from app.core.config import Settings
from app.core.errors import AppError
from app.models.campaign import Campaign
from app.models.campaign_assignment import CampaignAssignment
from app.models.disclosure import DisclosureQueryDecision
from app.models.impression import ImpressionEstimate
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
        "advertiser.campaign.performance",
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


async def require_governed_advertiser_output(
    session: AsyncSession,
    *,
    settings: Settings,
    route_id: str,
    user_id: UUID,
) -> UUID:
    if route_id not in DISCLOSURE_ROUTE_INVENTORY:
        raise RuntimeError(f"Unregistered disclosure route: {route_id}")
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
    from app.services.fraud_holds import lock_fraud_reconciliation_gate

    # Exclude fraud/money writers before parent FK and contributor row locks.
    await lock_fraud_reconciliation_gate(session, exclusive=True)
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
            select(Campaign.id).where(*campaign_filters).order_by(Campaign.id).with_for_update()
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
    resolution_m: int,
    settings: Settings,
) -> bool:
    """D107: a cell is released when at least three distinct cars contributed."""
    return (
        distinct_vehicle_count >= settings.privacy_min_vehicles_per_cell
        and resolution_m >= settings.privacy_min_resolution_m
    )


def audience_disclosure_policy(settings: Settings) -> dict[str, int | float | str]:
    return {
        "schema_version": "audience-disclosure-policy-v2",
        "minimum_distinct_vehicles": settings.privacy_min_vehicles_per_cell,
        "minimum_resolution_m": settings.privacy_min_resolution_m,
        "window_alignment": "whole_utc_hours",
    }


def _add_contribution(
    contributions: dict[str, Counter[UUID]],
    metric: str,
    vehicle_id: UUID,
    value: int | float | Decimal | None,
) -> None:
    amount = Decimal(str(value or 0))
    if amount > 0:
        contributions.setdefault(metric, Counter())[vehicle_id] += amount


def frozen_manifest_meets_disclosure_floor(manifest: dict[str, Any], *, settings: Settings) -> bool:
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
            and all(
                len(values) >= settings.privacy_min_vehicles_per_cell
                for metric, values in frozen_contributions.items()
                if metric.startswith("daily:trip_count:")
            )
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
    # Every released estimate and cost must belong to a trip in the same frozen cohort.
    if any(
        str(row.get("trip_session_id")) not in vehicle_by_trip
        for row in [*estimates, *calculations]
    ):
        return False
    vehicles_by_day: dict[date, set[UUID]] = {}
    for row in analytics:
        day = _utc_date(datetime.fromisoformat(str(row["started_at"])))
        vehicles_by_day.setdefault(day, set()).add(UUID(str(row["vehicle_id"])))
    return len(set(vehicle_by_trip.values())) >= settings.privacy_min_vehicles_per_cell and all(
        len(vehicles) >= settings.privacy_min_vehicles_per_cell
        for vehicles in vehicles_by_day.values()
    )


async def _dated_outputs_meet_floor(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    campaign_id: UUID | None,
    start_at: datetime | None,
    end_at: datetime | None,
    route_id: str,
    settings: Settings,
) -> bool:
    """D107 for a date range: estimates, costs and fraud flags are picked by their own
    timestamps, not by trip start, so each released set needs three cars of its own."""
    from app.services.impressions import current_authoritative_estimates
    from app.services.payouts.ledger import latest_payout_calculation_ids

    def scoped(statement, model, stamp):
        if campaign_id is not None:
            statement = statement.where(model.campaign_id == campaign_id)
        else:
            statement = statement.join(Campaign, Campaign.id == model.campaign_id).where(
                Campaign.organization_id == tenant_id
            )
        if start_at is not None:
            statement = statement.where(stamp >= start_at)
        if end_at is not None:
            statement = statement.where(stamp <= end_at)
        return statement

    estimates = await current_authoritative_estimates(
        session,
        list(
            await session.scalars(
                scoped(
                    select(ImpressionEstimate).where(
                        ImpressionEstimate.formula_version == settings.impression_formula_version,
                        ImpressionEstimate.is_authoritative.is_(True),
                    ),
                    ImpressionEstimate,
                    ImpressionEstimate.estimated_at,
                )
            )
        ),
        settings=settings,
    )
    released = [{row.vehicle_id for row in estimates}]
    if route_id != "advertiser.campaign.impressions_summary":
        latest = (
            latest_payout_calculation_ids(campaign_id=campaign_id)
            if campaign_id is not None
            else latest_payout_calculation_ids(organization_id=tenant_id)
        )
        released.append(
            set(
                await session.scalars(
                    scoped(
                        select(PayoutCalculation.vehicle_id).where(
                            PayoutCalculation.id.in_(latest)
                        ),
                        PayoutCalculation,
                        PayoutCalculation.calculated_at,
                    )
                )
            )
        )
        released.append(
            set(
                await session.scalars(
                    scoped(select(FraudFlag.vehicle_id), FraudFlag, FraudFlag.detected_at)
                )
            )
        )
    return all(
        len(vehicles) >= settings.privacy_min_vehicles_per_cell for vehicles in released if vehicles
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
    cohort: ReportCohort | None = None,
) -> bool | dict[str, Any]:
    filters = [Campaign.organization_id == tenant_id]
    if campaign_id is not None:
        filters.append(TripSession.campaign_id == campaign_id)
    if cohort is None and start_at is not None:
        filters.append(TripSession.started_at >= start_at)
    if cohort is None and end_at is not None:
        filters.append(TripSession.started_at <= end_at)
    if cohort is not None:
        filters.append(TripSession.id.in_(cohort.trip_ids))
    rows = (
        await session.execute(
            select(
                TripSession.id,
                TripSession.vehicle_id,
                (
                    TripSession.ended_at
                    if cohort is not None and cohort.terminal_period
                    else TripSession.started_at
                ).label("started_at"),
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
    vehicles = Counter(row.vehicle_id for row in rows)
    daily_metrics = route_id == "advertiser.campaign.daily_metrics"
    # D107: the only rule is three distinct cars (per day for daily rows). The trip counts
    # stay in the manifest so a frozen report can re-check its daily rows.
    contributions: dict[str, Counter[UUID]] = {}
    for row in rows:
        day = _utc_date(row.started_at)
        metric = f"trip_count:{day}" if daily_metrics else f"trip_status:{row.status}"
        _add_contribution(contributions, metric, row.vehicle_id, 1)
    passed = len(vehicles) >= settings.privacy_min_vehicles_per_cell and (
        not daily_metrics
        or all(
            len(values) >= settings.privacy_min_vehicles_per_cell
            for values in contributions.values()
        )
    )
    if passed and cohort is None and not daily_metrics and (start_at or end_at):
        passed = await _dated_outputs_meet_floor(
            session,
            tenant_id=tenant_id,
            campaign_id=campaign_id,
            start_at=start_at,
            end_at=end_at,
            route_id=route_id,
            settings=settings,
        )
    if not return_manifest:
        return passed
    return {
        "passed": passed,
        "vehicle_count": len(vehicles),
        "trip_count": len(rows),
        "day_count": len({_utc_date(row.started_at) for row in rows}),
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
    has_releasable_cells = (
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

    decision = "served"
    reason = "privacy_floor_passed"
    if not has_releasable_cells:
        decision = "suppressed"
        reason = "minimum_cars"
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
            expires_at=None,
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
