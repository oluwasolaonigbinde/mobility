import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
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

from app.models.audit import AuditEvent
from app.models.disbursement import (
    DriverCurrencyDebtAccount,
    PayoutBatchLine,
    PayoutDebtObligation,
)
from app.models.driver import DriverOnboardingStatus
from app.models.fraud_assessment import FraudAssessment
from app.models.notification import Notification, NotificationType
from app.models.payout import EarningsLedgerEntry
from app.models.route_replay import RouteReplaySignature, RouteReplayStatus
from app.models.trip import TripSessionStatus
from app.models.trip_analytics import FraudFlag
from app.models.user import UserRole
from app.models.vehicle import VehicleStatus
from app.services import earnings_release
from app.services.earnings_release import (
    escalate_fraud_flag_if_due,
    find_pending_release_trip_ids,
    release_pending_earnings_for_trip,
)
from app.services.fraud_assessments import (
    assess_trip_fraud,
    load_current_detection_flags,
    route_replay_assessment_facts,
)
from app.services.fraud_holds import acknowledge_fraud_flag, resolve_fraud_flag
from app.services.route_replay import route_replay_config_fingerprint
from app.services.trip_analytics import analytics_output_fingerprint

NOW = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)


def build_graph(db_sessionmaker, tag: str) -> SimpleNamespace:
    admin = create_test_user(db_sessionmaker, email=f"admin-release-{tag}@example.com")
    advertiser = create_test_user(
        db_sessionmaker,
        email=f"advertiser-release-{tag}@example.com",
        role=UserRole.ADVERTISER,
    )
    organization, _ = create_test_organization(
        db_sessionmaker,
        name=f"Release Org {tag}",
        owner_user_id=advertiser.id,
    )
    campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=advertiser.id,
    )
    driver = create_test_user(
        db_sessionmaker,
        email=f"driver-release-{tag}@example.com",
        role=UserRole.DRIVER,
    )
    profile = create_test_driver_profile(
        db_sessionmaker,
        user_id=driver.id,
        onboarding_status=DriverOnboardingStatus.ACTIVE,
    )
    vehicle = create_test_vehicle(
        db_sessionmaker,
        driver_profile_id=profile.id,
        plate_number=f"ER-{tag}",
        vehicle_status=VehicleStatus.ACTIVE,
    )
    assignment = create_test_campaign_assignment(
        db_sessionmaker,
        campaign_id=campaign.id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        assigned_by_user_id=admin.id,
    )
    trip = create_test_trip_session(
        db_sessionmaker,
        assignment_id=assignment.id,
        campaign_id=campaign.id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        started_by_user_id=driver.id,
        trip_status=TripSessionStatus.SEALED,
        started_at=NOW - timedelta(hours=1),
        ended_at=NOW,
    )
    analytics = create_test_trip_analytics(
        db_sessionmaker,
        trip_session_id=trip.id,
        assignment_id=assignment.id,
        campaign_id=campaign.id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        computed_at=NOW,
    )
    return SimpleNamespace(**locals())


def create_flag(db_sessionmaker, graph, *, flag_type="impossible_speed", detected_at=NOW):
    async def run():
        async with db_sessionmaker() as session:
            flag = FraudFlag(
                trip_session_id=graph.trip.id,
                trip_analytics_id=graph.analytics.id,
                assignment_id=graph.assignment.id,
                campaign_id=graph.campaign.id,
                driver_profile_id=graph.profile.id,
                vehicle_id=graph.vehicle.id,
                flag_type=flag_type,
                severity="high",
                status="open",
                description="Synthetic review evidence.",
                evidence={"test": True},
                detected_at=detected_at,
            )
            session.add(flag)
            await session.commit()
            await session.refresh(flag)
            return flag

    return asyncio.run(run())


