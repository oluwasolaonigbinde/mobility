"""Shared signed-evidence and daily-rate test setup."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from conftest import (
    create_test_campaign,
    create_test_campaign_assignment,
    create_test_campaign_creative,
    create_test_campaign_zone,
    create_test_driver_profile,
    create_test_organization,
    create_test_trip_session,
    create_test_user,
    create_test_vehicle,
    fetch_payout_calculations,
)
from sqlalchemy import delete, func, select
from test_trip_processing import FUTURE, PASSWORD, PAST, add_pings, build_graph, run_pipeline

from app.models.campaign import Campaign, CampaignStatus, CreativeStatus
from app.models.campaign_assignment import CampaignAssignment, CampaignAssignmentStatus
from app.models.campaign_zone import CampaignZone, CampaignZoneType
from app.models.driver import DriverOnboardingStatus, DriverProfile
from app.models.payout import (
    AssignmentRuleBinding,
    CampaignPayoutRule,
    CampaignPayoutRuleRevision,
    EarningsLedgerEntry,
    PayoutCalculation,
)
from app.models.trip import TripSession, TripSessionStatus
from app.models.user import UserRole
from app.models.vehicle import VehicleStatus
from app.schemas.campaign_assignments import CampaignAssignmentTransition
from app.services.campaign_assignments import (
    accept_driver_assignment,
    build_offer_terms,
    canonical_offer_terms_sha256,
    frozen_zone_geometry_hash,
    resolved_eligibility_snapshot,
)
from app.services.campaign_zones import geometry_expression
from app.services.payout_eligibility import (
    D39_STOP_OVERLAY,
    STATIONARY_POLICY_D39,
)
from app.services.payout_rule_serialization import (
    database_clock,
)
from app.services.payouts.common import PAYOUT_V4, lagos_day_for
from app.services.payouts.corrections import recompute_payout_day
from app.services.payouts.engine import calculate_trip_payout
from app.services.payouts.read import driver_earnings_summary
from app.services.trip_evidence import sign_manifest_receipt

TRIP_START = datetime(2026, 7, 20, 8, 0, tzinfo=UTC)
TRIP_END = TRIP_START + timedelta(minutes=30)
PAST_EFFECTIVE = datetime(2026, 1, 1, tzinfo=UTC)
BASE_LAT = 6.45
BASE_LON = 3.40


def moving_points(
    start: datetime,
    *,
    minutes: int = 30,
    step_seconds: int = 30,
    accuracy: float = 10.0,
    lon: float = BASE_LON,
) -> list[tuple[datetime, float, float, float]]:
    # ~90 m per 30 s (~11 km/h): moving under the stay-point rule.
    return [
        (
            start + timedelta(seconds=second),
            BASE_LAT + (second // step_seconds) * 0.00081,
            lon,
            accuracy,
        )
        for second in range(0, minutes * 60 + 1, step_seconds)
    ]


def deactivate_rules(db_sessionmaker, campaign_id) -> None:
    async def deactivate() -> None:
        async with db_sessionmaker() as session:
            rules = (
                await session.execute(
                    select(CampaignPayoutRule).where(CampaignPayoutRule.campaign_id == campaign_id)
                )
            ).scalars()
            for rule in rules:
                rule.status = "inactive"
            await session.commit()

    asyncio.run(deactivate())


def calculate(db_sessionmaker, trip_id, settings, **kwargs):
    async def run():
        async with db_sessionmaker() as session:
            result = await calculate_trip_payout(
                session,
                trip_id=trip_id,
                payout_rule_id=kwargs.get("payout_rule_id"),
                metadata={"source": "test"},
                settings=settings,
                now=kwargs.get("now"),
                strict_staleness=kwargs.get("strict_staleness", True),
            )
            await session.commit()
            return result

    return asyncio.run(run())


def create_signed_v2_test_trip_session(
    db_sessionmaker,
    settings,
    *,
    assignment_id,
    campaign_id,
    driver_profile_id,
    vehicle_id,
    started_by_user_id,
    started_at,
    ended_at,
):
    """Create the same accepted signed-v2 authority as build_graph's trip fixture."""
    trip = create_test_trip_session(
        db_sessionmaker,
        assignment_id=assignment_id,
        campaign_id=campaign_id,
        driver_profile_id=driver_profile_id,
        vehicle_id=vehicle_id,
        started_by_user_id=started_by_user_id,
        trip_status=TripSessionStatus.SEALED,
        started_at=started_at,
        ended_at=ended_at,
    )

    async def bind_v2_evidence_authority() -> None:
        async with db_sessionmaker() as session:
            stored = await session.get(TripSession, trip.id)
            stored.evidence_protocol_version = 2
            stored.evidence_manifest_version = 2
            stored.evidence_manifest_root_sha256 = "0" * 64
            stored.evidence_manifest_batch_count = 0
            stored.evidence_manifest_ping_count = 0
            stored.evidence_manifest_committed_at = ended_at
            stored.evidence_manifest_complete = True
            stored.evidence_manifest_verified_at = ended_at
            sign_manifest_receipt(stored, settings)
            await session.commit()

    asyncio.run(bind_v2_evidence_authority())
    return trip


