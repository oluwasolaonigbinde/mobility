import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from conftest import (
    create_test_campaign,
    create_test_campaign_assignment,
    create_test_driver_profile,
    create_test_impression_estimate,
    create_test_organization,
    create_test_payout_rule,
    create_test_traffic_density_profile,
    create_test_trip_analytics,
    create_test_trip_session,
    create_test_user,
    create_test_vehicle,
    fetch_audit_events,
    fetch_earnings_ledger_entries,
    fetch_impression_estimates,
    fetch_payout_calculations,
)
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.errors import AppError
from app.models.campaign import CampaignStatus
from app.models.campaign_assignment import CampaignAssignmentStatus
from app.models.driver import DriverOnboardingStatus
from app.models.fraud_assessment import FraudAssessment, FraudAssessmentStatus
from app.models.impression import ImpressionEstimate, TrafficDensityProfile
from app.models.payout import CampaignPayoutRule, EarningsLedgerEntry, PayoutCalculation
from app.models.route_replay import RouteReplaySignature
from app.models.trip import LocationPing, LocationPingBatch, TripSessionStatus
from app.models.trip_analytics import FraudFlag, FraudFlagStatus, FraudFlagType, TripAnalytics
from app.models.user import UserRole
from app.models.vehicle import VehicleStatus
from app.schemas.impressions import TrafficDensityProfileUpdate
from app.services import fraud_assessments, route_replay, trip_processing
from app.services.fraud_holds import acknowledge_fraud_flag, resolve_fraud_flag
from app.services.impressions import update_traffic_density_profile
from app.services.payouts import calculate_trip_payout
from app.services.trip_evidence import sign_manifest_receipt
from app.services.trip_processing import (
    AUDIT_ACTION_TRIP_PROCESSING,
    TripProcessingResult,
    find_unprocessed_trips,
    process_ended_trip,
)
from app.services.trips import point_value

PASSWORD = "long-secure-password"
BASE_TIME = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
PAST = datetime(2020, 1, 1, tzinfo=UTC)
FUTURE = datetime(2099, 1, 1, tzinfo=UTC)


def build_graph(
    db_sessionmaker: async_sessionmaker[AsyncSession],
    tag: str,
    *,
    trip_status: TripSessionStatus = TripSessionStatus.SEALED,
    started_at: datetime = BASE_TIME,
    ended_at: datetime | None = BASE_TIME + timedelta(minutes=30),
) -> SimpleNamespace:
    admin = create_test_user(db_sessionmaker, email=f"admin-{tag}@example.com", password=PASSWORD)
    advertiser = create_test_user(
        db_sessionmaker,
        email=f"advertiser-{tag}@example.com",
        password=PASSWORD,
        role=UserRole.ADVERTISER,
    )
    organization, _ = create_test_organization(
        db_sessionmaker,
        name=f"Org {tag}",
        owner_user_id=advertiser.id,
    )
    campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=advertiser.id,
        campaign_status=CampaignStatus.ACTIVE,
        start_at=PAST,
        end_at=FUTURE,
    )
    driver = create_test_user(
        db_sessionmaker,
        email=f"driver-{tag}@example.com",
        password=PASSWORD,
        role=UserRole.DRIVER,
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
        plate_number=f"TP-{tag[:10].upper()}",
        vehicle_status=VehicleStatus.ACTIVE,
    )
    assignment = create_test_campaign_assignment(
        db_sessionmaker,
        campaign_id=campaign.id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        assigned_by_user_id=admin.id,
        assignment_status=CampaignAssignmentStatus.ACTIVE,
        activated_at=started_at,
    )
    trip = create_test_trip_session(
        db_sessionmaker,
        assignment_id=assignment.id,
        campaign_id=campaign.id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        started_by_user_id=driver.id,
        trip_status=trip_status,
        started_at=started_at,
        ended_at=ended_at,
    )

    async def bind_v2_evidence_authority() -> None:
        async with db_sessionmaker() as session:
            stored = await session.get(type(trip), trip.id)
            stored.evidence_protocol_version = 2
            if trip_status == TripSessionStatus.SEALED:
                stored.evidence_manifest_version = 2
                stored.evidence_manifest_root_sha256 = "0" * 64
                stored.evidence_manifest_batch_count = 0
                stored.evidence_manifest_ping_count = 0
                stored.evidence_manifest_committed_at = ended_at
                stored.evidence_manifest_complete = True
                stored.evidence_manifest_verified_at = ended_at
                sign_manifest_receipt(stored, Settings(environment="test"))
            await session.commit()

    asyncio.run(bind_v2_evidence_authority())
    return SimpleNamespace(
        admin=admin,
        driver=driver,
        campaign=campaign,
        profile=profile,
        vehicle=vehicle,
        assignment=assignment,
        trip=trip,
    )


def add_pings(
    db_sessionmaker: async_sessionmaker[AsyncSession],
    *,
    trip_id,
    points: list[tuple[datetime, float, float, float]],
    idempotency_key: str = "processing-batch",
) -> None:
    async def create() -> None:
        async with db_sessionmaker() as session:
            received_at = datetime.now(UTC)
            batch = LocationPingBatch(
                trip_session_id=trip_id,
                idempotency_key=idempotency_key,
                payload_hash=f"hash-{idempotency_key}",
                pings_accepted=len(points),
                received_at=received_at,
                batch_metadata={},
            )
            session.add(batch)
            await session.flush()
            for sequence_number, (recorded_at, lat, lon, accuracy_m) in enumerate(points):
                session.add(
                    LocationPing(
                        trip_session_id=trip_id,
                        batch_id=batch.id,
                        recorded_at=recorded_at,
                        received_at=received_at,
                        sequence_number=sequence_number,
                        latitude=lat,
                        longitude=lon,
                        accuracy_m=accuracy_m,
                        speed_mps=None,
                        heading_degrees=None,
                        altitude_m=None,
                        geom=point_value(session, lon=lon, lat=lat),
                        ping_metadata={},
                    )
                )
            await session.commit()

    asyncio.run(create())


def moving_points() -> list[tuple[datetime, float, float, float]]:
    return [
        (BASE_TIME, 6.45, 3.39, 10),
        (BASE_TIME + timedelta(minutes=5), 6.45, 3.40, 12),
        (BASE_TIME + timedelta(minutes=10), 6.45, 3.42, 14),
    ]


def run_pipeline(
    db_sessionmaker: async_sessionmaker[AsyncSession],
    trip_id,
    settings,
) -> TripProcessingResult:
    async def run() -> TripProcessingResult:
        async with db_sessionmaker() as session:
            result = await process_ended_trip(session, trip_id=trip_id, settings=settings)
            await session.commit()
            return result

    return asyncio.run(run())


def table_counts(db_sessionmaker: async_sessionmaker[AsyncSession]) -> dict[str, int]:
    async def fetch() -> dict[str, int]:
        async with db_sessionmaker() as session:

            async def count(model) -> int:
                return int(await session.scalar(select(func.count()).select_from(model)) or 0)

            return {
                "analytics": await count(TripAnalytics),
                "assessments": await count(FraudAssessment),
                "replay_signatures": await count(RouteReplaySignature),
                "flags": await count(FraudFlag),
                "estimates": await count(ImpressionEstimate),
                "calculations": await count(PayoutCalculation),
                "ledger": await count(EarningsLedgerEntry),
            }

    return asyncio.run(fetch())


def worker_audit_events(db_sessionmaker: async_sessionmaker[AsyncSession]) -> list:
    return [
        event
        for event in fetch_audit_events(db_sessionmaker)
        if event.action == AUDIT_ACTION_TRIP_PROCESSING
    ]


def seed_analytics(
    db_sessionmaker: async_sessionmaker[AsyncSession],
    graph: SimpleNamespace,
    *,
    status: str = "computed",
    distance_m: Decimal = Decimal("5000"),
) -> TripAnalytics:
    return create_test_trip_analytics(
        db_sessionmaker,
        trip_session_id=graph.trip.id,
        assignment_id=graph.assignment.id,
        campaign_id=graph.campaign.id,
        driver_profile_id=graph.profile.id,
        vehicle_id=graph.vehicle.id,
        status=status,
        started_at=BASE_TIME,
        ended_at=BASE_TIME + timedelta(minutes=30),
        distance_m=distance_m,
        active_tracking_seconds=600,
        quality_score=1,
    )


def stage_outcomes(result: TripProcessingResult) -> dict[str, str]:
    return {stage.stage: stage.outcome for stage in result.stages}