def seed_assessment_authority(db_sessionmaker, graph, settings):
    async def run():
        async with db_sessionmaker() as session:
            analytics = await session.get(type(graph.analytics), graph.analytics.id)
            signature = await session.scalar(
                select(RouteReplaySignature).where(
                    RouteReplaySignature.trip_session_id == graph.trip.id
                )
            )
            if signature is None:
                fingerprint = analytics_output_fingerprint(analytics)
                signature = RouteReplaySignature(
                    trip_session_id=graph.trip.id,
                    trip_analytics_id=analytics.id,
                    status=RouteReplayStatus.COMPUTED.value,
                    detector_version=settings.route_replay_detector_version,
                    detector_config_fingerprint=route_replay_config_fingerprint(settings),
                    source_analytics_fingerprint=fingerprint,
                    payload_fingerprint="a" * 64,
                    normalized_fingerprint="b" * 64,
                    point_count=3,
                    error_code=None,
                    computed_at=NOW,
                )
                session.add(signature)
                await session.flush()
            flags = await load_current_detection_flags(session, analytics=analytics)
            result = await assess_trip_fraud(
                session,
                analytics=analytics,
                flags=flags,
                settings=settings,
                now=NOW,
                upstream_facts={"route_replay": route_replay_assessment_facts(signature)},
            )
            await session.commit()
            return result.assessment.id

    return asyncio.run(run())


def create_ledger(db_sessionmaker, graph, *, status="pending", release_at=None, amount="100.00"):
    async def run():
        async with db_sessionmaker() as session:
            entry = EarningsLedgerEntry(
                payout_calculation_id=None,
                driver_profile_id=graph.profile.id,
                driver_user_id=graph.driver.id,
                campaign_id=graph.campaign.id,
                trip_session_id=graph.trip.id,
                vehicle_id=graph.vehicle.id,
                entry_type="adjustment",
                status=status,
                amount=Decimal(amount),
                currency="NGN",
                occurred_at=NOW,
                release_at=release_at,
                ledger_metadata={},
            )
            session.add(entry)
            await session.commit()
            await session.refresh(entry)
            return entry

    return asyncio.run(run())


def release(db_sessionmaker, graph, settings):
    async def run():
        async with db_sessionmaker() as session:
            result = await release_pending_earnings_for_trip(
                session,
                trip_id=graph.trip.id,
                settings=settings,
            )
            await session.commit()
            return result

    return asyncio.run(run())


def test_clean_release_is_immediate_idempotent_and_audited(
    db_sessionmaker, settings
) -> None:
    graph = build_graph(db_sessionmaker, "clean")
    seed_assessment_authority(db_sessionmaker, graph, settings)
    entry = create_ledger(db_sessionmaker, graph)

    first = release(db_sessionmaker, graph, settings)
    second = release(db_sessionmaker, graph, settings)

    async def verify():
        async with db_sessionmaker() as session:
            stored = await session.get(EarningsLedgerEntry, entry.id)
            audits = await session.scalar(
                select(func.count(AuditEvent.id)).where(
                    AuditEvent.action == "worker.earnings.released",
                    AuditEvent.entity_id == str(graph.trip.id),
                )
            )
            notices = list(
                await session.scalars(
                    select(Notification).where(
                        Notification.recipient_user_id == graph.driver.id,
                        Notification.type_key == NotificationType.PAYOUT_RELEASED.value,
                    )
                )
            )
            return stored.status, audits, notices

    status, audits, notices = asyncio.run(verify())
    assert first.released_entry_ids == (entry.id,)
    assert second.released_entry_ids == ()
    assert status == "available"
    assert audits == 1
    assert len(notices) == 1
    assert notices[0].dedupe_key == f"payout:released:v1:{graph.trip.id}:in_app"
    assert notices[0].payload == {"trip_session_id": str(graph.trip.id)}


