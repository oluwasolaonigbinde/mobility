import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from conftest import (
    create_test_campaign,
    create_test_campaign_assignment,
    create_test_driver_profile,
    create_test_organization,
    create_test_trip_analytics,
    create_test_trip_session,
    create_test_user,
    create_test_vehicle,
)
from sqlalchemy import func, select

from app.models.campaign_assignment import CampaignAssignmentStatus
from app.models.driver import DriverOnboardingStatus
from app.models.route_replay import RouteReplaySignature, RouteReplayStatus
from app.models.trip import TripSessionStatus
from app.models.trip_analytics import FraudFlag, FraudFlagStatus, FraudFlagType
from app.models.user import User, UserRole
from app.models.vehicle import VehicleStatus
from app.services import route_replay
from app.services.fraud_holds import (
    acknowledge_fraud_flag,
    fraud_hold_counts,
    resolve_fraud_flag,
)

BASE_TIME = datetime(2026, 8, 1, 8, 0, tzinfo=UTC)
PASSWORD = "long-secure-password"


def ping(
    index: int,
    *,
    shifted_seconds: int = 0,
    interval_seconds: int = 10,
    latitude_offset: float = 0,
):
    return SimpleNamespace(
        recorded_at=BASE_TIME + timedelta(seconds=shifted_seconds + index * interval_seconds),
        sequence_number=index,
        latitude=6.50000 + latitude_offset + index * 0.0001,
        longitude=3.30000 + index * 0.0001,
        accuracy_m=5.0,
        speed_mps=8.0,
        heading_degrees=45.0,
        altitude_m=12.0,
        ping_metadata={"source": "fixture"},
    )


def fingerprints(points, *, tolerance: int = 5):
    return route_replay.canonical_route_fingerprints(
        points,
        detector_version="route_replay_test_v1",
        coordinate_precision=5,
        time_tolerance_seconds=tolerance,
        min_valid_pings=3,
        min_distance_m=100,
    )


def test_identical_payload_and_normalized_fingerprints_are_deterministic() -> None:
    first = [ping(index) for index in range(3)]
    second = [ping(index) for index in range(3)]

    assert fingerprints(first) == fingerprints(second)

    second[0].ping_metadata = {"source": "changed-payload-fact"}
    changed_payload = fingerprints(second)
    assert fingerprints(first).payload_fingerprint != changed_payload.payload_fingerprint
    assert fingerprints(first).normalized_fingerprint == changed_payload.normalized_fingerprint


def test_constant_time_shift_changes_payload_but_not_normalized_fingerprint() -> None:
    original = fingerprints([ping(index) for index in range(3)])
    shifted = fingerprints([ping(index, shifted_seconds=3600) for index in range(3)])

    assert original.payload_fingerprint != shifted.payload_fingerprint
    assert original.normalized_fingerprint == shifted.normalized_fingerprint


def test_distinct_route_does_not_match() -> None:
    original = fingerprints([ping(index) for index in range(3)])
    distinct = fingerprints([ping(index, latitude_offset=0.02) for index in range(3)])

    assert original.payload_fingerprint != distinct.payload_fingerprint
    assert original.normalized_fingerprint != distinct.normalized_fingerprint


@pytest.mark.parametrize("latitude_offset", [0.001 * index for index in range(1, 21)])
def test_distinct_route_family_has_no_false_match(latitude_offset: float) -> None:
    original = fingerprints([ping(index) for index in range(10)])
    distinct = fingerprints(
        [ping(index, latitude_offset=latitude_offset) for index in range(10)]
    )

    assert original.normalized_fingerprint != distinct.normalized_fingerprint


def test_interval_change_beyond_tolerance_does_not_normalize_to_same_route() -> None:
    original = fingerprints([ping(index, interval_seconds=10) for index in range(3)])
    stretched = fingerprints([ping(index, interval_seconds=20) for index in range(3)])

    assert original.normalized_fingerprint != stretched.normalized_fingerprint