def resign_signed_v2_manifest_receipt(db_sessionmaker, settings, trip_id) -> None:
    async def resign() -> None:
        async with db_sessionmaker() as session:
            trip = await session.get(TripSession, trip_id)
            sign_manifest_receipt(trip, settings)
            await session.commit()

    asyncio.run(resign())


def run_recompute(db_sessionmaker, settings, graph, *, lagos_date=None):
    async def run():
        async with db_sessionmaker() as session:
            outcome = await recompute_payout_day(
                session,
                campaign_id=graph.campaign.id,
                driver_profile_id=graph.profile.id,
                lagos_date=lagos_date or lagos_day_for(graph.trip.started_at),
                request_metadata={"source": "test"},
                settings=settings,
            )
            await session.commit()
            return outcome

    return asyncio.run(run())


def driver_totals(db_sessionmaker, settings, user_id):
    async def run():
        async with db_sessionmaker() as session:
            summary = await driver_earnings_summary(
                session, user_id=user_id, currency=None, settings=settings
            )
            return summary.totals_by_currency[0]

    return asyncio.run(run())


def build_offered_graph(db_sessionmaker, tag: str) -> SimpleNamespace:
    """build_graph twin with an OFFERED assignment and no trip yet, so the
    accept service (the binding writer) can be exercised end-to-end."""
    admin = create_test_user(db_sessionmaker, email=f"admin-{tag}@example.com", password=PASSWORD)
    advertiser = create_test_user(
        db_sessionmaker,
        email=f"advertiser-{tag}@example.com",
        password=PASSWORD,
        role=UserRole.ADVERTISER,
    )
    organization, _ = create_test_organization(
        db_sessionmaker, name=f"Org {tag}", owner_user_id=advertiser.id
    )
    campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=advertiser.id,
        campaign_status=CampaignStatus.ACTIVE,
        start_at=PAST,
        end_at=FUTURE,
    )
    creative = create_test_campaign_creative(
        db_sessionmaker,
        campaign_id=campaign.id,
        creative_status=CreativeStatus.APPROVED,
    )
    target_zone = create_test_campaign_zone(
        db_sessionmaker,
        campaign_id=campaign.id,
        created_by_user_id=admin.id,
    )
    driver = create_test_user(
        db_sessionmaker, email=f"driver-{tag}@example.com", password=PASSWORD, role=UserRole.DRIVER
    )
    profile = create_test_driver_profile(
        db_sessionmaker,
        user_id=driver.id,
        onboarding_status=DriverOnboardingStatus.ACTIVE,
        license_number=f"DRV-{tag}",
    )
    vehicle = create_test_vehicle(
        db_sessionmaker,
        driver_profile_id=profile.id,
        plate_number=f"V3-{tag[:10].upper()}",
        vehicle_status=VehicleStatus.ACTIVE,
    )
    assignment = create_test_campaign_assignment(
        db_sessionmaker,
        campaign_id=campaign.id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        assigned_by_user_id=admin.id,
        assignment_status=CampaignAssignmentStatus.OFFERED,
    )
    return SimpleNamespace(
        admin=admin,
        driver=driver,
        campaign=campaign,
        profile=profile,
        vehicle=vehicle,
        assignment=assignment,
        creative=creative,
        target_zone=target_zone,
    )


def add_target_zone(
    db_sessionmaker,
    *,
    campaign_id,
    created_by_user_id,
    name: str,
    lat_min: float,
    lat_max: float,
    lon_min: float = 3.30,
    lon_max: float = 3.50,
    zone_type: str = CampaignZoneType.TARGET.value,
) -> CampaignZone:
    async def create() -> CampaignZone:
        async with db_sessionmaker() as session:
            zone = CampaignZone(
                campaign_id=campaign_id,
                created_by_user_id=created_by_user_id,
                name=name,
                zone_type=zone_type,
                geom=geometry_expression(
                    json.dumps(
                        {
                            "type": "Polygon",
                            "coordinates": [
                                [
                                    [lon_min, lat_min],
                                    [lon_max, lat_min],
                                    [lon_max, lat_max],
                                    [lon_min, lat_max],
                                    [lon_min, lat_min],
                                ]
                            ],
                        }
                    )
                ),
                zone_metadata={},
            )
            session.add(zone)
            await session.commit()
            await session.refresh(zone)
            return zone

    return asyncio.run(create())