def test_release_creates_one_reversal_debt_obligation_before_commit(
    db_sessionmaker, settings
) -> None:
    """A due reversal cannot become available without entering debt authority."""
    graph = build_graph(db_sessionmaker, "released-reversal-debt")
    seed_assessment_authority(db_sessionmaker, graph, settings)
    credit = create_ledger(db_sessionmaker, graph, amount="100.00")

    async def seed_reversal():
        async with db_sessionmaker() as session:
            reversal = EarningsLedgerEntry(
                payout_calculation_id=None,
                driver_profile_id=graph.profile.id,
                driver_user_id=graph.driver.id,
                campaign_id=graph.campaign.id,
                trip_session_id=graph.trip.id,
                vehicle_id=graph.vehicle.id,
                entry_type="reversal",
                status="pending",
                amount=Decimal("60.00"),
                currency="NGN",
                occurred_at=NOW,
                release_at=None,
                ledger_metadata={},
            )
            session.add(reversal)
            await session.commit()
            return reversal.id

    reversal_id = asyncio.run(seed_reversal())
    first = release(db_sessionmaker, graph, settings)
    second = release(db_sessionmaker, graph, settings)

    async def verify():
        async with db_sessionmaker() as session:
            reversal = await session.get(EarningsLedgerEntry, reversal_id)
            obligations = tuple((await session.scalars(select(PayoutDebtObligation))).all())
            account = await session.scalar(select(DriverCurrencyDebtAccount))
            return reversal, obligations, account

    reversal, obligations, account = asyncio.run(verify())
    assert set(first.released_entry_ids) == {credit.id, reversal_id}
    assert second.released_entry_ids == ()
    assert reversal.status == "available"
    assert len(obligations) == 1
    assert obligations[0].source_reversal_entry_id == reversal_id
    assert account.outstanding_amount == Decimal("60.00")


def test_candidate_cursor_skips_future_and_reaches_eligible_after_blocked_pages(
    db_sessionmaker, settings, monkeypatch
) -> None:
    graphs = sorted(
        (build_graph(db_sessionmaker, f"page-{index}") for index in range(4)),
        key=lambda graph: graph.trip.id,
    )
    held, stale, eligible, future = graphs
    create_flag(db_sessionmaker, held)
    seed_assessment_authority(db_sessionmaker, held, settings)
    create_ledger(db_sessionmaker, held)
    seed_assessment_authority(db_sessionmaker, stale, settings)
    create_ledger(db_sessionmaker, stale)
    seed_assessment_authority(db_sessionmaker, eligible, settings)
    create_ledger(db_sessionmaker, eligible)
    seed_assessment_authority(db_sessionmaker, future, settings)
    create_ledger(db_sessionmaker, future, release_at=NOW + timedelta(days=1))

    async def make_stale():
        async with db_sessionmaker() as session:
            assessment = await session.scalar(
                select(FraudAssessment).where(
                    FraudAssessment.trip_session_id == stale.trip.id
                )
            )
            assessment.inputs_fingerprint = "f" * 64
            await session.commit()

    asyncio.run(make_stale())

    async def fixed_clock(_session):
        return NOW

    monkeypatch.setattr(earnings_release, "database_clock", fixed_clock)

    async def paginate():
        seen = []
        after = None
        async with db_sessionmaker() as session:
            for _ in range(3):
                page = await find_pending_release_trip_ids(
                    session, limit=1, after=after
                )
                if not page:
                    break
                seen.extend(page)
                after = page[-1]
        return seen

    seen = asyncio.run(paginate())
    assert seen == [held.trip.id, stale.trip.id, eligible.trip.id]
    assert future.trip.id not in seen