def test_happy_path_creates_full_chain_and_audits(postgis_db_sessionmaker, settings) -> None:
    graph = build_graph(postgis_db_sessionmaker, "happy")
    create_test_payout_rule(
        postgis_db_sessionmaker,
        campaign_id=graph.campaign.id,
        created_by_user_id=graph.admin.id,
        base_rate_per_km=10,
    )
    add_pings(postgis_db_sessionmaker, trip_id=graph.trip.id, points=moving_points())

    result = run_pipeline(postgis_db_sessionmaker, graph.trip.id, settings)

    assert result.overall == "completed"
    assert stage_outcomes(result) == {
        "analytics": "created",
        "fraud_assessment": "created",
        "impressions": "created",
        "payout": "created",
    }
    counts = table_counts(postgis_db_sessionmaker)
    assert counts["analytics"] == 1
    assert counts["estimates"] == 1
    assert counts["calculations"] == 1
    assert counts["ledger"] == 1
    assert counts["flags"] == int(result.stages[0].row_ids["open_fraud_flag_count"])
    estimate = fetch_impression_estimates(postgis_db_sessionmaker)[0]
    assert estimate.formula_version == settings.impression_formula_version

    async def default_profile_used() -> bool:
        async with postgis_db_sessionmaker() as session:
            profile = await session.get(TrafficDensityProfile, estimate.traffic_density_profile_id)
            return profile is not None and profile.is_default

    assert asyncio.run(default_profile_used())
    calculation = fetch_payout_calculations(postgis_db_sessionmaker)[0]
    assert calculation.status == "calculated"
    assert calculation.final_payout > 0
    ledger = fetch_earnings_ledger_entries(postgis_db_sessionmaker)[0]
    assert ledger.status == "pending"
    assert ledger.amount == calculation.final_payout
    events = worker_audit_events(postgis_db_sessionmaker)
    assert len(events) == 1
    assert events[0].actor_user_id is None
    assert events[0].entity_type == "trip_session"
    assert events[0].entity_id == str(graph.trip.id)
    assert events[0].event_metadata["stages"] == {
        "analytics": "created",
        "fraud_assessment": "created",
        "impressions": "created",
        "payout": "created",
    }


def test_injected_time_stamps_the_full_postgis_pipeline(
    postgis_db_sessionmaker,
    settings,
) -> None:
    graph = build_graph(postgis_db_sessionmaker, "clock-full")
    create_test_payout_rule(
        postgis_db_sessionmaker,
        campaign_id=graph.campaign.id,
        created_by_user_id=graph.admin.id,
        base_rate_per_km=10,
    )
    add_pings(
        postgis_db_sessionmaker,
        trip_id=graph.trip.id,
        points=[(BASE_TIME, 6.45, 3.39, 10)],
    )
    frozen_now = datetime(2026, 2, 3, 4, 5, tzinfo=UTC)

    async def run() -> None:
        async with postgis_db_sessionmaker() as session:
            await process_ended_trip(
                session,
                trip_id=graph.trip.id,
                settings=settings,
                now=frozen_now,
            )
            analytics = await session.scalar(
                select(TripAnalytics).where(TripAnalytics.trip_session_id == graph.trip.id)
            )
            flags = list(
                (
                    await session.execute(
                        select(FraudFlag).where(FraudFlag.trip_session_id == graph.trip.id)
                    )
                ).scalars()
            )
            estimate = await session.scalar(
                select(ImpressionEstimate).where(
                    ImpressionEstimate.trip_session_id == graph.trip.id
                )
            )
            calculation = await session.scalar(
                select(PayoutCalculation).where(
                    PayoutCalculation.trip_session_id == graph.trip.id
                )
            )
            assert analytics.computed_at == frozen_now
            assert flags
            assert all(flag.detected_at == frozen_now for flag in flags)
            assert estimate.estimated_at == frozen_now
            assert calculation.calculated_at == frozen_now
            await session.commit()

    asyncio.run(run())


def test_idempotent_repeat_creates_no_new_rows(postgis_db_sessionmaker, settings) -> None:
    graph = build_graph(postgis_db_sessionmaker, "idem")
    create_test_payout_rule(
        postgis_db_sessionmaker,
        campaign_id=graph.campaign.id,
        created_by_user_id=graph.admin.id,
        base_rate_per_km=10,
    )
    add_pings(postgis_db_sessionmaker, trip_id=graph.trip.id, points=moving_points())

    run_pipeline(postgis_db_sessionmaker, graph.trip.id, settings)
    counts_before = table_counts(postgis_db_sessionmaker)
    second = run_pipeline(postgis_db_sessionmaker, graph.trip.id, settings)

    assert second.overall == "completed"
    assert stage_outcomes(second) == {
        "analytics": "reused",
        "fraud_assessment": "reused",
        "impressions": "reused",
        "payout": "reused",
    }
    assert table_counts(postgis_db_sessionmaker) == counts_before
    assert len(worker_audit_events(postgis_db_sessionmaker)) == 1


def test_preexisting_analytics_is_reused(db_sessionmaker, settings) -> None:
    graph = build_graph(db_sessionmaker, "reuse-ana")
    create_test_payout_rule(
        db_sessionmaker,
        campaign_id=graph.campaign.id,
        created_by_user_id=graph.admin.id,
        base_rate_per_km=10,
    )
    analytics = seed_analytics(db_sessionmaker, graph)

    result = run_pipeline(db_sessionmaker, graph.trip.id, settings)

    assert result.overall == "completed"
    assert stage_outcomes(result) == {
        "analytics": "reused",
        "fraud_assessment": "created",
        "impressions": "created",
        "payout": "created",
    }
    assert result.stages[0].row_ids == {"trip_analytics_id": str(analytics.id)}
    counts = table_counts(db_sessionmaker)
    assert counts["analytics"] == 1
    assert counts["estimates"] == 1
    assert counts["calculations"] == 1
    assert counts["ledger"] == 1
    assert len(worker_audit_events(db_sessionmaker)) == 1


def test_assessment_error_stays_due_and_retry_converges(
    db_sessionmaker,
    settings,
    monkeypatch,
) -> None:
    graph = build_graph(db_sessionmaker, "assessment-retry")
    create_test_payout_rule(
        db_sessionmaker,
        campaign_id=graph.campaign.id,
        created_by_user_id=graph.admin.id,
        base_rate_per_km=10,
    )
    seed_analytics(db_sessionmaker, graph)
    original = fraud_assessments.assessment_inputs_fingerprint

    def fail_fingerprint(**_kwargs):
        raise RuntimeError("synthetic assessment failure")

    monkeypatch.setattr(
        fraud_assessments,
        "assessment_inputs_fingerprint",
        fail_fingerprint,
    )
    first = run_pipeline(db_sessionmaker, graph.trip.id, settings)
    assert first.overall == "partial"
    assert stage_outcomes(first)["fraud_assessment"] == "blocked"
    assert find_due(db_sessionmaker, settings) == [graph.trip.id]

    monkeypatch.setattr(
        fraud_assessments,
        "assessment_inputs_fingerprint",
        original,
    )
    second = run_pipeline(db_sessionmaker, graph.trip.id, settings)
    assert second.overall == "completed"
    assert stage_outcomes(second)["fraud_assessment"] == "created"
    assert find_due(db_sessionmaker, settings) == []


def test_replay_detector_error_marks_assessment_error_until_retry(
    db_sessionmaker,
    settings,
    monkeypatch,
) -> None:
    graph = build_graph(db_sessionmaker, "replay-error")
    seed_analytics(db_sessionmaker, graph, distance_m=Decimal("5000"))
    points = [
        (
            BASE_TIME + timedelta(minutes=index),
            6.45 + index * 0.0005,
            3.39 + index * 0.0005,
            10,
        )
        for index in range(settings.route_replay_min_valid_pings)
    ]
    add_pings(db_sessionmaker, trip_id=graph.trip.id, points=points)
    original = route_replay.canonical_route_fingerprints

    def fail_route_fingerprint(*_args, **_kwargs):
        raise RuntimeError("private replay evaluation failure")

    monkeypatch.setattr(
        route_replay,
        "canonical_route_fingerprints",
        fail_route_fingerprint,
    )
    first = run_pipeline(db_sessionmaker, graph.trip.id, settings)
    assert first.overall == "partial"
    assert stage_outcomes(first)["fraud_assessment"] == "blocked"
    assert first.stages[1].reason == "route_replay_evaluation_failed"
    assert find_due(db_sessionmaker, settings) == [graph.trip.id]

    monkeypatch.setattr(route_replay, "canonical_route_fingerprints", original)
    second = run_pipeline(db_sessionmaker, graph.trip.id, settings)
    assert stage_outcomes(second)["fraud_assessment"] == "created"
    assert find_due(db_sessionmaker, settings) == []