def test_detector_config_fingerprint_changes_with_evidence_policy(settings) -> None:
    original = route_replay.route_replay_config_fingerprint(settings)
    changed = route_replay.route_replay_config_fingerprint(
        settings.model_copy(
            update={
                "route_replay_max_evidence_matches": (
                    settings.route_replay_max_evidence_matches + 1
                )
            }
        )
    )

    assert original != changed


def create_graph(db_sessionmaker, suffix: str, *, ended_at: datetime):
    admin = create_test_user(
        db_sessionmaker,
        email=f"replay-admin-{suffix}@example.com",
        password=PASSWORD,
    )
    advertiser = create_test_user(
        db_sessionmaker,
        email=f"replay-advertiser-{suffix}@example.com",
        password=PASSWORD,
        role=UserRole.ADVERTISER,
    )
    organization, _ = create_test_organization(
        db_sessionmaker,
        name=f"Replay Org {suffix}",
        owner_user_id=advertiser.id,
    )
    campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=advertiser.id,
        name=f"Replay Campaign {suffix}",
    )
    driver = create_test_user(
        db_sessionmaker,
        email=f"replay-driver-{suffix}@example.com",
        password=PASSWORD,
        role=UserRole.DRIVER,
    )
    profile = create_test_driver_profile(
        db_sessionmaker,
        user_id=driver.id,
        onboarding_status=DriverOnboardingStatus.ACTIVE,
        license_number=f"REPLAY-{suffix}",
    )
    vehicle = create_test_vehicle(
        db_sessionmaker,
        driver_profile_id=profile.id,
        plate_number=f"RPL-{suffix}",
        vehicle_status=VehicleStatus.ACTIVE,
    )
    assignment = create_test_campaign_assignment(
        db_sessionmaker,
        campaign_id=campaign.id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        assigned_by_user_id=admin.id,
        assignment_status=CampaignAssignmentStatus.ACTIVE,
        activated_at=BASE_TIME,
    )
    trip = create_test_trip_session(
        db_sessionmaker,
        assignment_id=assignment.id,
        campaign_id=campaign.id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        started_by_user_id=driver.id,
        trip_status=TripSessionStatus.SEALED,
        started_at=ended_at - timedelta(minutes=20),
        ended_at=ended_at,
    )
    analytics = create_test_trip_analytics(
        db_sessionmaker,
        trip_session_id=trip.id,
        assignment_id=assignment.id,
        campaign_id=campaign.id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        distance_m=1000,
        computed_at=ended_at,
    )
    return trip, analytics


def run_detection(db_sessionmaker, *, trip, analytics, points, settings, now):
    async def run():
        async with db_sessionmaker() as session:
            result = await route_replay.detect_route_replay(
                session,
                trip=trip,
                analytics=analytics,
                ordered_pings=points,
                settings=settings,
                now=now,
            )
            await session.commit()
            return result

    return asyncio.run(run())


def create_related_trip(db_sessionmaker, source_trip, suffix: str, *, ended_at: datetime):
    trip = create_test_trip_session(
        db_sessionmaker,
        assignment_id=source_trip.assignment_id,
        campaign_id=source_trip.campaign_id,
        driver_profile_id=source_trip.driver_profile_id,
        vehicle_id=source_trip.vehicle_id,
        started_by_user_id=source_trip.started_by_user_id,
        trip_status=TripSessionStatus.SEALED,
        started_at=ended_at - timedelta(minutes=20),
        ended_at=ended_at,
        metadata={"fixture": suffix},
    )
    analytics = create_test_trip_analytics(
        db_sessionmaker,
        trip_session_id=trip.id,
        assignment_id=trip.assignment_id,
        campaign_id=trip.campaign_id,
        driver_profile_id=trip.driver_profile_id,
        vehicle_id=trip.vehicle_id,
        distance_m=1000,
        computed_at=ended_at,
    )
    return trip, analytics