def test_active_hold_and_dismissed_stale_assessment_block_until_reassessed(
    db_sessionmaker, settings
) -> None:
    graph = build_graph(db_sessionmaker, "dismiss")
    flag = create_flag(db_sessionmaker, graph)
    seed_assessment_authority(db_sessionmaker, graph, settings)
    entry = create_ledger(db_sessionmaker, graph)

    held = release(db_sessionmaker, graph, settings)

    async def dismiss():
        async with db_sessionmaker() as session:
            await acknowledge_fraud_flag(
                session, flag_id=flag.id, actor_user_id=graph.admin.id, now=NOW
            )
            await resolve_fraud_flag(
                session,
                flag_id=flag.id,
                actor_user_id=graph.admin.id,
                outcome="dismissed",
                resolution_note="Evidence accepted.",
                now=NOW + timedelta(seconds=1),
            )
            await session.commit()

    asyncio.run(dismiss())
    stale = release(db_sessionmaker, graph, settings)
    seed_assessment_authority(db_sessionmaker, graph, settings)
    released = release(db_sessionmaker, graph, settings)

    assert held.hold_active is True
    assert stale.hold_active is False and stale.assessment_current is False
    assert released.released_entry_ids == (entry.id,)


def test_open_acknowledged_and_confirmed_each_hold_release(db_sessionmaker, settings) -> None:
    graph = build_graph(db_sessionmaker, "all-hold-states")
    flag = create_flag(db_sessionmaker, graph)
    seed_assessment_authority(db_sessionmaker, graph, settings)
    create_ledger(db_sessionmaker, graph)

    assert release(db_sessionmaker, graph, settings).hold_active is True

    async def acknowledge():
        async with db_sessionmaker() as session:
            await acknowledge_fraud_flag(
                session, flag_id=flag.id, actor_user_id=graph.admin.id, now=NOW
            )
            await session.commit()

    asyncio.run(acknowledge())
    assert release(db_sessionmaker, graph, settings).hold_active is True

    async def confirm():
        async with db_sessionmaker() as session:
            await resolve_fraud_flag(
                session,
                flag_id=flag.id,
                actor_user_id=graph.admin.id,
                outcome="confirmed",
                resolution_note="Confirmed before release.",
                now=NOW + timedelta(seconds=1),
            )
            await session.commit()

    asyncio.run(confirm())
    assert release(db_sessionmaker, graph, settings).hold_active is True


@pytest.mark.parametrize(
    "drift",
    [
        "assessment_pending",
        "assessment_error",
        "assessment_formula",
        "analytics_formula",
        "replay_detector",
        "assessment_fingerprint",
        "flag_count",
        "flag_watermark",
    ],
)
def test_any_assessment_authority_drift_blocks_release(db_sessionmaker, settings, drift):
    graph = build_graph(db_sessionmaker, f"drift-{drift}")
    seed_assessment_authority(db_sessionmaker, graph, settings)
    create_ledger(db_sessionmaker, graph)

    async def mutate():
        async with db_sessionmaker() as session:
            assessment = await session.scalar(
                select(FraudAssessment).where(
                    FraudAssessment.trip_session_id == graph.trip.id
                )
            )
            analytics = await session.get(type(graph.analytics), graph.analytics.id)
            replay = await session.scalar(
                select(RouteReplaySignature).where(
                    RouteReplaySignature.trip_session_id == graph.trip.id
                )
            )
            if drift == "assessment_pending":
                assessment.status = "pending"
            elif drift == "assessment_error":
                assessment.status = "error"
                assessment.error_code = "test_error"
            elif drift == "assessment_formula":
                assessment.formula_version = "fraud_stale"
            elif drift == "analytics_formula":
                analytics.formula_version = "analytics_stale"
            elif drift == "replay_detector":
                replay.detector_version = "replay_stale"
            elif drift == "assessment_fingerprint":
                assessment.inputs_fingerprint = "f" * 64
            elif drift == "flag_count":
                assessment.flags_count += 1
            else:
                assessment.flags_updated_through = NOW - timedelta(days=1)
            await session.commit()

    asyncio.run(mutate())
    result = release(db_sessionmaker, graph, settings)
    assert result.assessment_current is False
    assert result.released_entry_ids == ()


