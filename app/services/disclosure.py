from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

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
        "advertiser.campaign.daily_metrics",
        "advertiser.campaign.report",
        "advertiser.campaign.performance",
        "advertiser.campaign.live_positions",
        "admin.heatmap",
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
    """Freeze report contributors before response construction under PostgreSQL.

    Readers share: each campaign terms key is taken shared (sorted, before any
    row), then rows ``FOR SHARE``. Writers of these rows take the exclusive
    campaign key or the trip row ``FOR UPDATE`` (see ``fraud_holds``), so they
    wait for the read, and readers never wait for each other. Callers must not
    lock these rows again for update in the same transaction.
    """
    from app.services.payout_rule_serialization import acquire_campaign_terms_shared_lock

    campaign_filters = [Campaign.organization_id == tenant_id]
    if campaign_id is not None:
        campaign_filters.append(Campaign.id == campaign_id)
    scoped_campaign_ids = list(await session.scalars(select(Campaign.id).where(*campaign_filters)))
    for scoped_campaign_id in sorted(scoped_campaign_ids, key=str):
        await acquire_campaign_terms_shared_lock(session, scoped_campaign_id)
    await session.scalar(
        select(AdvertiserOrganization.id)
        .where(AdvertiserOrganization.id == tenant_id)
        .with_for_update(read=True)
    )
    campaign_ids = list(
        await session.scalars(
            select(Campaign.id)
            .where(*campaign_filters)
            .order_by(Campaign.id)
            .with_for_update(read=True)
        )
    )
    if not campaign_ids:
        return
    list(
        await session.scalars(
            select(CampaignAssignment.id)
            .where(CampaignAssignment.campaign_id.in_(campaign_ids))
            .order_by(CampaignAssignment.id)
            .with_for_update(read=True)
        )
    )
    trip_ids = list(
        await session.scalars(
            select(TripSession.id)
            .where(TripSession.campaign_id.in_(campaign_ids))
            .order_by(TripSession.id)
            .with_for_update(read=True)
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
            .with_for_update(read=True)
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
    if query.route_id not in {"admin.heatmap"}:
        raise RuntimeError("Heatmap disclosure history received a non-heatmap route")
    await record_disclosure(
        session,
        query=query,
        settings=settings,
        has_releasable_cells=has_releasable_cells,
        result_hash=result_hash,
    )


LAGOS = ZoneInfo("Africa/Lagos")


def aware(value):
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def midnight(value):
    return datetime.combine(aware(value).astimezone(LAGOS).date(), time.min, LAGOS)


def after_day(value):
    return midnight(value) + timedelta(days=1)


def validate_window(start, end):
    for value in (start, end):
        if value is not None and aware(value) != midnight(value):
            raise AppError("REPORT_PERIOD_INVALID", "Choose whole Nigeria days", status_code=422)
    if start is not None and end is not None and start >= end:
        raise AppError(
            "REPORT_PERIOD_INVALID", "Choose a nonempty reporting period", status_code=422
        )


def trip_final(trip, analytics):
    if trip.evidence_adjudication_outcome == "incomplete_grace_expired":
        return True
    return (
        trip.status == "sealed"
        and trip.sealed_at is not None
        and analytics is not None
        and aware(analytics.computed_at) >= aware(trip.sealed_at)
    )


def released_totals(days):
    released = [d for d in days if d.status == "released"]

    def total(field):
        return sum((getattr(d, field) for d in released), Decimal(0))

    return {
        "distance_m": total("distance_m").quantize(Decimal("0.01")),
        "trip_count": int(total("trip_count")),
        "driving_seconds": int(total("driving_seconds")),
        "driving_days": sum(d.trip_count > 0 for d in released),
        "average_cars_per_day": total("vehicle_count") / len(released) if released else None,
        "estimated_views": total("estimated_impressions")
        if all(d.estimated_impressions is not None for d in released)
        else None,
    }


def area_week_figures(trips, cells_by_zone, estimates):
    """Pure exact-membership partition release; no query-history state."""
    membership = {str(t.id): set() for t in trips}
    for zone, cells in cells_by_zone.items():
        for cell in cells:
            membership[str(cell["trip_session_id"])].add(zone)
    partitions = {}
    for trip in trips:
        partitions.setdefault(frozenset(membership[str(trip.id)]), set()).add(trip.vehicle_id)
    if any(len(cars) < 3 for cars in partitions.values()):
        return None
    figures = {}
    for zone, cells in cells_by_zone.items():
        members = {str(c["trip_session_id"]) for c in cells}
        allocated = {}
        for c in cells:
            ident = str(c["trip_session_id"])
            key = (c["grid_x"], c["grid_y"])
            if ident in estimates:
                allocated[key] = allocated.get(key, Decimal(0)) + estimates[ident] * Decimal(
                    c["cell_ping_count"]
                ) / Decimal(c["total_ping_count"])
        figures[zone] = {
            "trip_count": len(members),
            "estimated_views": sum(
                (v.quantize(Decimal("0.0001")) for v in allocated.values()), Decimal(0)
            )
            if members <= estimates.keys()
            else None,
        }
    return figures


async def blocked_days(session, *, campaign_id, start, end, now):
    from app.services.fraud_holds import fraud_hold_active_clause
    from app.services.trips import _last_location_at

    active = list(
        await session.scalars(
            select(_last_location_at()).where(
                TripSession.campaign_id == campaign_id, TripSession.status == "active"
            )
        )
    )
    held = list(
        await session.scalars(
            select(TripSession.ended_at)
            .join(FraudFlag, FraudFlag.trip_session_id == TripSession.id)
            .where(
                TripSession.campaign_id == campaign_id,
                TripSession.ended_at >= start,
                TripSession.ended_at < end,
                fraud_hold_active_clause(),
            )
        )
    )
    blocked = {aware(at).astimezone(LAGOS).date() for at in held}
    day = midnight(start)
    while day < end:
        boundary = day + timedelta(days=1)
        if now < boundary or any(aware(at) < boundary for at in active):
            blocked.add(day.date())
        day = boundary
    return blocked


async def load_cells(session, *, campaign_id, start, end, settings, now):
    from app.services.report_cohorts import select_report_cohort
    from app.services.reports import campaign_daily_series

    validate_window(start, end)
    cohort = await select_report_cohort(
        session,
        campaign_id=campaign_id,
        start_at=start,
        end_at=end,
        settings=settings,
        terminal_period=True,
        include_money=False,
    )
    blocked = await blocked_days(session, campaign_id=campaign_id, start=start, end=end, now=now)
    days = campaign_daily_series(
        cohort,
        start_day=start.astimezone(LAGOS).date(),
        end_day=(end - timedelta(microseconds=1)).astimezone(LAGOS).date(),
        now=now,
        blocked_days=blocked,
    )
    return cohort, days