def fetch_bindings(db_sessionmaker) -> list[AssignmentRuleBinding]:
    async def fetch() -> list[AssignmentRuleBinding]:
        async with db_sessionmaker() as session:
            result = await session.execute(
                select(AssignmentRuleBinding).order_by(AssignmentRuleBinding.bound_at)
            )
            return list(result.scalars().all())

    return asyncio.run(fetch())


def accept_assignment(db_sessionmaker, settings, *, user_id, assignment_id):
    async def run():
        async with db_sessionmaker() as session:
            assignment = await accept_driver_assignment(
                session,
                user_id=user_id,
                assignment_id=assignment_id,
                payload=CampaignAssignmentTransition(),
                settings=settings,
            )
            await session.commit()
            return assignment

    return asyncio.run(run())


def materialize_offer(
    db_sessionmaker,
    settings,
    graph,
    *,
    legacy_top_level_currency_only: bool = False,
    null_payout_currency: bool = False,
    nested_payout_currency: str | None = None,
) -> None:
    """Populate the new immutable offer snapshot after test revisions exist."""

    async def run() -> None:
        async with db_sessionmaker() as session:
            assignment = await session.get(CampaignAssignment, graph.assignment.id)
            campaign = await session.get(Campaign, graph.campaign.id)
            profile = await session.get(DriverProfile, graph.profile.id)
            now = await database_clock(session)
            terms, fingerprint = await build_offer_terms(
                session,
                campaign=campaign,
                driver_profile=profile,
                now=now,
                creative_id=graph.creative.id,
                settings=settings,
            )
            if legacy_top_level_currency_only:
                terms["payout"].pop("currency")
            elif null_payout_currency:
                terms["payout"]["currency"] = None
            elif nested_payout_currency is not None:
                terms["payout"]["currency"] = nested_payout_currency
            if (
                legacy_top_level_currency_only
                or null_payout_currency
                or nested_payout_currency is not None
            ):
                fingerprint = canonical_offer_terms_sha256(terms)
            assignment.offer_terms = terms
            assignment.offer_terms_sha256 = fingerprint
            assignment.expires_at = FUTURE - timedelta(days=1)
            await session.commit()

    asyncio.run(run())


def delete_money_rows(db_sessionmaker, trip_id) -> None:
    """Test-only reset so the deterministic v3 computation can be re-run
    (calculations are write-once in production)."""

    async def run() -> None:
        async with db_sessionmaker() as session:
            await session.execute(
                delete(EarningsLedgerEntry).where(EarningsLedgerEntry.trip_session_id == trip_id)
            )
            await session.execute(
                delete(PayoutCalculation).where(PayoutCalculation.trip_session_id == trip_id)
            )
            await session.commit()

    asyncio.run(run())


DEFAULT_TERMS = {
    "daily_rate_naira": "8000.00",
    "daily_target_miles": "8.000",
    "shortfall_strategy": "proportional",
    "deduction_per_mile_naira": None,
    "minimum_miles": "0.000",
    "outside_area_weight": "0.0000",
}


def create_v4_rule(db, *, campaign_id, admin_id, rule_status="active") -> CampaignPayoutRule:
    async def create():
        async with db() as session:
            rule = CampaignPayoutRule(
                campaign_id=campaign_id,
                created_by_user_id=admin_id,
                formula_version=PAYOUT_V4,
                status=rule_status,
                currency="NGN",
                rule_metadata={},
            )
            session.add(rule)
            await session.commit()
            await session.refresh(rule)
            return rule

    return asyncio.run(create())


def create_v4_revision(
    db, *, campaign_id, rule_id, admin_id, number=1, effective_from=None, **overrides
):
    values = {**DEFAULT_TERMS, **overrides}

    async def create():
        async with db() as session:
            revision = CampaignPayoutRuleRevision(
                campaign_id=campaign_id,
                payout_rule_id=rule_id,
                revision_number=number,
                effective_from=effective_from or PAST_EFFECTIVE + timedelta(days=number),
                currency="NGN",
                eligibility_params=dict(D39_STOP_OVERLAY),
                formula_version=PAYOUT_V4,
                reason="synthetic test revision",
                created_by_user_id=admin_id,
                **{
                    key: (Decimal(value) if key != "shortfall_strategy" and value else value)
                    for key, value in values.items()
                },
            )
            session.add(revision)
            await session.commit()
            await session.refresh(revision)
            return revision

    return asyncio.run(create())