def test_time_shifted_cross_account_route_flags_latest_assessment(
    postgis_db_sessionmaker,
    settings,
) -> None:
    earlier = build_graph(
        postgis_db_sessionmaker,
        "replay-earlier",
        started_at=BASE_TIME,
        ended_at=BASE_TIME + timedelta(minutes=30),
    )
    later = build_graph(
        postgis_db_sessionmaker,
        "replay-later",
        started_at=BASE_TIME + timedelta(hours=2),
        ended_at=BASE_TIME + timedelta(hours=2, minutes=30),
    )

    def route(shift: timedelta) -> list[tuple[datetime, float, float, float]]:
        return [
            (
                BASE_TIME + shift + timedelta(minutes=index),
                6.45 + index * 0.0005,
                3.39 + index * 0.0005,
                10,
            )
            for index in range(settings.route_replay_min_valid_pings)
        ]

    add_pings(
        postgis_db_sessionmaker,
        trip_id=earlier.trip.id,
        points=route(timedelta(0)),
        idempotency_key="replay-earlier",
    )
    add_pings(
        postgis_db_sessionmaker,
        trip_id=later.trip.id,
        points=route(timedelta(hours=2)),
        idempotency_key="replay-later",
    )

    first = run_pipeline(postgis_db_sessionmaker, earlier.trip.id, settings)
    second = run_pipeline(postgis_db_sessionmaker, later.trip.id, settings)

    async def inspect():
        async with postgis_db_sessionmaker() as session:
            assessment = await session.scalar(
                select(FraudAssessment).where(
                    FraudAssessment.trip_session_id == later.trip.id
                )
            )
            flag = await session.scalar(
                select(FraudFlag).where(
                    FraudFlag.trip_session_id == later.trip.id,
                    FraudFlag.flag_type == FraudFlagType.ROUTE_REPLAY.value,
                )
            )
            return assessment, flag

    assessment, flag = asyncio.run(inspect())
    assert stage_outcomes(first)["fraud_assessment"] == "created"
    assert stage_outcomes(second)["fraud_assessment"] == "created"
    assert assessment.status == FraudAssessmentStatus.FLAGGED.value
    assert flag.evidence["match_kind"] == "time_shifted"
    assert flag.evidence["cross_account_match_count"] == 1
    assert find_due(postgis_db_sessionmaker, settings) == []


def test_preexisting_explicit_profile_estimate_is_reused(db_sessionmaker, settings) -> None:
    graph = build_graph(db_sessionmaker, "reuse-est")
    create_test_payout_rule(
        db_sessionmaker,
        campaign_id=graph.campaign.id,
        created_by_user_id=graph.admin.id,
        base_rate_per_km=10,
    )
    analytics = seed_analytics(db_sessionmaker, graph)
    explicit_profile = create_test_traffic_density_profile(
        db_sessionmaker,
        name="Explicit Corridor",
        profile_type="custom",
    )
    estimate = create_test_impression_estimate(
        db_sessionmaker,
        trip_session_id=graph.trip.id,
        trip_analytics_id=analytics.id,
        assignment_id=graph.assignment.id,
        campaign_id=graph.campaign.id,
        driver_profile_id=graph.profile.id,
        vehicle_id=graph.vehicle.id,
        traffic_density_profile_id=explicit_profile.id,
        estimated_impressions=Decimal("1000"),
    )

    result = run_pipeline(db_sessionmaker, graph.trip.id, settings)

    assert stage_outcomes(result) == {
        "analytics": "reused",
        "fraud_assessment": "created",
        "impressions": "reused",
        "payout": "created",
    }
    estimates = fetch_impression_estimates(db_sessionmaker)
    assert len(estimates) == 1
    assert estimates[0].id == estimate.id
    calculation = fetch_payout_calculations(db_sessionmaker)[0]
    assert calculation.impression_estimate_id == estimate.id


def test_preexisting_payout_calculation_is_reused_and_ledger_ensured(
    db_sessionmaker,
    settings,
) -> None:
    graph = build_graph(db_sessionmaker, "reuse-pay")
    create_test_payout_rule(
        db_sessionmaker,
        campaign_id=graph.campaign.id,
        created_by_user_id=graph.admin.id,
        base_rate_per_km=10,
    )
    analytics = seed_analytics(db_sessionmaker, graph)
    profile = create_test_traffic_density_profile(db_sessionmaker, name="Reuse Profile")
    create_test_impression_estimate(
        db_sessionmaker,
        trip_session_id=graph.trip.id,
        trip_analytics_id=analytics.id,
        assignment_id=graph.assignment.id,
        campaign_id=graph.campaign.id,
        driver_profile_id=graph.profile.id,
        vehicle_id=graph.vehicle.id,
        traffic_density_profile_id=profile.id,
        estimated_impressions=Decimal("1000"),
    )

    async def admin_calculate() -> None:
        async with db_sessionmaker() as session:
            await calculate_trip_payout(
                session,
                trip_id=graph.trip.id,
                payout_rule_id=None,
                metadata={"source": "admin"},
                settings=settings,
            )
            await session.commit()

    asyncio.run(admin_calculate())

    async def drop_ledger() -> None:
        async with db_sessionmaker() as session:
            await session.execute(delete(EarningsLedgerEntry))
            await session.commit()

    asyncio.run(drop_ledger())

    result = run_pipeline(db_sessionmaker, graph.trip.id, settings)

    assert result.overall == "completed"
    assert stage_outcomes(result) == {
        "ledger_repair": "created",
        "analytics": "reused",
        "fraud_assessment": "created",
        "impressions": "reused",
        "payout": "reused",
    }
    counts = table_counts(db_sessionmaker)
    assert counts["calculations"] == 1
    assert counts["ledger"] == 1
    # Ledger creation alone (calculation reused) must still be audited: money moved.
    assert len(worker_audit_events(db_sessionmaker)) == 1


def test_repairs_every_missing_ledger_before_stale_analytics_gate(
    db_sessionmaker,
    settings,
) -> None:
    graph = build_graph(db_sessionmaker, "repair-all")
    analytics = seed_analytics(db_sessionmaker, graph)
    profile = create_test_traffic_density_profile(db_sessionmaker, name="Repair Profile")
    create_test_impression_estimate(
        db_sessionmaker,
        trip_session_id=graph.trip.id,
        trip_analytics_id=analytics.id,
        assignment_id=graph.assignment.id,
        campaign_id=graph.campaign.id,
        driver_profile_id=graph.profile.id,
        vehicle_id=graph.vehicle.id,
        traffic_density_profile_id=profile.id,
        estimated_impressions=Decimal("1000"),
    )
    first_rule = create_test_payout_rule(
        db_sessionmaker,
        campaign_id=graph.campaign.id,
        created_by_user_id=graph.admin.id,
        base_rate_per_km=10,
    )

    async def create_first_calculation_and_deactivate_rule() -> None:
        async with db_sessionmaker() as session:
            await calculate_trip_payout(
                session,
                trip_id=graph.trip.id,
                payout_rule_id=first_rule.id,
                metadata={"source": "test"},
                settings=settings,
            )
            await session.commit()
        async with db_sessionmaker() as session:
            stored_first_rule = await session.get(CampaignPayoutRule, first_rule.id)
            stored_first_rule.status = "inactive"
            await session.commit()

    asyncio.run(create_first_calculation_and_deactivate_rule())
    second_rule = create_test_payout_rule(
        db_sessionmaker,
        campaign_id=graph.campaign.id,
        created_by_user_id=graph.admin.id,
        base_rate_per_km=12,
    )

    async def create_second_calculation_then_break_chain() -> None:
        async with db_sessionmaker() as session:
            await calculate_trip_payout(
                session,
                trip_id=graph.trip.id,
                payout_rule_id=second_rule.id,
                metadata={"source": "test"},
                settings=settings,
            )
            await session.commit()
        async with db_sessionmaker() as session:
            stored_analytics = await session.get(TripAnalytics, analytics.id)
            stored_analytics.formula_version = "route_analytics_v0"
            await session.execute(delete(EarningsLedgerEntry))
            await session.commit()

    asyncio.run(create_second_calculation_then_break_chain())

    assert find_due(db_sessionmaker, settings) == [graph.trip.id]
    result = run_pipeline(db_sessionmaker, graph.trip.id, settings)

    assert result.overall == "blocked"
    assert stage_outcomes(result) == {
        "ledger_repair": "created",
        "analytics": "blocked",
        "fraud_assessment": "skipped",
        "impressions": "skipped",
        "payout": "skipped",
    }
    # One trip_payout entry per trip across calculations (0013 guard): the
    # older calculation's entry is repaired, the second is skipped instead of
    # double-paying the same trip under a superseded rule.
    entries = fetch_earnings_ledger_entries(db_sessionmaker)
    assert len(entries) == 1
    events = worker_audit_events(db_sessionmaker)
    assert len(events) == 1
    assert len(events[0].event_metadata["repaired_ledger_entry_ids"]) == 1
    assert find_due(db_sessionmaker, settings) == []