def test_same_trip_retry_converges_on_one_signature(
    db_sessionmaker,
    settings,
) -> None:
    trip, analytics = create_graph(
        db_sessionmaker, "same", ended_at=BASE_TIME + timedelta(minutes=30)
    )
    points = [ping(index) for index in range(settings.route_replay_min_valid_pings)]

    first = run_detection(
        db_sessionmaker,
        trip=trip,
        analytics=analytics,
        points=points,
        settings=settings,
        now=BASE_TIME + timedelta(hours=1),
    )
    second = run_detection(
        db_sessionmaker,
        trip=trip,
        analytics=analytics,
        points=points,
        settings=settings,
        now=BASE_TIME + timedelta(hours=2),
    )

    async def inspect():
        async with db_sessionmaker() as session:
            return await session.scalar(select(func.count()).select_from(RouteReplaySignature))

    assert first.changed is True
    assert second.changed is False
    assert first.signature.id == second.signature.id
    assert (
        second.signature.detector_config_fingerprint
        == route_replay.route_replay_config_fingerprint(settings)
    )
    assert asyncio.run(inspect()) == 1


def test_cross_account_time_shift_flag_has_bounded_redacted_evidence(
    db_sessionmaker,
    settings,
) -> None:
    earlier_trip, earlier_analytics = create_graph(
        db_sessionmaker, "early", ended_at=BASE_TIME + timedelta(minutes=30)
    )
    later_trip, later_analytics = create_graph(
        db_sessionmaker, "late", ended_at=BASE_TIME + timedelta(hours=2)
    )
    point_count = settings.route_replay_min_valid_pings
    earlier_points = [ping(index) for index in range(point_count)]
    later_points = [ping(index, shifted_seconds=3600) for index in range(point_count)]

    first = run_detection(
        db_sessionmaker,
        trip=earlier_trip,
        analytics=earlier_analytics,
        points=earlier_points,
        settings=settings,
        now=BASE_TIME + timedelta(hours=3),
    )
    second = run_detection(
        db_sessionmaker,
        trip=later_trip,
        analytics=later_analytics,
        points=later_points,
        settings=settings,
        now=BASE_TIME + timedelta(hours=3, minutes=1),
    )

    assert first.replay_flag is None
    assert second.match_kind == "time_shifted"
    assert second.replay_flag is not None
    evidence = second.replay_flag.evidence
    assert evidence == {
        "detector_version": settings.route_replay_detector_version,
        "match_kind": "time_shifted",
        "total_match_count": 1,
        "cross_account_match_count": 1,
        "sampled_matched_trip_ids": [str(earlier_trip.id)],
    }
    serialized = str(evidence)
    assert "6.5" not in serialized
    assert "2026-" not in serialized
    assert str(earlier_trip.driver_profile_id) not in serialized

    latest_trip, latest_analytics = create_graph(
        db_sessionmaker, "latest", ended_at=BASE_TIME + timedelta(hours=4)
    )
    third = run_detection(
        db_sessionmaker,
        trip=latest_trip,
        analytics=latest_analytics,
        points=[ping(index, shifted_seconds=7200) for index in range(point_count)],
        settings=settings,
        now=BASE_TIME + timedelta(hours=5),
    )

    async def inspect_group_flags():
        async with db_sessionmaker() as session:
            return list(
                (
                    await session.scalars(
                        select(FraudFlag).where(
                            FraudFlag.flag_type == FraudFlagType.ROUTE_REPLAY.value,
                            FraudFlag.status == FraudFlagStatus.OPEN.value,
                        )
                    )
                ).all()
            )

    group_flags = asyncio.run(inspect_group_flags())
    assert len(group_flags) == 1
    assert group_flags[0].trip_session_id == latest_trip.id
    assert third.replay_flag is not None
    assert third.replay_flag.evidence["total_match_count"] == 2
    assert third.replay_flag.evidence["cross_account_match_count"] == 2


