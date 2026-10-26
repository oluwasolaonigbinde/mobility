"""Exact pre-slim-down synthetic money baseline captured at be1fc9de (S1).

Frozen time and density reproduce 300 calculations and their ledger rows. Trip
identity uses campaign, driver, dates and seed key; report-route keys omit their
random source UUID. Hashes cover each exact amount and ledger-to-trip identity.
Storage/scanning are synthetic; no payment provider is contacted.
"""

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from test_seed_demo import seed_demo_graph
from test_seed_demo import seed_private_storage as seed_private_storage

from app.models.campaign import Campaign
from app.models.driver import DriverProfile
from app.models.payout import EarningsLedgerEntry, PayoutCalculation
from app.models.trip import TripSession
from app.models.user import User
from app.seeds import demo, rich


def _digest(rows: list) -> str:
    return hashlib.sha256(
        json.dumps(rows, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()


def _stable_trip_identity(name, email, start, end, metadata) -> list[str]:
    key = metadata["seed_trip_key"]
    if key.startswith("report-route:"):
        prefix, _random_source_trip_id, driver_index, leg = key.split(":")
        key = f"{prefix}:{driver_index}:{leg}"
    return [name, email, start.isoformat(), end.isoformat(), key]


def test_seed_pay_and_ledger_match_before_slimdown(
    postgis_db_sessionmaker, settings, monkeypatch
) -> None:
    now = datetime(2026, 10, 20, 12, tzinfo=UTC)
    monkeypatch.setenv("F7_SEED_MAX_TRIPS_PER_DAY", "1")
    monkeypatch.setattr(demo, "utc_now", lambda: now)
    monkeypatch.setattr(rich, "utc_now", lambda: now)

    async def fixed_cancellation_clock(_session):
        return now

    # Refund seed facts are also dated by the frozen seed clock. Otherwise this
    # exact historical baseline ages out of its 24-hour window on a later day.
    monkeypatch.setattr(
        "app.services.campaign_cancellations.database_clock", fixed_cancellation_clock
    )
    seed_demo_graph(postgis_db_sessionmaker, settings)

    async def read_money():
        async with postgis_db_sessionmaker() as session:
            trips = (
                await session.execute(
                    select(
                        TripSession.id,
                        Campaign.name,
                        User.email,
                        TripSession.started_at,
                        TripSession.ended_at,
                        TripSession.trip_metadata,
                    )
                    .join(Campaign, Campaign.id == TripSession.campaign_id)
                    .join(DriverProfile, DriverProfile.id == TripSession.driver_profile_id)
                    .join(User, User.id == DriverProfile.user_id)
                    .where(TripSession.id.in_(select(PayoutCalculation.trip_session_id)))
                )
            ).all()
            identities = {
                trip_id: _stable_trip_identity(name, email, start, end, metadata)
                for trip_id, name, email, start, end, metadata in trips
            }
            calculations = sorted(
                [
                    *identities[row.trip_session_id],
                    str(row.gross_payout),
                    str(row.final_payout),
                    row.currency,
                ]
                for row in (await session.scalars(select(PayoutCalculation))).all()
            )
            ledger = sorted(
                [
                    *identities[row.trip_session_id],
                    row.entry_type,
                    row.status,
                    str(row.amount),
                    row.currency,
                ]
                for row in (await session.scalars(select(EarningsLedgerEntry))).all()
            )
            return calculations, ledger

    calculations, ledger = asyncio.run(read_money())
    assert len(calculations) == len(ledger) == 300
    assert len({tuple(row[:5]) for row in calculations}) == 300
    assert len({tuple(row[:5]) for row in ledger}) == 300
    assert (
        _digest(calculations) == "5e4c7a9579c53e9f7fd6b05cdf000ccacb721a0d7968926b279bcc0c6eb51814"
    )
    assert _digest(ledger) == "54daf385b28af837ef7350f604d064ba392b4bd75abe9842c561d1bcc3dc6f57"
    assert sum(Decimal(row[7]) for row in ledger) == Decimal("497627.06")