def test_stale_analytics_is_blocked_in_worker_and_shared_services(
    db_sessionmaker,
    settings,
) -> None:
    graph = build_graph(db_sessionmaker, "stale-formula")
    analytics = create_test_trip_analytics(
        db_sessionmaker,
        trip_session_id=graph.trip.id,
        assignment_id=graph.assignment.id,
        campaign_id=graph.campaign.id,
        driver_profile_id=graph.profile.id,
        vehicle_id=graph.vehicle.id,
        formula_version="route_analytics_v0",
        started_at=BASE_TIME,
        ended_at=BASE_TIME + timedelta(minutes=30),
        distance_m=5000,
    )
    profile = create_test_traffic_density_profile(db_sessionmaker, name="Stale Profile")
    create_test_impression_estimate(
        db_sessionmaker,
        trip_session_id=graph.trip.id,
        trip_analytics_id=analytics.id,
        assignment_id=graph.assignment.id,
        campaign_id=graph.campaign.id,
        driver_profile_id=graph.profile.id,
        vehicle_id=graph.vehicle.id,
        traffic_density_profile_id=profile.id,
        metadata={"source_analytics_formula_version": "route_analytics_v0"},
    )
    create_test_payout_rule(
        db_sessionmaker,
        campaign_id=graph.campaign.id,
        created_by_user_id=graph.admin.id,
        base_rate_per_km=10,
    )

    result = run_pipeline(db_sessionmaker, graph.trip.id, settings)

    assert result.overall == "blocked"
    assert stage_outcomes(result) == {
        "analytics": "blocked",
        "fraud_assessment": "skipped",
        "impressions": "skipped",
        "payout": "skipped",
    }
    assert find_due(db_sessionmaker, settings) == []

    from app.services.impressions import estimate_trip_impressions

    async def direct_calls() -> None:
        async with db_sessionmaker() as session:
            with pytest.raises(AppError) as estimate_error:
                await estimate_trip_impressions(
                    session,
                    trip_id=graph.trip.id,
                    traffic_density_profile_id=None,
                    metadata={"source": "admin"},
                    settings=settings,
                )
            assert estimate_error.value.code == "ANALYTICS_FORMULA_VERSION_MISMATCH"
            with pytest.raises(AppError) as payout_error:
                await calculate_trip_payout(
                    session,
                    trip_id=graph.trip.id,
                    payout_rule_id=None,
                    metadata={"source": "admin"},
                    settings=settings,
                )
            assert payout_error.value.code == "ANALYTICS_FORMULA_VERSION_MISMATCH"

    asyncio.run(direct_calls())


def test_admin_downstream_endpoints_reject_stale_analytics(db_client, db_sessionmaker) -> None:
    graph = build_graph(db_sessionmaker, "stale-admin")
    create_test_trip_analytics(
        db_sessionmaker,
        trip_session_id=graph.trip.id,
        assignment_id=graph.assignment.id,
        campaign_id=graph.campaign.id,
        driver_profile_id=graph.profile.id,
        vehicle_id=graph.vehicle.id,
        formula_version="route_analytics_v0",
        started_at=BASE_TIME,
        ended_at=BASE_TIME + timedelta(minutes=30),
    )
    login = db_client.post(
        "/api/v1/auth/login",
        json={"email": graph.admin.email, "password": PASSWORD},
    )
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    estimate = db_client.post(
        f"/api/v1/admin/trips/{graph.trip.id}/estimate-impressions",
        headers=headers,
    )
    payout = db_client.post(
        f"/api/v1/admin/trips/{graph.trip.id}/calculate-payout",
        headers=headers,
    )

    assert estimate.status_code == 409
    assert estimate.json()["error"]["code"] == "ANALYTICS_FORMULA_VERSION_MISMATCH"
    assert payout.status_code == 409
    assert payout.json()["error"]["code"] == "ANALYTICS_FORMULA_VERSION_MISMATCH"


def test_changed_analytics_requires_estimate_refresh_and_new_payout_version(
    db_sessionmaker,
    settings,
) -> None:
    graph = build_graph(db_sessionmaker, "source-refresh")
    analytics = seed_analytics(db_sessionmaker, graph)
    create_test_payout_rule(
        db_sessionmaker,
        campaign_id=graph.campaign.id,
        created_by_user_id=graph.admin.id,
        base_rate_per_km=10,
    )
    run_pipeline(db_sessionmaker, graph.trip.id, settings)

    async def mutate_and_verify() -> None:
        from app.services.impressions import estimate_trip_impressions
        from app.services.trip_analytics import analytics_output_fingerprint

        async with db_sessionmaker() as session:
            stored_analytics = await session.get(TripAnalytics, analytics.id)
            stored_analytics.distance_m = Decimal("9000")
            metadata = dict(stored_analytics.analytics_metadata)
            metadata["output_fingerprint"] = analytics_output_fingerprint(stored_analytics)
            stored_analytics.analytics_metadata = metadata
            await session.commit()
        async with db_sessionmaker() as session:
            with pytest.raises(AppError) as stale_estimate:
                await calculate_trip_payout(
                    session,
                    trip_id=graph.trip.id,
                    payout_rule_id=None,
                    metadata={"source": "admin"},
                    settings=settings,
                )
            assert stale_estimate.value.code == "IMPRESSION_ESTIMATE_STALE"
            await session.rollback()
        async with db_sessionmaker() as session:
            await estimate_trip_impressions(
                session,
                trip_id=graph.trip.id,
                traffic_density_profile_id=None,
                metadata={"source": "admin"},
                settings=settings,
            )
            with pytest.raises(AppError) as stale_payout:
                await calculate_trip_payout(
                    session,
                    trip_id=graph.trip.id,
                    payout_rule_id=None,
                    metadata={"source": "admin"},
                    settings=settings,
                )
            assert stale_payout.value.code == "PAYOUT_CALCULATION_STALE"
            await session.rollback()

    asyncio.run(mutate_and_verify())
    assert find_due(db_sessionmaker, settings) == [graph.trip.id]


def test_formula_only_estimate_provenance_still_requires_timestamp_order(
    db_sessionmaker,
    settings,
) -> None:
    graph = build_graph(db_sessionmaker, "estimate-formula-time")
    analytics = create_test_trip_analytics(
        db_sessionmaker,
        trip_session_id=graph.trip.id,
        assignment_id=graph.assignment.id,
        campaign_id=graph.campaign.id,
        driver_profile_id=graph.profile.id,
        vehicle_id=graph.vehicle.id,
        started_at=BASE_TIME,
        ended_at=BASE_TIME + timedelta(minutes=30),
        computed_at=BASE_TIME + timedelta(hours=2),
    )
    profile = create_test_traffic_density_profile(db_sessionmaker, name="Formula-only")
    create_test_impression_estimate(
        db_sessionmaker,
        trip_session_id=graph.trip.id,
        trip_analytics_id=analytics.id,
        assignment_id=graph.assignment.id,
        campaign_id=graph.campaign.id,
        driver_profile_id=graph.profile.id,
        vehicle_id=graph.vehicle.id,
        traffic_density_profile_id=profile.id,
        estimated_at=BASE_TIME + timedelta(hours=1),
        metadata={
            "source_analytics_formula_version": settings.route_analytics_formula_version,
            "fraud_flag_counts": {"low": 0, "medium": 0, "high": 0},
        },
    )
    create_test_payout_rule(
        db_sessionmaker,
        campaign_id=graph.campaign.id,
        created_by_user_id=graph.admin.id,
        base_rate_per_km=10,
    )

    async def calculate() -> None:
        async with db_sessionmaker() as session:
            with pytest.raises(AppError) as exc_info:
                await calculate_trip_payout(
                    session,
                    trip_id=graph.trip.id,
                    payout_rule_id=None,
                    metadata={"source": "test"},
                    settings=settings,
                )
            assert exc_info.value.code == "IMPRESSION_ESTIMATE_STALE"

    asyncio.run(calculate())
    assert find_due(db_sessionmaker, settings) == [graph.trip.id]