@pytest.mark.parametrize("review_status", ["acknowledged", "confirmed", "dismissed"])
def test_replay_redetection_preserves_active_review_and_reopens_after_dismissal(
    db_sessionmaker,
    settings,
    review_status: str,
) -> None:
    earlier_trip, earlier_analytics = create_graph(
        db_sessionmaker,
        f"review-early-{review_status}",
        ended_at=BASE_TIME + timedelta(minutes=30),
    )
    later_trip, later_analytics = create_graph(
        db_sessionmaker,
        f"review-late-{review_status}",
        ended_at=BASE_TIME + timedelta(hours=2),
    )
    point_count = settings.route_replay_min_valid_pings
    earlier_points = [ping(index) for index in range(point_count)]
    later_points = [ping(index, shifted_seconds=3600) for index in range(point_count)]
    run_detection(
        db_sessionmaker,
        trip=earlier_trip,
        analytics=earlier_analytics,
        points=earlier_points,
        settings=settings,
        now=BASE_TIME + timedelta(hours=3),
    )
    detected = run_detection(
        db_sessionmaker,
        trip=later_trip,
        analytics=later_analytics,
        points=later_points,
        settings=settings,
        now=BASE_TIME + timedelta(hours=3, minutes=1),
    )
    original_id = detected.replay_flag.id

    async def review_and_redetect():
        async with db_sessionmaker() as session:
            actor = await session.scalar(
                select(User).where(
                    User.email == f"replay-admin-review-late-{review_status}@example.com"
                )
            )
            await acknowledge_fraud_flag(
                session,
                flag_id=original_id,
                actor_user_id=actor.id,
                now=BASE_TIME + timedelta(hours=4),
            )
            if review_status != "acknowledged":
                await resolve_fraud_flag(
                    session,
                    flag_id=original_id,
                    actor_user_id=actor.id,
                    outcome=review_status,
                    resolution_note=f"Review outcome: {review_status}.",
                    now=BASE_TIME + timedelta(hours=4, minutes=1),
                )
            await session.commit()

        async with db_sessionmaker() as session:
            await route_replay.detect_route_replay(
                session,
                trip=later_trip,
                analytics=later_analytics,
                ordered_pings=later_points,
                settings=settings,
                now=BASE_TIME + timedelta(hours=5),
            )
            await session.commit()

        async with db_sessionmaker() as session:
            return list(
                (
                    await session.scalars(
                        select(FraudFlag)
                        .where(
                            FraudFlag.trip_session_id == later_trip.id,
                            FraudFlag.flag_type == FraudFlagType.ROUTE_REPLAY.value,
                        )
                        .order_by(FraudFlag.created_at, FraudFlag.id)
                    )
                ).all()
            )

    flags = asyncio.run(review_and_redetect())
    if review_status == "dismissed":
        assert len(flags) == 2
        assert {flag.status for flag in flags} == {"dismissed", "open"}
    else:
        assert len(flags) == 1
        assert flags[0].id == original_id
        assert flags[0].status == review_status


def test_mixed_exact_and_time_shifted_members_stay_in_one_group(
    db_sessionmaker,
    settings,
) -> None:
    trips = [
        create_graph(
            db_sessionmaker,
            f"mixed-{index}",
            ended_at=BASE_TIME + timedelta(hours=index + 1),
        )
        for index in range(3)
    ]
    count = settings.route_replay_min_valid_pings
    routes = [
        [ping(index) for index in range(count)],
        [ping(index, shifted_seconds=3600) for index in range(count)],
        [ping(index, shifted_seconds=3600) for index in range(count)],
    ]
    results = [
        run_detection(
            db_sessionmaker,
            trip=trip,
            analytics=analytics,
            points=points,
            settings=settings,
            now=BASE_TIME + timedelta(hours=5, minutes=offset),
        )
        for offset, ((trip, analytics), points) in enumerate(zip(trips, routes, strict=True))
    ]

    assert results[-1].match_kind == "identical"
    assert results[-1].replay_flag is not None
    assert results[-1].replay_flag.evidence["total_match_count"] == 2
    assert set(results[-1].replay_flag.evidence["sampled_matched_trip_ids"]) == {
        str(trips[0][0].id),
        str(trips[1][0].id),
    }


