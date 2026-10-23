"""S9/D118 replaces measurement issuance and removes money from reports.

Keep the signed-ledger, immutable-history and concurrency assertions directly;
do not weaken them by merely dropping the old financial export assertions.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from conftest import create_test_campaign, create_test_organization, create_test_user
from report_fixtures import DAY_1, create_report_graph
from sqlalchemy import select
from test_stored_files import FakeStorageProvider

from app.core.errors import AppError
from app.models.campaign import CampaignStatus
from app.models.payout import EarningsLedgerEntry
from app.models.trip import TripSession
from app.models.user import UserRole
from app.services.campaign_report_delivery import _pair
from app.services.campaign_reports import create_report
from app.services.disclosure import _canonical_hash
from app.services.fraud_holds import lock_fraud_reconciliation_gate
from app.services.payout_rule_serialization import acquire_campaign_terms_lock


def graph(factory, suffix):
    admin = create_test_user(factory, email=f"corrected-staff-{suffix}@example.com")
    owner = create_test_user(
        factory, email=f"corrected-owner-{suffix}@example.com", role=UserRole.ADVERTISER
    )
    organization, _ = create_test_organization(factory, owner_user_id=owner.id)
    campaign = create_test_campaign(
        factory,
        organization_id=organization.id,
        created_by_user_id=owner.id,
        campaign_status=CampaignStatus.ACTIVE,
        start_at=DAY_1 - timedelta(days=1),
        end_at=DAY_1 + timedelta(days=10),
    )
    create_report_graph(
        factory,
        admin=admin,
        advertiser=owner,
        campaign=campaign,
        driver_email=f"corrected-driver-{suffix}@example.com",
        plate_number=f"COR-{suffix}",
        started_at=DAY_1,
    )
    return admin, campaign


async def issue(factory, admin, campaign, settings, *, start=DAY_1, end=DAY_1 + timedelta(days=1)):
    async with factory() as session:
        identity = uuid4()
        report = await create_report(
            session,
            actor_user_id=admin.id,
            campaigns=[campaign],
            request_id=identity,
            request_fingerprint=_canonical_hash(str(identity)),
            start=start,
            end=end,
            kind="custom",
            settings=settings,
            storage=FakeStorageProvider(),
            now=datetime.now(UTC),
        )
        await session.commit()
        return report


async def ledger_total(factory):
    async with factory() as session:
        rows = list(await session.scalars(select(EarningsLedgerEntry)))
        return sum(
            (
                (-row.amount if row.entry_type == "reversal" else row.amount)
                for row in rows
                if row.status != "voided"
            ),
            Decimal("0.00"),
        )


def test_signed_corrections_stay_in_ledger_and_prior_report_facts_never_change(
    db_sessionmaker, settings
):
    admin, campaign = graph(db_sessionmaker, "signed")

    async def exercise():
        first = await issue(db_sessionmaker, admin, campaign, settings)
        original_snapshot = first.snapshot.copy()
        original_sha = first.snapshot_sha256
        assert await ledger_total(db_sessionmaker) == Decimal("1200.00")
        async with db_sessionmaker() as session:
            original = await session.scalar(select(EarningsLedgerEntry))
            for kind, amount, state in [
                ("adjustment", "300.00", "pending"),
                ("reversal", "100.00", "available"),
                ("adjustment", "500.00", "voided"),
            ]:
                session.add(
                    EarningsLedgerEntry(
                        driver_profile_id=original.driver_profile_id,
                        driver_user_id=original.driver_user_id,
                        campaign_id=campaign.id,
                        trip_session_id=original.trip_session_id,
                        vehicle_id=original.vehicle_id,
                        entry_type=kind,
                        status=state,
                        amount=Decimal(amount),
                        currency="NGN",
                        occurred_at=DAY_1 + timedelta(days=5),
                    )
                )
            original.status = "reversed"
            await session.commit()
        second = await issue(db_sessionmaker, admin, campaign, settings)
        assert await ledger_total(db_sessionmaker) == Decimal("1400.00")
        assert first.snapshot == original_snapshot and first.snapshot_sha256 == original_sha
        assert second.id != first.id
        # One car stays withheld, even though staff can see its ledger.
        assert all(value is None for value in second.snapshot["campaigns"][0]["measured"].values())
        assert not any(
            key in str(second.snapshot)
            for key in ("cost_summary", "payout", "budget", "ROI", "CTR")
        )

    asyncio.run(exercise())


@pytest.mark.parametrize("end_offset", [0, 1])
def test_cross_period_terminal_trip_is_not_counted_twice(db_sessionmaker, settings, end_offset):
    admin, campaign = graph(db_sessionmaker, f"boundary-{end_offset}")

    async def exercise():
        async with db_sessionmaker() as session:
            trip = await session.scalar(select(TripSession))
            trip.ended_at = DAY_1 + timedelta(days=1, microseconds=end_offset)
            await session.commit()
        first = await issue(db_sessionmaker, admin, campaign, settings)
        second = await issue(
            db_sessionmaker,
            admin,
            campaign,
            settings,
            start=DAY_1 + timedelta(days=1),
            end=DAY_1 + timedelta(days=2),
        )
        assert first.snapshot["campaigns"][0]["measured"]["distance_m"] == "0.00"
        assert second.snapshot["campaigns"][0]["measured"]["distance_m"] is None
        assert second.snapshot["campaigns"][0]["daily"][0]["suppressed"] is True
        assert await ledger_total(db_sessionmaker) == Decimal("1200.00")

    asyncio.run(exercise())


@pytest.mark.parametrize("report_first", [True, False])
def test_report_and_ledger_append_use_the_same_postgres_lock_order(
    db_sessionmaker,
    settings,
    monkeypatch,
    report_first,
):
    import app.services.campaign_reports as reports

    admin, campaign = graph(db_sessionmaker, f"race-{report_first}")
    original = reports.build_report_snapshot

    async def exercise():
        locked, release = asyncio.Event(), asyncio.Event()

        async def pause_snapshot(*args, **kwargs):
            locked.set()
            await release.wait()
            return await original(*args, **kwargs)

        if report_first:
            monkeypatch.setattr(reports, "build_report_snapshot", pause_snapshot)

        async def append():
            async with db_sessionmaker() as session:
                await lock_fraud_reconciliation_gate(session, exclusive=False)
                await acquire_campaign_terms_lock(session, campaign.id)
                row = await session.scalar(select(EarningsLedgerEntry))
                if not report_first:
                    locked.set()
                    await release.wait()
                session.add(
                    EarningsLedgerEntry(
                        driver_profile_id=row.driver_profile_id,
                        driver_user_id=row.driver_user_id,
                        campaign_id=campaign.id,
                        trip_session_id=row.trip_session_id,
                        vehicle_id=row.vehicle_id,
                        entry_type="adjustment",
                        status="pending",
                        amount=Decimal("100.00"),
                        currency="NGN",
                        occurred_at=DAY_1 + timedelta(days=3),
                    )
                )
                await session.commit()

        first = asyncio.create_task(
            issue(db_sessionmaker, admin, campaign, settings) if report_first else append()
        )
        await asyncio.wait_for(locked.wait(), 5)
        second = asyncio.create_task(
            append() if report_first else issue(db_sessionmaker, admin, campaign, settings)
        )
        await asyncio.sleep(0.2)
        assert not second.done()
        release.set()
        await asyncio.wait_for(asyncio.gather(first, second), 15)
        assert await ledger_total(db_sessionmaker) == Decimal("1300.00")

    asyncio.run(exercise())


def test_non_money_report_never_queries_payout_cost_authority(
    db_sessionmaker, settings, monkeypatch
):
    admin, campaign = graph(db_sessionmaker, "no-cost")

    def forbidden(**_kwargs):
        raise AssertionError("Report attempted a money query")

    monkeypatch.setattr("app.services.report_cohorts.latest_payout_calculation_ids", forbidden)
    report = asyncio.run(issue(db_sessionmaker, admin, campaign, settings))
    assert report.status == "queued"
    assert asyncio.run(ledger_total(db_sessionmaker)) == Decimal("1200.00")


def test_unknown_report_renderer_is_rejected_instead_of_reinterpreting_an_issued_format():
    snapshot = {"schema_version": "future-unknown"}
    report = SimpleNamespace(snapshot=snapshot, snapshot_sha256=_canonical_hash(snapshot))
    with pytest.raises(ValueError, match="REPORT_SNAPSHOT_INVALID"):
        _pair(report)


def test_cohort_cost_reads_only_its_own_trip_ledger_rows():
    from types import SimpleNamespace

    from app.services.report_cohorts import ReportCohort

    first_trip, second_trip = uuid4(), uuid4()

    def payout(trip_id, currency="NGN"):
        return SimpleNamespace(
            id=uuid4(), trip_session_id=trip_id, status="calculated", currency=currency
        )

    first, second = payout(first_trip), payout(second_trip)

    def row(trip_id, calculation, entry_type, amount, currency="NGN"):
        return SimpleNamespace(
            trip_session_id=trip_id,
            payout_calculation_id=calculation.id if calculation else None,
            entry_type=entry_type,
            status="available",
            amount=Decimal(amount),
            currency=currency,
        )

    cohort = ReportCohort(
        trips=(),
        analytics=(),
        impressions=(),
        payouts=(first, second),
        ledger=(
            row(first_trip, first, "trip_payout", "100.00"),
            row(second_trip, second, "trip_payout", "70.00"),
            row(first_trip, None, "reversal", "15.00"),
            row(second_trip, None, "adjustment", "5.00"),
        ),
        terminal_period=True,
    )

    assert cohort.final_cost(first) == Decimal("85.00")
    assert cohort.final_cost(second) == Decimal("75.00")
    with pytest.raises(AppError) as missing:
        cohort.final_cost(payout(uuid4()))
    assert missing.value.code == "MEASUREMENT_LEDGER_INCOMPLETE"
    mixed = ReportCohort(
        trips=(),
        analytics=(),
        impressions=(),
        payouts=(first,),
        ledger=(row(first_trip, first, "trip_payout", "100.00", currency="USD"),),
        terminal_period=True,
    )
    with pytest.raises(AppError) as conflict:
        mixed.final_cost(first)
    assert conflict.value.code == "MEASUREMENT_LEDGER_CURRENCY_CONFLICT"