@pytest.mark.parametrize(
    ("offset", "released"),
    [(-timedelta(microseconds=1), True), (timedelta(0), True), (timedelta(microseconds=1), False)],
)
def test_release_at_exact_boundary(db_sessionmaker, settings, monkeypatch, offset, released):
    graph = build_graph(db_sessionmaker, f"boundary-{released}-{offset.total_seconds()}")
    seed_assessment_authority(db_sessionmaker, graph, settings)
    entry = create_ledger(db_sessionmaker, graph, release_at=NOW + offset)

    async def fixed_clock(_session):
        return NOW

    monkeypatch.setattr(earnings_release, "database_clock", fixed_clock)
    result = release(db_sessionmaker, graph, settings)
    assert bool(result.released_entry_ids) is released
    assert result.released_entry_ids in {(entry.id,), ()}


def test_seven_day_escalation_is_once_and_never_releases(
    db_sessionmaker, settings, monkeypatch
) -> None:
    graph = build_graph(db_sessionmaker, "sla")
    flag = create_flag(db_sessionmaker, graph, detected_at=NOW - timedelta(days=7))
    seed_assessment_authority(db_sessionmaker, graph, settings)
    entry = create_ledger(db_sessionmaker, graph)

    async def fixed_clock(_session):
        return NOW

    monkeypatch.setattr(earnings_release, "database_clock", fixed_clock)

    async def escalate_twice():
        async with db_sessionmaker() as session:
            first = await escalate_fraud_flag_if_due(
                session, flag_id=flag.id, review_sla_days=7
            )
            await session.commit()
        async with db_sessionmaker() as session:
            second = await escalate_fraud_flag_if_due(
                session, flag_id=flag.id, review_sla_days=7
            )
            await session.commit()
            stored_flag = await session.get(FraudFlag, flag.id)
            stored_entry = await session.get(EarningsLedgerEntry, entry.id)
            return first, second, stored_flag.escalated_at, stored_entry.status

    first, second, escalated_at, status = asyncio.run(escalate_twice())
    assert first is True and second is False
    assert escalated_at == NOW.replace(tzinfo=None)
    assert status == "pending"


def test_confirmed_post_release_flag_posts_one_netted_reversal(
    db_sessionmaker, settings
) -> None:
    graph = build_graph(db_sessionmaker, "reversal")
    flag = create_flag(db_sessionmaker, graph)
    second_flag = create_flag(db_sessionmaker, graph, flag_type="stationary_trip")
    create_ledger(db_sessionmaker, graph, status="available", amount="125.50")

    async def review():
        async with db_sessionmaker() as session:
            await acknowledge_fraud_flag(
                session, flag_id=flag.id, actor_user_id=graph.admin.id, now=NOW
            )
            first = await resolve_fraud_flag(
                session,
                flag_id=flag.id,
                actor_user_id=graph.admin.id,
                outcome="confirmed",
                resolution_note="Fraud confirmed.",
                now=NOW + timedelta(seconds=1),
            )
            retry = await resolve_fraud_flag(
                session,
                flag_id=flag.id,
                actor_user_id=graph.admin.id,
                outcome="confirmed",
                resolution_note="Fraud confirmed.",
                now=NOW + timedelta(seconds=2),
            )
            await acknowledge_fraud_flag(
                session,
                flag_id=second_flag.id,
                actor_user_id=graph.admin.id,
                now=NOW + timedelta(seconds=3),
            )
            await resolve_fraud_flag(
                session,
                flag_id=second_flag.id,
                actor_user_id=graph.admin.id,
                outcome="confirmed",
                resolution_note="Second flag confirmed.",
                now=NOW + timedelta(seconds=4),
            )
            await session.commit()
            entries = list(
                (
                    await session.scalars(
                        select(EarningsLedgerEntry).where(
                            EarningsLedgerEntry.trip_session_id == graph.trip.id
                        )
                    )
                ).all()
            )
            return first.changed, retry.changed, entries

    first_changed, retry_changed, entries = asyncio.run(review())
    reversals = [entry for entry in entries if entry.entry_type == "reversal"]
    net = sum(
        (-entry.amount if entry.entry_type == "reversal" else entry.amount)
        for entry in entries
        if entry.status == "available"
    )
    assert first_changed is True and retry_changed is False
    assert len(reversals) == 1
    assert reversals[0].source_fraud_flag_id == flag.id
    assert reversals[0].amount == Decimal("125.50")
    assert net == Decimal("0.00")