def test_same_account_repeated_route_is_indexed_without_fraud_flag(
    db_sessionmaker,
    settings,
) -> None:
    first_trip, first_analytics = create_graph(
        db_sessionmaker, "same-account", ended_at=BASE_TIME + timedelta(hours=1)
    )
    second_trip, second_analytics = create_related_trip(
        db_sessionmaker,
        first_trip,
        "same-account-2",
        ended_at=BASE_TIME + timedelta(hours=2),
    )
    count = settings.route_replay_min_valid_pings
    run_detection(
        db_sessionmaker,
        trip=first_trip,
        analytics=first_analytics,
        points=[ping(index) for index in range(count)],
        settings=settings,
        now=BASE_TIME + timedelta(hours=3),
    )
    result = run_detection(
        db_sessionmaker,
        trip=second_trip,
        analytics=second_analytics,
        points=[ping(index, shifted_seconds=3600) for index in range(count)],
        settings=settings,
        now=BASE_TIME + timedelta(hours=3, minutes=1),
    )

    async def inspect():
        async with db_sessionmaker() as session:
            signature_count = await session.scalar(
                select(func.count()).select_from(RouteReplaySignature)
            )
            flag_count = await session.scalar(
                select(func.count())
                .select_from(FraudFlag)
                .where(FraudFlag.flag_type == FraudFlagType.ROUTE_REPLAY.value)
            )
            return signature_count, flag_count

    assert result.replay_flag is None
    assert asyncio.run(inspect()) == (2, 0)


def test_latest_member_departure_promotes_latest_remaining_group_member(
    db_sessionmaker,
    settings,
) -> None:
    graphs = [
        create_graph(
            db_sessionmaker,
            f"departure-{index}",
            ended_at=BASE_TIME + timedelta(hours=index + 1),
        )
        for index in range(3)
    ]
    count = settings.route_replay_min_valid_pings
    for index, (trip, analytics) in enumerate(graphs):
        run_detection(
            db_sessionmaker,
            trip=trip,
            analytics=analytics,
            points=[ping(point, shifted_seconds=index * 3600) for point in range(count)],
            settings=settings,
            now=BASE_TIME + timedelta(hours=5, minutes=index),
        )

    departing_trip, departing_analytics = graphs[-1]
    run_detection(
        db_sessionmaker,
        trip=departing_trip,
        analytics=departing_analytics,
        points=[ping(point, latitude_offset=0.03) for point in range(count)],
        settings=settings,
        now=BASE_TIME + timedelta(hours=6),
    )

    async def inspect():
        async with db_sessionmaker() as session:
            return list(
                (
                    await session.scalars(
                        select(FraudFlag).where(
                            FraudFlag.flag_type == FraudFlagType.ROUTE_REPLAY.value,
                            FraudFlag.status == FraudFlagStatus.OPEN.value,
                        )
                    )
                ).all()
            )

    flags = asyncio.run(inspect())
    assert len(flags) == 1
    assert flags[0].trip_session_id == graphs[1][0].id
    assert flags[0].evidence["total_match_count"] == 1
    assert flags[0].evidence["sampled_matched_trip_ids"] == [str(graphs[0][0].id)]


def test_large_group_counts_all_matches_but_bounds_evidence_sample(
    db_sessionmaker,
    settings,
) -> None:
    bounded_settings = settings.model_copy(
        update={"route_replay_max_evidence_matches": 3}
    )
    graphs = [
        create_graph(
            db_sessionmaker,
            f"scale-{index}",
            ended_at=BASE_TIME + timedelta(hours=index + 1),
        )
        for index in range(7)
    ]
    count = bounded_settings.route_replay_min_valid_pings
    last_result = None
    for index, (trip, analytics) in enumerate(graphs):
        last_result = run_detection(
            db_sessionmaker,
            trip=trip,
            analytics=analytics,
            points=[ping(point, shifted_seconds=index * 3600) for point in range(count)],
            settings=bounded_settings,
            now=BASE_TIME + timedelta(hours=10, minutes=index),
        )

    assert last_result is not None and last_result.replay_flag is not None
    assert last_result.replay_flag.evidence["total_match_count"] == 6
    assert last_result.replay_flag.evidence["cross_account_match_count"] == 6
    assert len(last_result.replay_flag.evidence["sampled_matched_trip_ids"]) == 3