def test_formula_only_payout_provenance_still_requires_timestamp_order(
    db_sessionmaker,
    settings,
) -> None:
    graph = build_graph(db_sessionmaker, "payout-formula-time")
    seed_analytics(db_sessionmaker, graph)
    create_test_payout_rule(
        db_sessionmaker,
        campaign_id=graph.campaign.id,
        created_by_user_id=graph.admin.id,
        base_rate_per_km=10,
    )
    run_pipeline(db_sessionmaker, graph.trip.id, settings)

    async def make_formula_only_and_stale() -> None:
        async with db_sessionmaker() as session:
            calculation = await session.scalar(select(PayoutCalculation))
            estimate = await session.scalar(select(ImpressionEstimate))
            metadata = dict(calculation.payout_metadata)
            metadata.pop("source_analytics_fingerprint", None)
            metadata.pop("source_impression_fingerprint", None)
            calculation.payout_metadata = metadata
            estimate.estimated_at = calculation.calculated_at + timedelta(seconds=1)
            await session.commit()
        async with db_sessionmaker() as session:
            with pytest.raises(AppError) as exc_info:
                await calculate_trip_payout(
                    session,
                    trip_id=graph.trip.id,
                    payout_rule_id=None,
                    metadata={"source": "test"},
                    settings=settings,
                )
            assert exc_info.value.code == "PAYOUT_CALCULATION_STALE"

    asyncio.run(make_formula_only_and_stale())
    assert find_due(db_sessionmaker, settings) == [graph.trip.id]


def test_review_status_changes_refresh_assessment_and_dismissal_refreshes_money_inputs(
    db_sessionmaker,
    settings,
) -> None:
    graph = build_graph(db_sessionmaker, "fraud-refresh")
    analytics = seed_analytics(db_sessionmaker, graph)

    async def add_high_flag() -> None:
        async with db_sessionmaker() as session:
            session.add(
                FraudFlag(
                    trip_session_id=graph.trip.id,
                    trip_analytics_id=analytics.id,
                    assignment_id=graph.assignment.id,
                    campaign_id=graph.campaign.id,
                    driver_profile_id=graph.profile.id,
                    vehicle_id=graph.vehicle.id,
                    flag_type="impossible_speed",
                    severity="high",
                    status=FraudFlagStatus.OPEN.value,
                    description="test high flag",
                    evidence={},
                    detected_at=analytics.computed_at,
                )
            )
            await session.commit()

    asyncio.run(add_high_flag())
    first = run_pipeline(db_sessionmaker, graph.trip.id, settings)
    assert first.overall == "partial"
    first_estimate = fetch_impression_estimates(db_sessionmaker)[0]
    first_fingerprint = first_estimate.estimate_metadata["output_fingerprint"]
    assert first_estimate.fraud_adjustment_multiplier == Decimal("0.2500")

    async def acknowledge_flag() -> None:
        async with db_sessionmaker() as session:
            flag = await session.scalar(select(FraudFlag))
            await acknowledge_fraud_flag(
                session,
                flag_id=flag.id,
                actor_user_id=graph.admin.id,
                now=BASE_TIME + timedelta(hours=1),
            )
            await session.commit()

    asyncio.run(acknowledge_flag())
    assert find_due(db_sessionmaker, settings) == [graph.trip.id]

    acknowledged = run_pipeline(db_sessionmaker, graph.trip.id, settings)
    still_held = fetch_impression_estimates(db_sessionmaker)[0]
    assert stage_outcomes(acknowledged)["fraud_assessment"] == "created"
    assert still_held.fraud_adjustment_multiplier == Decimal("0.2500")
    assert find_due(db_sessionmaker, settings) == []

    async def dismiss_flag() -> None:
        async with db_sessionmaker() as session:
            flag = await session.scalar(select(FraudFlag))
            await resolve_fraud_flag(
                session,
                flag_id=flag.id,
                actor_user_id=graph.admin.id,
                outcome=FraudFlagStatus.DISMISSED.value,
                resolution_note="Detector evidence was not fraudulent.",
                now=BASE_TIME + timedelta(hours=2),
            )
            await session.commit()

    asyncio.run(dismiss_flag())
    assert find_due(db_sessionmaker, settings) == [graph.trip.id]

    second = run_pipeline(db_sessionmaker, graph.trip.id, settings)
    refreshed = fetch_impression_estimates(db_sessionmaker)[0]
    assert second.overall == "partial"
    assert stage_outcomes(second)["impressions"] == "created"
    assert refreshed.fraud_adjustment_multiplier == Decimal("1.0000")
    assert refreshed.estimate_metadata["fraud_flag_counts"] == {
        "low": 0,
        "medium": 0,
        "high": 0,
    }
    assert refreshed.estimate_metadata["output_fingerprint"] != first_fingerprint


def test_confirmed_review_transition_is_due_but_remains_held(
    db_sessionmaker,
    settings,
) -> None:
    graph = build_graph(db_sessionmaker, "fraud-confirmed-due")
    analytics = seed_analytics(db_sessionmaker, graph)

    async def add_flag() -> None:
        async with db_sessionmaker() as session:
            session.add(
                FraudFlag(
                    trip_session_id=graph.trip.id,
                    trip_analytics_id=analytics.id,
                    assignment_id=graph.assignment.id,
                    campaign_id=graph.campaign.id,
                    driver_profile_id=graph.profile.id,
                    vehicle_id=graph.vehicle.id,
                    flag_type="impossible_speed",
                    severity="high",
                    status=FraudFlagStatus.OPEN.value,
                    description="test high flag",
                    evidence={},
                    detected_at=analytics.computed_at,
                )
            )
            await session.commit()

    asyncio.run(add_flag())
    run_pipeline(db_sessionmaker, graph.trip.id, settings)

    async def transition(*, confirm: bool) -> None:
        async with db_sessionmaker() as session:
            flag = await session.scalar(select(FraudFlag))
            if confirm:
                await resolve_fraud_flag(
                    session,
                    flag_id=flag.id,
                    actor_user_id=graph.admin.id,
                    outcome=FraudFlagStatus.CONFIRMED.value,
                    resolution_note="Fraud evidence confirmed.",
                    now=BASE_TIME + timedelta(hours=2),
                )
            else:
                await acknowledge_fraud_flag(
                    session,
                    flag_id=flag.id,
                    actor_user_id=graph.admin.id,
                    now=BASE_TIME + timedelta(hours=1),
                )
            await session.commit()

    asyncio.run(transition(confirm=False))
    run_pipeline(db_sessionmaker, graph.trip.id, settings)
    asyncio.run(transition(confirm=True))
    assert find_due(db_sessionmaker, settings) == [graph.trip.id]

    confirmed = run_pipeline(db_sessionmaker, graph.trip.id, settings)
    estimate = fetch_impression_estimates(db_sessionmaker)[0]
    assert stage_outcomes(confirmed)["fraud_assessment"] == "created"
    assert estimate.fraud_adjustment_multiplier == Decimal("0.2500")
    assert estimate.estimate_metadata["fraud_flag_counts"] == {
        "low": 0,
        "medium": 0,
        "high": 1,
    }
    assert find_due(db_sessionmaker, settings) == []


def test_injected_processing_time_stamps_downstream_rows(db_sessionmaker, settings) -> None:
    graph = build_graph(db_sessionmaker, "clock")
    seed_analytics(db_sessionmaker, graph)
    create_test_payout_rule(
        db_sessionmaker,
        campaign_id=graph.campaign.id,
        created_by_user_id=graph.admin.id,
        base_rate_per_km=10,
    )
    frozen_now = datetime(2026, 2, 3, 4, 5, tzinfo=UTC)

    async def run() -> None:
        async with db_sessionmaker() as session:
            await process_ended_trip(
                session,
                trip_id=graph.trip.id,
                settings=settings,
                now=frozen_now,
            )
            await session.commit()

    asyncio.run(run())

    estimate = fetch_impression_estimates(db_sessionmaker)[0]
    calculation = fetch_payout_calculations(db_sessionmaker)[0]
    assert estimate.estimated_at.replace(tzinfo=UTC) == frozen_now
    assert calculation.calculated_at.replace(tzinfo=UTC) == frozen_now


def test_missing_active_rule_blocks_payout_then_completes(
    postgis_db_sessionmaker,
    settings,
) -> None:
    graph = build_graph(postgis_db_sessionmaker, "norule")
    add_pings(postgis_db_sessionmaker, trip_id=graph.trip.id, points=moving_points())

    first = run_pipeline(postgis_db_sessionmaker, graph.trip.id, settings)

    assert first.overall == "partial"
    assert stage_outcomes(first) == {
        "analytics": "created",
        "fraud_assessment": "created",
        "impressions": "created",
        "payout": "blocked",
    }
    assert first.stages[3].reason == "no_active_payout_rule"
    counts = table_counts(postgis_db_sessionmaker)
    assert counts["analytics"] == 1
    assert counts["estimates"] == 1
    assert counts["calculations"] == 0
    assert counts["ledger"] == 0
    assert len(worker_audit_events(postgis_db_sessionmaker)) == 1

    create_test_payout_rule(
        postgis_db_sessionmaker,
        campaign_id=graph.campaign.id,
        created_by_user_id=graph.admin.id,
        base_rate_per_km=10,
    )
    second = run_pipeline(postgis_db_sessionmaker, graph.trip.id, settings)

    assert second.overall == "completed"
    assert stage_outcomes(second) == {
        "analytics": "reused",
        "fraud_assessment": "reused",
        "impressions": "reused",
        "payout": "created",
    }
    counts = table_counts(postgis_db_sessionmaker)
    assert counts["calculations"] == 1
    assert counts["ledger"] == 1
    assert len(worker_audit_events(postgis_db_sessionmaker)) == 2


