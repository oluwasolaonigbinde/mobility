"""Payouts: evidence domain operations."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import Text as SQLText
from sqlalchemy import cast, false, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.config import Settings
from app.core.errors import AppError
from app.models.campaign_zone import CampaignZone
from app.models.impression import ImpressionEstimate
from app.models.payout import (
    AssignmentRuleBinding,
)
from app.models.trip import LocationPing, TripSession, TripSessionStatus
from app.models.trip_analytics import (
    TripAnalytics,
)
from app.services.impressions import (
    get_authoritative_estimate_for_trip,
    impression_estimate_stale,
)
from app.services.payout_eligibility import (
    STATIONARY_POLICY_D39,
    EligibilityParams,
    EligibilityPing,
)
from app.services.payouts.common import (
    PAYOUT_SOURCE_FIELDS,
    RESOLVED_ELIGIBILITY_PARAM_KEYS,
    impression_estimate_not_found,
    payout_source_mismatch,
)
from app.services.provenance import stable_source_fingerprint
from app.services.trip_analytics import (
    analytics_not_found,
)
from app.services.trip_evidence import verify_manifest_receipt
from app.services.trips import trip_not_found


async def get_trip_for_payout(
    session: AsyncSession, trip_id: UUID, settings: Settings
) -> TripSession:
    trip = await session.get(TripSession, trip_id)
    if trip is None:
        raise trip_not_found()
    # Money is sealed-only (RM3): an `ended` trip may still be receiving late
    # batches inside the grace window, and write-once payouts must never
    # fingerprint an incomplete ping set. This also covers the admin
    # recompute endpoints — corrections only ever reprice sealed trips.
    if trip.status != TripSessionStatus.SEALED.value or trip.ended_at is None:
        raise AppError(
            "TRIP_NOT_SEALED",
            "Payout can only be calculated for sealed trips",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if trip.evidence_manifest_verified_at is None or not verify_manifest_receipt(trip, settings):
        raise AppError(
            "TRIP_EVIDENCE_NOT_VERIFIED",
            "Payout requires an authenticated v2 trip evidence manifest",
            status_code=status.HTTP_409_CONFLICT,
        )
    return trip


async def get_analytics_for_trip(session: AsyncSession, trip_id: UUID) -> TripAnalytics:
    analytics = await session.scalar(
        select(TripAnalytics).where(TripAnalytics.trip_session_id == trip_id)
    )
    if analytics is None:
        raise analytics_not_found()
    return analytics


async def get_impression_estimate_for_trip(
    session: AsyncSession,
    *,
    trip_id: UUID,
    settings: Settings,
) -> ImpressionEstimate:
    estimate = await get_authoritative_estimate_for_trip(
        session,
        trip_id=trip_id,
        settings=settings,
        validate_source=False,
    )
    if estimate is None:
        raise impression_estimate_not_found()
    current = await get_authoritative_estimate_for_trip(
        session,
        trip_id=trip_id,
        settings=settings,
    )
    if current is None:
        raise impression_estimate_stale()
    return current


def ensure_payout_sources_match(
    *,
    trip: TripSession,
    analytics: TripAnalytics,
    estimate: ImpressionEstimate,
) -> None:
    mismatches = []
    for field in PAYOUT_SOURCE_FIELDS:
        trip_value = getattr(trip, field)
        analytics_value = getattr(analytics, field)
        estimate_value = getattr(estimate, field)
        if analytics_value != trip_value:
            mismatches.append(
                {
                    "field": field,
                    "source": "trip_analytics",
                    "expected": str(trip_value),
                    "actual": str(analytics_value),
                }
            )
        if estimate_value != trip_value:
            mismatches.append(
                {
                    "field": field,
                    "source": "impression_estimate",
                    "expected": str(trip_value),
                    "actual": str(estimate_value),
                }
            )
    if estimate.trip_analytics_id != analytics.id:
        mismatches.append(
            {
                "field": "trip_analytics_id",
                "source": "impression_estimate",
                "expected": str(analytics.id),
                "actual": str(estimate.trip_analytics_id),
            }
        )
    if mismatches:
        raise payout_source_mismatch(mismatches)


@dataclass(frozen=True)
class EligibilityPingRow:
    id: UUID
    ping: EligibilityPing


@dataclass(frozen=True)
class CampaignZoneState:
    fingerprint: str
    zone_count: int
    max_updated_at: datetime | None


def frozen_eligibility_params(binding: AssignmentRuleBinding) -> EligibilityParams:
    """Read the complete acceptance-time classifier values, never Settings.

    An incomplete binding cannot prove the accepted snapshot; fail closed
    rather than silently filling its gaps from mutable runtime configuration.
    """
    expected_marker = STATIONARY_POLICY_D39
    if binding.stationary_policy_marker != expected_marker:
        raise AppError(
            "PAYOUT_STATIONARY_POLICY_UNRESOLVED",
            f"The {binding.formula_version} assignment binding does not contain the approved"
            " stationary detector policy; resolve manually",
            status_code=status.HTTP_409_CONFLICT,
        )
    snapshot = binding.resolved_eligibility_params or {}
    if set(snapshot) != RESOLVED_ELIGIBILITY_PARAM_KEYS:
        raise AppError(
            "PAYOUT_BINDING_INCOMPLETE",
            "The daily-rate assignment binding does not contain a complete"
            " frozen eligibility snapshot; resolve manually",
            status_code=status.HTTP_409_CONFLICT,
        )
    return EligibilityParams(
        stationary_radius_m=float(snapshot["stationary_radius_m"]),
        stationary_window_seconds=int(snapshot["stationary_window_seconds"]),
        stationary_grace_seconds=int(snapshot["stationary_grace_seconds"]),
        max_accuracy_m=float(snapshot["max_accuracy_m"]),
        teleport_kmh=float(snapshot["teleport_kmh"]),
        max_ping_gap_seconds=int(snapshot["max_ping_gap_seconds"]),
    )


async def load_eligibility_pings(
    session: AsyncSession,
    *,
    trip_id: UUID,
    campaign_id: UUID,
    frozen_premium_zone_wkts: list[str],
    frozen_exclusion_zone_wkts: list[str],
    recorded_through: datetime | None = None,
) -> list[EligibilityPingRow]:
    """Read signed trip pings against the frozen accepted service area."""

    def frozen_zone_hit(wkts: list[str]):
        conditions = [
            func.ST_Intersects(func.ST_GeomFromText(wkt, 4326), LocationPing.geom) for wkt in wkts
        ]
        return or_(*conditions) if conditions else false()

    in_area = ~frozen_zone_hit(frozen_exclusion_zone_wkts)
    in_premium = frozen_zone_hit(frozen_premium_zone_wkts)
    ping_filters = [LocationPing.trip_session_id == trip_id]
    if recorded_through is not None:
        ping_filters.append(LocationPing.recorded_at <= recorded_through)
    result = await session.execute(
        select(
            LocationPing.id,
            LocationPing.recorded_at,
            LocationPing.latitude,
            LocationPing.longitude,
            LocationPing.accuracy_m,
            in_area.label("in_area"),
            in_premium.label("in_premium"),
        )
        .where(*ping_filters)
        .order_by(
            LocationPing.recorded_at,
            LocationPing.sequence_number.asc().nullslast(),
            LocationPing.created_at,
            LocationPing.id,
        )
    )
    return [
        EligibilityPingRow(
            id=row.id,
            ping=EligibilityPing(
                recorded_at=row.recorded_at,
                latitude=row.latitude,
                longitude=row.longitude,
                accuracy_m=row.accuracy_m,
                in_area=bool(row.in_area),
                in_premium=bool(row.in_premium),
            ),
        )
        for row in result.all()
    ]


async def campaign_zone_state(
    session: AsyncSession,
    campaign_id: UUID,
) -> CampaignZoneState:
    result = await session.execute(
        select(
            CampaignZone.id,
            cast(CampaignZone.geom, SQLText).label("geom_wkb"),
            CampaignZone.updated_at,
        )
        .where(CampaignZone.campaign_id == campaign_id)
        .order_by(CampaignZone.id)
    )
    rows = result.all()
    fingerprint = stable_source_fingerprint(
        {
            "zones": [
                {"id": row.id, "geom": row.geom_wkb, "updated_at": row.updated_at} for row in rows
            ]
        }
    )
    max_updated_at = max((row.updated_at for row in rows), default=None)
    return CampaignZoneState(
        fingerprint=fingerprint,
        zone_count=len(rows),
        max_updated_at=max_updated_at,
    )


def ping_set_fingerprint(rows: list[EligibilityPingRow]) -> str:
    return stable_source_fingerprint({"ping_ids": [row.id for row in rows]})