def test_evaluation_failure_is_sanitized_and_persisted(
    db_sessionmaker,
    settings,
    monkeypatch,
) -> None:
    trip, analytics = create_graph(
        db_sessionmaker, "error", ended_at=BASE_TIME + timedelta(minutes=30)
    )
    points = [ping(index) for index in range(settings.route_replay_min_valid_pings)]

    def fail(*args, **kwargs):
        raise RuntimeError("secret coordinate 6.5000,3.3000")

    monkeypatch.setattr(route_replay, "canonical_route_fingerprints", fail)
    result = run_detection(
        db_sessionmaker,
        trip=trip,
        analytics=analytics,
        points=points,
        settings=settings,
        now=BASE_TIME + timedelta(hours=1),
    )

    assert result.signature.status == RouteReplayStatus.ERROR.value
    assert result.signature.error_code == "route_replay_evaluation_failed"
    assert result.signature.payload_fingerprint is None
    assert result.signature.normalized_fingerprint is None
    assert "secret" not in str(result.signature.__dict__)


def test_distinct_route_removes_only_current_open_replay_flag(
    db_sessionmaker,
    settings,
) -> None:
    trip, analytics = create_graph(
        db_sessionmaker, "clear", ended_at=BASE_TIME + timedelta(minutes=30)
    )

    async def seed_flag():
        async with db_sessionmaker() as session:
            session.add(
                FraudFlag(
                    trip_session_id=trip.id,
                    trip_analytics_id=analytics.id,
                    assignment_id=trip.assignment_id,
                    campaign_id=trip.campaign_id,
                    driver_profile_id=trip.driver_profile_id,
                    vehicle_id=trip.vehicle_id,
                    flag_type=FraudFlagType.ROUTE_REPLAY.value,
                    severity="high",
                    status=FraudFlagStatus.OPEN.value,
                    description="stale replay",
                    evidence={},
                    detected_at=BASE_TIME,
                )
            )
            await session.commit()

    asyncio.run(seed_flag())
    result = run_detection(
        db_sessionmaker,
        trip=trip,
        analytics=analytics,
        points=[ping(index, latitude_offset=0.03) for index in range(10)],
        settings=settings,
        now=BASE_TIME + timedelta(hours=1),
    )

    async def count_open():
        async with db_sessionmaker() as session:
            return await session.scalar(
                select(func.count())
                .select_from(FraudFlag)
                .where(
                    FraudFlag.trip_session_id == trip.id,
                    FraudFlag.flag_type == FraudFlagType.ROUTE_REPLAY.value,
                    FraudFlag.status == FraudFlagStatus.OPEN.value,
                )
            )

    assert result.replay_flag is None
    assert asyncio.run(count_open()) == 0