def test_insufficient_data_terminates_with_zero_payout(postgis_db_sessionmaker, settings) -> None:
    graph = build_graph(postgis_db_sessionmaker, "insuff")
    create_test_payout_rule(
        postgis_db_sessionmaker,
        campaign_id=graph.campaign.id,
        created_by_user_id=graph.admin.id,
        base_rate_per_km=10,
    )
    add_pings(
        postgis_db_sessionmaker,
        trip_id=graph.trip.id,
        points=[(BASE_TIME, 6.45, 3.39, 10)],
    )

    result = run_pipeline(postgis_db_sessionmaker, graph.trip.id, settings)

    assert result.overall == "completed"
    assert stage_outcomes(result) == {
        "analytics": "created",
        "fraud_assessment": "created",
        "impressions": "created",
        "payout": "created",
    }
    analytics_rows = table_counts(postgis_db_sessionmaker)
    assert analytics_rows["flags"] >= 1
    estimate = fetch_impression_estimates(postgis_db_sessionmaker)[0]
    assert estimate.status == "insufficient_data"
    calculation = fetch_payout_calculations(postgis_db_sessionmaker)[0]
    assert calculation.status == "insufficient_data"
    assert calculation.final_payout == 0
    assert fetch_earnings_ledger_entries(postgis_db_sessionmaker) == []
    assert len(worker_audit_events(postgis_db_sessionmaker)) == 1
    # Terminal: a current-formula payout row exists, so the sweep stops selecting it.
    async def still_due() -> list:
        async with postgis_db_sessionmaker() as session:
            return await find_unprocessed_trips(session, limit=10, settings=settings)

    assert asyncio.run(still_due()) == []


def test_blocked_analytics_produces_excluded_estimate_and_blocked_payout(
    db_sessionmaker,
    settings,
) -> None:
    graph = build_graph(db_sessionmaker, "blocked")
    create_test_payout_rule(
        db_sessionmaker,
        campaign_id=graph.campaign.id,
        created_by_user_id=graph.admin.id,
        base_rate_per_km=10,
    )
    seed_analytics(db_sessionmaker, graph, status="blocked")

    result = run_pipeline(db_sessionmaker, graph.trip.id, settings)

    assert result.overall == "completed"
    assert stage_outcomes(result) == {
        "analytics": "reused",
        "fraud_assessment": "created",
        "impressions": "created",
        "payout": "created",
    }
    estimate = fetch_impression_estimates(db_sessionmaker)[0]
    assert estimate.status == "excluded"
    calculation = fetch_payout_calculations(db_sessionmaker)[0]
    assert calculation.status == "blocked"
    assert calculation.final_payout == 0
    assert fetch_earnings_ledger_entries(db_sessionmaker) == []


def test_trip_not_found_and_trip_not_sealed(db_sessionmaker, settings) -> None:
    async def missing_trip() -> None:
        async with db_sessionmaker() as session:
            with pytest.raises(AppError) as exc_info:
                await process_ended_trip(session, trip_id=uuid4(), settings=settings)
            assert exc_info.value.code == "TRIP_NOT_FOUND"

    asyncio.run(missing_trip())

    graph = build_graph(
        db_sessionmaker,
        "active",
        trip_status=TripSessionStatus.ACTIVE,
        ended_at=None,
    )
    result = run_pipeline(db_sessionmaker, graph.trip.id, settings)

    assert result.overall == "blocked"
    assert result.stages[0].reason == "trip_not_sealed"
    counts = table_counts(db_sessionmaker)
    assert counts == {
        "analytics": 0,
        "assessments": 0,
        "replay_signatures": 0,
        "flags": 0,
        "estimates": 0,
        "calculations": 0,
        "ledger": 0,
    }
    assert worker_audit_events(db_sessionmaker) == []


def test_unexpected_failure_rolls_back_whole_run_then_retry_completes(
    postgis_db_sessionmaker,
    settings,
    monkeypatch,
) -> None:
    graph = build_graph(postgis_db_sessionmaker, "boom")
    create_test_payout_rule(
        postgis_db_sessionmaker,
        campaign_id=graph.campaign.id,
        created_by_user_id=graph.admin.id,
        base_rate_per_km=10,
    )
    add_pings(postgis_db_sessionmaker, trip_id=graph.trip.id, points=moving_points())

    async def boom(*args, **kwargs):
        raise RuntimeError("estimate stage exploded")

    with monkeypatch.context() as patch:
        patch.setattr(trip_processing, "estimate_trip_impressions", boom)

        async def failing_run() -> None:
            async with postgis_db_sessionmaker() as session:
                with pytest.raises(RuntimeError):
                    await process_ended_trip(session, trip_id=graph.trip.id, settings=settings)
                await session.rollback()

        asyncio.run(failing_run())

    counts = table_counts(postgis_db_sessionmaker)
    assert counts["analytics"] == 0
    assert counts["flags"] == 0
    assert counts["estimates"] == 0

    result = run_pipeline(postgis_db_sessionmaker, graph.trip.id, settings)

    assert result.overall == "completed"
    counts = table_counts(postgis_db_sessionmaker)
    assert counts["analytics"] == 1
    assert counts["estimates"] == 1
    assert counts["calculations"] == 1
    assert counts["ledger"] == 1


def test_analytics_savepoint_propagates_unexpected_check_failure(
    db_sessionmaker,
) -> None:
    from app.services.trip_analytics import upsert_analytics

    graph = build_graph(db_sessionmaker, "analytics-fk")

    async def exercise() -> None:
        async with db_sessionmaker() as session:
            trip = await session.get(type(graph.trip), graph.trip.id)
            with pytest.raises(IntegrityError):
                await upsert_analytics(
                    session,
                    trip=trip,
                    values={
                        "assignment_id": graph.assignment.id,
                        "campaign_id": graph.campaign.id,
                        "driver_profile_id": graph.profile.id,
                        "vehicle_id": graph.vehicle.id,
                        "formula_version": "route_analytics_v1",
                        "status": "computed",
                        "ping_count": 2,
                        "valid_ping_count": 2,
                        "invalid_ping_count": 0,
                        "duration_seconds": 0,
                        "active_tracking_seconds": 0,
                        "moving_seconds": 0,
                        "stationary_seconds": 0,
                        "distance_m": 0,
                        "poor_accuracy_ping_count": 0,
                        "target_zone_distance_m": 0,
                        "bonus_zone_distance_m": 0,
                        "exclusion_zone_distance_m": 0,
                        "target_zone_seconds": 0,
                        "bonus_zone_seconds": 0,
                        "exclusion_zone_seconds": 0,
                        "quality_score": 2,
                        "computed_at": BASE_TIME,
                        "analytics_metadata": {},
                    },
                )
            assert await session.get(type(graph.trip), graph.trip.id) is not None

    asyncio.run(exercise())


def test_impression_savepoint_propagates_unexpected_check_failure(
    db_sessionmaker,
    settings,
    monkeypatch,
) -> None:
    from app.services import impressions

    graph = build_graph(db_sessionmaker, "estimate-check")
    seed_analytics(db_sessionmaker, graph)
    profile = create_test_traffic_density_profile(db_sessionmaker, name="Invalid Estimate")
    original_estimate_values = impressions.estimate_values

    def invalid_estimate_values(**kwargs):
        values = original_estimate_values(**kwargs)
        values["quality_multiplier"] = Decimal("2")
        return values

    monkeypatch.setattr(impressions, "estimate_values", invalid_estimate_values)

    async def exercise() -> None:
        async with db_sessionmaker() as session:
            with pytest.raises(IntegrityError):
                await impressions.estimate_trip_impressions(
                    session,
                    trip_id=graph.trip.id,
                    traffic_density_profile_id=profile.id,
                    metadata={"source": "test"},
                    settings=settings,
                )
            estimate_count = await session.scalar(
                select(func.count()).select_from(ImpressionEstimate)
            )
            assert estimate_count == 0

    asyncio.run(exercise())


