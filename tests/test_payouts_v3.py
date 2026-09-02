"""MNY-06B: acceptance-time freeze + payout_v3 engine (D18, PR2/PR4/PR5/PR10/PR11/PR14).

Covers the accept-path binding (frozen values incl. the premium zone
snapshot; offers without complete revisions fail closed), the PR2 concurrent
accept race and the PR10 accept-vs-supersede determinism, and the v3 engine:
tier pricing from the BINDING only (base-only / premium-only / mixed with a
zone transition mid-trip), the no-repricing core guarantee after a
supersede, PR4 chronological cap truncation across tiers, the PR5 shared
v2+v3 day cap pool, midnight-spanning per-day allocation, and fingerprint
completeness (B2/Q6).
"""

import asyncio
import hashlib
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from conftest import (
    create_test_campaign,
    create_test_campaign_assignment,
    create_test_campaign_creative,
    create_test_campaign_zone,
    create_test_driver_profile,
    create_test_organization,
    create_test_user,
    create_test_vehicle,
    fetch_activation_events,
    fetch_earnings_ledger_entries,
    fetch_payout_calculations,
)
from sqlalchemy import delete, func, select, update
from test_payout_rule_revisions import service_create_revision
from test_payouts_v2 import (
    TRIP_START,
    build_v2_graph,
    calculate,
    create_signed_v2_test_trip_session,
    create_v2_rule,
    moving_points,
    pipeline_to_v2,
)
from test_trip_processing import FUTURE, PASSWORD, PAST, add_pings, run_pipeline

from app.core.errors import AppError
from app.models.campaign import Campaign, CampaignStatus, CreativeStatus
from app.models.campaign_assignment import CampaignAssignment, CampaignAssignmentStatus
from app.models.campaign_zone import CampaignZone, CampaignZoneType
from app.models.driver import DriverOnboardingStatus, DriverProfile
from app.models.payout import (
    AssignmentRuleBinding,
    CampaignPayoutRuleRevision,
    EarningsLedgerEntry,
    EarningsLedgerEntryStatus,
    EarningsLedgerEntryType,
    PayoutCalculation,
    PayoutCalculationStatus,
)
from app.models.user import UserRole
from app.models.vehicle import VehicleStatus
from app.schemas.campaign_assignments import CampaignAssignmentCreate, CampaignAssignmentTransition
from app.schemas.payouts import CampaignPayoutRuleRevisionCreate
from app.services import payouts
from app.services.campaign_assignments import (
    accept_driver_assignment,
    build_offer_terms,
    create_campaign_assignment,
    premium_zone_geometry_hash,
    resolved_eligibility_snapshot,
)
from app.services.campaign_zones import geometry_expression
from app.services.payout_eligibility import (
    STATIONARY_POLICY_V1,
    EligibilityParams,
    EligibilityPing,
    classify_session,
)
from app.services.payout_rule_serialization import (
    acquire_campaign_terms_lock,
    database_clock,
)
from app.services.payouts import (
    PAYOUT_V2,
    PAYOUT_V3,
    allocate_tier_amount_components,
    day_consumed_payable_seconds,
    driver_trip_earnings_breakdown,
    price_tiered_payable_seconds,
    v3_inputs_fingerprint,
)

PAST_EFFECTIVE = datetime(2026, 1, 1, tzinfo=UTC)


# --- Helpers -----------------------------------------------------------------


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


def create_revision_row(
    db_sessionmaker,
    *,
    campaign_id,
    rule_id,
    created_by_user_id,
    number: int = 1,
    effective_from: datetime = PAST_EFFECTIVE,
    base: str = "1000.00",
    premium: str | None = "2000.00",
    cap: str = "8.00",
    params: dict | None = None,
) -> CampaignPayoutRuleRevision:
    async def create() -> CampaignPayoutRuleRevision:
        async with db_sessionmaker() as session:
            revision = CampaignPayoutRuleRevision(
                campaign_id=campaign_id,
                payout_rule_id=rule_id,
                revision_number=number,
                effective_from=effective_from,
                hourly_rate_naira=Decimal(base),
                premium_hourly_rate_naira=Decimal(premium) if premium is not None else None,
                daily_payable_hours_cap=Decimal(cap),
                eligibility_params=params or {},
                formula_version=PAYOUT_V3,
                reason="test revision",
                created_by_user_id=created_by_user_id,
            )
            session.add(revision)
            await session.commit()
            await session.refresh(revision)
            return revision

    return asyncio.run(create())