def test_postgres_concurrent_reverse_processing_flags_only_latest_trip(
    postgis_db_sessionmaker,
    settings,
    monkeypatch,
) -> None:
    earlier_trip, earlier_analytics = create_graph(
        postgis_db_sessionmaker,
        "pg-early",
        ended_at=BASE_TIME + timedelta(minutes=30),
    )
    later_trip, later_analytics = create_graph(
        postgis_db_sessionmaker,
        "pg-late",
        ended_at=BASE_TIME + timedelta(hours=2),
    )
    point_count = settings.route_replay_min_valid_pings
    earlier_points = [ping(index) for index in range(point_count)]
    later_points = [ping(index, shifted_seconds=3600) for index in range(point_count)]
    earlier_payload = route_replay.canonical_route_fingerprints(
        earlier_points,
        detector_version=settings.route_replay_detector_version,
        coordinate_precision=settings.route_replay_coordinate_precision,
        time_tolerance_seconds=settings.route_replay_time_tolerance_seconds,
        min_valid_pings=settings.route_replay_min_valid_pings,
        min_distance_m=settings.route_replay_min_distance_m,
    ).payload_fingerprint
    later_committed = asyncio.Event()
    original_lock = route_replay._lock_transition_fingerprints

    async def ordered_lock(session, *, old_signature, new_fingerprints):
        if (
            new_fingerprints is not None
            and new_fingerprints.payload_fingerprint == earlier_payload
        ):
            await later_committed.wait()
        await original_lock(
            session,
            old_signature=old_signature,
            new_fingerprints=new_fingerprints,
        )

    monkeypatch.setattr(route_replay, "_lock_transition_fingerprints", ordered_lock)

    async def exercise_reverse_order() -> None:
        async def process(trip, analytics, points, *, signal=False):
            async with postgis_db_sessionmaker() as session:
                await route_replay.detect_route_replay(
                    session,
                    trip=trip,
                    analytics=analytics,
                    ordered_pings=points,
                    settings=settings,
                    now=BASE_TIME + timedelta(hours=4),
                )
                await session.commit()
                if signal:
                    later_committed.set()

        await asyncio.gather(
            process(later_trip, later_analytics, later_points, signal=True),
            process(earlier_trip, earlier_analytics, earlier_points),
        )

    asyncio.run(exercise_reverse_order())

    async def inspect():
        async with postgis_db_sessionmaker() as session:
            flags = list(
                (
                    await session.scalars(
                        select(FraudFlag).where(
                            FraudFlag.flag_type == FraudFlagType.ROUTE_REPLAY.value,
                            FraudFlag.status == FraudFlagStatus.OPEN.value,
                        )
                    )
                ).all()
            )
            signature_count = await session.scalar(
                select(func.count()).select_from(RouteReplaySignature)
            )
            return flags, signature_count

    flags, signature_count = asyncio.run(inspect())
    assert signature_count == 2
    assert len(flags) == 1
    assert flags[0].trip_session_id == later_trip.id
    assert flags[0].detected_at == later_analytics.computed_at
    assert flags[0].evidence["sampled_matched_trip_ids"] == [str(earlier_trip.id)]


def test_postgres_reconciliation_waits_for_other_trip_money_hold(
    postgis_db_sessionmaker,
    settings,
) -> None:
    earlier_trip, earlier_analytics = create_graph(
        postgis_db_sessionmaker,
        "gate-early",
        ended_at=BASE_TIME + timedelta(minutes=30),
    )
    held_trip, held_analytics = create_graph(
        postgis_db_sessionmaker,
        "gate-held",
        ended_at=BASE_TIME + timedelta(hours=2),
    )
    incoming_trip, incoming_analytics = create_graph(
        postgis_db_sessionmaker,
        "gate-incoming",
        ended_at=BASE_TIME + timedelta(hours=3),
    )
    count = settings.route_replay_min_valid_pings
    run_detection(
        postgis_db_sessionmaker,
        trip=earlier_trip,
        analytics=earlier_analytics,
        points=[ping(index) for index in range(count)],
        settings=settings,
        now=BASE_TIME + timedelta(hours=4),
    )
    detected = run_detection(
        postgis_db_sessionmaker,
        trip=held_trip,
        analytics=held_analytics,
        points=[ping(index, shifted_seconds=3600) for index in range(count)],
        settings=settings,
        now=BASE_TIME + timedelta(hours=4, minutes=1),
    )
    assert detected.replay_flag is not None

    async def exercise_gate() -> None:
        hold_acquired = asyncio.Event()
        release_hold = asyncio.Event()

        async def hold_money_scope() -> None:
            async with postgis_db_sessionmaker() as session:
                counts = await fraud_hold_counts(session, held_trip.id)
                assert counts == {"low": 0, "medium": 0, "high": 1}
                hold_acquired.set()
                await release_hold.wait()
                await session.commit()

        async def reconcile_incoming() -> None:
            async with postgis_db_sessionmaker() as session:
                await route_replay.detect_route_replay(
                    session,
                    trip=incoming_trip,
                    analytics=incoming_analytics,
                    ordered_pings=[
                        ping(index, shifted_seconds=7200) for index in range(count)
                    ],
                    settings=settings,
                    now=BASE_TIME + timedelta(hours=5),
                )
                await session.commit()

        holder = asyncio.create_task(hold_money_scope())
        await hold_acquired.wait()
        detector = asyncio.create_task(reconcile_incoming())
        try:
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(asyncio.shield(detector), timeout=0.25)
            async with postgis_db_sessionmaker() as session:
                held_flag = await session.scalar(
                    select(FraudFlag).where(
                        FraudFlag.trip_session_id == held_trip.id,
                        FraudFlag.flag_type == FraudFlagType.ROUTE_REPLAY.value,
                        FraudFlag.status == FraudFlagStatus.OPEN.value,
                    )
                )
                assert held_flag is not None
        finally:
            release_hold.set()
        await asyncio.gather(holder, detector)

    asyncio.run(exercise_gate())

    async def inspect_final_flags():
        async with postgis_db_sessionmaker() as session:
            return list(
                (
                    await session.scalars(
                        select(FraudFlag).where(
                            FraudFlag.flag_type == FraudFlagType.ROUTE_REPLAY.value,
                            FraudFlag.status == FraudFlagStatus.OPEN.value,
                        )
                    )
                ).all()
            )

    flags = asyncio.run(inspect_final_flags())
    assert {flag.trip_session_id for flag in flags} == {incoming_trip.id}