@pytest.mark.parametrize("outcome", ["dismissed", "confirmed"])
def test_dismissed_or_pre_release_review_posts_no_reversal(
    db_sessionmaker, settings, outcome
) -> None:
    graph = build_graph(db_sessionmaker, f"no-reversal-{outcome}")
    flag = create_flag(db_sessionmaker, graph)
    create_ledger(db_sessionmaker, graph, status="pending")

    async def review():
        async with db_sessionmaker() as session:
            await acknowledge_fraud_flag(
                session, flag_id=flag.id, actor_user_id=graph.admin.id, now=NOW
            )
            await resolve_fraud_flag(
                session,
                flag_id=flag.id,
                actor_user_id=graph.admin.id,
                outcome=outcome,
                resolution_note="Reviewed.",
                now=NOW + timedelta(seconds=1),
            )
            await session.commit()
            return await session.scalar(
                select(func.count(EarningsLedgerEntry.id)).where(
                    EarningsLedgerEntry.source_fraud_flag_id == flag.id
                )
            )

    assert asyncio.run(review()) == 0


def test_postgres_two_release_workers_converge_once(
    postgis_db_sessionmaker, settings
) -> None:
    graph = build_graph(postgis_db_sessionmaker, "pg-workers")
    seed_assessment_authority(postgis_db_sessionmaker, graph, settings)
    entry = create_ledger(postgis_db_sessionmaker, graph)

    async def process():
        async with postgis_db_sessionmaker() as session:
            result = await release_pending_earnings_for_trip(
                session, trip_id=graph.trip.id, settings=settings
            )
            await session.commit()
            return result.released_entry_ids

    async def race():
        return await asyncio.wait_for(asyncio.gather(process(), process()), timeout=10)

    outcomes = asyncio.run(race())
    assert sum(outcome == (entry.id,) for outcome in outcomes) == 1
    assert sum(outcome == () for outcome in outcomes) == 1