def test_concurrent_runs_on_same_trip_never_duplicate(postgis_db_sessionmaker, settings) -> None:
    graph = build_graph(postgis_db_sessionmaker, "race")
    create_test_payout_rule(
        postgis_db_sessionmaker,
        campaign_id=graph.campaign.id,
        created_by_user_id=graph.admin.id,
        base_rate_per_km=10,
    )
    add_pings(postgis_db_sessionmaker, trip_id=graph.trip.id, points=moving_points())

    async def run_one() -> str:
        async with postgis_db_sessionmaker() as session:
            await process_ended_trip(session, trip_id=graph.trip.id, settings=settings)
            await session.commit()
            return "ok"

    async def race() -> list[str]:
        return list(await asyncio.gather(run_one(), run_one()))

    outcomes = asyncio.run(race())

    assert outcomes == ["ok", "ok"]
    counts = table_counts(postgis_db_sessionmaker)
    assert counts["analytics"] == 1
    assert counts["assessments"] == 1
    assert counts["estimates"] == 1
    assert counts["calculations"] == 1
    assert counts["ledger"] == 1


def test_concurrent_assessment_creation_with_existing_analytics_converges(
    postgis_db_sessionmaker,
    settings,
) -> None:
    graph = build_graph(postgis_db_sessionmaker, "assessment-race")
    seed_analytics(postgis_db_sessionmaker, graph)

    async def run_one() -> str:
        async with postgis_db_sessionmaker() as session:
            await process_ended_trip(session, trip_id=graph.trip.id, settings=settings)
            await session.commit()
            return "ok"

    async def race() -> list[str]:
        return list(await asyncio.gather(run_one(), run_one()))

    assert asyncio.run(race()) == ["ok", "ok"]
    counts = table_counts(postgis_db_sessionmaker)
    assert counts["analytics"] == 1
    assert counts["assessments"] == 1


def test_concurrent_runs_on_different_trips_both_complete(
    postgis_db_sessionmaker,
    settings,
) -> None:
    graph_a = build_graph(postgis_db_sessionmaker, "par-a")
    graph_b = build_graph(postgis_db_sessionmaker, "par-b")
    for graph in (graph_a, graph_b):
        create_test_payout_rule(
            postgis_db_sessionmaker,
            campaign_id=graph.campaign.id,
            created_by_user_id=graph.admin.id,
            base_rate_per_km=10,
        )
    add_pings(
        postgis_db_sessionmaker,
        trip_id=graph_a.trip.id,
        points=moving_points(),
        idempotency_key="par-a",
    )
    add_pings(
        postgis_db_sessionmaker,
        trip_id=graph_b.trip.id,
        points=moving_points(),
        idempotency_key="par-b",
    )

    async def run_one(trip_id) -> str:
        async with postgis_db_sessionmaker() as session:
            result = await process_ended_trip(session, trip_id=trip_id, settings=settings)
            await session.commit()
            return result.overall

    async def race() -> list[str]:
        return list(await asyncio.gather(run_one(graph_a.trip.id), run_one(graph_b.trip.id)))

    assert asyncio.run(race()) == ["completed", "completed"]
    counts = table_counts(postgis_db_sessionmaker)
    assert counts["analytics"] == 2
    assert counts["estimates"] == 2
    assert counts["calculations"] == 2
    assert counts["ledger"] == 2


def test_admin_and_worker_race_keeps_single_consistent_chain(
    postgis_db_sessionmaker,
    settings,
) -> None:
    graph = build_graph(postgis_db_sessionmaker, "admin-race")
    create_test_payout_rule(
        postgis_db_sessionmaker,
        campaign_id=graph.campaign.id,
        created_by_user_id=graph.admin.id,
        base_rate_per_km=10,
    )
    add_pings(postgis_db_sessionmaker, trip_id=graph.trip.id, points=moving_points())

    from app.services.impressions import estimate_trip_impressions
    from app.services.trip_analytics import recompute_trip_analytics

    async def worker_run() -> str:
        async with postgis_db_sessionmaker() as session:
            await process_ended_trip(session, trip_id=graph.trip.id, settings=settings)
            await session.commit()
            return "ok"

    async def admin_run() -> str:
        async with postgis_db_sessionmaker() as session:
            await recompute_trip_analytics(
                session,
                trip_id=graph.trip.id,
                metadata={"source": "admin"},
                settings=settings,
            )
            await estimate_trip_impressions(
                session,
                trip_id=graph.trip.id,
                traffic_density_profile_id=None,
                metadata={"source": "admin"},
                settings=settings,
            )
            await calculate_trip_payout(
                session,
                trip_id=graph.trip.id,
                payout_rule_id=None,
                metadata={"source": "admin"},
                settings=settings,
            )
            await session.commit()
            return "ok"

    async def race() -> list[str]:
        return list(await asyncio.gather(worker_run(), admin_run()))

    outcomes = asyncio.run(race())

    assert outcomes == ["ok", "ok"]
    counts = table_counts(postgis_db_sessionmaker)
    assert counts["analytics"] == 1
    assert counts["estimates"] == 1
    assert counts["calculations"] == 1
    assert counts["ledger"] == 1
    calculation = fetch_payout_calculations(postgis_db_sessionmaker)[0]
    ledger = fetch_earnings_ledger_entries(postgis_db_sessionmaker)[0]
    assert ledger.amount == calculation.final_payout
    assert ledger.payout_calculation_id == calculation.id


def find_due(db_sessionmaker, settings, *, limit: int = 10) -> list:
    async def fetch() -> list:
        async with db_sessionmaker() as session:
            return await find_unprocessed_trips(session, limit=limit, settings=settings)

    return asyncio.run(fetch())


def test_due_work_selects_unprocessed_and_skips_active(db_sessionmaker, settings) -> None:
    graph = build_graph(db_sessionmaker, "due1")
    create_test_trip_session(
        db_sessionmaker,
        assignment_id=graph.assignment.id,
        campaign_id=graph.campaign.id,
        driver_profile_id=graph.profile.id,
        vehicle_id=graph.vehicle.id,
        started_by_user_id=graph.driver.id,
        trip_status=TripSessionStatus.ACTIVE,
        started_at=BASE_TIME,
        ended_at=None,
    )

    assert find_due(db_sessionmaker, settings) == [graph.trip.id]


def test_due_work_excludes_fully_processed_trip(db_sessionmaker, settings) -> None:
    graph = build_graph(db_sessionmaker, "due2")
    create_test_payout_rule(
        db_sessionmaker,
        campaign_id=graph.campaign.id,
        created_by_user_id=graph.admin.id,
        base_rate_per_km=10,
    )
    seed_analytics(db_sessionmaker, graph)
    run_pipeline(db_sessionmaker, graph.trip.id, settings)

    assert find_due(db_sessionmaker, settings) == []


def test_profile_replacement_reissues_worker_estimate_and_blocks_stale_payout(
    db_sessionmaker,
    settings,
) -> None:
    graph = build_graph(db_sessionmaker, "profile-replacement")
    seed_analytics(db_sessionmaker, graph)
    run_pipeline(db_sessionmaker, graph.trip.id, settings)
    original = fetch_impression_estimates(db_sessionmaker)[0]

    async def replace_profile(profile_id) -> None:
        async with db_sessionmaker() as session:
            profile = await session.get(TrafficDensityProfile, profile_id)
            assert profile is not None
            await update_traffic_density_profile(
                session,
                profile_id=profile.id,
                payload=TrafficDensityProfileUpdate(
                    description="Replacement profile",
                    expected_revision=profile.revision,
                    expected_value_fingerprint=profile.value_fingerprint,
                ),
            )
            await session.commit()

    asyncio.run(replace_profile(original.traffic_density_profile_id))

    assert find_due(db_sessionmaker, settings) == [graph.trip.id]
    result = run_pipeline(db_sessionmaker, graph.trip.id, settings)
    assert stage_outcomes(result)["impressions"] == "created"
    estimates = fetch_impression_estimates(db_sessionmaker)
    assert len(estimates) == 2
    assert sum(estimate.is_authoritative for estimate in estimates) == 1

    current = next(estimate for estimate in estimates if estimate.is_authoritative)
    create_test_payout_rule(
        db_sessionmaker,
        campaign_id=graph.campaign.id,
        created_by_user_id=graph.admin.id,
        base_rate_per_km=10,
    )
    run_pipeline(db_sessionmaker, graph.trip.id, settings)
    asyncio.run(replace_profile(current.traffic_density_profile_id))

    async def check_payout() -> None:
        async with db_sessionmaker() as session:
            with pytest.raises(AppError) as stale_estimate:
                await calculate_trip_payout(
                    session,
                    trip_id=graph.trip.id,
                    payout_rule_id=None,
                    metadata={"source": "admin"},
                    settings=settings,
                )
            assert stale_estimate.value.code == "IMPRESSION_ESTIMATE_STALE"

    asyncio.run(check_payout())


