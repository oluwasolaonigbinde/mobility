"""REQ-310: reporting fixtures cannot become money through the real worker."""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from test_seed_demo import seed_demo_graph, seed_private_storage  # noqa: F401

from app.jobs import trip_processing as jobs
from app.models.campaign import Campaign
from app.models.payout import AssignmentRuleBinding, EarningsLedgerEntry, PayoutCalculation
from app.models.trip import TripSession
from app.services import trip_processing as processing
from app.services.trips import auto_end_inactive_trip


async def payout_snapshot(sessionmaker):
    async with sessionmaker() as session:
        result = {}
        for name, model, amount in (
            ("payouts", PayoutCalculation, PayoutCalculation.final_payout),
            ("ledger", EarningsLedgerEntry, EarningsLedgerEntry.amount),
        ):
            result[name] = (
                await session.execute(
                    select(func.count(model.id), func.coalesce(func.sum(amount), 0))
                )
            ).one()
            for campaign_name, count, total in await session.execute(
                select(Campaign.name, func.count(model.id), func.coalesce(func.sum(amount), 0))
                .join(Campaign, Campaign.id == model.campaign_id)
                .group_by(Campaign.name)
            ):
                result[f"{name}:{campaign_name}"] = (count, Decimal(total))
        return result


async def run_reporting_worker_paths(sessionmaker, settings, monkeypatch):
    settings = settings.model_copy(update={"worker_sweep_batch_size": 2000})
    ctx = {"settings": settings, "sessionmaker": sessionmaker}
    before = await payout_snapshot(sessionmaker)
    sweep = await jobs.process_unprocessed_trips(ctx)
    after_sweep = await payout_snapshot(sessionmaker)
    print("SWEEP_MONEY_BEFORE", before, "AFTER", after_sweep, flush=True)
    future = datetime.now(UTC).replace(microsecond=0) + timedelta(hours=3)
    async with sessionmaker() as session:
        live = list(
            await session.scalars(
                select(TripSession).where(
                    TripSession.trip_metadata["seed_version"].as_string() == "demo-live-v1"
                )
            )
        )
        assert len(live) == 2
        reporting_assignments = select(TripSession.assignment_id).where(
            TripSession.trip_metadata["seed_trip_key"].as_string().startswith("reporting-day-")
        )
        assert (
            await session.scalar(
                select(func.count(AssignmentRuleBinding.id)).where(
                    AssignmentRuleBinding.assignment_id.in_(reporting_assignments)
                )
            )
            == 0
        )
        for trip in live:
            assert await auto_end_inactive_trip(
                session, trip_id=trip.id, settings=settings, now=future
            )
        await session.commit()

    async def clock(_session):
        return future

    monkeypatch.setattr(processing, "database_now", clock)
    second = await jobs.process_unprocessed_trips(ctx)
    after_auto_end = await payout_snapshot(sessionmaker)
    print("WORKER_SWEEP", sweep, "AUTO_END_SWEEP", second)
    print("MONEY_BEFORE", before, "AFTER_SWEEP", after_sweep, "AFTER_AUTO_END", after_auto_end)
    return before, after_sweep, after_auto_end


def test_reporting_and_live_trips_never_create_worker_money(
    postgis_db_sessionmaker, settings, monkeypatch
):
    monkeypatch.setenv("F7_SEED_MAX_TRIPS_PER_DAY", "2")
    seed_demo_graph(postgis_db_sessionmaker, settings)
    before, swept, ended = asyncio.run(
        run_reporting_worker_paths(postgis_db_sessionmaker, settings, monkeypatch)
    )
    assert swept == before, ("worker sweep changed seeded money", before, swept)
    assert ended == before, ("auto-ended live trips changed seeded money", before, ended)