def test_postgres_concurrent_old_to_new_group_transition_reconciles_both_groups(
    postgis_db_sessionmaker,
    settings,
) -> None:
    old_first = create_graph(
        postgis_db_sessionmaker,
        "move-old-first",
        ended_at=BASE_TIME + timedelta(hours=1),
    )
    moving = create_graph(
        postgis_db_sessionmaker,
        "move-current",
        ended_at=BASE_TIME + timedelta(hours=2),
    )
    new_first = create_graph(
        postgis_db_sessionmaker,
        "move-new-first",
        ended_at=BASE_TIME + timedelta(hours=1, minutes=30),
    )
    old_latest = create_graph(
        postgis_db_sessionmaker,
        "move-old-latest",
        ended_at=BASE_TIME + timedelta(hours=3),
    )
    count = settings.route_replay_min_valid_pings
    old_route = [ping(index) for index in range(count)]
    new_route = [ping(index, latitude_offset=0.03) for index in range(count)]
    run_detection(
        postgis_db_sessionmaker,
        trip=old_first[0],
        analytics=old_first[1],
        points=old_route,
        settings=settings,
        now=BASE_TIME + timedelta(hours=4),
    )
    run_detection(
        postgis_db_sessionmaker,
        trip=moving[0],
        analytics=moving[1],
        points=[ping(index, shifted_seconds=3600) for index in range(count)],
        settings=settings,
        now=BASE_TIME + timedelta(hours=4, minutes=1),
    )
    run_detection(
        postgis_db_sessionmaker,
        trip=new_first[0],
        analytics=new_first[1],
        points=new_route,
        settings=settings,
        now=BASE_TIME + timedelta(hours=4, minutes=2),
    )

    async def transition_and_add() -> None:
        async def process(trip, analytics, points):
            async with postgis_db_sessionmaker() as session:
                await route_replay.detect_route_replay(
                    session,
                    trip=trip,
                    analytics=analytics,
                    ordered_pings=points,
                    settings=settings,
                    now=BASE_TIME + timedelta(hours=5),
                )
                await session.commit()

        await asyncio.gather(
            process(
                moving[0],
                moving[1],
                [
                    ping(index, shifted_seconds=3600, latitude_offset=0.03)
                    for index in range(count)
                ],
            ),
            process(
                old_latest[0],
                old_latest[1],
                [ping(index, shifted_seconds=7200) for index in range(count)],
            ),
        )

    asyncio.run(transition_and_add())

    async def inspect():
        async with postgis_db_sessionmaker() as session:
            return list(
                (
                    await session.scalars(
                        select(FraudFlag).where(
                            FraudFlag.flag_type == FraudFlagType.ROUTE_REPLAY.value,
                            FraudFlag.status == FraudFlagStatus.OPEN.value,
                        )
                    )
                ).all()
            )

    flags = asyncio.run(inspect())
    assert {flag.trip_session_id for flag in flags} == {moving[0].id, old_latest[0].id}
    assert all(flag.evidence["total_match_count"] == 1 for flag in flags)