def test_postgres_release_vs_reservation_is_all_or_nothing_for_reversal_debt(
    postgis_db_sessionmaker, settings
) -> None:
    """The release trip lock and reservation lock have one safe serial outcome."""
    from test_payout_batches import _seed_authority

    from app.core.errors import AppError
    from app.services.disbursements import create_payout_batch_draft, reserve_payout_batch

    graph = build_graph(postgis_db_sessionmaker, "pg-release-reservation-debt")
    seed_assessment_authority(postgis_db_sessionmaker, graph, settings)

    async def setup():
        async with postgis_db_sessionmaker() as session:
            credit = await _seed_authority(session, graph, amount="100.00")
            reversal = EarningsLedgerEntry(
                payout_calculation_id=None,
                driver_profile_id=graph.profile.id,
                driver_user_id=graph.driver.id,
                campaign_id=graph.campaign.id,
                trip_session_id=graph.trip.id,
                vehicle_id=graph.vehicle.id,
                entry_type="reversal",
                status="pending",
                amount=Decimal("60.00"),
                currency="NGN",
                occurred_at=NOW,
                release_at=None,
                ledger_metadata={},
            )
            session.add(reversal)
            batch = await create_payout_batch_draft(
                session, currency="NGN", actor_user_id=graph.admin.id
            )
            await session.commit()
            return credit.id, reversal.id, batch.id

    credit_id, reversal_id, batch_id = asyncio.run(setup())

    async def release_task():
        async with postgis_db_sessionmaker() as session:
            try:
                result = await release_pending_earnings_for_trip(
                    session, trip_id=graph.trip.id, settings=settings
                )
                await session.commit()
                return "released", result.released_entry_ids
            except AppError as exc:
                await session.rollback()
                return exc.code, ()

    async def reserve_task():
        async with postgis_db_sessionmaker() as session:
            try:
                await reserve_payout_batch(
                    session,
                    batch_id=batch_id,
                    ledger_entry_ids=(credit_id,),
                    actor_user_id=graph.admin.id,
                )
                await session.commit()
                return "reserved"
            except AppError as exc:
                await session.rollback()
                return exc.code

    async def race():
        release_result, reservation_result = await asyncio.wait_for(
            asyncio.gather(release_task(), reserve_task()), timeout=10
        )
        async with postgis_db_sessionmaker() as session:
            reversal = await session.get(EarningsLedgerEntry, reversal_id)
            obligation_count = int(
                await session.scalar(select(func.count(PayoutDebtObligation.id))) or 0
            )
            account_count = int(
                await session.scalar(select(func.count(DriverCurrencyDebtAccount.id))) or 0
            )
            active_lines = int(
                await session.scalar(
                    select(func.count()).select_from(PayoutBatchLine).where(
                        PayoutBatchLine.ledger_entry_id == credit_id,
                        PayoutBatchLine.reservation_active.is_(True),
                    )
                )
                or 0
            )
            audits = int(
                await session.scalar(
                    select(func.count(AuditEvent.id)).where(
                        AuditEvent.action == "worker.earnings.released",
                        AuditEvent.entity_id == str(graph.trip.id),
                    )
                )
                or 0
            )
            return (
                release_result,
                reservation_result,
                reversal,
                obligation_count,
                account_count,
                active_lines,
                audits,
            )

    (
        release_result,
        reservation_result,
        reversal,
        obligation_count,
        account_count,
        active_lines,
        audits,
    ) = asyncio.run(race())
    assert {release_result[0], reservation_result} & {"released", "reserved"}
    if release_result[0] == "released":
        assert reversal.status == "available"
        assert obligation_count == account_count == 1
        assert active_lines == 0
        assert audits == 1
    else:
        assert release_result[0] == "PAYOUT_DEBT_ACTIVE_RESERVATION"
        assert reservation_result == "reserved"
        assert reversal.status == "pending"
        assert obligation_count == account_count == audits == 0
        assert active_lines == 1


def test_postgres_release_vs_dismiss_never_releases_stale_assessment(
    postgis_db_sessionmaker, settings
) -> None:
    graph = build_graph(postgis_db_sessionmaker, "pg-review-race")
    flag = create_flag(postgis_db_sessionmaker, graph)
    seed_assessment_authority(postgis_db_sessionmaker, graph, settings)
    entry = create_ledger(postgis_db_sessionmaker, graph)

    async def prepare():
        async with postgis_db_sessionmaker() as session:
            await acknowledge_fraud_flag(
                session, flag_id=flag.id, actor_user_id=graph.admin.id, now=NOW
            )
            await session.commit()

    asyncio.run(prepare())

    async def release_task():
        async with postgis_db_sessionmaker() as session:
            result = await release_pending_earnings_for_trip(
                session, trip_id=graph.trip.id, settings=settings
            )
            await session.commit()
            return result.released_entry_ids

    async def dismiss_task():
        async with postgis_db_sessionmaker() as session:
            await resolve_fraud_flag(
                session,
                flag_id=flag.id,
                actor_user_id=graph.admin.id,
                outcome="dismissed",
                resolution_note="Race-safe dismissal.",
                now=NOW + timedelta(seconds=1),
            )
            await session.commit()

    async def race():
        released, _ = await asyncio.wait_for(
            asyncio.gather(release_task(), dismiss_task()), timeout=10
        )
        async with postgis_db_sessionmaker() as session:
            stored = await session.get(EarningsLedgerEntry, entry.id)
            return released, stored.status

    released, status = asyncio.run(race())
    assert released == ()
    assert status == "pending"