def insert_binding(
    db_sessionmaker,
    settings,
    *,
    assignment_id,
    revision: CampaignPayoutRuleRevision,
    zone_ids=(),
    geometry_hash: str = "hash-frozen-at-accept",
    stationary_policy_marker: str = STATIONARY_POLICY_V1,
) -> AssignmentRuleBinding:
    async def create() -> AssignmentRuleBinding:
        async with db_sessionmaker() as session:
            campaign = await session.get(Campaign, revision.campaign_id)
            premium_rows = (
                (
                    await session.execute(
                        select(CampaignZone.id, func.ST_AsText(CampaignZone.geom))
                        .where(CampaignZone.id.in_(list(zone_ids)))
                        .order_by(CampaignZone.id)
                    )
                ).all()
                if zone_ids
                else []
            )
            exclusion_rows = (
                await session.execute(
                    select(CampaignZone.id, func.ST_AsText(CampaignZone.geom))
                    .where(
                        CampaignZone.campaign_id == revision.campaign_id,
                        CampaignZone.zone_type == CampaignZoneType.EXCLUSION.value,
                    )
                    .order_by(CampaignZone.id)
                )
            ).all()
            binding = AssignmentRuleBinding(
                assignment_id=assignment_id,
                revision_id=revision.id,
                hourly_rate_naira=revision.hourly_rate_naira,
                premium_hourly_rate_naira=revision.premium_hourly_rate_naira,
                daily_payable_hours_cap=revision.daily_payable_hours_cap,
                eligibility_params=revision.eligibility_params or {},
                resolved_eligibility_params=resolved_eligibility_snapshot(
                    settings, revision.eligibility_params
                ),
                formula_version=revision.formula_version,
                premium_zone_ids=[str(zone_id) for zone_id in zone_ids],
                premium_zone_geometry_hash=geometry_hash,
                premium_zone_geometry_wkts=[str(row[1]) for row in premium_rows],
                exclusion_zone_ids=[str(row[0]) for row in exclusion_rows],
                exclusion_zone_geometry_hash=premium_zone_geometry_hash(exclusion_rows),
                exclusion_zone_geometry_wkts=[str(row[1]) for row in exclusion_rows],
                stationary_policy_marker=stationary_policy_marker,
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


def materialize_offer(db_sessionmaker, settings, graph) -> None:
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


def bind_v2_graph(
    db_sessionmaker,
    settings,
    graph,
    *,
    base: str = "1000.00",
    premium: str | None = "2000.00",
    cap: str = "8.00",
    zone_ids=(),
    params: dict | None = None,
) -> SimpleNamespace:
    """Attach a revision + binding to build_v2_graph's ACTIVE assignment.

    The revision values deliberately DIFFER from the v2 rule row so any
    amount computed from them proves the engine read the binding."""
    revision = create_revision_row(
        db_sessionmaker,
        campaign_id=graph.campaign.id,
        rule_id=graph.rule.id,
        created_by_user_id=graph.admin.id,
        base=base,
        premium=premium,
        cap=cap,
        params=params,
    )
    binding = insert_binding(
        db_sessionmaker,
        settings,
        assignment_id=graph.assignment.id,
        revision=revision,
        zone_ids=zone_ids,
    )
    graph.revision = revision
    graph.binding = binding
    return graph


# --- Accept-path freeze (B1 rubric) ------------------------------------------


def test_accept_freezes_effective_revision_with_zone_snapshot(
    postgis_db_sessionmaker,
    settings,
) -> None:
    graph = build_offered_graph(postgis_db_sessionmaker, "v3-accept")
    rule = create_v2_rule(
        postgis_db_sessionmaker,
        campaign_id=graph.campaign.id,
        created_by_user_id=graph.admin.id,
    )
    revision = create_revision_row(
        postgis_db_sessionmaker,
        campaign_id=graph.campaign.id,
        rule_id=rule.id,
        created_by_user_id=graph.admin.id,
        base="1500.00",
        premium="2500.00",
        cap="6.00",
        params={"stationary_grace_min": 5},
    )
    zone = add_target_zone(
        postgis_db_sessionmaker,
        campaign_id=graph.campaign.id,
        created_by_user_id=graph.admin.id,
        name="Premium A",
        lat_min=6.40,
        lat_max=6.52,
    )
    materialize_offer(postgis_db_sessionmaker, settings, graph)

    accepted = accept_assignment(
        postgis_db_sessionmaker,
        settings,
        user_id=graph.driver.id,
        assignment_id=graph.assignment.id,
    )
    assert accepted.status == CampaignAssignmentStatus.ACCEPTED.value

    bindings = fetch_bindings(postgis_db_sessionmaker)
    assert len(bindings) == 1
    binding = bindings[0]
    assert binding.assignment_id == graph.assignment.id
    assert binding.revision_id == revision.id
    assert binding.hourly_rate_naira == Decimal("1500.00")
    assert binding.premium_hourly_rate_naira == Decimal("2500.00")
    assert binding.daily_payable_hours_cap == Decimal("6.00")
    assert binding.eligibility_params == {"stationary_grace_min": 5}
    assert binding.formula_version == PAYOUT_V3
    assert set(binding.premium_zone_ids) == {str(zone.id), str(graph.target_zone.id)}
    assert binding.stationary_policy_marker == STATIONARY_POLICY_V1
    assert binding.campaign_window_start_at == graph.campaign.start_at
    assert binding.campaign_window_end_at == graph.campaign.end_at
    assert binding.campaign_window_frozen is True
    assert binding.bound_at == accepted.accepted_at
    assert binding.resolved_eligibility_params == {
        "stationary_radius_m": 200.0,
        "stationary_window_seconds": 300,
        "stationary_grace_seconds": 300,
        "max_accuracy_m": 75.0,
        "teleport_kmh": 180.0,
        "max_ping_gap_seconds": 120,
        "rolling_window_seconds": 120,
        "rolling_stride_seconds": 120,
        "rolling_max_displacement_m": 25.0,
        "rolling_confirmation_windows": 2,
        "rolling_release_windows": 1,
    }

    # The geometry hash is the deterministic sha256 of the frozen target
    # zones' (id, geometry) pairs sorted by id.
    async def expected_hash() -> str:
        async with postgis_db_sessionmaker() as session:
            rows = (
                await session.execute(
                    select(CampaignZone.id, func.ST_AsText(CampaignZone.geom))
                    .where(
                        CampaignZone.campaign_id == graph.campaign.id,
                        CampaignZone.zone_type == CampaignZoneType.TARGET.value,
                    )
                    .order_by(CampaignZone.id)
                )
            ).all()
            return premium_zone_geometry_hash(rows)

    assert binding.premium_zone_geometry_hash == asyncio.run(expected_hash())
    assert len(binding.premium_zone_geometry_hash) == 64
    int(binding.premium_zone_geometry_hash, 16)  # hex digest


def test_rolling_policy_changes_only_through_revision_overlay(settings) -> None:
    same_revision: dict = {}
    first_acceptance = resolved_eligibility_snapshot(settings, same_revision)
    runtime_mutated = settings.model_copy(
        update={
            "payout_eligibility_rolling_window_seconds": 999,
            "payout_eligibility_rolling_stride_seconds": 998,
            "payout_eligibility_rolling_max_displacement_m": 997.0,
            "payout_eligibility_rolling_confirmation_windows": 996,
            "payout_eligibility_rolling_release_windows": 995,
        }
    )

    second_acceptance = resolved_eligibility_snapshot(runtime_mutated, same_revision)

    rolling_keys = {
        "rolling_window_seconds",
        "rolling_stride_seconds",
        "rolling_max_displacement_m",
        "rolling_confirmation_windows",
        "rolling_release_windows",
    }
    assert {key: first_acceptance[key] for key in rolling_keys} == {
        key: second_acceptance[key] for key in rolling_keys
    }

    later_revision = resolved_eligibility_snapshot(
        runtime_mutated,
        {
            "rolling_window_seconds": 180,
            "rolling_stride_seconds": 180,
            "rolling_max_displacement_m": 30,
            "rolling_confirmation_windows": 3,
            "rolling_release_windows": 2,
        },
    )
    assert {key: later_revision[key] for key in rolling_keys} == {
        "rolling_window_seconds": 180,
        "rolling_stride_seconds": 180,
        "rolling_max_displacement_m": 30.0,
        "rolling_confirmation_windows": 3,
        "rolling_release_windows": 2,
    }


def test_offer_without_frozen_terms_rejects_acceptance_without_binding(
    postgis_db_sessionmaker, settings
) -> None:
    graph = build_offered_graph(postgis_db_sessionmaker, "v3-none")
    # Rule row inserted directly (no revision chain): legacy campaign shape.
    create_v2_rule(
        postgis_db_sessionmaker,
        campaign_id=graph.campaign.id,
        created_by_user_id=graph.admin.id,
    )
    with pytest.raises(AppError) as exc_info:
        accept_assignment(
            postgis_db_sessionmaker,
            settings,
            user_id=graph.driver.id,
            assignment_id=graph.assignment.id,
        )
    assert exc_info.value.code == "FROZEN_OFFER_TERMS_REQUIRED"
    assert fetch_bindings(postgis_db_sessionmaker) == []


# --- PR2 / PR10 races (PostGIS) ----------------------------------------------


def test_concurrent_accepts_yield_exactly_one_binding(postgis_db_sessionmaker, settings) -> None:
    graph = build_offered_graph(postgis_db_sessionmaker, "v3-race")
    rule = create_v2_rule(
        postgis_db_sessionmaker,
        campaign_id=graph.campaign.id,
        created_by_user_id=graph.admin.id,
    )
    create_revision_row(
        postgis_db_sessionmaker,
        campaign_id=graph.campaign.id,
        rule_id=rule.id,
        created_by_user_id=graph.admin.id,
    )
    materialize_offer(postgis_db_sessionmaker, settings, graph)

    async def attempt():
        async with postgis_db_sessionmaker() as session:
            try:
                await accept_driver_assignment(
                    session,
                    user_id=graph.driver.id,
                    assignment_id=graph.assignment.id,
                    payload=CampaignAssignmentTransition(),
                    settings=settings,
                )
                await session.commit()
                return "accepted"
            except AppError as exc:
                await session.rollback()
                return exc

    async def race():
        return await asyncio.gather(attempt(), attempt())

    outcomes = asyncio.run(race())
    assert outcomes == ["accepted", "accepted"]
    assert len(fetch_bindings(postgis_db_sessionmaker)) == 1
    assert [event.event_type for event in fetch_activation_events(postgis_db_sessionmaker)] == [
        "accepted"
    ]


def test_revision_publication_before_accept_binds_from_shared_lock_and_db_clock(
    postgis_db_sessionmaker,
    settings,
) -> None:
    graph = build_offered_graph(postgis_db_sessionmaker, "v3-sup-race")
    rule = create_v2_rule(
        postgis_db_sessionmaker,
        campaign_id=graph.campaign.id,
        created_by_user_id=graph.admin.id,
    )
    revision1 = create_revision_row(
        postgis_db_sessionmaker,
        campaign_id=graph.campaign.id,
        rule_id=rule.id,
        created_by_user_id=graph.admin.id,
    )
    materialize_offer(postgis_db_sessionmaker, settings, graph)

    revision_has_lock = asyncio.Event()

    async def accept():
        await revision_has_lock.wait()
        async with postgis_db_sessionmaker() as session:
            assignment = await accept_driver_assignment(
                session,
                user_id=graph.driver.id,
                assignment_id=graph.assignment.id,
                payload=CampaignAssignmentTransition(),
                settings=settings,
            )
            await session.commit()
            return assignment

    async def supersede():
        async with postgis_db_sessionmaker() as session:
            # Establish publication-first ordering while acceptance is live
            # and waiting on the exact same campaign transaction lock.
            await acquire_campaign_terms_lock(session, graph.campaign.id)
            effective_from = await database_clock(session) + timedelta(seconds=2)
            revision_has_lock.set()
            revision, previous = await payouts.create_payout_rule_revision(
                session,
                campaign_id=graph.campaign.id,
                rule_id=rule.id,
                payload=CampaignPayoutRuleRevisionCreate(
                    effective_from=effective_from,
                    hourly_rate_naira=Decimal("9999.00"),
                    premium_hourly_rate_naira=Decimal("10999.00"),
                    daily_payable_hours_cap=Decimal("8.00"),
                    reason="publication wins shared serialization",
                ),
                actor_user_id=graph.admin.id,
            )
            # Keep the transaction lock through the effective boundary. The
            # waiting acceptance must then take a fresh database wall clock,
            # which is necessarily after this newly published revision.
            await asyncio.sleep(2.1)
            await session.commit()
            return revision, previous, effective_from

    async def race():
        published, accepted = await asyncio.gather(supersede(), accept())
        return accepted, published

    accepted, (rev2, _, effective_from) = asyncio.run(race())
    assert accepted.status == CampaignAssignmentStatus.ACCEPTED.value
    assert rev2.revision_number == 2

    bindings = fetch_bindings(postgis_db_sessionmaker)
    assert len(bindings) == 1
    # The offer was materialized from rev1 before publication.  Acceptance
    # must therefore bind that immutable displayed snapshot, even when rev2
    # publishes before the decision commits; mutable producer edits never
    # reprice an already-offered assignment.
    assert bindings[0].revision_id == revision1.id
    assert bindings[0].hourly_rate_naira == revision1.hourly_rate_naira
    assert bindings[0].daily_payable_hours_cap == revision1.daily_payable_hours_cap
    assert bindings[0].bound_at is not None


def test_offer_creation_after_revision_publication_freezes_new_revision_postgres(
    postgis_db_sessionmaker,
    settings,
) -> None:
    graph = build_offered_graph(postgis_db_sessionmaker, "v3-offer-pub-race")
    rule = create_v2_rule(
        postgis_db_sessionmaker,
        campaign_id=graph.campaign.id,
        created_by_user_id=graph.admin.id,
    )
    revision1 = create_revision_row(
        postgis_db_sessionmaker,
        campaign_id=graph.campaign.id,
        rule_id=rule.id,
        created_by_user_id=graph.admin.id,
    )

    async def remove_fixture_offer() -> None:
        async with postgis_db_sessionmaker() as session:
            await session.execute(
                delete(CampaignAssignment).where(CampaignAssignment.id == graph.assignment.id)
            )
            await session.commit()

    asyncio.run(remove_fixture_offer())
    publication_has_lock = asyncio.Event()

    async def publish():
        async with postgis_db_sessionmaker() as session:
            await acquire_campaign_terms_lock(session, graph.campaign.id)
            effective_from = await database_clock(session) + timedelta(seconds=2)
            publication_has_lock.set()
            revision2, _ = await payouts.create_payout_rule_revision(
                session,
                campaign_id=graph.campaign.id,
                rule_id=rule.id,
                payload=CampaignPayoutRuleRevisionCreate(
                    effective_from=effective_from,
                    hourly_rate_naira=Decimal("9999.00"),
                    premium_hourly_rate_naira=Decimal("10999.00"),
                    daily_payable_hours_cap=Decimal("8.00"),
                    reason="offer publication race",
                ),
                actor_user_id=graph.admin.id,
            )
            await asyncio.sleep(2.1)
            await session.commit()
            return revision2

    async def offer():
        await publication_has_lock.wait()
        async with postgis_db_sessionmaker() as session:
            assignment = await create_campaign_assignment(
                session,
                admin_user_id=graph.admin.id,
                payload=CampaignAssignmentCreate(
                    campaign_id=graph.campaign.id,
                    driver_profile_id=graph.profile.id,
                    vehicle_id=graph.vehicle.id,
                    creative_id=graph.creative.id,
                    expires_at=FUTURE - timedelta(days=1),
                ),
                settings=settings,
            )
            await session.commit()
            return assignment

    async def race():
        return await asyncio.wait_for(asyncio.gather(publish(), offer()), timeout=10)

    revision2, offered = asyncio.run(race())
    assert revision1.id != revision2.id
    assert offered.offer_terms is not None
    assert offered.offer_terms["payout"]["revision_id"] == str(revision2.id)
    assert offered.offer_terms["payout"]["hourly_rate_naira"] == str(revision2.hourly_rate_naira)
    assert offered.offer_terms["payout"]["daily_payable_hours_cap"] == str(
        revision2.daily_payable_hours_cap
    )


# --- payout_v3 engine --------------------------------------------------------


def tier_split(calculation: PayoutCalculation) -> dict:
    return calculation.payout_metadata["cap"]["payable_seconds_by_day_tier"]


def test_v3_base_only_prices_from_binding_not_rule(postgis_db_sessionmaker, settings) -> None:
    graph = build_v2_graph(postgis_db_sessionmaker, "v3-base")  # rule: 1200/h
    bind_v2_graph(postgis_db_sessionmaker, settings, graph, base="1000.00", premium="2000.00")
    result = pipeline_to_v2(postgis_db_sessionmaker, settings, graph)

    assert result.overall == "completed"
    calculations = fetch_payout_calculations(postgis_db_sessionmaker)
    assert len(calculations) == 1
    calculation = calculations[0]
    assert calculation.formula_version == PAYOUT_V3
    assert calculation.status == "calculated"
    assert calculation.payout_rule_id == graph.rule.id
    assert calculation.eligible_seconds == 1800
    assert calculation.payable_seconds == 1800
    # No frozen premium zones -> everything base, priced at the BINDING's
    # 1000/h, not the rule row's 1200/h (the freeze is the value source).
    assert calculation.final_payout == Decimal("500.00")
    day = calculation.payout_metadata["lagos_day"]
    assert calculation.payable_seconds_by_day == {day: 1800}
    assert tier_split(calculation) == {day: {"base": 1800, "premium": 0}}
    assert calculation.inputs_fingerprint
    binding_meta = calculation.payout_metadata["binding"]
    assert binding_meta["binding_id"] == str(graph.binding.id)
    assert binding_meta["revision_id"] == str(graph.revision.id)
    assert binding_meta["stationary_policy_marker"] == STATIONARY_POLICY_V1
    assert binding_meta["campaign_window_start_at"] == graph.campaign.start_at.isoformat()
    assert binding_meta["campaign_window_end_at"] == graph.campaign.end_at.isoformat()

    entries = fetch_earnings_ledger_entries(postgis_db_sessionmaker)
    assert len(entries) == 1
    assert entries[0].amount == Decimal("500.00")
    assert entries[0].ledger_metadata["formula_version"] == PAYOUT_V3

    # Explicit-rule surface: a bound trip refuses a foreign rule identity.
    try:
        calculate(postgis_db_sessionmaker, graph.trip.id, settings, payout_rule_id=uuid4())
        raise AssertionError("expected AppError")
    except AppError as exc:
        assert exc.code in {"PAYOUT_RULE_NOT_FOUND", "INVALID_PAYOUT_RULE"}


def test_v3_payout_metadata_preserves_legitimate_null_accepted_window(
    postgis_db_sessionmaker,
    settings,
) -> None:
    graph = build_v2_graph(postgis_db_sessionmaker, "v3-null-window")

    async def clear_window() -> None:
        async with postgis_db_sessionmaker() as session:
            await session.execute(
                update(Campaign)
                .where(Campaign.id == graph.campaign.id)
                .values(start_at=None, end_at=None)
            )
            await session.commit()

    asyncio.run(clear_window())
    bind_v2_graph(postgis_db_sessionmaker, settings, graph)
    pipeline_to_v2(postgis_db_sessionmaker, settings, graph)

    binding_meta = fetch_payout_calculations(postgis_db_sessionmaker)[0].payout_metadata["binding"]
    assert binding_meta["campaign_window_start_at"] is None
    assert binding_meta["campaign_window_end_at"] is None


def test_ext_rm2_fail_closed_binding_rejects_initial_payout(
    postgis_db_sessionmaker, settings
) -> None:
    """Binding marker created before FND-02B must not calculate payout_v3."""
    graph = build_v2_graph(postgis_db_sessionmaker, "v3-rm2-fail-closed")
    bind_v2_graph(postgis_db_sessionmaker, settings, graph)

    async def mark_unresolved() -> None:
        async with postgis_db_sessionmaker() as session:
            binding = await session.get(AssignmentRuleBinding, graph.binding.id)
            binding.stationary_policy_marker = "ext-rm2-fail-closed"
            await session.commit()

    asyncio.run(mark_unresolved())

    try:
        pipeline_to_v2(postgis_db_sessionmaker, settings, graph)
        raise AssertionError("expected unresolved stationary binding to fail closed")
    except AppError as exc:
        assert exc.code == "PAYOUT_STATIONARY_POLICY_UNRESOLVED"
    assert fetch_payout_calculations(postgis_db_sessionmaker) == []
    assert fetch_earnings_ledger_entries(postgis_db_sessionmaker) == []


def test_v3_stop_hop_persists_detector_evidence_and_driver_reason(
    postgis_db_sessionmaker, settings
) -> None:
    graph = build_v2_graph(postgis_db_sessionmaker, "v3-stop-hop")
    bind_v2_graph(postgis_db_sessionmaker, settings, graph)
    points = []
    cycle = 0
    while cycle * 309 < 1800:
        stop_start = cycle * 309
        stop_lat = 6.45 + cycle * 0.003
        for second in range(stop_start, min(stop_start + 299, 1800), 30):
            points.append((graph.trip.started_at + timedelta(seconds=second), stop_lat, 3.40, 10.0))
        if stop_start + 299 <= 1800:
            points.append(
                (graph.trip.started_at + timedelta(seconds=stop_start + 299), stop_lat, 3.40, 10.0)
            )
        if stop_start + 309 <= 1800:
            points.append(
                (
                    graph.trip.started_at + timedelta(seconds=stop_start + 309),
                    stop_lat + 0.003,
                    3.40,
                    10.0,
                )
            )
        cycle += 1
    if points[-1][0] != graph.trip.ended_at:
        points.append((graph.trip.ended_at, points[-1][1], 3.40, 10.0))

    result = pipeline_to_v2(postgis_db_sessionmaker, settings, graph, points=points)

    assert result.overall == "completed"
    calculation = fetch_payout_calculations(postgis_db_sessionmaker)[0]
    assert calculation.excluded_seconds_by_reason["stationary_rolling_displacement"] > 0
    evidence = calculation.payout_metadata["stationary_detector"]
    assert evidence["version"] == STATIONARY_POLICY_V1
    assert evidence["params"] == graph.binding.resolved_eligibility_params
    assert evidence["classified_stationary_ranges"]
    assert any(item.get("transition") == "confirmed" for item in evidence["window_observations"])
    assert all(
        "latitude" not in item and "longitude" not in item
        for item in evidence["window_observations"]
    )
    assert calculation.inputs_fingerprint

    async def breakdown():
        async with postgis_db_sessionmaker() as session:
            return await driver_trip_earnings_breakdown(
                session, user_id=graph.driver.id, trip_id=graph.trip.id
            )

    driver = asyncio.run(breakdown())
    assert driver.excluded_seconds_by_reason["stationary_rolling_displacement"] > 0


def test_v3_premium_only_prices_at_premium_rate(postgis_db_sessionmaker, settings) -> None:
    graph = build_v2_graph(postgis_db_sessionmaker, "v3-prem")
    zone = add_target_zone(
        postgis_db_sessionmaker,
        campaign_id=graph.campaign.id,
        created_by_user_id=graph.admin.id,
        name="Premium all",
        lat_min=6.40,
        lat_max=6.52,
    )
    bind_v2_graph(
        postgis_db_sessionmaker,
        settings,
        graph,
        base="1000.00",
        premium="2400.00",
        zone_ids=[zone.id],
    )
    result = pipeline_to_v2(postgis_db_sessionmaker, settings, graph)

    assert result.overall == "completed"
    calculation = fetch_payout_calculations(postgis_db_sessionmaker)[0]
    assert calculation.formula_version == PAYOUT_V3
    assert calculation.payable_seconds == 1800
    day = calculation.payout_metadata["lagos_day"]
    assert tier_split(calculation) == {day: {"base": 0, "premium": 1800}}
    # 1800 s at the frozen premium 2400/h, one HALF_UP quantization.
    assert calculation.final_payout == Decimal("1200.00")


def test_v3_mixed_tiers_cut_at_zone_transition(postgis_db_sessionmaker, settings) -> None:
    graph = build_v2_graph(postgis_db_sessionmaker, "v3-mixed")
    zone_a = add_target_zone(
        postgis_db_sessionmaker,
        campaign_id=graph.campaign.id,
        created_by_user_id=graph.admin.id,
        name="Premium A",
        lat_min=6.44,
        lat_max=6.4745,
    )
    # Second target zone added AFTER the frozen snapshot: eligible (in-area)
    # but NOT premium — the natural base tier under D18/Q5.
    add_target_zone(
        postgis_db_sessionmaker,
        campaign_id=graph.campaign.id,
        created_by_user_id=graph.admin.id,
        name="Base B",
        lat_min=6.4745,
        lat_max=6.52,
    )
    bind_v2_graph(
        postgis_db_sessionmaker,
        settings,
        graph,
        base="1000.00",
        premium="2000.00",
        zone_ids=[zone_a.id],
    )
    result = pipeline_to_v2(postgis_db_sessionmaker, settings, graph)

    assert result.overall == "completed"
    calculation = fetch_payout_calculations(postgis_db_sessionmaker)[0]
    assert calculation.formula_version == PAYOUT_V3
    assert calculation.eligible_seconds == 1800
    assert calculation.payable_seconds == 1800
    day = calculation.payout_metadata["lagos_day"]
    # The trip drives out of frozen zone A at t=900s: the tier cut lands on
    # the ping boundary exactly like the in_area cuts (PR14).
    assert tier_split(calculation) == {day: {"base": 900, "premium": 900}}
    # (900*1000 + 900*2000)/3600, quantized once.
    assert calculation.final_payout == Decimal("750.00")
    components = calculation.payout_metadata["components"]
    assert components["base_payable_seconds"] == 900
    assert components["premium_payable_seconds"] == 900
    assert components["base_amount"] == "250.00"
    assert components["premium_amount"] == "500.00"

    async def read_driver_breakdown():
        async with postgis_db_sessionmaker() as session:
            return await driver_trip_earnings_breakdown(
                session, user_id=graph.driver.id, trip_id=graph.trip.id
            )

    driver_breakdown = asyncio.run(read_driver_breakdown())
    assert driver_breakdown.formula_version == PAYOUT_V3
    assert driver_breakdown.base_payable_seconds == 900
    assert driver_breakdown.premium_payable_seconds == 900
    assert driver_breakdown.base_hourly_rate == Decimal("1000.00")
    assert driver_breakdown.premium_hourly_rate == Decimal("2000.00")
    assert driver_breakdown.base_amount == Decimal("250.00")
    assert driver_breakdown.premium_amount == Decimal("500.00")
    assert driver_breakdown.base_amount + driver_breakdown.premium_amount == (
        driver_breakdown.amount
    )


def test_v3_supersede_after_accept_never_reprices(postgis_db_sessionmaker, settings) -> None:
    """The no-repricing core guarantee: recomputing after a later revision
    reproduces identical money and an identical fingerprint."""
    graph = build_v2_graph(postgis_db_sessionmaker, "v3-frozen")
    bind_v2_graph(postgis_db_sessionmaker, settings, graph, base="1000.00", premium="2000.00")
    pipeline_to_v2(postgis_db_sessionmaker, settings, graph)

    first = fetch_payout_calculations(postgis_db_sessionmaker)[0]
    assert first.formula_version == PAYOUT_V3
    assert first.final_payout == Decimal("500.00")
    frozen_fingerprint = first.inputs_fingerprint

    # Supersede with radically different values (service path, PR1-valid).
    service_create_revision(
        postgis_db_sessionmaker,
        campaign_id=graph.campaign.id,
        rule_id=graph.rule.id,
        actor_user_id=graph.admin.id,
        effective_from=datetime.now(UTC) + timedelta(hours=1),
        hourly_rate_naira=Decimal("9999.00"),
        reason="post-accept supersede; must never reprice",
    )

    # Reuse path first: reprocessing the trip must not create a second
    # calculation or a second ledger entry.
    result = run_pipeline(postgis_db_sessionmaker, graph.trip.id, settings)
    assert result.overall == "completed"
    assert len(fetch_payout_calculations(postgis_db_sessionmaker)) == 1

    # Deterministic recompute: with the write-once rows cleared (test-only),
    # the engine re-prices from the FROZEN binding, not the new revision.
    delete_money_rows(postgis_db_sessionmaker, graph.trip.id)
    result = run_pipeline(postgis_db_sessionmaker, graph.trip.id, settings)
    assert result.overall == "completed"
    second = fetch_payout_calculations(postgis_db_sessionmaker)[0]
    assert second.final_payout == Decimal("500.00")
    assert second.inputs_fingerprint == frozen_fingerprint
    assert second.payout_metadata["binding"]["revision_id"] == str(graph.revision.id)
    entries = fetch_earnings_ledger_entries(postgis_db_sessionmaker)
    assert [entry.amount for entry in entries] == [Decimal("500.00")]


def test_v3_campaign_window_edits_never_reprice_accepted_work(
    postgis_db_sessionmaker, settings
) -> None:
    graph = build_v2_graph(postgis_db_sessionmaker, "v3-frozen-window")
    bind_v2_graph(postgis_db_sessionmaker, settings, graph, base="1000.00")
    pipeline_to_v2(postgis_db_sessionmaker, settings, graph)
    first = fetch_payout_calculations(postgis_db_sessionmaker)[0]
    frozen_fingerprint = first.inputs_fingerprint
    frozen_amount = first.final_payout

    async def move_live_window() -> None:
        async with postgis_db_sessionmaker() as session:
            await session.execute(
                update(Campaign)
                .where(Campaign.id == graph.campaign.id)
                .values(
                    start_at=graph.trip.ended_at + timedelta(days=10),
                    end_at=graph.trip.ended_at + timedelta(days=20),
                )
            )
            await session.commit()

    asyncio.run(move_live_window())

    # Strict reuse sees no drift because v3 fingerprints the accepted window.
    assert run_pipeline(postgis_db_sessionmaker, graph.trip.id, settings).overall == "completed"
    delete_money_rows(postgis_db_sessionmaker, graph.trip.id)
    assert run_pipeline(postgis_db_sessionmaker, graph.trip.id, settings).overall == "completed"
    replayed = fetch_payout_calculations(postgis_db_sessionmaker)[0]
    assert replayed.final_payout == frozen_amount
    assert replayed.inputs_fingerprint == frozen_fingerprint


def test_legacy_v3_binding_without_window_freeze_fails_closed(
    postgis_db_sessionmaker, settings
) -> None:
    graph = build_v2_graph(postgis_db_sessionmaker, "v3-legacy-window")
    bind_v2_graph(postgis_db_sessionmaker, settings, graph)

    async def mark_legacy() -> None:
        async with postgis_db_sessionmaker() as session:
            await session.execute(
                update(AssignmentRuleBinding)
                .where(AssignmentRuleBinding.id == graph.binding.id)
                .values(
                    campaign_window_start_at=None,
                    campaign_window_end_at=None,
                    campaign_window_frozen=False,
                )
            )
            await session.commit()

    asyncio.run(mark_legacy())
    with pytest.raises(AppError) as error:
        run_pipeline(postgis_db_sessionmaker, graph.trip.id, settings)
    assert error.value.code == "PAYOUT_BINDING_WINDOW_NOT_FROZEN"


def test_v3_replay_uses_frozen_geometry_and_resolved_eligibility(
    postgis_db_sessionmaker, settings
) -> None:
    graph = build_v2_graph(postgis_db_sessionmaker, "v3-immutable-inputs")
    premium = add_target_zone(
        postgis_db_sessionmaker,
        campaign_id=graph.campaign.id,
        created_by_user_id=graph.admin.id,
        name="Frozen premium",
        lat_min=6.40,
        lat_max=6.52,
    )
    bind_v2_graph(
        postgis_db_sessionmaker,
        settings,
        graph,
        base="1000.00",
        premium="2000.00",
        zone_ids=[premium.id],
    )
    pipeline_to_v2(postgis_db_sessionmaker, settings, graph)
    first = fetch_payout_calculations(postgis_db_sessionmaker)[0]
    assert first.final_payout == Decimal("1000.00")
    frozen_fingerprint = first.inputs_fingerprint

    async def mutate_live_inputs() -> None:
        async with postgis_db_sessionmaker() as session:
            far_away = geometry_expression(
                json.dumps(
                    {
                        "type": "Polygon",
                        "coordinates": [
                            [[4.0, 7.0], [4.1, 7.0], [4.1, 7.1], [4.0, 7.1], [4.0, 7.0]]
                        ],
                    }
                )
            )
            await session.execute(
                update(CampaignZone).where(CampaignZone.id == premium.id).values(geom=far_away)
            )
            await session.commit()

    asyncio.run(mutate_live_inputs())
    add_target_zone(
        postgis_db_sessionmaker,
        campaign_id=graph.campaign.id,
        created_by_user_id=graph.admin.id,
        name="Late exclusion must not reprice",
        lat_min=6.40,
        lat_max=6.52,
        zone_type=CampaignZoneType.EXCLUSION.value,
    )
    changed_settings = settings.model_copy(
        update={
            "payout_eligibility_max_accuracy_m": 1.0,
            "payout_eligibility_rolling_max_displacement_m": 1.0,
        }
    )

    delete_money_rows(postgis_db_sessionmaker, graph.trip.id)
    run_pipeline(postgis_db_sessionmaker, graph.trip.id, changed_settings)
    replayed = fetch_payout_calculations(postgis_db_sessionmaker)[0]
    assert replayed.final_payout == Decimal("1000.00")
    assert replayed.inputs_fingerprint == frozen_fingerprint
    day = replayed.payout_metadata["lagos_day"]
    assert tier_split(replayed) == {day: {"base": 0, "premium": 1800}}


def test_v3_cap_truncation_is_chronological_across_tiers(postgis_db_sessionmaker, settings) -> None:
    """PR4: the day cap is consumed by the EARLIEST eligible seconds, each
    priced at its own tier — premium-first here because the premium half of
    the trip comes first, not because premium wins any priority."""
    graph = build_v2_graph(postgis_db_sessionmaker, "v3-cap")
    zone_a = add_target_zone(
        postgis_db_sessionmaker,
        campaign_id=graph.campaign.id,
        created_by_user_id=graph.admin.id,
        name="Premium A",
        lat_min=6.44,
        lat_max=6.4745,
    )
    add_target_zone(
        postgis_db_sessionmaker,
        campaign_id=graph.campaign.id,
        created_by_user_id=graph.admin.id,
        name="Base B",
        lat_min=6.4745,
        lat_max=6.52,
    )
    bind_v2_graph(
        postgis_db_sessionmaker,
        settings,
        graph,
        base="1000.00",
        premium="2000.00",
        cap="0.25",  # 900 s
        zone_ids=[zone_a.id],
    )
    pipeline_to_v2(postgis_db_sessionmaker, settings, graph)

    calculation = fetch_payout_calculations(postgis_db_sessionmaker)[0]
    assert calculation.formula_version == PAYOUT_V3
    assert calculation.eligible_seconds == 1800
    assert calculation.payable_seconds == 900
    day = calculation.payout_metadata["lagos_day"]
    # Chronological fill: the first 900 eligible seconds are all premium; the
    # base half arrives after the cap is exhausted and pays nothing. A
    # cheapest-first (base-first) fill would show base=900 instead.
    assert tier_split(calculation) == {day: {"base": 0, "premium": 900}}
    assert calculation.final_payout == Decimal("500.00")  # 900 s at 2000/h


def build_mixed_engine_day(postgis_db_sessionmaker, settings, tag: str, *, cap: str):
    """One driver/campaign/Lagos-day with a v2 trip (unbound assignment) and
    a v3 trip (bound assignment on a second vehicle)."""
    graph = build_v2_graph(postgis_db_sessionmaker, tag, daily_cap_hours=cap)
    vehicle2 = create_test_vehicle(
        postgis_db_sessionmaker,
        driver_profile_id=graph.profile.id,
        plate_number=f"M2-{tag[:10].upper()}",
        vehicle_status=VehicleStatus.ACTIVE,
    )
    assignment2 = create_test_campaign_assignment(
        postgis_db_sessionmaker,
        campaign_id=graph.campaign.id,
        driver_profile_id=graph.profile.id,
        vehicle_id=vehicle2.id,
        assigned_by_user_id=graph.admin.id,
        assignment_status=CampaignAssignmentStatus.ACCEPTED,
    )
    revision = create_revision_row(
        postgis_db_sessionmaker,
        campaign_id=graph.campaign.id,
        rule_id=graph.rule.id,
        created_by_user_id=graph.admin.id,
        base="1200.00",
        premium=None,
        cap=cap,
    )
    insert_binding(
        postgis_db_sessionmaker,
        settings,
        assignment_id=assignment2.id,
        revision=revision,
    )
    trip2_start = TRIP_START + timedelta(hours=1)
    trip2 = create_signed_v2_test_trip_session(
        postgis_db_sessionmaker,
        settings,
        assignment_id=assignment2.id,
        campaign_id=graph.campaign.id,
        driver_profile_id=graph.profile.id,
        vehicle_id=vehicle2.id,
        started_by_user_id=graph.driver.id,
        started_at=trip2_start,
        ended_at=trip2_start + timedelta(minutes=30),
    )
    add_pings(
        postgis_db_sessionmaker,
        trip_id=graph.trip.id,
        points=moving_points(graph.trip.started_at),
        idempotency_key=f"{tag}-t1",
    )
    add_pings(
        postgis_db_sessionmaker,
        trip_id=trip2.id,
        points=moving_points(trip2_start),
        idempotency_key=f"{tag}-t2",
    )
    graph.trip2 = trip2
    return graph


def test_mixed_v2_v3_trips_share_one_day_cap_pool(postgis_db_sessionmaker, settings) -> None:
    """PR5: ONE shared D4 cap pool per driver/campaign/Lagos-day across
    engines — the v3 trip only gets what the v2 trip left."""
    graph = build_mixed_engine_day(postgis_db_sessionmaker, settings, "v3-pool", cap="0.75")
    result1 = run_pipeline(postgis_db_sessionmaker, graph.trip.id, settings)
    result2 = run_pipeline(postgis_db_sessionmaker, graph.trip2.id, settings)
    assert result1.overall == "completed"
    assert result2.overall == "completed"

    calculations = {
        calc.trip_session_id: calc for calc in fetch_payout_calculations(postgis_db_sessionmaker)
    }
    v2_calc = calculations[graph.trip.id]
    v3_calc = calculations[graph.trip2.id]
    assert v2_calc.formula_version == PAYOUT_V2
    assert v3_calc.formula_version == PAYOUT_V3
    assert v2_calc.payable_seconds == 1800
    # Cap 2700 s shared across engines: the bound trip gets the remainder.
    assert v3_calc.payable_seconds == 900
    assert v2_calc.payable_seconds + v3_calc.payable_seconds == 2700
    assert v3_calc.final_payout == Decimal("300.00")  # 900 s at 1200/h


def test_mixed_v2_v3_cap_race_never_exceeds_day_cap(postgis_db_sessionmaker, settings) -> None:
    """PR5 race: whichever engine wins the advisory lock, the shared pool
    never exceeds the D4 cap in any serialization."""
    from app.services.trip_processing import process_ended_trip

    graph = build_mixed_engine_day(postgis_db_sessionmaker, settings, "v3-pool-race", cap="0.75")

    async def process(trip_id):
        async with postgis_db_sessionmaker() as session:
            result = await process_ended_trip(session, trip_id=trip_id, settings=settings)
            await session.commit()
            return result

    async def race():
        return await asyncio.gather(process(graph.trip.id), process(graph.trip2.id))

    results = asyncio.run(race())
    assert {result.overall for result in results} == {"completed"}

    day_key = graph.trip.started_at.date().isoformat()
    calculations = fetch_payout_calculations(postgis_db_sessionmaker)
    assert len(calculations) == 2
    allocations = sorted(
        int((calc.payable_seconds_by_day or {}).get(day_key, 0)) for calc in calculations
    )
    # One serialization gives (1800, 900), the other (900, 1800); the pool
    # total equals the cap and can never exceed it.
    assert allocations == [900, 1800]
    assert sum(allocations) == 2700


def test_v3_midnight_spanning_trip_allocates_per_day(postgis_db_sessionmaker, settings) -> None:
    # 22:30 -> 23:30 UTC == 23:30 -> 00:30 Africa/Lagos: two payable days.
    started_at = datetime(2026, 7, 20, 22, 30, tzinfo=UTC)
    ended_at = started_at + timedelta(minutes=60)
    graph = build_v2_graph(
        postgis_db_sessionmaker, "v3-midnight", started_at=started_at, ended_at=ended_at
    )
    bind_v2_graph(postgis_db_sessionmaker, settings, graph, base="1200.00", premium=None)
    result = pipeline_to_v2(
        postgis_db_sessionmaker,
        settings,
        graph,
        points=moving_points(started_at, minutes=60),
    )

    assert result.overall == "completed"
    calculation = fetch_payout_calculations(postgis_db_sessionmaker)[0]
    assert calculation.formula_version == PAYOUT_V3
    assert calculation.eligible_seconds == 3600
    # RM1 day slicing survives v3: each Lagos day carries its own allocation.
    assert calculation.payable_seconds_by_day == {
        "2026-07-20": 1800,
        "2026-07-21": 1800,
    }
    assert tier_split(calculation) == {
        "2026-07-20": {"base": 1800, "premium": 0},
        "2026-07-21": {"base": 1800, "premium": 0},
    }
    assert calculation.final_payout == Decimal("1200.00")  # 3600 s at 1200/h


# --- Fingerprint completeness (B2/Q6) and pure tier slicing ------------------


def test_tier_component_allocator_reconciles_once_quantized_total() -> None:
    total = price_tiered_payable_seconds(1, 1, Decimal("18.00"), Decimal("18.00"))
    # Each raw component is half a kobo. Rounding both independently would
    # produce 0.02, but the once-quantized authoritative total is 0.01.
    components = allocate_tier_amount_components(
        base_seconds=1,
        premium_seconds=1,
        base_rate=Decimal("18.00"),
        premium_rate=Decimal("18.00"),
        authoritative_total=total,
    )
    assert components.base_amount == Decimal("0.01")
    assert components.premium_amount == Decimal("0.00")
    assert components.base_amount + components.premium_amount == total


def test_tier_component_allocator_preserves_empty_tiers_and_base_rate_fallback() -> None:
    base_only = allocate_tier_amount_components(
        base_seconds=1800,
        premium_seconds=0,
        base_rate=Decimal("1000.00"),
        premium_rate=Decimal("1000.00"),
        authoritative_total=Decimal("500.00"),
    )
    assert base_only.base_amount == Decimal("500.00")
    assert base_only.premium_amount == Decimal("0.00")

    premium_only = allocate_tier_amount_components(
        base_seconds=0,
        premium_seconds=1800,
        base_rate=Decimal("1000.00"),
        # A NULL frozen premium rate is resolved to base before allocation.
        premium_rate=Decimal("1000.00"),
        authoritative_total=Decimal("500.00"),
    )
    assert premium_only.base_amount == Decimal("0.00")
    assert premium_only.premium_amount == Decimal("500.00")


def test_driver_breakdown_uses_latest_valid_nonvoided_v3_authority(
    postgis_db_sessionmaker, settings
) -> None:
    graph = build_v2_graph(postgis_db_sessionmaker, "v3-driver-supersession")
    bind_v2_graph(
        postgis_db_sessionmaker,
        settings,
        graph,
        base="1000.00",
        premium="1800.00",
    )
    pipeline_to_v2(postgis_db_sessionmaker, settings, graph)
    calculation = fetch_payout_calculations(postgis_db_sessionmaker)[0]
    day = calculation.payout_metadata["lagos_day"]

    def metadata(*, base: int, premium: int, total: str) -> dict:
        components = allocate_tier_amount_components(
            base_seconds=base,
            premium_seconds=premium,
            base_rate=Decimal("1000.00"),
            premium_rate=Decimal("1800.00"),
            authoritative_total=Decimal(total),
        )
        return {
            "recompute_day": True,
            "payout_calculation_id": str(calculation.id),
            "formula_version": PAYOUT_V3,
            "breakdown": {
                "eligible_seconds": base + premium,
                "payable_seconds": base + premium,
                "payable_seconds_by_day": {day: base + premium},
                "payable_seconds_by_day_tier": {day: {"base": base, "premium": premium}},
                "base_payable_seconds": base,
                "premium_payable_seconds": premium,
                "hourly_rate_naira": "1000.00",
                "premium_hourly_rate_naira": "1800.00",
                "base_amount": str(components.base_amount),
                "premium_amount": str(components.premium_amount),
                "target_amount": total,
            },
        }

    async def insert_entries() -> tuple[EarningsLedgerEntry, EarningsLedgerEntry]:
        async with postgis_db_sessionmaker() as session:
            positive = EarningsLedgerEntry(
                driver_profile_id=graph.profile.id,
                driver_user_id=graph.driver.id,
                campaign_id=graph.campaign.id,
                trip_session_id=graph.trip.id,
                vehicle_id=graph.vehicle.id,
                entry_type=EarningsLedgerEntryType.ADJUSTMENT.value,
                status=EarningsLedgerEntryStatus.PENDING.value,
                amount=Decimal("500.00"),
                currency="NGN",
                occurred_at=graph.trip.ended_at + timedelta(minutes=1),
                ledger_metadata=metadata(base=0, premium=1800, total="1000.00"),
            )
            reversal = EarningsLedgerEntry(
                driver_profile_id=graph.profile.id,
                driver_user_id=graph.driver.id,
                campaign_id=graph.campaign.id,
                trip_session_id=graph.trip.id,
                vehicle_id=graph.vehicle.id,
                entry_type=EarningsLedgerEntryType.REVERSAL.value,
                status=EarningsLedgerEntryStatus.PENDING.value,
                amount=Decimal("300.00"),
                currency="NGN",
                occurred_at=graph.trip.ended_at + timedelta(minutes=2),
                ledger_metadata=metadata(base=900, premium=900, total="700.00"),
            )
            session.add_all([positive, reversal])
            await session.commit()
            return positive, reversal

    positive, reversal = asyncio.run(insert_entries())

    async def breakdown():
        async with postgis_db_sessionmaker() as session:
            return await driver_trip_earnings_breakdown(
                session, user_id=graph.driver.id, trip_id=graph.trip.id
            )

    latest = asyncio.run(breakdown())
    assert latest.superseded_by_recompute is True
    assert latest.amount == Decimal("700.00")
    assert latest.base_payable_seconds == 900
    assert latest.premium_payable_seconds == 900
    assert latest.base_amount == Decimal("250.00")
    assert latest.premium_amount == Decimal("450.00")

    async def insert_malformed_latest() -> None:
        async with postgis_db_sessionmaker() as session:
            malformed = metadata(base=900, premium=900, total="700.00")
            malformed["breakdown"]["base_payable_seconds"] = 1800
            session.add(
                EarningsLedgerEntry(
                    driver_profile_id=graph.profile.id,
                    driver_user_id=graph.driver.id,
                    campaign_id=graph.campaign.id,
                    trip_session_id=graph.trip.id,
                    vehicle_id=graph.vehicle.id,
                    entry_type=EarningsLedgerEntryType.ADJUSTMENT.value,
                    status=EarningsLedgerEntryStatus.PENDING.value,
                    amount=Decimal("0.00"),
                    currency="NGN",
                    occurred_at=graph.trip.ended_at + timedelta(minutes=3),
                    ledger_metadata=malformed,
                )
            )
            await session.commit()

    asyncio.run(insert_malformed_latest())
    malformed_ignored = asyncio.run(breakdown())
    assert malformed_ignored.base_payable_seconds == 900
    assert malformed_ignored.premium_payable_seconds == 900

    async def void_latest() -> None:
        async with postgis_db_sessionmaker() as session:
            stored = await session.get(EarningsLedgerEntry, reversal.id)
            stored.status = EarningsLedgerEntryStatus.VOIDED.value
            await session.commit()

    asyncio.run(void_latest())
    fallback = asyncio.run(breakdown())
    assert fallback.superseded_by_recompute is True
    assert fallback.base_payable_seconds == 0
    assert fallback.premium_payable_seconds == 1800
    assert fallback.base_amount == Decimal("0.00")
    assert fallback.premium_amount == Decimal("1000.00")
    assert positive.status == EarningsLedgerEntryStatus.PENDING.value

    async def mark_original_insufficient_and_get_consumed() -> int:
        async with postgis_db_sessionmaker() as session:
            stored = await session.get(PayoutCalculation, calculation.id)
            stored.status = PayoutCalculationStatus.INSUFFICIENT_DATA.value
            await session.commit()
            return await day_consumed_payable_seconds(
                session,
                driver_profile_id=graph.profile.id,
                campaign_id=graph.campaign.id,
                lagos_day=datetime.fromisoformat(day).date(),
            )

    # A recompute can heal an insufficient-data calculation. Its latest
    # authoritative target must still consume the shared day cap.
    assert asyncio.run(mark_original_insufficient_and_get_consumed()) == 1800

    async def void_original() -> None:
        async with postgis_db_sessionmaker() as session:
            original = await session.scalar(
                select(EarningsLedgerEntry).where(
                    EarningsLedgerEntry.trip_session_id == graph.trip.id,
                    EarningsLedgerEntry.entry_type == EarningsLedgerEntryType.TRIP_PAYOUT.value,
                )
            )
            original.status = EarningsLedgerEntryStatus.VOIDED.value
            await session.commit()

    asyncio.run(void_original())
    inconsistent_target_hidden = asyncio.run(breakdown())
    assert inconsistent_target_hidden.amount == Decimal("500.00")
    assert inconsistent_target_hidden.base_amount is None
    assert inconsistent_target_hidden.premium_amount is None

    async def consumed_after_void() -> int:
        async with postgis_db_sessionmaker() as session:
            return await day_consumed_payable_seconds(
                session,
                driver_profile_id=graph.profile.id,
                campaign_id=graph.campaign.id,
                lagos_day=datetime.fromisoformat(day).date(),
            )

    assert asyncio.run(consumed_after_void()) == 0


def test_v3_fingerprint_covers_every_frozen_binding_input() -> None:
    def binding(**overrides) -> SimpleNamespace:
        values = {
            "id": "11111111-1111-1111-1111-111111111111",
            "revision_id": "22222222-2222-2222-2222-222222222222",
            "hourly_rate_naira": Decimal("1000.00"),
            "premium_hourly_rate_naira": Decimal("2000.00"),
            "daily_payable_hours_cap": Decimal("8.00"),
            "eligibility_params": {"stationary_grace_min": 5},
            "resolved_eligibility_params": params.as_metadata(),
            "premium_zone_ids": ["33333333-3333-3333-3333-333333333333"],
            "premium_zone_geometry_hash": hashlib.sha256(b"zones").hexdigest(),
            "exclusion_zone_ids": ["44444444-4444-4444-4444-444444444444"],
            "exclusion_zone_geometry_hash": hashlib.sha256(b"exclusions").hexdigest(),
            "stationary_policy_marker": "ext-rm2-fail-closed",
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    params = EligibilityParams(
        stationary_radius_m=50.0,
        stationary_window_seconds=600,
        stationary_grace_seconds=300,
        max_accuracy_m=50.0,
        teleport_kmh=150.0,
        max_ping_gap_seconds=120,
    )

    def fingerprint(b, **overrides) -> str:
        kwargs = {
            "binding": b,
            "currency": "NGN",
            "params": params,
            "ping_fingerprint": "ping-fp",
            "zone_fingerprint": "zone-fp",
            "window_start_at": None,
            "window_end_at": None,
        }
        kwargs.update(overrides)
        return v3_inputs_fingerprint(**kwargs)

    baseline = fingerprint(binding())
    assert baseline == fingerprint(binding())  # deterministic
    variants = [
        binding(id="99999999-9999-9999-9999-999999999999"),
        binding(revision_id="99999999-9999-9999-9999-999999999999"),
        binding(hourly_rate_naira=Decimal("1001.00")),
        binding(premium_hourly_rate_naira=Decimal("2001.00")),
        binding(premium_hourly_rate_naira=None),
        binding(daily_payable_hours_cap=Decimal("7.00")),
        binding(eligibility_params={"stationary_grace_min": 6}),
        binding(resolved_eligibility_params={**params.as_metadata(), "max_accuracy_m": 51.0}),
        binding(
            resolved_eligibility_params={
                **params.as_metadata(),
                "rolling_max_displacement_m": 26.0,
            }
        ),
        binding(
            resolved_eligibility_params={
                **params.as_metadata(),
                "rolling_window_seconds": 121,
            }
        ),
        binding(
            resolved_eligibility_params={
                **params.as_metadata(),
                "rolling_stride_seconds": 121,
            }
        ),
        binding(
            resolved_eligibility_params={
                **params.as_metadata(),
                "rolling_confirmation_windows": 3,
            }
        ),
        binding(
            resolved_eligibility_params={
                **params.as_metadata(),
                "rolling_release_windows": 2,
            }
        ),
        binding(premium_zone_ids=[]),
        binding(premium_zone_geometry_hash=hashlib.sha256(b"other").hexdigest()),
        binding(exclusion_zone_ids=[]),
        binding(exclusion_zone_geometry_hash=hashlib.sha256(b"other-exclusion").hexdigest()),
        binding(stationary_policy_marker="something-else"),
    ]
    fingerprints = [fingerprint(variant) for variant in variants]
    fingerprints.extend(
        [
            fingerprint(binding(), currency="USD"),
            fingerprint(binding(), ping_fingerprint="other"),
            fingerprint(binding(), zone_fingerprint="other"),
            fingerprint(binding(), window_start_at=datetime(2026, 1, 1, tzinfo=UTC)),
        ]
    )
    assert baseline not in fingerprints
    assert len(set(fingerprints)) == len(fingerprints)


def test_classify_session_tier_slices_preserve_sum_invariant() -> None:
    start = datetime(2026, 7, 20, 8, 0, tzinfo=UTC)

    def ping(offset: int, lat: float, premium: bool) -> EligibilityPing:
        return EligibilityPing(
            recorded_at=start + timedelta(seconds=offset),
            latitude=lat,
            longitude=3.40,
            accuracy_m=10.0,
            in_area=True,
            in_premium=premium,
        )

    pings = [
        ping(offset, 6.45 + (offset // 30) * 0.00081, premium=offset < 300)
        for offset in range(0, 601, 30)
    ]
    params = EligibilityParams(
        stationary_radius_m=50.0,
        stationary_window_seconds=600,
        stationary_grace_seconds=300,
        max_accuracy_m=50.0,
        teleport_kmh=150.0,
        max_ping_gap_seconds=120,
    )
    breakdown = classify_session(
        session_started_at=start,
        session_ended_at=start + timedelta(seconds=600),
        pings=pings,
        window_start_at=None,
        window_end_at=None,
        params=params,
    )
    assert breakdown.total_seconds == 600
    assert sum(s.length for s in breakdown.eligible_slices) == breakdown.eligible_seconds
    # Premium requires BOTH governing pings inside the premium area — the
    # transition interval [270, 300) resolves base, mirroring in_area.
    premium_seconds = sum(s.length for s in breakdown.eligible_slices if s.premium)
    assert premium_seconds == 270
    assert breakdown.eligible_seconds == 600
    # Slices stay chronological and non-overlapping.
    offsets = [(s.start_offset, s.end_offset) for s in breakdown.eligible_slices]
    assert offsets == sorted(offsets)
    assert all(end > start_ for start_, end in offsets)