def insert_v4_binding(db, settings, *, assignment_id, revision, zone_ids=()):
    async def create():
        async with db() as session:
            campaign = await session.get(Campaign, revision.campaign_id)
            target_rows = (
                await session.execute(
                    select(CampaignZone.id, func.ST_AsText(CampaignZone.geom))
                    .where(CampaignZone.id.in_(list(zone_ids)))
                    .order_by(CampaignZone.id)
                )
            ).all()
            exclusion_rows = (
                await session.execute(
                    select(CampaignZone.id, func.ST_AsText(CampaignZone.geom)).where(
                        CampaignZone.campaign_id == revision.campaign_id,
                        CampaignZone.zone_type == CampaignZoneType.EXCLUSION.value,
                    )
                )
            ).all()
            binding = AssignmentRuleBinding(
                assignment_id=assignment_id,
                revision_id=revision.id,
                currency=revision.currency,
                daily_rate_naira=revision.daily_rate_naira,
                daily_target_miles=revision.daily_target_miles,
                shortfall_strategy=revision.shortfall_strategy,
                deduction_per_mile_naira=revision.deduction_per_mile_naira,
                minimum_miles=revision.minimum_miles,
                outside_area_weight=revision.outside_area_weight,
                eligibility_params=revision.eligibility_params,
                resolved_eligibility_params=resolved_eligibility_snapshot(
                    revision.eligibility_params
                ),
                formula_version=PAYOUT_V4,
                premium_zone_ids=[str(row[0]) for row in target_rows],
                premium_zone_geometry_hash=frozen_zone_geometry_hash(target_rows),
                premium_zone_geometry_wkts=[str(row[1]) for row in target_rows],
                exclusion_zone_ids=[str(row[0]) for row in exclusion_rows],
                exclusion_zone_geometry_hash=frozen_zone_geometry_hash(exclusion_rows),
                exclusion_zone_geometry_wkts=[str(row[1]) for row in exclusion_rows],
                stationary_policy_marker=STATIONARY_POLICY_D39,
                campaign_window_start_at=campaign.start_at,
                campaign_window_end_at=campaign.end_at,
                campaign_window_frozen=True,
                bound_at=datetime.now(UTC),
            )
            session.add(binding)
            await session.commit()
            await session.refresh(binding)
            return binding

    return asyncio.run(create())


def build_v4_graph(db, settings, tag, *, started_at=TRIP_START, ended_at=TRIP_END, **overrides):
    graph = build_graph(db, tag, started_at=started_at, ended_at=ended_at)
    graph.rule = create_v4_rule(db, campaign_id=graph.campaign.id, admin_id=graph.admin.id)
    graph.zone = add_target_zone(
        db,
        campaign_id=graph.campaign.id,
        created_by_user_id=graph.admin.id,
        name="Target",
        lat_min=6.40,
        lat_max=6.60,
    )
    graph.revision = create_v4_revision(
        db,
        campaign_id=graph.campaign.id,
        rule_id=graph.rule.id,
        admin_id=graph.admin.id,
        **overrides,
    )
    graph.binding = insert_v4_binding(
        db,
        settings,
        assignment_id=graph.assignment.id,
        revision=graph.revision,
        zone_ids=[graph.zone.id],
    )
    graph.terms = {**DEFAULT_TERMS, **overrides}
    return graph


def add_trip(db, settings, graph, *, started_at, minutes=30, assignment=None, vehicle=None):
    return create_signed_v2_test_trip_session(
        db,
        settings,
        assignment_id=(assignment or graph.assignment).id,
        campaign_id=graph.campaign.id,
        driver_profile_id=graph.profile.id,
        vehicle_id=(vehicle or graph.vehicle).id,
        started_by_user_id=graph.driver.id,
        started_at=started_at,
        ended_at=started_at + timedelta(minutes=minutes),
    )


def drive(db, settings, trip, *, minutes=30, key=None):
    points = moving_points(trip.started_at, minutes=minutes)
    add_pings(db, trip_id=trip.id, points=points, idempotency_key=key or f"v4-{trip.id}")
    result = run_pipeline(db, trip.id, settings)
    assert result.overall == "completed"
    return [(p[0], p[1], p[2]) for p in points]


def calculations_by_trip(db) -> dict:
    return {calc.trip_session_id: calc for calc in fetch_payout_calculations(db)}
