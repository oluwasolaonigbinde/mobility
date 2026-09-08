import asyncio
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select
from test_advertiser_reports import DAY_1
from test_measurement_runs import create_measurement_graph, issue_payload

from app.core.errors import AppError
from app.models.payout import EarningsLedgerEntry, PayoutCalculation
from app.models.trip import TripSession
from app.schemas.measurement import MeasurementRunCreate
from app.services.measurement import issue_measurement_run, measurement_run_reproducible
from app.services.payout_rule_serialization import acquire_campaign_terms_lock


async def issue(factory, admin, campaign, settings, **period):
    async with factory() as session:
        run = await issue_measurement_run(
            session,
            actor_user_id=admin.id,
            payload=MeasurementRunCreate(**{**issue_payload(campaign.id), **period}),
            settings=settings,
        )
        await session.commit()
        return run


def costs(run):
    return next(m for m in run.result_manifest["metrics"] if m["id"] == "driver_campaign_cost")


def test_new_reports_freeze_signed_corrections_and_preserve_issued_runs(
    postgis_db_sessionmaker, settings
):
    factory = postgis_db_sessionmaker
    admin, _, campaign = create_measurement_graph(factory, identity_tag="corrected-report")

    async def exercise():
        first = await issue(factory, admin, campaign, settings)
        first_hash = first.input_manifest_sha256
        async with factory() as session:
            original = await session.scalar(select(EarningsLedgerEntry))
            for kind, amount, state in [
                ("adjustment", "300.00", "pending"),
                ("reversal", "100.00", "available"),
                ("debt_remainder", "900.00", "available"),
                ("adjustment", "500.00", "voided"),
            ]:
                session.add(
                    EarningsLedgerEntry(
                        id=uuid4(),
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
        second = await issue(factory, admin, campaign, settings)
        assert costs(second)["totals_by_currency"] == [{"currency": "NGN", "value": "1400.00"}]
        assert (
            second.report_snapshot["cost_summary"]["totals_by_currency"][0]["final_payout_total"]
            == "1400.00"
        )
        assert second.report_snapshot["daily_metrics"][0]["final_payout_total"] == "1400.00"
        assert costs(first)["totals_by_currency"] == [{"currency": "NGN", "value": "1200.00"}]
        contributions = second.input_manifest["disclosure_authority"]["contributions"]
        assert list(contributions["cost:NGN:final_payout"].values()) == ["1400.00"]
        assert list(contributions["cost:NGN:reversal"].values()) == ["100.00"]
        assert list(contributions["cost:NGN:credit"].values()) == ["1500.00"]
        assert first.input_manifest_sha256 == first_hash
        assert measurement_run_reproducible(first) and measurement_run_reproducible(second)
        async with factory() as session:
            payout = await session.scalar(select(PayoutCalculation))
            assert payout.final_payout == Decimal("1200.00")
        repeat = await issue(factory, admin, campaign, settings)
        assert repeat.input_manifest_sha256 == second.input_manifest_sha256

    asyncio.run(exercise())


@pytest.mark.parametrize("end_offset", [0, 1])
def test_cross_period_trip_appears_once_at_terminal_boundary(
    postgis_db_sessionmaker, settings, end_offset
):
    factory = postgis_db_sessionmaker
    admin, _, campaign = create_measurement_graph(factory, identity_tag="terminal-report")

    async def exercise():
        async with factory() as session:
            trip = await session.scalar(select(TripSession))
            trip.ended_at = DAY_1 + timedelta(days=1, microseconds=end_offset)
            await session.commit()
        first = await issue(factory, admin, campaign, settings)
        second = await issue(
            factory,
            admin,
            campaign,
            settings,
            period_start_at=DAY_1 + timedelta(days=1),
            period_end_at=DAY_1 + timedelta(days=2),
        )
        assert costs(first)["completeness"]["denominator_trip_count"] == 0
        assert costs(first)["completeness"]["in_progress_trip_count"] == 1
        assert costs(first)["totals_by_currency"] == []
        assert first.report_snapshot["daily_metrics"] == []
        assert costs(second)["completeness"]["denominator_trip_count"] == 1
        assert costs(second)["totals_by_currency"] == [{"currency": "NGN", "value": "1200.00"}]
        assert (
            second.report_snapshot["daily_metrics"][0]["date"]
            == (DAY_1 + timedelta(days=1)).date().isoformat()
        )
        assert measurement_run_reproducible(first) and measurement_run_reproducible(second)

    asyncio.run(exercise())


@pytest.mark.parametrize("report_first", [True, False])
def test_report_and_ledger_append_have_one_coherent_postgres_cutoff(
    postgis_db_sessionmaker, settings, monkeypatch, report_first
):
    import app.services.measurement as measurement

    factory = postgis_db_sessionmaker
    admin, _, campaign = create_measurement_graph(factory, identity_tag="report-cutoff")

    async def exercise():
        locked, release = asyncio.Event(), asyncio.Event()
        proof = measurement._proof_manifest

        async def paused_proof(*args, **kwargs):
            locked.set()
            await release.wait()
            return await proof(*args, **kwargs)

        if report_first:
            monkeypatch.setattr(measurement, "_proof_manifest", paused_proof)

        async def append():
            async with factory() as session:
                await acquire_campaign_terms_lock(session, campaign.id)
                original = await session.scalar(select(EarningsLedgerEntry))
                if not report_first:
                    await session.scalar(select(TripSession).with_for_update())
                    locked.set()
                    await release.wait()
                session.add(
                    EarningsLedgerEntry(
                        driver_profile_id=original.driver_profile_id,
                        driver_user_id=original.driver_user_id,
                        campaign_id=campaign.id,
                        trip_session_id=original.trip_session_id,
                        vehicle_id=original.vehicle_id,
                        entry_type="adjustment",
                        status="pending",
                        amount=Decimal("100.00"),
                        currency="NGN",
                        occurred_at=DAY_1 + timedelta(days=3),
                    )
                )
                await session.commit()

        first_task = asyncio.create_task(
            issue(factory, admin, campaign, settings) if report_first else append()
        )
        await asyncio.wait_for(locked.wait(), 5)
        second_task = asyncio.create_task(
            append() if report_first else issue(factory, admin, campaign, settings)
        )
        await asyncio.sleep(0.25)
        assert not second_task.done()
        release.set()
        results = await asyncio.wait_for(asyncio.gather(first_task, second_task), 10)
        run = results[0 if report_first else 1]
        expected = "1200.00" if report_first else "1300.00"
        assert costs(run)["totals_by_currency"] == [{"currency": "NGN", "value": expected}]
        assert (
            run.report_snapshot["cost_summary"]["totals_by_currency"][0]["final_payout_total"]
            == expected
        )
        later = await issue(factory, admin, campaign, settings)
        assert costs(later)["totals_by_currency"] == [{"currency": "NGN", "value": "1300.00"}]
        assert measurement_run_reproducible(run) and measurement_run_reproducible(later)

    asyncio.run(exercise())


def test_missing_ledger_blocks_new_issuance_instead_of_using_original_calculation(
    postgis_db_sessionmaker, settings, monkeypatch
):
    from dataclasses import replace

    import app.services.measurement as measurement

    factory = postgis_db_sessionmaker
    admin, _, campaign = create_measurement_graph(factory, identity_tag="missing-ledger")
    selector = measurement.select_report_cohort

    async def absent_ledger(*args, **kwargs):
        return replace(await selector(*args, **kwargs), ledger=())

    monkeypatch.setattr(measurement, "select_report_cohort", absent_ledger)
    with pytest.raises(AppError) as error:
        asyncio.run(issue(factory, admin, campaign, settings))
    assert error.value.code == "MEASUREMENT_LEDGER_INCOMPLETE"


def test_unknown_measurement_formula_cannot_be_reinterpreted_as_legacy():
    from test_measurement_runs import _disclosure_manifest

    from app.services.measurement import calculate_measurement_result

    manifest = _disclosure_manifest()
    manifest["formula_version"] = "future-unknown"
    with pytest.raises(ValueError, match="Unsupported measurement formula"):
        calculate_measurement_result(manifest)