def test_due_work_replaces_scenario_only_estimate_with_canonical_authority(
    db_sessionmaker,
    settings,
) -> None:
    graph = build_graph(db_sessionmaker, "due-scenario-only")
    seed_analytics(db_sessionmaker, graph)
    run_pipeline(db_sessionmaker, graph.trip.id, settings)
    original = fetch_impression_estimates(db_sessionmaker)[0]

    async def demote_to_scenario() -> None:
        async with db_sessionmaker() as session:
            estimate = await session.get(ImpressionEstimate, original.id)
            profile = await session.get(
                TrafficDensityProfile,
                original.traffic_density_profile_id,
            )
            assert estimate is not None
            assert profile is not None
            estimate.is_authoritative = False
            estimate.estimate_metadata = {
                **(estimate.estimate_metadata or {}),
                "authority": "scenario",
            }
            profile.is_default = False
            await session.commit()

    asyncio.run(demote_to_scenario())

    assert find_due(db_sessionmaker, settings) == [graph.trip.id]
    result = run_pipeline(db_sessionmaker, graph.trip.id, settings)
    assert stage_outcomes(result)["impressions"] == "created"

    estimates = fetch_impression_estimates(db_sessionmaker)
    authoritative = [estimate for estimate in estimates if estimate.is_authoritative]
    assert len(estimates) == 2
    assert len(authoritative) == 1
    assert authoritative[0].id != original.id
    assert authoritative[0].traffic_density_profile_id != original.traffic_density_profile_id


def test_due_work_reselects_changed_replay_detector_version(
    db_sessionmaker,
    settings,
) -> None:
    graph = build_graph(db_sessionmaker, "due-replay-version")
    seed_analytics(db_sessionmaker, graph)
    run_pipeline(db_sessionmaker, graph.trip.id, settings)
    assert find_due(db_sessionmaker, settings) == []

    next_settings = settings.model_copy(
        update={"route_replay_detector_version": "route_replay_v2"}
    )
    assert find_due(db_sessionmaker, next_settings) == [graph.trip.id]

    run_pipeline(db_sessionmaker, graph.trip.id, next_settings)
    assert find_due(db_sessionmaker, next_settings) == []

    async def inspect() -> tuple[int, str]:
        async with db_sessionmaker() as session:
            count = await session.scalar(
                select(func.count()).select_from(RouteReplaySignature)
            )
            signature = await session.scalar(select(RouteReplaySignature))
            return int(count or 0), signature.detector_version

    assert asyncio.run(inspect()) == (1, "route_replay_v2")


def test_due_work_reselects_changed_replay_tolerance(
    db_sessionmaker,
    settings,
) -> None:
    graph = build_graph(db_sessionmaker, "due-replay-tolerance")
    seed_analytics(db_sessionmaker, graph)
    run_pipeline(db_sessionmaker, graph.trip.id, settings)
    assert find_due(db_sessionmaker, settings) == []

    next_settings = settings.model_copy(
        update={
            "route_replay_time_tolerance_seconds": (
                settings.route_replay_time_tolerance_seconds + 1
            )
        }
    )
    assert find_due(db_sessionmaker, next_settings) == [graph.trip.id]
    run_pipeline(db_sessionmaker, graph.trip.id, next_settings)
    assert find_due(db_sessionmaker, next_settings) == []


def test_due_work_selects_assessment_after_current_flag_change(
    postgis_db_sessionmaker,
    settings,
) -> None:
    graph = build_graph(postgis_db_sessionmaker, "due-assessment-flags")
    analytics = seed_analytics(postgis_db_sessionmaker, graph)
    run_pipeline(postgis_db_sessionmaker, graph.trip.id, settings)
    assert find_due(postgis_db_sessionmaker, settings) == []

    async def add_current_flag() -> None:
        async with postgis_db_sessionmaker() as session:
            session.add(
                FraudFlag(
                    trip_session_id=graph.trip.id,
                    trip_analytics_id=analytics.id,
                    assignment_id=graph.assignment.id,
                    campaign_id=graph.campaign.id,
                    driver_profile_id=graph.profile.id,
                    vehicle_id=graph.vehicle.id,
                    flag_type="impossible_speed",
                    severity="high",
                    status=FraudFlagStatus.OPEN.value,
                    description="current replay evidence",
                    evidence={"source": "test"},
                    detected_at=analytics.computed_at,
                )
            )
            await session.commit()

    asyncio.run(add_current_flag())
    assert find_due(postgis_db_sessionmaker, settings) == [graph.trip.id]

    result = run_pipeline(postgis_db_sessionmaker, graph.trip.id, settings)
    assert stage_outcomes(result)["fraud_assessment"] == "created"
    assert find_due(postgis_db_sessionmaker, settings) == []


def test_due_work_selects_trip_missing_only_estimate(db_sessionmaker, settings) -> None:
    graph = build_graph(db_sessionmaker, "due3")
    seed_analytics(db_sessionmaker, graph)

    assert find_due(db_sessionmaker, settings) == [graph.trip.id]


def test_due_work_ruleless_trip_becomes_due_when_rule_appears(db_sessionmaker, settings) -> None:
    graph = build_graph(db_sessionmaker, "due4")
    analytics = seed_analytics(db_sessionmaker, graph)
    profile = create_test_traffic_density_profile(db_sessionmaker, name="Due Profile")
    create_test_impression_estimate(
        db_sessionmaker,
        trip_session_id=graph.trip.id,
        trip_analytics_id=analytics.id,
        assignment_id=graph.assignment.id,
        campaign_id=graph.campaign.id,
        driver_profile_id=graph.profile.id,
        vehicle_id=graph.vehicle.id,
        traffic_density_profile_id=profile.id,
    )

    # The missing assessment is due even without a payout rule. Once assessed,
    # the ruleless trip stops rescanning until a rule becomes available.
    assert find_due(db_sessionmaker, settings) == [graph.trip.id]
    first = run_pipeline(db_sessionmaker, graph.trip.id, settings)
    assert first.overall == "partial"
    assert stage_outcomes(first)["fraud_assessment"] == "created"
    assert find_due(db_sessionmaker, settings) == []

    create_test_payout_rule(
        db_sessionmaker,
        campaign_id=graph.campaign.id,
        created_by_user_id=graph.admin.id,
        base_rate_per_km=10,
    )

    assert find_due(db_sessionmaker, settings) == [graph.trip.id]


def test_due_work_orders_by_ended_at_and_respects_limit(db_sessionmaker, settings) -> None:
    graph = build_graph(db_sessionmaker, "due5")

    def extra_trip(ended_at: datetime):
        trip = create_test_trip_session(
            db_sessionmaker,
            assignment_id=graph.assignment.id,
            campaign_id=graph.campaign.id,
            driver_profile_id=graph.profile.id,
            vehicle_id=graph.vehicle.id,
            started_by_user_id=graph.driver.id,
            trip_status=TripSessionStatus.SEALED,
            started_at=BASE_TIME,
            ended_at=ended_at,
        )
        async def bind_evidence() -> None:
            async with db_sessionmaker() as session:
                stored = await session.get(type(trip), trip.id)
                stored.evidence_protocol_version = 2
                stored.evidence_manifest_version = 2
                stored.evidence_manifest_root_sha256 = "0" * 64
                stored.evidence_manifest_batch_count = 0
                stored.evidence_manifest_ping_count = 0
                stored.evidence_manifest_committed_at = ended_at
                stored.evidence_manifest_complete = True
                stored.evidence_manifest_verified_at = ended_at
                stored.evidence_manifest_receipt_format_version = 2
                stored.evidence_manifest_receipt_key_version = 1
                stored.evidence_manifest_receipt_signature = "test-v2-manifest-receipt"
                await session.commit()

        asyncio.run(bind_evidence())
        return trip

    # Inserted out of ended_at order to prove ordering is not insertion order.
    trip_late = extra_trip(BASE_TIME + timedelta(minutes=50))
    trip_mid = extra_trip(BASE_TIME + timedelta(minutes=40))

    expected = [graph.trip.id, trip_mid.id, trip_late.id]
    assert find_due(db_sessionmaker, settings) == expected
    assert find_due(db_sessionmaker, settings, limit=2) == expected[:2]


def test_service_module_has_no_api_or_queue_imports() -> None:
    source = Path(trip_processing.__file__).read_text()

    assert "app.api" not in source
    assert "import arq" not in source
    assert "from arq" not in source
